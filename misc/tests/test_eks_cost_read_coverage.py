"""Run the Idle Resources Bash examples against authored Kubernetes responses.

Requires Bash, jq and Python 3. No cluster, credentials or network calls are used.
Success/denial/empty expectations follow #335; this does not test live EKS or
complete orphan detection (for example, Helm ownership still needs confirmation).
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "skills/eks-cost-intelligence/references/idle-resources.md"


def item(kind, name="web", namespace="team", **fields):
    return {"kind": kind, "metadata": {"name": name, "namespace": namespace}, **fields}


def inventory(*items):
    return {"items": list(items)}


def fixture():
    return {"services": inventory(), "endpoints:team/web": {"kind": "Endpoints"},
            "namespaces": inventory(item("Namespace", name="team")), "pods": inventory(),
            "resourcequotas": inventory(), "limitranges": inventory(),
            "configmaps": inventory(), "secrets": inventory()}


MOCK = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["MOCK_CALLS"], "a") as log:
    log.write(json.dumps(args) + "\n")
if not args or args[0] != "get":
    sys.exit("Only fixture get operations are permitted")
kind = {"configmap":"configmaps", "secret":"secrets"}.get(args[1], args[1])
key = kind
namespace = args[args.index("-n") + 1] if "-n" in args else None
if kind == "endpoints":
    key += ":" + namespace + "/" + args[2]
with open(os.environ["MOCK_FIXTURE"]) as source:
    data = json.load(source)
if key not in data:
    sys.exit("Unexpected fixture request: " + key)
result = data[key]
if "error" in result:
    print(result["error"], file=sys.stderr)
    sys.exit(1)
if namespace and "items" in result:
    result = {"items":[x for x in result["items"] if x["metadata"].get("namespace") == namespace]}
if "--no-headers" in args:
    rows = "\n".join(x["metadata"]["name"] for x in result.get("items", []))
    print(rows, end="\n" if rows else "")
else:
    print(json.dumps(result))
'''


@unittest.skipUnless(shutil.which("bash") and shutil.which("jq"), "Bash and jq required")
class ReadCoverage(unittest.TestCase):
    def run_example(self, label, responses):
        markdown = SOURCE.read_text(encoding="utf-8")
        blocks = re.findall(r"```bash\n(.*?)\n```", markdown, re.S)
        script = next(block for block in blocks if block.startswith("# Read-coverage guard: " + label + "\n"))
        with tempfile.TemporaryDirectory(prefix="apex-cost-coverage-") as tmp:
            work = Path(tmp)
            mock = work / "kubectl"
            mock.write_text(MOCK, encoding="utf-8")
            mock.chmod(0o755)
            (work / "fixture.json").write_text(json.dumps(responses), encoding="utf-8")
            env = dict(os.environ, PATH=str(work) + os.pathsep + os.environ["PATH"],
                       MOCK_FIXTURE=str(work / "fixture.json"), MOCK_CALLS=str(work / "calls.jsonl"))
            result = subprocess.run(["bash", "-c", script], cwd=work, env=env,
                                    capture_output=True, text=True, timeout=10)
            calls = [json.loads(line) for line in (work / "calls.jsonl").read_text().splitlines()]
        return result, calls

    def lb(self, **overrides):
        data = fixture()
        data["services"] = inventory(item("Service", spec={"type": "LoadBalancer"}))
        data.update(overrides)
        return self.run_example("idle load balancers", data)

    def test_empty_services_succeeds_without_endpoints(self):
        result, calls = self.run_example("idle load balancers", fixture())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(calls), 1)

    def test_denied_services_is_not_empty(self):
        result, calls = self.lb(services={"error": "Forbidden: services"})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("IDLE_LB", result.stdout)
        self.assertEqual(len(calls), 1)

    def test_denied_endpoints_is_not_zero(self):
        result, _ = self.lb(**{"endpoints:team/web": {"error": "Forbidden: endpoints"}})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("IDLE_LB", result.stdout)

    def test_timeout_is_not_zero(self):
        result, _ = self.lb(**{"endpoints:team/web": {"error": "request timed out"}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timed out", result.stderr)
        self.assertNotIn("IDLE_LB", result.stdout)

    def test_successful_empty_endpoints_is_idle(self):
        result, _ = self.lb()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("IDLE_LB: team/web", result.stdout)

    def test_mixed_subsets_with_ready_address_are_not_idle(self):
        endpoint = {"kind": "Endpoints", "subsets": [{"notReadyAddresses": [{"ip": "10.0.0.2"}]},
                                                       {"addresses": [{"ip": "10.0.0.1"}]}]}
        result, _ = self.lb(**{"endpoints:team/web": endpoint})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("IDLE_LB", result.stdout)

    def test_wrong_response_shape_is_not_zero(self):
        result, _ = self.lb(**{"endpoints:team/web": {"kind": "Status"}})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("IDLE_LB", result.stdout)

    def test_prior_verified_service_survives_later_denial(self):
        data = fixture()
        data["services"] = inventory(item("Service", spec={"type": "LoadBalancer"}),
                                     item("Service", name="denied", spec={"type": "LoadBalancer"}))
        data["endpoints:team/denied"] = {"error": "Forbidden"}
        result, _ = self.run_example("idle load balancers", data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("IDLE_LB: team/web", result.stdout)
        self.assertNotIn("IDLE_LB: team/denied", result.stdout)

    def test_denied_pods_cannot_make_empty_namespace(self):
        data = fixture()
        data.update(pods={"error": "Forbidden"}, resourcequotas=inventory(item("ResourceQuota")))
        result, _ = self.run_example("empty namespaces", data)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("EMPTY_NS", result.stdout)

    def test_only_system_namespaces_need_no_pod_read(self):
        data = fixture()
        data.update(namespaces=inventory(item("Namespace", name="kube-system"),
                                         item("Namespace", name="default")), pods={"error": "Forbidden"})
        result, calls = self.run_example("empty namespaces", data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.stdout, "")

    def test_confirmed_quota_and_empty_pods_need_no_limitrange(self):
        data = fixture()
        data["resourcequotas"] = inventory(item("ResourceQuota"))
        result, calls = self.run_example("empty namespaces", data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EMPTY_NS_WITH_QUOTA: team", result.stdout)
        self.assertFalse(any(c[1] == "limitranges" for c in calls))

    def test_limitrange_can_prove_presence_when_quota_denied(self):
        data = fixture()
        data.update(resourcequotas={"error": "Forbidden"}, limitranges=inventory(item("LimitRange")))
        result, _ = self.run_example("empty namespaces", data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EMPTY_NS_WITH_QUOTA: team", result.stdout)
        self.assertIn("quotas=UNKNOWN", result.stdout)

    def test_empty_limitrange_does_not_resolve_unknown_quota(self):
        data = fixture()
        data["resourcequotas"] = {"error": "Forbidden"}
        result, _ = self.run_example("empty namespaces", data)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("EMPTY_NS", result.stdout)

    def test_running_namespace_needs_no_quota_read(self):
        data = fixture()
        data["pods"] = inventory(item("Pod", status={"phase": "Running"}))
        result, calls = self.run_example("empty namespaces", data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.stdout, "")

    def test_empty_config_inventories_need_no_pod_read(self):
        result, calls = self.run_example("unreferenced configuration", fixture())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(c[1] == "pods" for c in calls))
        self.assertEqual(result.stdout, "")

    def test_only_excluded_config_objects_need_no_pod_read(self):
        data = fixture()
        data.update(pods={"error": "Forbidden"},
                    configmaps=inventory(item("ConfigMap", name="kube-root-ca.crt"),
                                         item("ConfigMap", namespace="kube-system")),
                    secrets=inventory(item("Secret", type="kubernetes.io/service-account-token"),
                                      item("Secret", name="release", type="helm.sh/release.v1")))
        result, calls = self.run_example("unreferenced configuration", data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(c[1] == "pods" for c in calls))
        self.assertEqual(result.stdout, "")

    def test_root_ca_close_name_still_requires_pod_references(self):
        data = fixture()
        data.update(pods={"error": "Forbidden"},
                    configmaps=inventory(item("ConfigMap", name="kube-root-ca-backup")))
        result, calls = self.run_example("unreferenced configuration", data)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(c[1] == "pods" for c in calls))
        self.assertEqual(result.stdout, "")

    def test_unknown_pod_references_cannot_orphan_objects(self):
        data = fixture()
        data.update(pods={"error": "Forbidden"}, configmaps=inventory(item("ConfigMap")),
                    secrets=inventory(item("Secret")))
        result, _ = self.run_example("unreferenced configuration", data)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_config_candidate_survives_denied_secret_list(self):
        data = fixture()
        data.update(configmaps=inventory(item("ConfigMap")), secrets={"error": "Forbidden"})
        result, _ = self.run_example("unreferenced configuration", data)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "team/configmap/web")

    def test_known_references_match_namespace_and_kind(self):
        data = fixture()
        pod = item("Pod", status={"phase": "Running"}, spec={"volumes": [{"configMap": {"name": "web"}}]})
        data.update(pods=inventory(pod), configmaps=inventory(item("ConfigMap"), item("ConfigMap", namespace="other")),
                    secrets=inventory(item("Secret")))
        result, _ = self.run_example("unreferenced configuration", data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(result.stdout.splitlines()), {"other/configmap/web", "team/secret/web"})


if __name__ == "__main__":
    unittest.main()
