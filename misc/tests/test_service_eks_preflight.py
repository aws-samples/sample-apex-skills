#!/usr/bin/env python3
"""classes/service-eks: the preflight's offline tests and the static --context grep.

The preflight runs against fake kubectl and aws on PATH (no live AWS, no cluster). The
stop-and-name path: an `auth can-i` answer of no, or an error, stops the run before any read
and names each missing verb and resource. The static grep: every kubectl read line in a
service-eks member's SKILL.md, scripts/, tools/ and assets/ carries --context; kubectl lines in
references/ are not checked by it. It blocks on members (metadata.apex-classes names service-eks)
and on the class's rules.md, and prints a non-blocking, rough (line heuristic) report count for
every other eks-* skill. Stdlib only.

Override the preflight under test with SERVICE_EKS_PREFLIGHT=<path> (used for a negative control).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLASS_DIR = os.path.join(REPO, "classes", "service-eks")
PREFLIGHT = os.environ.get("SERVICE_EKS_PREFLIGHT") or os.path.join(CLASS_DIR, "scripts", "preflight.py")
ENDPOINT = "https://ABC123.gr7.us-west-2.eks.amazonaws.com"

# One fake for both tools. FAKE_STATE (JSON) sets the answers; every call is logged to FAKE_LOG.
FAKE = r'''#!{python} -B
import json, os, sys
tool = os.path.basename(sys.argv[0]); args = sys.argv[1:]
st = json.load(open(os.environ["FAKE_STATE"]))
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps([tool] + args) + "\n")
def out(text, rc=0, err=""):
    if text: print(text)
    if err: sys.stderr.write(err + "\n")
    sys.exit(rc)
if tool == "aws":
    if args[:2] == ["eks", "describe-cluster"]:
        d = st["describe"]
        out(d.get("out", ""), d.get("rc", 0), d.get("err", ""))
    out("", 255, "fake aws: unexpected call")
if "--kubeconfig" in args:
    i = args.index("--kubeconfig"); del args[i:i + 2]
ctx = None
if "--context" in args:
    i = args.index("--context"); ctx = args[i + 1]; del args[i:i + 2]
if args[:2] == ["config", "get-contexts"]:
    out("\n".join(st["contexts"]))
if args[:2] == ["config", "current-context"]:
    cur = st.get("current", "")
    out(cur, 0) if cur else out("", 1, "error: current-context is not set")
if args[:2] == ["config", "use-context"]:
    st["current"] = args[2]; json.dump(st, open(os.environ["FAKE_STATE"], "w"))
    out('Switched to context "%s".' % args[2])
if args[:2] == ["config", "view"]:
    out(st["servers"].get(ctx, ""))
if args[:2] == ["auth", "can-i"]:
    key = " ".join(args[2:4]) + (" -n " + args[args.index("-n") + 1] if "-n" in args else " -A")
    a = st.get("can_i", {}).get(key, "yes")
    if a == "yes": out("yes")
    if a == "no": out("no", 1)
    out("", 1, a)
out("", 1, "fake kubectl: unexpected call %s" % args)
'''


class PreflightCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="service-eks-preflight-")
        self.bin = os.path.join(self.tmp, "bin")
        os.mkdir(self.bin)
        for tool in ("kubectl", "aws"):
            path = os.path.join(self.bin, tool)
            with open(path, "w", encoding="utf-8") as f:
                f.write(FAKE.replace("{python}", sys.executable))
            os.chmod(path, 0o700)
        self.log = os.path.join(self.tmp, "calls.jsonl")
        self.state = os.path.join(self.tmp, "state.json")
        self.set_state()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def set_state(self, **over):
        st = {"contexts": ["user-ctx", "other-ctx", "demo-alias"], "current": "other-ctx",
              "servers": {"user-ctx": ENDPOINT, "demo-alias": ENDPOINT.lower() + ":443/",
                          "other-ctx": "https://OTHER.gr7.us-west-2.eks.amazonaws.com"},
              "describe": {"out": ENDPOINT}, "can_i": {}}
        st.update(over)
        with open(self.state, "w", encoding="utf-8") as f:
            json.dump(st, f)

    def run_pf(self, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "KUBECONFIG"))}
        env.update({"PATH": self.bin + os.pathsep + "/usr/bin:/bin", "FAKE_STATE": self.state,
                    "FAKE_LOG": self.log, "HOME": self.tmp})
        p = subprocess.run([sys.executable, "-B", PREFLIGHT] + list(args), capture_output=True, text=True,
                           timeout=60, env=env, cwd=self.tmp)
        try:
            body = json.loads(p.stdout)
        except ValueError:
            body = None
        return p.returncode, body, p.stderr

    def check(self, *extra, context="user-ctx"):
        return self.run_pf("check", "--cluster", "demo", "--region", "us-west-2", "--context", context,
                           "--read", "list:nodes", "--read", "list:pods", "--read", "get:deployments:kube-system",
                           *extra)

    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def kubectl_calls(self):
        return [c[1:] for c in self.calls() if c[0] == "kubectl"]

    def assert_no_kubeconfig_write(self):
        for c in self.kubectl_calls():
            self.assertNotIn("use-context", c)
            self.assertNotIn("set-context", c)
            self.assertNotIn("set-cluster", c)
        for c in self.calls():
            self.assertNotIn("update-kubeconfig", c)


class Check(PreflightCase):
    def test_ok_binds_context_and_records_current(self):
        rc, body, err = self.check()
        self.assertEqual(rc, 0, err)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["recorded_context"], "other-ctx")
        self.assertEqual([r["answer"] for r in body["can_i"]], ["yes", "yes", "yes"])
        self.assert_no_kubeconfig_write()

    def test_every_cluster_call_carries_context(self):
        self.check()
        local = (["config", "get-contexts"], ["config", "current-context"])
        cluster_calls = [c for c in self.kubectl_calls() if c[:2] not in local]
        self.assertTrue(cluster_calls)
        for c in cluster_calls:
            self.assertIn("--context", c)
            self.assertEqual(c[c.index("--context") + 1], "user-ctx")

    def test_can_i_scope_all_namespaces_and_named_namespace(self):
        self.check()
        can_i = [c for c in self.kubectl_calls() if "can-i" in c]
        self.assertEqual(len(can_i), 3)
        self.assertIn("-A", can_i[1])
        self.assertEqual(can_i[2][can_i[2].index("-n") + 1], "kube-system")

    def test_kubeconfig_passes_to_every_kubectl_call(self):
        rc, body, _ = self.check("--kubeconfig", "/proj/kubeconfig")
        self.assertIn("--context user-ctx --kubeconfig /proj/kubeconfig", body["message"])
        for c in self.kubectl_calls():
            self.assertEqual(c[:2], ["--kubeconfig", "/proj/kubeconfig"])

    def test_alias_with_matching_endpoint_is_accepted(self):
        rc, body, err = self.check(context="demo-alias")
        self.assertEqual(rc, 0, err)
        self.assertEqual(body["context"], "demo-alias")

    def test_stop_on_no_names_verb_and_resource(self):
        self.set_state(can_i={"list pods -A": "no"})
        rc, body, _ = self.check()
        self.assertEqual(rc, 2)
        self.assertEqual(body["status"], "stop")
        self.assertEqual(body["reason"], "permission_missing")
        self.assertEqual([(m["verb"], m["resource"]) for m in body["missing"]], [("list", "pods")])
        self.assertIn("list pods across the cluster (-A): denied", body["message"])
        self.assertIn("STOP", body["message"])

    def test_stop_on_error_names_verb_and_resource(self):
        self.set_state(can_i={"get deployments -n kube-system": "Unable to connect to the server: i/o timeout"})
        rc, body, _ = self.check()
        self.assertEqual(rc, 2)
        self.assertEqual(body["reason"], "permission_missing")
        self.assertIn("get deployments in namespace kube-system: check failed (Unable to connect", body["message"])
        self.assertIn("fix the credentials or the network first", body["message"])

    def test_stop_names_every_missing_read_and_makes_no_read(self):
        self.set_state(can_i={"list nodes -A": "no", "list pods -A": "forbidden: oops"})
        rc, body, _ = self.check()
        self.assertEqual(rc, 2)
        self.assertEqual(len(body["missing"]), 2)
        reads = [c for c in self.kubectl_calls() if any(v in c for v in ("get", "list", "describe")) and "can-i" not in c]
        self.assertEqual(reads, [])

    def test_missing_context_stops_and_asks_without_writing(self):
        rc, body, _ = self.check(context="not-there")
        self.assertEqual(rc, 2)
        self.assertEqual(body["reason"], "context_missing")
        self.assertIn("ask the user to add the entry", body["message"])
        self.assertFalse([c for c in self.kubectl_calls() if "can-i" in c or "view" in c])
        self.assert_no_kubeconfig_write()

    def test_endpoint_mismatch_stops_before_can_i(self):
        rc, body, _ = self.check(context="other-ctx")
        self.assertEqual(rc, 2)
        self.assertEqual(body["reason"], "endpoint_mismatch")
        self.assertFalse([c for c in self.kubectl_calls() if "can-i" in c])

    def test_describe_cluster_failure_stops(self):
        self.set_state(describe={"rc": 254, "err": "An error occurred (ResourceNotFoundException)"})
        rc, body, _ = self.check()
        self.assertEqual(rc, 2)
        self.assertEqual(body["reason"], "describe_cluster_failed")
        self.assertIn("eks:DescribeCluster", body["message"])

    def test_secret_reads_and_write_verbs_are_refused(self):
        for spec in ("list:secrets", "get:secrets:default", "get:secret", "get:*", "create:pods", "delete:nodes"):
            rc, body, _ = self.run_pf("check", "--cluster", "demo", "--region", "us-west-2", "--context", "user-ctx",
                                      "--read", spec)
            self.assertEqual(rc, 64, spec)
            self.assertEqual(body["status"], "usage", spec)
        self.assertEqual(self.calls(), [])

    def test_missing_read_list_is_usage(self):
        rc, _, _ = self.run_pf("check", "--cluster", "demo", "--region", "us-west-2", "--context", "user-ctx")
        self.assertEqual(rc, 64)


class Restore(PreflightCase):
    def test_switches_back_when_changed(self):
        self.set_state(current="user-ctx")
        rc, body, _ = self.run_pf("restore", "--recorded", "other-ctx")
        self.assertEqual(rc, 0)
        self.assertTrue(body["restored"])
        self.assertIn(["config", "use-context", "other-ctx"], self.kubectl_calls())

    def test_no_switch_when_unchanged(self):
        rc, body, _ = self.run_pf("restore", "--recorded", "other-ctx")
        self.assertEqual(rc, 0)
        self.assertFalse(body["restored"])
        self.assert_no_kubeconfig_write()

    def test_none_recorded_says_which_is_set(self):
        self.set_state(current="user-ctx")
        rc, body, _ = self.run_pf("restore", "--recorded", "")
        self.assertEqual(rc, 0)
        self.assertIn("now 'user-ctx'", body["message"])
        self.assert_no_kubeconfig_write()


# The static grep. A kubectl read line is a line naming `kubectl` followed by a read
# subcommand; a line naming only a kubeconfig-local read (config current-context,
# config get-contexts, version --client) does not reach a cluster and is skipped.
READ_SUBCOMMANDS = {"get", "describe", "logs", "top", "auth", "api-resources", "api-versions", "cluster-info",
                    "explain", "events", "version", "config"}
VALUE_FLAGS = {"-n", "--namespace", "--kubeconfig", "--context", "--cluster", "--user", "-o", "--output", "-l",
               "--selector", "--request-timeout", "-s", "--server"}
KUBECTL = re.compile(r"(?:^|[^\w./-])kubectl\s+(.*)")
SCAN_DIRS = ("scripts", "tools", "assets")


def is_unbound_read(line):
    """True when the line runs a kubectl read and carries no --context."""
    m = KUBECTL.search(line)
    if not m or "--context" in line:
        return False
    toks = m.group(1).replace("`", " ").split()
    i, sub = 0, []
    while i < len(toks) and len(sub) < 2:
        t = toks[i]
        if t.startswith("-"):
            i += 2 if (t in VALUE_FLAGS and "=" not in t) else 1
            continue
        sub.append(t)
        i += 1
    if not sub or sub[0] not in READ_SUBCOMMANDS:
        return False
    if sub[0] == "config":
        return len(sub) > 1 and sub[1] == "view"
    if sub[0] == "version" and "--client" in toks:
        return False
    return True


def scan_files(root):
    files = [os.path.join(root, "SKILL.md")]
    for d in SCAN_DIRS:
        for dirpath, _, names in os.walk(os.path.join(root, d)):
            files += [os.path.join(dirpath, n) for n in sorted(names)]
    return [f for f in files if os.path.isfile(f)]


def unbound_lines(root):
    hits = []
    for path in scan_files(root):
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        hits += ["%s:%d: %s" % (os.path.relpath(path, REPO), n, ln.strip())
                 for n, ln in enumerate(lines, 1) if is_unbound_read(ln)]
    return hits


def is_member(skill_dir):
    try:
        with open(os.path.join(skill_dir, "SKILL.md"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    fm = text.split("---", 2)[1] if text.startswith("---") else ""
    m = re.search(r"(?:^|[{,])\s*apex-classes:\s*([^}#\n]*)", fm, re.M)
    return bool(m) and "service-eks" in re.split(r"[\s\"',\[\]]+", m.group(1))


class StaticGrep(unittest.TestCase):
    def test_detector(self):
        for line in ("kubectl get pods -A", "  kubectl -n kube-system get deploy", "run `kubectl auth can-i list pods`",
                     "kubectl config view --minify", "kubectl --kubeconfig k get nodes", "kubectl version"):
            self.assertTrue(is_unbound_read(line), line)
        for line in ("kubectl --context \"$CTX\" get pods -A", "kubectl config current-context",
                     "kubectl config get-contexts -o name", "kubectl version --client", "kubectl apply -f x.yaml",
                     "kubectl_base = 1", "no kubectl here", "mykubectl get pods"):
            self.assertFalse(is_unbound_read(line), line)

    def test_blocks_on_a_hostile_member(self):
        tmp = tempfile.mkdtemp(prefix="service-eks-grep-")
        try:
            os.makedirs(os.path.join(tmp, "scripts"))
            with open(os.path.join(tmp, "SKILL.md"), "w") as f:
                f.write("---\nname: x\nmetadata:\n  apex-classes: \"service-eks script\"\n---\nkubectl get nodes\n")
            with open(os.path.join(tmp, "scripts", "a.sh"), "w") as f:
                f.write("kubectl --context \"$C\" get pods -A\nkubectl -n x describe pod y\n")
            self.assertTrue(is_member(tmp))
            self.assertEqual(len(unbound_lines(tmp)), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_is_member_flow_form_and_trailing_comment(self):
        tmp = tempfile.mkdtemp(prefix="service-eks-member-")
        try:
            for fm, want in (('metadata: { apex-classes: "service-eks script" }', True),
                             ('metadata: { name: x, apex-classes: "service-eks" }', True),
                             ('metadata:\n  apex-classes: "eks-recon"  # service-eks later', False),
                             ('metadata: { apex-classes: "script" }  # service-eks', False)):
                with open(os.path.join(tmp, "SKILL.md"), "w") as f:
                    f.write("---\nname: x\n%s\n---\nbody\n" % fm)
                self.assertEqual(is_member(tmp), want, fm)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_class_files_carry_context(self):
        hits = []
        path = os.path.join(CLASS_DIR, "rules.md")
        with open(path, encoding="utf-8") as f:
            hits += ["%s:%d" % (path, n) for n, ln in enumerate(f, 1) if is_unbound_read(ln)]
        self.assertEqual(hits, [])

    def test_members_carry_context(self):
        skills = os.path.join(REPO, "skills")
        members = [d for d in sorted(os.listdir(skills)) if is_member(os.path.join(skills, d))]
        hits = [h for d in members for h in unbound_lines(os.path.join(skills, d))]
        self.assertEqual(hits, [], "service-eks members with kubectl reads lacking --context:\n" + "\n".join(hits))

    def test_report_other_eks_skills(self):
        """Non-blocking: skills not yet in service-eks, a rough (line heuristic) count for their own rebuild steps."""
        skills = os.path.join(REPO, "skills")
        rows = []
        for d in sorted(os.listdir(skills)):
            root = os.path.join(skills, d)
            if d.startswith("eks-") and os.path.isdir(root) and not is_member(root):
                rows.append("%s: %d" % (d, len(unbound_lines(root))))
        sys.stderr.write("\n[report, non-blocking] kubectl read lines without --context: " + ", ".join(rows) + "\n")


if __name__ == "__main__":
    unittest.main()
