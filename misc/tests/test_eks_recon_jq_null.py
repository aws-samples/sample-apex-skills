"""Offline fixtures for eks-recon jq queries and optional fields.

Run with Python 3 and jq on PATH:
    python3 misc/tests/test_eks_recon_jq_null.py -v

Queries come from the maintained Markdown. Inputs and expected outputs are
hand-authored from the detection contracts, not captured from a cluster.
The DevOps Agent pseudocode is exercised with client-shaped Python objects;
this is not an end-to-end agent or Kubernetes client integration test.
"""
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[2]


def load_queries(root=ROOT):
    queries = {}
    for key, filename, marker in (
        ("env_map", "networking.md", "# All AWS_/ENABLE_/WARM_/MINIMUM_ env vars in one map"),
        ("prefix", "networking.md", "# Prefix delegation"),
        ("pod_eni", "networking.md", "# Security groups for pods"),
        ("custom", "networking.md", "# Custom networking config flag"),
        ("dns", "networking.md", "### 9. external-dns"),
        ("amp", "observability.md", "# Check for ADOT or Prometheus remote write config"),
        ("search", "observability.md", "# Check for OpenSearch endpoint in configs"),
        ("kyverno", "security.md", "kubectl get clusterpolicies.kyverno.io -o json"),
        ("gatekeeper", "security.md", "kubectl get constraints -o json"),
    ):
        text = (root / "skills/eks-recon/references" / filename).read_text(encoding="utf-8")
        if text.count(marker) != 1:
            raise ValueError(f"Expected exactly one marker for {key}")
        match = re.search(r"\bjq\s+-r\s+'([^']+)'", text.split(marker, 1)[1])
        if not match:
            raise ValueError(f"Missing jq query for {key}")
        queries[key] = match.group(1)
    return queries


def run_jq(query, data):
    result = subprocess.run(
        ["jq", "-c", query], input=json.dumps(data), text=True,
        capture_output=True, timeout=10,
    )
    if result.returncode:
        raise AssertionError(f"jq exited {result.returncode}: {result.stderr.strip()}")
    return [json.loads(line) for line in result.stdout.splitlines()]


def fixture_cases():
    env = [{"name": name, "value": "true"} for name in (
        "ENABLE_PREFIX_DELEGATION", "ENABLE_POD_ENI", "AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG",
    )] + [{"name": "WARM_IP_TARGET", "value": "5"}, {"name": "UNRELATED", "value": "ignored"}]
    for state in ("missing", "null", "empty", "populated"):
        container = {"name": "example"}
        config = {"metadata": {"namespace": "test", "name": "config"}}
        if state != "missing":
            container["env"] = {"null": None, "empty": [], "populated": env}[state]
            container["args"] = {"null": None, "empty": [], "populated": [
                "--source=service", "--domain-filter=example.test", "--domain-filter=other.test",
            ]}[state]
            config["data"] = {"null": None, "empty": {}, "populated": {
                "config": "https://aps-workspaces.test https://opensearch.test",
            }}[state]
        daemonset = {"spec": {"template": {"spec": {"containers": [container]}}}}
        deployment = copy.deepcopy(daemonset)
        deployment["metadata"] = {"namespace": "test"}
        populated = state == "populated"
        for key in ("env_map", "prefix", "pod_eni", "custom"):
            expected = [{entry["name"]: entry["value"] for entry in env[:-1]}] if key == "env_map" else ["true"]
            yield f"{key}_{state}", key, daemonset, expected if populated else ([{}] if key == "env_map" else [])
        yield f"dns_{state}", "dns", {"items": [deployment]}, [{
            "ns": "test", "domain_filters": container.get("args", [])[1:] if populated else [],
        }]
        for key in ("amp", "search"):
            yield f"{key}_{state}", key, {"items": [config]}, ([{"namespace": "test", "name": "config"}] if populated else [])

    for key, value in (("amp", "aps-workspaces"), ("search", "opensearch"), ("search", "elasticsearch")):
        match = {"metadata": {"namespace": "test", "name": "later"}, "data": {"url": value}}
        yield f"{key}_{value}_after_missing", key, {"items": [{"metadata": {"name": "empty"}}, match]}, [{"namespace": "test", "name": "later"}]
        yield f"{key}_{value}_nonmatch", key, {"items": [{**match, "data": {"url": "unrelated"}}]}, []
        yield f"{key}_{value}_multiple_matches", key, {"items": [{**match, "data": {
            "first": value, "second": value,
        }}]}, [{"namespace": "test", "name": "later"}] * 2
    for key, name in (("prefix", "ENABLE_PREFIX_DELEGATION"), ("pod_eni", "ENABLE_POD_ENI"),
                      ("custom", "AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG")):
        yield f"{key}_single_false_flag", key, {"spec": {"template": {"spec": {"containers": [{
            "name": "aws-node", "env": [{"name": name, "value": "false"}],
        }]}}}}, ["false"]
    yield "dns_after_missing", "dns", {"items": [
        {"metadata": {"namespace": "first"}, "spec": {"template": {"spec": {"containers": [{"name": "dns"}]}}}},
        {"metadata": {"namespace": "second"}, "spec": {"template": {"spec": {"containers": [{"name": "dns", "args": ["--domain-filter=example.test"]}]}}}},
    ]}, [{"ns": "first", "domain_filters": []}, {"ns": "second", "domain_filters": ["--domain-filter=example.test"]}]


def admission_policy_cases():
    pod = {"resources": {"kinds": ["Pod"]}}
    service = {"resources": {"kinds": ["Service"]}}
    wildcard = {"resources": {"kinds": ["*"]}}
    mixed = {"resources": {"kinds": ["Service", "Pod"]}}
    subject = {"subjects": [{"kind": "ServiceAccount", "name": "builder", "namespace": "default"}]}
    core_pod = {"apiGroups": [""], "kinds": ["Pod"]}
    for name, matches, expected in (
        ("legacy_pod", [pod], True),
        ("legacy_mixed", [mixed], True),
        ("legacy_wildcard", [wildcard], True),
        ("any_mixed", [{"any": [service, mixed]}], True),
        ("any_wildcard", [{"any": [service, wildcard]}], True),
        ("all_pod", [{"all": [pod, mixed]}], True),
        ("all_with_subject", [{"all": [pod, subject]}], True),
        ("all_wildcard", [{"all": [wildcard, pod]}], True),
        ("all_disjoint", [{"all": [pod, service]}], False),
        ("all_without_kinds", [{"all": [{}]}], False),
        ("later_rule", [{}, pod], True),
        ("multiple_matching_rules", [pod, mixed], True),
        ("non_pod", [service], False),
        ("no_rules", [], False),
    ):
        item = {"metadata": {"name": name}, "spec": {"rules": [{"match": m} for m in matches]}}
        yield f"kyverno_{name}", "kyverno", {"items": [item]}, [name] if expected else []

    for name, spec, expected in (
        ("legacy_pod", {"match": {"kinds": [core_pod]}}, True),
        ("wildcard", {"match": {"kinds": [{"apiGroups": ["*"], "kinds": ["*"]}]}}, True),
        ("no_match", {}, True),
        ("no_kinds", {"match": {"scope": "Namespaced"}}, True),
        ("empty_kinds", {"match": {"kinds": []}}, True),
        ("empty_group", {"match": {"kinds": [{"apiGroups": [], "kinds": ["Pod"]}]}}, True),
        ("group_only", {"match": {"kinds": [{"apiGroups": [""]}]}}, True),
        ("non_pod", {"match": {"kinds": [{"apiGroups": [""], "kinds": ["Service"]}]}}, False),
        ("wrong_group", {"match": {"kinds": [{"apiGroups": ["apps"], "kinds": ["Pod", "*"]}]}}, False),
        ("cluster_scope", {"match": {"scope": "Cluster", "kinds": [core_pod]}}, False),
    ):
        item = {"metadata": {"name": name}, "spec": spec}
        yield f"gatekeeper_{name}", "gatekeeper", {"items": [item]}, [name] if expected else []

    for engine in ("kyverno", "gatekeeper"):
        yield f"{engine}_empty_inventory", engine, {"items": []}, []


class QueryFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("jq"):
            raise RuntimeError("jq is required; install it and put it on PATH")
        cls.queries = load_queries()


for name, key, data, expected in (*fixture_cases(), *admission_policy_cases()):
    def _check_fixture(self, key=key, data=data, expected=expected):
        self.assertEqual(run_jq(self.queries[key], data), expected)
    setattr(QueryFixtures, "test_" + name.replace("-", "_"), _check_fixture)


class PortPseudocode(unittest.TestCase):
    def test_optional_env_and_populated_values(self):
        reference = (ROOT / "devops-agent/eks-recon/references/networking.md").read_text(encoding="utf-8")
        code = reference.split("env = ", 1)[1].split("prefix_delegation =", 1)[0]
        for env, expected in ((None, {}), ([], {}), ([
            SimpleNamespace(name="ENABLE_POD_ENI", value="true"),
            SimpleNamespace(name="UNRELATED", value="ignored"),
        ], {"ENABLE_POD_ENI": "true"})):
            with self.subTest(env=env):
                ds = SimpleNamespace(spec=SimpleNamespace(template=SimpleNamespace(
                    spec=SimpleNamespace(containers=[SimpleNamespace(env=env)]))))
                scope = {"ds": ds}
                exec("env = " + code, scope)
                self.assertEqual(scope["env"], expected)


if __name__ == "__main__":
    unittest.main()
