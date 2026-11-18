#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Mutation guard: a PreToolUse hook that stops cloud and cluster writes.

Backs advisor.no-side-effects (--mode block: every write) and
operator.confirm-before-change (--mode ask: the user confirms each write).
Opt-in: each class.yaml hooks entry ships with `enabled: false`, the Kiro
default and the plugin's userConfig default. A guardrail, not a guarantee: it
reads the command text, so a script, an alias or text built at run time
passes. RBAC, the stage helper and the PR merge stay the real gate.

Usage: mutation_guard.py --mode ask|block [--id <class.yaml hooks id>]
       (one PreToolUse event as JSON on stdin)

One script backs two ids, so the command names its id. The off switch is the
environment variable CLAUDE_PLUGIN_OPTION_<KEY>, KEY the --id with every . and
- as _, uppercased (CLAUDE_PLUGIN_OPTION_OPERATOR_CONFIRM_BEFORE_CHANGE,
CLAUDE_PLUGIN_OPTION_ADVISOR_NO_SIDE_EFFECTS; Claude Code exports one per
plugin option). Absent, or no --id: on. true or false, in any case,
surrounding whitespace stripped: false is off, no decision (exit 0, no output)
whatever the event. Any other value, an empty one included, blocks (exit 2,
one stderr line naming the variable and the value).

A write is:
- kubectl apply, create, delete, edit, patch, replace, set, expose, run, scale,
  autoscale, label, annotate, taint, cordon, uncordon, drain, exec, cp, attach,
  debug; certificate approve|deny; rollout restart|undo|pause|resume; auth
  reconcile; config set, set-cluster, set-context, set-credentials, unset,
  delete-cluster, delete-context, delete-user, rename-context. With
  --dry-run=client or =server it is not a write.
- helm install, upgrade, uninstall (del, delete, un), rollback, test, push;
  any helm --dry-run is not a write.
- terraform apply, destroy, import, refresh, taint, untaint, force-unlock, test,
  state mv|push|replace-provider|rm, workspace new|delete.
- eksctl, every command but get, info, version, help and completion.
- aws, every operation but describe-*, list-*, get-*, batch-get-*, search-*,
  lookup-*, wait, help, s3 ls, logs start-query, configure list|get and
  eks update-kubeconfig.
- EKS MCP Server tools by name suffix: manage_k8s_resource (operation not
  read), apply_yaml, manage_eks_stacks (operation not describe),
  add_inline_policy; structured AWS calls (use_aws and MCP tools with
  service_name and operation_name) by the aws rule; a cli_command string as a
  shell command.
`kubectl config use-context` and `aws eks update-kubeconfig` pass: the
kubeconfig setup apex.read-only-unless-confirmed allows.

Output: block is exit 2 with the reason on stderr. Ask prints Claude Code's
permissionDecision "ask" JSON on exit 0, only for an event with
permission_mode and no turn_id (Claude Code's shape). Codex has no PreToolUse
ask, and Kiro documents one only for Kiro CLI 3.4.0 or later (a JSON decision
on exit 0), not for Kiro IDE; this script prints no Kiro ask, so on Codex and
Kiro ask mode blocks. No write, or an event it cannot read, gets no decision
(exit 0, no output).
"""

import argparse
import json
import os
import re
import shlex
import sys

# --- shared splitter: byte-identical in secret_deny.py and mutation_guard.py ---
MAX_DEPTH = 8
ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
# Prefix commands dropped before the command word, with their options that take a value.
PREFIXES = {
    "env": {"-u", "--unset", "-C", "--chdir"},
    "sudo": {"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C",
             "--close-from", "-D", "--chdir", "-r", "--role", "-t", "--type", "-U",
             "--other-user", "-T", "--command-timeout"},
    "xargs": {"-a", "--arg-file", "-d", "--delimiter", "-E", "-I", "-L", "--max-lines",
              "-n", "--max-args", "-P", "--max-procs", "-s", "--max-chars"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "nohup": set(),
    "time": {"-f", "--format", "-o", "--output"},
    "nice": {"-n", "--adjustment"},
    "command": set(),
    "builtin": set(),
    "exec": {"-a"},
}


def _subst_bodies(text):
    """The bodies of $(...) and `...` in text, so a command inside one is checked too."""
    bodies = []
    i = text.find("$(")
    while i >= 0:
        depth, j = 1, i + 2
        while j < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[j], 0)
            j += 1
        bodies.append(text[i + 2:j - 1] if depth == 0 else text[i + 2:])
        i = text.find("$(", i + 2)
    bodies.extend(re.findall(r"`([^`]*)`", text))
    return bodies


def _tokens(text):
    lex = shlex.shlex(text, posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        return list(lex)
    except ValueError:  # an unclosed quote: split on whitespace instead
        return re.sub(r"[;&|()]", " ; ", text).split()


def _parts(tokens):
    part = []
    for t in tokens:
        if t in ("{", "}", "!") or set(t) <= set(";&|()"):
            if part:
                yield part
            part = []
        else:
            part.append(t)
    if part:
        yield part


def _command(part):
    """The part's command word (its last path segment) and arguments, prefixes dropped."""
    i = 0
    while i < len(part):
        if ASSIGN.match(part[i]):
            i += 1
            continue
        name = part[i].rsplit("/", 1)[-1]
        if name not in PREFIXES:
            break
        i += 1
        while i < len(part) and part[i].startswith("-") and part[i] != "-":
            opt = part[i]
            i += 1
            if opt == "--":
                break
            if "=" not in opt and opt in PREFIXES[name]:
                i += 1
        if name == "timeout":
            i += 1  # the duration
    if i >= len(part):
        return None, []
    return part[i].rsplit("/", 1)[-1], part[i + 1:]


def simple_commands(text, depth=0):
    """Yield (command word, arguments) for each simple command in a shell string.

    Splits on ; & | ( ) { } ! and newlines, checks $(...) and backtick bodies, the
    script of bash/sh -c and the text of eval, and drops leading VAR=value words and
    the PREFIXES commands with their options.
    """
    if depth > MAX_DEPTH:
        return
    for body in _subst_bodies(text):
        yield from simple_commands(body, depth + 1)
    text = text.replace("\n", " ; ").replace("`", " ; ")
    for part in _parts(_tokens(text)):
        word, args = _command(part)
        if word is None:
            continue
        if word in SHELLS:
            for k, a in enumerate(args):
                if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a):
                    if k + 1 < len(args):
                        yield from simple_commands(args[k + 1], depth + 1)
                    break
        elif word == "eval":
            yield from simple_commands(" ".join(args), depth + 1)
        else:
            yield word, args


def positionals(args, takes_value):
    """The arguments that are not flags, skipping the value of each flag in takes_value."""
    out, i = [], 0
    while i < len(args):
        a = args[i]
        i += 1
        if a == "--":
            out.extend(args[i:])
            break
        if a.startswith("-") and len(a) > 1:
            if "=" not in a and a in takes_value:
                i += 1
            continue
        out.append(a)
    return out


def dry_run(args):
    """The --dry-run value (client, server, none), "client" for a bare flag, else None."""
    for k, a in enumerate(args):
        if a.startswith("--dry-run="):
            return a.split("=", 1)[1]
        if a == "--dry-run":
            nxt = args[k + 1] if k + 1 < len(args) else ""
            return nxt if nxt in ("client", "server", "none") else "client"
    return None


KUBECTL_VALUE_FLAGS = {
    # kubectl options (client v1.33.1)
    "--as", "--as-group", "--as-uid", "--cache-dir", "--certificate-authority",
    "--client-certificate", "--client-key", "--cluster", "--context", "--kubeconfig",
    "--log-flush-frequency", "-n", "--namespace", "--password", "--profile",
    "--profile-output", "--request-timeout", "-s", "--server", "--tls-server-name",
    "--token", "--user", "--username", "-v", "--v", "--vmodule",
    # common subcommand flags
    "-o", "--output", "-l", "--selector", "-f", "--filename", "--field-selector",
    "-L", "--label-columns", "--sort-by", "--template", "-c", "--container", "-k",
    "--kustomize", "--chunk-size", "--raw", "--type", "--timeout", "--for",
}
HELM_VALUE_FLAGS = {
    # helm --help Flags (v3.16.2)
    "--burst-limit", "--kube-apiserver", "--kube-as-group", "--kube-as-user",
    "--kube-ca-file", "--kube-context", "--kube-tls-server-name", "--kube-token",
    "--kubeconfig", "-n", "--namespace", "--qps", "--registry-config",
    "--repository-cache", "--repository-config",
    # common subcommand flags
    "-f", "--values", "--set", "--set-string", "--set-file", "--set-json", "--version",
    "-o", "--output", "--timeout", "--description", "--repo", "--revision", "--max",
    "--filter", "--post-renderer",
}
# --- end of the shared splitter -----------------------------------------------

RULES = {"block": "advisor.no-side-effects", "ask": "operator.confirm-before-change"}

AWS_VALUE_FLAGS = {
    "--region", "--profile", "--output", "--endpoint-url", "--query", "--cli-read-timeout",
    "--cli-connect-timeout", "--ca-bundle", "--color", "--cli-binary-format",
}
AWS_READ_PREFIXES = ("describe", "list", "get", "batchget", "search", "lookup")

KUBECTL_WRITES = {
    "apply", "create", "delete", "edit", "patch", "replace", "set", "expose", "run", "scale",
    "autoscale", "label", "annotate", "taint", "cordon", "uncordon", "drain", "exec", "cp",
    "attach", "debug",
}
KUBECTL_SUB_WRITES = {
    "certificate": {"approve", "deny"},
    "rollout": {"restart", "undo", "pause", "resume"},
    "auth": {"reconcile"},
    "config": {"set", "set-cluster", "set-context", "set-credentials", "unset", "delete-cluster",
               "delete-context", "delete-user", "rename-context"},
}
HELM_WRITES = {"install", "upgrade", "uninstall", "del", "delete", "un", "rollback", "test", "push"}
TERRAFORM_WRITES = {"apply", "destroy", "import", "refresh", "taint", "untaint", "force-unlock", "test"}
TERRAFORM_SUB_WRITES = {"state": {"mv", "push", "replace-provider", "rm"}, "workspace": {"new", "delete"}}
EKSCTL_READS = {"get", "info", "version", "help", "completion"}


def kubectl_writes(args):
    pos = positionals(args, KUBECTL_VALUE_FLAGS)
    if not pos or dry_run(args) in ("client", "server"):
        return False
    verb, sub = pos[0], pos[1] if len(pos) > 1 else ""
    if verb == "apply" and sub == "view-last-applied":
        return False
    return verb in KUBECTL_WRITES or sub in KUBECTL_SUB_WRITES.get(verb, ())


def helm_writes(args):
    pos = positionals(args, HELM_VALUE_FLAGS)
    return bool(pos) and pos[0] in HELM_WRITES and dry_run(args) is None


def terraform_writes(args):
    pos = [a for a in args if not a.startswith("-")]
    if not pos:
        return False
    sub = pos[1] if len(pos) > 1 else ""
    return pos[0] in TERRAFORM_WRITES or sub in TERRAFORM_SUB_WRITES.get(pos[0], ())


def eksctl_writes(args):
    pos = [a for a in args if not a.startswith("-")]
    return bool(pos) and pos[0] not in EKSCTL_READS


def aws_op_writes(service, operation):
    """The aws rule on a service and an operation, CLI or structured."""
    op = operation.lower().replace("-", "").replace("_", "")
    service = service.lower()
    if not op or service == "help" or op in ("help", "wait") or op.startswith(AWS_READ_PREFIXES):
        return False
    return (service, op) not in {("s3", "ls"), ("logs", "startquery"), ("configure", "list"),
                                 ("configure", "get"), ("eks", "updatekubeconfig")}


def aws_writes(args):
    pos = positionals(args, AWS_VALUE_FLAGS)
    return len(pos) >= 2 and aws_op_writes(pos[0], pos[1])


TOOLS = {"kubectl": kubectl_writes, "helm": helm_writes, "terraform": terraform_writes,
         "eksctl": eksctl_writes, "aws": aws_writes}


def shell_reason(command):
    for word, args in simple_commands(command):
        if word in TOOLS and TOOLS[word](args):
            return f"this command changes a cluster or cloud account: {word} " + " ".join(args)
    return None


def mcp_reason(name, tool_input):
    op = str(tool_input.get("operation", "")).lower()
    if (name.endswith("_manage_k8s_resource") and op != "read") \
            or name.endswith(("_apply_yaml", "_add_inline_policy")) \
            or (name.endswith("_manage_eks_stacks") and op != "describe"):
        return "this MCP call changes a cluster or cloud account: " + name
    service = tool_input.get("service_name") or tool_input.get("service") or tool_input.get("serviceName")
    operation = tool_input.get("operation_name") or tool_input.get("operation") or tool_input.get("operationName")
    if isinstance(service, str) and isinstance(operation, str) and aws_op_writes(service, operation):
        return f"this AWS call changes a cloud account: {service} {operation}"
    if isinstance(tool_input.get("cli_command"), str):
        return shell_reason(tool_input["cli_command"])
    return None


def switch_off(hook_id):
    """True when the hook's switch reads false; ValueError for a value not true or false."""
    if not hook_id:
        return False
    name = "CLAUDE_PLUGIN_OPTION_" + re.sub(r"[.-]", "_", hook_id).upper()
    value = os.environ.get(name)
    if value is None or value.strip().lower() == "true":
        return False
    if value.strip().lower() == "false":
        return True
    raise ValueError(f"apex hook: {name} must be true or false, got {value!r}")


def main(argv):
    parser = argparse.ArgumentParser(description="Stop cloud and cluster writes (PreToolUse).")
    parser.add_argument("--mode", choices=["ask", "block"], required=True)
    parser.add_argument("--id")
    args = parser.parse_args(argv)
    try:
        off = switch_off(args.id)
    except ValueError as e:
        sys.stdin.read()
        print(e, file=sys.stderr)
        return 2
    if off:
        sys.stdin.read()
        return 0
    mode = args.mode
    try:
        event = json.load(sys.stdin)
    except ValueError:
        event = None
    if not isinstance(event, dict) or not isinstance(event.get("tool_input"), dict):
        print("mutation guard: the event is not a tool call it can read; no decision", file=sys.stderr)
        return 0
    name, tool_input = str(event.get("tool_name") or ""), event["tool_input"]
    if name == "use_aws" or name.startswith("mcp_"):
        reason = mcp_reason(name, tool_input)
    elif isinstance(tool_input.get("command"), str):
        reason = shell_reason(tool_input["command"])
    else:
        reason = None
    if not reason:
        return 0
    text = f"APEX mutation guard ({RULES[mode]}): {reason}."
    if mode == "ask" and "permission_mode" in event and "turn_id" not in event:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "ask",
            "permissionDecisionReason": text + " Confirm only if the user asked for this change."}}))
        return 0
    print(f"Blocked by the {text} Show the user the exact command and what it changes; it runs "
          "only when the user runs it or turns this hook off.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
