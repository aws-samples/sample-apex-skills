#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""service-eks preflight: bind kubectl to the user's named cluster before any Kubernetes read.

Usage:
  preflight.py check --cluster <name> --region <region> --context <ctx>
                     [--kubeconfig <file>] --read <verb>:<resource>[:<namespace>] ...
  preflight.py restore --recorded <ctx or "">  [--kubeconfig <file>]

check runs, in order, and stops at the first failed step:
  1. The context the user named exists in the kubeconfig. This script never writes a
     kubeconfig entry of its own: a missing context stops the run and the skill asks the
     user to add the target's entry (or to name another context).
  2. It records the current context (kubectl config current-context). It never switches.
  3. Endpoint check: the context's server must match `aws eks describe-cluster`'s endpoint
     for the named cluster. A context name that differs from the cluster name (an alias)
     is accepted when the endpoints match.
  4. An `auth can-i` check, with --context, for every read the skill passes with --read. A `no` or an error
     on any of them stops the run, naming each missing verb and resource. Nothing is read
     from the cluster beyond these checks.

Every kubectl call that reaches the cluster carries --context. Reads of Secrets are refused
as input (apex.no-secrets), and only the read verbs get, list and watch are accepted.

restore is for a skill that switched the context: given the context check recorded, it
switches back when the current context differs, and says which context is set when none
was recorded.

Output: one JSON object on stdout, except argparse usage errors (stderr, exit 64). Exit 0 ok, 2 stop (a check failed: show "message" to
the user and do not read the cluster), 64 bad usage. Stdlib only.
"""

import argparse
import json
import shutil
import subprocess
import sys

READ_VERBS = ("get", "list", "watch")
TIMEOUT = 60


def run(argv):
    """Run argv, return (rc, stdout, stderr). A missing binary or a timeout is rc 127 / 124."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT)
    except FileNotFoundError:
        return 127, "", "%s: command not found" % argv[0]
    except subprocess.TimeoutExpired:
        return 124, "", "%s timed out after %ds" % (" ".join(argv[:3]), TIMEOUT)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def kubectl_base(kubeconfig):
    base = ["kubectl"]
    if kubeconfig:
        base += ["--kubeconfig", kubeconfig]
    return base


def norm_endpoint(url):
    u = (url or "").strip().lower().rstrip("/")
    if u.endswith(":443"):
        u = u[: -len(":443")]
    return u


def parse_read(spec):
    parts = spec.split(":")
    if len(parts) not in (2, 3) or not parts[0] or not parts[1]:
        raise ValueError("--read %r: use <verb>:<resource>[:<namespace>]" % spec)
    verb, resource = parts[0].lower(), parts[1].lower()
    ns = parts[2] if len(parts) == 3 else ""
    if verb not in READ_VERBS:
        raise ValueError("--read %r: verb must be one of %s" % (spec, ", ".join(READ_VERBS)))
    if resource.split("/")[0].split(".")[0] in ("secret", "secrets", "*"):
        raise ValueError("--read %r: Secrets are never read (apex.no-secrets)" % spec)
    return {"verb": verb, "resource": resource, "namespace": ns}


def scope(r):
    return "in namespace %s" % r["namespace"] if r["namespace"] else "across the cluster (-A)"


def stop(reason, message, **extra):
    out = {"status": "stop", "reason": reason, "message": message}
    out.update(extra)
    return out, 2


def check(args):
    try:
        reads = [parse_read(s) for s in args.read]
    except ValueError as e:
        return {"status": "usage", "message": str(e)}, 64
    ctx = args.context
    kc = kubectl_base(args.kubeconfig)
    for tool in ("kubectl", "aws"):
        if shutil.which(tool) is None:
            return stop("tool_missing", "%s is not on PATH; install it, or use the EKS MCP Server route." % tool)

    # 1. The named context exists (local kubeconfig read, no cluster call).
    rc, out, err = run(kc + ["config", "get-contexts", "-o", "name"])
    if rc != 0:
        return stop("kubeconfig_unreadable", "Cannot read the kubeconfig: %s" % (err or out))
    if ctx not in out.splitlines():
        return stop("context_missing",
                    "Context %r is not in the kubeconfig. This skill does not add kubeconfig entries: "
                    "ask the user to add the entry for cluster %s, or to name another context." % (ctx, args.cluster))

    # 2. Record the current context; this script never changes it.
    rc, out, _ = run(kc + ["config", "current-context"])
    recorded = out if rc == 0 else ""

    # 3. Endpoint check.
    rc, server, err = run(kc + ["--context", ctx, "config", "view", "--minify",
                                "-o", "jsonpath={.clusters[0].cluster.server}"])
    if rc != 0 or not server:
        return stop("context_server_unreadable", "Cannot read the server of context %r: %s" % (ctx, err or "empty"),
                    recorded_context=recorded)
    rc, endpoint, err = run(["aws", "eks", "describe-cluster", "--name", args.cluster, "--region", args.region,
                             "--query", "cluster.endpoint", "--output", "text"])
    if rc != 0 or not endpoint or endpoint == "None":
        return stop("describe_cluster_failed", "aws eks describe-cluster for %s in %s failed (it needs eks:DescribeCluster): %s"
                    % (args.cluster, args.region, err or endpoint or "empty"), recorded_context=recorded)
    if norm_endpoint(server) != norm_endpoint(endpoint):
        return stop("endpoint_mismatch",
                    "Context %r points at %s, but cluster %s in %s has endpoint %s. Do not read through this "
                    "context; ask the user for the context of %s." % (ctx, server, args.cluster, args.region,
                                                                       endpoint, args.cluster),
                    recorded_context=recorded)

    # 4. An auth can-i check for each read; a no or an error stops the run.
    results, missing = [], []
    for r in reads:
        argv = kc + ["--context", ctx, "auth", "can-i", r["verb"], r["resource"]]
        argv += ["-n", r["namespace"]] if r["namespace"] else ["-A"]
        rc, out, err = run(argv)
        answer = out.split()[0].lower() if out else ""
        if rc == 0 and answer == "yes":
            results.append(dict(r, answer="yes"))
            continue
        if rc == 1 and answer == "no":
            item = dict(r, answer="no")
        else:
            item = dict(r, answer="error", error=(err or out or "rc %d" % rc)[:300])
        results.append(item)
        missing.append(item)
    if missing:
        lines = ["- %s %s %s: %s" % (m["verb"], m["resource"], scope(m),
                                     "denied" if m["answer"] == "no" else "check failed (%s)" % m["error"])
                 for m in missing]
        return stop("permission_missing",
                    "STOP: the caller on context %r is missing permission, or the check failed, for %d read(s) this "
                    "skill needs:\n%s\nNo cluster read was made. For a denied read, ask the cluster admin to "
                    "grant these verbs on these resources (an access entry on an API or API_AND_CONFIG_MAP "
                    "cluster; the aws-auth ConfigMap on CONFIG_MAP). For a "
                    "failed check, fix the credentials or the network first. Then run the preflight again."
                    % (ctx, len(missing), "\n".join(lines)),
                    recorded_context=recorded, missing=missing)

    flags = "--context %s" % ctx + (" --kubeconfig %s" % args.kubeconfig if args.kubeconfig else "")
    return {"status": "ok", "context": ctx, "cluster": args.cluster, "region": args.region,
            "endpoint": endpoint, "recorded_context": recorded, "can_i": results,
            "message": "Context %r is bound to cluster %s and every read passed the can-i check. "
                       "Run every kubectl read with %s." % (ctx, args.cluster, flags)}, 0


def restore(args):
    kc = kubectl_base(args.kubeconfig)
    rc, current, _ = run(kc + ["config", "current-context"])
    current = current if rc == 0 else ""
    if not args.recorded:
        return {"status": "ok", "restored": False, "current_context": current,
                "message": "There was no current context before the run; the current context is now %s."
                           % (repr(current) if current else "unset")}, 0
    if current == args.recorded:
        return {"status": "ok", "restored": False, "current_context": current,
                "message": "The current context is still %r." % current}, 0
    rc, out, err = run(kc + ["config", "use-context", args.recorded])
    if rc != 0:
        return stop("restore_failed", "Could not switch back to %r (now %r): %s"
                    % (args.recorded, current, err or out), current_context=current)
    return {"status": "ok", "restored": True, "current_context": args.recorded,
            "message": "Switched the current context back from %r to %r." % (current, args.recorded)}, 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="service-eks preflight")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--cluster", required=True)
    c.add_argument("--region", required=True)
    c.add_argument("--context", required=True, help="the context the user named; never guessed")
    c.add_argument("--kubeconfig", default="")
    c.add_argument("--read", action="append", required=True,
                   help="<verb>:<resource>[:<namespace>], one per read the skill needs")
    r = sub.add_parser("restore")
    r.add_argument("--recorded", required=True, help="recorded_context from check; \"\" when there was none")
    r.add_argument("--kubeconfig", default="")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 64 if e.code else 0
    out, code = (check if args.cmd == "check" else restore)(args)
    print(json.dumps(out, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
