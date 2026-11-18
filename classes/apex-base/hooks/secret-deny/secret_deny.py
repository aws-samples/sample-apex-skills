#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""apex-base secret deny: a PreToolUse hook that blocks reading Kubernetes Secrets.

Backs apex.no-secrets (classes/apex-base/rules.md). Once the plugin is enabled
the hook runs; its own switch, the plugin's userConfig boolean apex_no_secrets,
turns it off only when false is saved for it (an unset variable reads as on,
below); the plugin's
hooks.json, which runs this script, comes with the class sync. A guardrail, not
a guarantee: it reads the command text, so a script, an alias or text built at
run time passes.

Usage: secret_deny.py --mode block [--id apex.no-secrets]
       (one PreToolUse event as JSON on stdin)

The off switch is the environment variable CLAUDE_PLUGIN_OPTION_<KEY>, KEY the
--id with every . and - as _, uppercased (CLAUDE_PLUGIN_OPTION_APEX_NO_SECRETS;
Claude Code exports one per plugin option). Absent, or no --id: on. true or
false, in any case, surrounding whitespace stripped: false is off, no decision
(exit 0, no output) whatever the event. Any other value, an empty one included,
blocks (exit 2, one stderr line naming the variable and the value). On Codex
no CLAUDE_PLUGIN_OPTION_* reaches the script (Codex's hooks docs name none), so
the hook runs once trusted in Codex's /hooks, unless disabled there.

Claude Code, Codex and Kiro all send `tool_name` and `tool_input`; a shell call
carries `tool_input.command`. It blocks (exit 2, the reason on stderr):
- kubectl get, describe or edit of secret(s) in any case, with or without a
  .version.group suffix, alone, as secret/<name> or in a comma list, in every
  output form; apply view-last-applied of a Secret; get --raw on a /secrets path.
- helm list, ls, history, hist, status and every helm get (Helm keeps release
  records in Secrets), helm install or upgrade with --dry-run=server, and helm
  template with --dry-run=server, =none or =false (each lets a chart's lookup
  read the cluster: helm v3.16.2 pkg/action/install.go:254). --hide-secret is
  no exemption: it hides only rendered kind Secret v1 manifests
  (pkg/action/action.go:203), not a looked-up value rendered elsewhere.
- EKS MCP Server tools, matched by name suffix whatever the server key:
  read_k8s_resource and list_k8s_resources of kind Secret, and
  manage_k8s_resource with operation read of kind Secret.
Anything else gets no decision (exit 0, no output); an event it cannot read
gets no decision too, with nothing on stdout and one stderr line. AWS Secrets
Manager is the aws-core plugin's hook (aws/agent-toolkit-for-aws), not this one.
"""

import argparse
import json
import os
import re
import shlex
import sys

RULE = "apex.no-secrets"

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
    """The last --dry-run value (client, server, none), "client" for a bare flag, else None.

    The last one counts, as kubectl and helm read a repeated flag."""
    value = None
    for k, a in enumerate(args):
        if a.startswith("--dry-run="):
            value = a.split("=", 1)[1]
        elif a == "--dry-run":
            nxt = args[k + 1] if k + 1 < len(args) else ""
            value = nxt if nxt in ("client", "server", "none") else "client"
    return value


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


def names_secret(word):
    """True when a kubectl resource argument names the secrets resource."""
    return any(p.split("/", 1)[0].split(".", 1)[0].lower() in ("secret", "secrets")
               for p in word.split(","))


def kubectl_reads_secret(args):
    pos = positionals(args, KUBECTL_VALUE_FLAGS)
    if not pos:
        return False
    verb, rest = pos[0], pos[1:]
    if verb in ("get", "describe", "edit") and any(names_secret(r) for r in rest):
        return True
    if verb == "apply" and rest[:1] == ["view-last-applied"] and any(names_secret(r) for r in rest[1:]):
        return True
    if verb == "get":
        for k, a in enumerate(args):
            path = a[len("--raw="):] if a.startswith("--raw=") else (
                args[k + 1] if a == "--raw" and k + 1 < len(args) else "")
            if "/secrets" in path.lower():
                return True
    return False


def helm_reads_secret(args):
    pos = positionals(args, HELM_VALUE_FLAGS)
    if not pos:
        return False
    if pos[0] in ("list", "ls", "history", "hist", "status", "get"):
        return True
    if pos[0] == "template":
        return dry_run(args) in ("server", "none", "false")
    return pos[0] in ("install", "upgrade") and dry_run(args) == "server"


def shell_reason(command):
    for word, args in simple_commands(command):
        if word == "kubectl" and kubectl_reads_secret(args):
            return "this kubectl command reads Kubernetes Secrets: kubectl " + " ".join(args)
        if word == "helm" and helm_reads_secret(args):
            return ("this helm command reads Helm's release records, which Helm keeps in "
                    "Secrets: helm " + " ".join(args))
    return None


def mcp_reason(name, tool_input):
    if str(tool_input.get("kind", "")).lower() not in ("secret", "secrets"):
        return None
    if name.endswith(("_read_k8s_resource", "_list_k8s_resources")) or (
            name.endswith("_manage_k8s_resource")
            and str(tool_input.get("operation", "")).lower() == "read"):
        return "this MCP call reads Kubernetes Secrets: " + name
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
    parser = argparse.ArgumentParser(description="Block Kubernetes Secret reads (PreToolUse).")
    parser.add_argument("--mode", choices=["block"], default="block")
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
    try:
        event = json.load(sys.stdin)
    except ValueError:
        event = None
    if not isinstance(event, dict) or not isinstance(event.get("tool_input"), dict):
        print("secret deny: the event is not a tool call it can read; no decision", file=sys.stderr)
        return 0
    name, tool_input = str(event.get("tool_name") or ""), event["tool_input"]
    if name.startswith("mcp_"):
        reason = mcp_reason(name, tool_input)
    elif isinstance(tool_input.get("command"), str):
        reason = shell_reason(tool_input["command"])
    else:
        reason = None
    if reason:
        print(f"Blocked by the APEX secret deny hook ({RULE}): {reason}. Do not read Secret "
              "values; find what you need from other objects, or ask the user.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
