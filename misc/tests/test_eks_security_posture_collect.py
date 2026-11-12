#!/usr/bin/env python3
"""posture_collect.sh by_ids: one bad instance id must not drop the rest of its batch.

EC2 fails a whole describe-instances --instance-ids call when one id is not returned or is malformed. When EC2 names an id, the collector retries that batch one id at a time and keeps the
ones that resolve; an id that still fails is logged with EC2's error and the id. A throttle or a denial is not
re-asked per id. Fake aws and kubectl on PATH, no live AWS.
"""

import json
import os
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_eks_security_match import ASSETS, CASES, NEEDS_JQ, TmpCase, last_json, write_stubs  # noqa: E402

IDS = ["i-0aaa1111111111111", "i-0bbb2222222222222", "i-0ccc3333333333333"]

# Answers ec2 describe-instances --instance-ids per id from IDS_RULE; every other call goes to the shared stub.
#   mode notfound|malformed: a call holding a `bad` id fails naming it; throttle|denied: every call fails;
#   single_throttle: a one-id call for one of these ids fails with a throttle that does not name the id.
WRAPPER = r'''#!{python} -B
import json, os, sys
args = sys.argv[1:]
if args[:2] == ["ec2", "describe-instances"] and "--instance-ids" in args:
    i = args.index("--instance-ids") + 1
    ids = []
    while i < len(args) and not args[i].startswith("--"):
        ids.append(args[i]); i += 1
    cfg = dict({"mode": "ok", "bad": []}, **json.loads(os.environ["IDS_RULE"]))
    with open(os.environ["IDS_LOG"], "a") as f:
        f.write(json.dumps(ids) + "\n")
    code = {"notfound": "InvalidInstanceID.NotFound", "malformed": "InvalidInstanceID.Malformed",
            "throttle": "RequestLimitExceeded", "denied": "UnauthorizedOperation"}
    if len(ids) == 1 and ids[0] in cfg.get("single_throttle", []):
        sys.stderr.write("An error occurred (RequestLimitExceeded) when calling the DescribeInstances operation: Request limit exceeded.\n")
        sys.exit(254)
    bad = [x for x in ids if x in cfg["bad"]] if cfg["mode"] in ("notfound", "malformed") else ids
    if cfg["mode"] != "ok" and bad:
        sys.stderr.write("An error occurred (%s) when calling the DescribeInstances operation: %s\n" % (code[cfg["mode"]], ", ".join(bad)))
        sys.exit(254)
    print(json.dumps({"Reservations": [{"Instances": [{"InstanceId": x, "MetadataOptions": {"HttpTokens": "required"}}
                                                      for x in ids]}]}))
    sys.exit(0)
os.execv(os.path.join(os.environ["BASE_BIN"], "aws"), [os.path.join(os.environ["BASE_BIN"], "aws")] + args)
'''


def node(iid):
    return {"metadata": {"name": "ip-10-0-1-%s.us-west-2.compute.internal" % iid[-2:]},
            "spec": {"providerID": "aws:///us-west-2a/%s" % iid}}


@NEEDS_JQ
class ByIdsRetry(TmpCase):
    def run_case(self, rule):
        pc = CASES["posture"]
        base = os.path.join(self.tmp, "base")
        write_stubs(base)
        bindir = os.path.join(self.tmp, "bin")
        os.mkdir(bindir)
        with open(os.path.join(bindir, "aws"), "w", encoding="utf-8") as f:
            f.write(WRAPPER.replace("{python}", sys.executable))
        os.chmod(os.path.join(bindir, "aws"), 0o700)
        files = dict(pc["files"], nodes={"apiVersion": "v1", "kind": "List", "items": [node(i) for i in IDS]})
        aws = dict(pc["stub_aws"], **{"ec2 describe-instances": {"json": {"Reservations": []}}})
        kubectl = dict(pc["stub_kubectl"], **{"get nodes": {"file": "nodes"}})
        resp = self.write("responses.json", {"aws": aws, "kubectl": kubectl, "files": files, "lenient": True})
        log = os.path.join(self.tmp, "ids.jsonl")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "KUBECONFIG"))}
        env.update({"PATH": bindir + os.pathsep + base + os.pathsep + env.get("PATH", "/usr/bin:/bin"),
                    "BASE_BIN": base, "STUB_RESP": resp, "STUB_LOG": os.path.join(self.tmp, "calls.jsonl"),
                    "HOME": self.tmp, "IDS_RULE": json.dumps(rule), "IDS_LOG": log})
        work = os.path.join(self.tmp, "work")
        p = subprocess.run(["bash", os.path.join(ASSETS, "posture_collect.sh"), "--cluster", "demo", "--region",
                            "us-west-2", "--context", "demo-ctx", "--work", work],
                           capture_output=True, text=True, timeout=300, env=env, cwd=self.tmp)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(last_json(p.stdout)["ok"])
        with open(log, encoding="utf-8") as f:
            calls = [json.loads(ln) for ln in f if ln.strip()]
        P = os.path.join(work, "posture")
        with open(os.path.join(P, "instances.json"), encoding="utf-8") as f:
            inst = sorted(i["InstanceId"] for r in json.load(f)["Reservations"] for i in r["Instances"])
        with open(os.path.join(P, "meta.json"), encoding="utf-8") as f:
            errors = [e for e in json.load(f)["errors"] if e["step"] == "instances"]
        return calls, inst, errors

    def test_all_good_one_call(self):
        calls, inst, errors = self.run_case({})
        self.assertEqual(calls, [IDS])
        self.assertEqual(inst, IDS)
        self.assertEqual(errors, [])

    def assert_one_bad_kept_rest(self, mode):
        calls, inst, errors = self.run_case({"mode": mode, "bad": [IDS[1]]})
        self.assertEqual(calls, [IDS] + [[i] for i in IDS])
        self.assertEqual(inst, [IDS[0], IDS[2]])
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("failed for 1 id(s) (%s)" % IDS[1], errors[0]["message"])

    def test_notfound_id_keeps_the_others(self):
        self.assert_one_bad_kept_rest("notfound")

    def test_malformed_id_keeps_the_others(self):
        self.assert_one_bad_kept_rest("malformed")

    def test_throttled_retry_names_the_id(self):
        # EC2's throttle text names no id, so the log line must
        calls, inst, errors = self.run_case({"mode": "notfound", "bad": [IDS[1]], "single_throttle": [IDS[2]]})
        self.assertEqual(inst, [IDS[0]])
        msgs = [e["message"] for e in errors]
        self.assertEqual(len(msgs), 2, msgs)
        self.assertTrue(any("(%s)" % IDS[2] in m and "RequestLimitExceeded" in m for m in msgs), msgs)

    def assert_batch_failed_not_retried(self, mode):
        calls, inst, errors = self.run_case({"mode": mode})
        self.assertEqual(calls, [IDS])
        self.assertEqual(inst, [])
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("failed for 3 id(s)", errors[0]["message"])

    def test_throttle_not_retried_per_id(self):
        self.assert_batch_failed_not_retried("throttle")

    def test_denied_not_retried_per_id(self):
        self.assert_batch_failed_not_retried("denied")


if __name__ == "__main__":
    unittest.main()
