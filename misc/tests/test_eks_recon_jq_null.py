#!/usr/bin/env python3
"""Null-iteration fixtures for the eks-recon jq snippets (issue 292).

Each case reads its jq filter out of the reference markdown itself (located by
a unique substring), then runs it with jq against synthetic JSON where the
optional field is missing, null, empty, and populated. Missing, null and empty
must exit 0 with an empty result; the populated control must give the expected
value.

Run with either:

    python3 -m pytest misc/tests/test_eks_recon_jq_null.py -q
    python3 misc/tests/test_eks_recon_jq_null.py

Set EKS_RECON_SRC_ROOT to a directory holding a copy of the repo's
skills/eks-recon/references/ tree to run the same cases against other content
(for example a `git show origin/main:<path>` export).
"""

import json
import os
import shutil
import subprocess
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_ROOT = os.environ.get("EKS_RECON_SRC_ROOT", REPO_ROOT)
REF_DIR = os.path.join(SRC_ROOT, "skills", "eks-recon", "references")
JQ = shutil.which("jq")


def extract_filter(md_name, marker):
    """Return the single-quoted jq filter that contains `marker` in md_name."""
    with open(os.path.join(REF_DIR, md_name), encoding="utf-8") as f:
        text = f.read()
    assert text.count(marker) == 1, "marker %r not unique in %s" % (marker, md_name)
    pos = text.index(marker)
    start = text.rindex("jq -r '", 0, pos) + len("jq -r '")
    end = text.index("'", pos)
    return text[start:end]


def run_jq(filt, doc):
    """Run jq -c; return (returncode, list of parsed output values, stderr)."""
    proc = subprocess.run(
        [JQ, "-c", filt],
        input=json.dumps(doc),
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    return proc.returncode, out, proc.stderr.strip()


def ds(container):
    """aws-node DaemonSet shell around one container object."""
    return {"spec": {"template": {"spec": {"containers": [container]}}}}


def deploy_list(container):
    """Deployment list with one deployment around one container object."""
    return {"items": [{
        "metadata": {"namespace": "external-dns", "name": "external-dns"},
        "spec": {"template": {"spec": {"containers": [container]}}},
    }]}


def cm_list(cm_extra):
    """ConfigMap list with one ConfigMap; cm_extra merges into the object."""
    cm = {"metadata": {"namespace": "obs", "name": "cfg"}}
    cm.update(cm_extra)
    return {"items": [cm]}


ENV = [
    {"name": "AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG", "value": "true"},
    {"name": "ENABLE_PREFIX_DELEGATION", "value": "true"},
    {"name": "ENABLE_POD_ENI", "value": "false"},
    {"name": "OTHER", "value": "x"},
]
ARGS = ["--source=service", "--domain-filter=example.com"]


def env_variants(build, key, populated):
    return {
        "missing": build({"name": "aws-node"}),
        "null": build({"name": "aws-node", key: None}),
        "empty": build({"name": "aws-node", key: []}),
        "control": build({"name": "aws-node", key: populated}),
    }


def data_variants(value):
    return {
        "missing": cm_list({}),
        "null": cm_list({"data": None}),
        "empty": cm_list({"data": {}}),
        "control": cm_list({"data": {"cfg.yaml": value}}),
    }


CM_HIT = [{"namespace": "obs", "name": "cfg"}]


def crd_list(crd_extra):
    """CRD list with one CRD; crd_extra merges into the object."""
    crd = {"metadata": {"name": "widgets.example.com"}}
    crd.update(crd_extra)
    return {"items": [crd]}


CRD_VARIANTS = {
    "missing": crd_list({}),
    "null": crd_list({"status": {"conditions": None}}),
    "empty": crd_list({"status": {"conditions": []}}),
    "control": crd_list({"status": {"conditions": [
        {"type": "NamesAccepted", "status": "True"}]}}),
}

# (case id, markdown file, unique marker, inputs, expected output for
#  missing/null/empty, expected output for the control)
CASES = [
    ("networking-env-map", "networking.md", 'startswith("MINIMUM_")',
     env_variants(ds, "env", ENV), [{}],
     [{"AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG": "true",
       "ENABLE_PREFIX_DELEGATION": "true", "ENABLE_POD_ENI": "false"}]),
    ("networking-env-prefix-delegation", "networking.md",
     'select(.name=="ENABLE_PREFIX_DELEGATION")',
     env_variants(ds, "env", ENV), [], ["true"]),
    ("networking-env-pod-eni", "networking.md", 'select(.name=="ENABLE_POD_ENI")',
     env_variants(ds, "env", ENV), [], ["false"]),
    ("networking-env-custom-network", "networking.md",
     'select(.name=="AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG")',
     env_variants(ds, "env", ENV), [], ["true"]),
    ("networking-external-dns-args", "networking.md", 'select(startswith("--domain-filter"))',
     env_variants(deploy_list, "args", ARGS),
     [{"ns": "external-dns", "domain_filters": []}],
     [{"ns": "external-dns", "domain_filters": ["--domain-filter=example.com"]}]),
    ("observability-amp-configmap", "observability.md", 'contains("aps-workspaces")',
     data_variants("remote_write: https://aps-workspaces.us-east-1.amazonaws.com/x"),
     [], CM_HIT),
    ("observability-opensearch-configmap", "observability.md", 'contains("opensearch")',
     data_variants("host: search-logs.us-east-1.es.amazonaws.com opensearch"),
     [], CM_HIT),
    ("addons-crd-names-accepted", "addons.md", '"NamesAccepted"',
     CRD_VARIANTS, [], ["widgets.example.com"]),
]


@unittest.skipIf(JQ is None, "jq not installed")
class TestEksReconJqNull(unittest.TestCase):
    def test_cases(self):
        for case_id, md, marker, inputs, empty_expect, control_expect in CASES:
            filt = extract_filter(md, marker)
            for variant, doc in inputs.items():
                expect = control_expect if variant == "control" else empty_expect
                with self.subTest(case=case_id, variant=variant):
                    rc, out, err = run_jq(filt, doc)
                    self.assertEqual(rc, 0, "%s/%s: jq rc=%d: %s" % (case_id, variant, rc, err))
                    self.assertEqual(out, expect)


if __name__ == "__main__":
    unittest.main()
