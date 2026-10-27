#!/usr/bin/env python3
"""Offline checks of eks-recon's artifact assertions for issue #250.

Fixtures and expected outcomes are hand-authored from the output-path contract.
These exercise the real artifact validator, not an agent or a live cluster.
Run: python3 misc/tests/test_eks_recon_artifacts.py -v (requires PyYAML).
"""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "misc/evals/scripts"))

from artifact_validation import validate_run
from recon_output_oracle import check_outputs, inventory

EVALS = json.loads(
    (REPO_ROOT / "misc/evals/eks-recon/evals.json").read_text(encoding="utf-8")
)["evals"]
CONFIGS = {entry["id"]: entry["artifact_assertions"] for entry in EVALS}
DEFAULT_PREFIX = "EKS-Recon-prod-eu-2026-10-27-0905"
CUSTOM_PREFIX = "reports/team-handoff"
YAML_REPORT = """cluster:
  name: prod-eu
  version: "1.31"
compute:
  strategy: MNG
addons:
  eks_managed: []
iac:
  tool: unknown
cicd:
  argocd:
    detected: false
"""


class ReconArtifactAssertionsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_pair(self, prefix, *, directory=None, yaml_text=YAML_REPORT,
                   reference=None):
        directory = directory or self.root
        markdown = directory / (prefix + ".md")
        yaml_path = directory / (prefix + ".yaml")
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(
            "# EKS Recon\n\n## Machine artifact\n"
            + "- `" + (reference or prefix + ".yaml") + "` written\n",
            encoding="utf-8",
        )
        yaml_path.write_text(yaml_text, encoding="utf-8")
        return markdown, yaml_path

    def check_result(self, eval_id, *, passed, directory=None):
        result = validate_run(directory or self.root, CONFIGS[eval_id], REPO_ROOT)
        evidence = result.to_dict()
        if passed:
            self.assertEqual(result.structural_failed, 0, evidence)
            self.assertEqual(result.structural_skipped, 0, evidence)
            self.assertEqual(
                result.structural_passed,
                len(CONFIGS[eval_id]["structural"]), evidence,
            )
        else:
            self.assertGreater(result.structural_failed, 0, evidence)
        return result

    def test_default_accepts_different_clusters_and_timestamps(self):
        for prefix in (DEFAULT_PREFIX, "EKS-Recon-dev_team-2027-01-02-2359"):
            with self.subTest(prefix=prefix):
                directory = self.root / prefix
                self.write_pair(prefix, directory=directory)
                self.check_result(1, passed=True, directory=directory)

    def test_custom_prefix_in_subdirectory(self):
        self.write_pair(CUSTOM_PREFIX)
        self.check_result(2, passed=True)

    def test_custom_prefix_cannot_be_ignored(self):
        self.write_pair(DEFAULT_PREFIX)
        self.check_result(2, passed=False)

    def test_default_requires_timestamp_shape(self):
        for prefix in ("EKS-Recon-prod", "EKS-Recon-prod-YYYY-MM-DD-HHMM"):
            with self.subTest(prefix=prefix):
                directory = self.root / prefix
                self.write_pair(prefix, directory=directory)
                self.check_result(1, passed=False, directory=directory)

    def test_legacy_outputs_fail_both_evals(self):
        self.write_pair(".eks-recon-report")
        for eval_id in CONFIGS:
            with self.subTest(eval_id=eval_id):
                self.check_result(eval_id, passed=False)

    def test_missing_artifacts_fail_both_evals(self):
        for eval_id in CONFIGS:
            with self.subTest(eval_id=eval_id):
                self.check_result(eval_id, passed=False)

    def test_each_artifact_is_required(self):
        for eval_id, prefix in ((1, DEFAULT_PREFIX), (2, CUSTOM_PREFIX)):
            for extension in (".md", ".yaml"):
                with self.subTest(eval_id=eval_id, missing=extension):
                    directory = self.root / (str(eval_id) + extension)
                    self.write_pair(prefix, directory=directory)
                    (directory / (prefix + extension)).unlink()
                    self.check_result(eval_id, passed=False, directory=directory)

    def test_invalid_yaml_is_rejected(self):
        for eval_id, prefix in ((1, DEFAULT_PREFIX), (2, CUSTOM_PREFIX)):
            with self.subTest(eval_id=eval_id):
                self.write_pair(prefix, yaml_text=YAML_REPORT + "broken: [\n")
                result = self.check_result(eval_id, passed=False)
                self.assertTrue(any(
                    r.assertion["type"] == "yaml-valid" and r.status == "failed"
                    for r in result.structural_results
                ))

    def test_required_yaml_content_is_still_checked(self):
        for eval_id, prefix in ((1, DEFAULT_PREFIX), (2, CUSTOM_PREFIX)):
            with self.subTest(eval_id=eval_id):
                self.write_pair(prefix, yaml_text=YAML_REPORT.replace("compute:", "other:"))
                self.check_result(eval_id, passed=False)

    def test_legacy_machine_reference_is_rejected(self):
        for eval_id, prefix in ((1, DEFAULT_PREFIX), (2, CUSTOM_PREFIX)):
            with self.subTest(eval_id=eval_id):
                self.write_pair(prefix, reference=".eks-recon-report.yaml")
                self.check_result(eval_id, passed=False)

    def test_extra_legacy_output_is_rejected(self):
        self.write_pair(DEFAULT_PREFIX)
        self.write_pair(CUSTOM_PREFIX)
        self.write_pair(".eks-recon-report")
        for eval_id in CONFIGS:
            with self.subTest(eval_id=eval_id):
                self.check_result(eval_id, passed=False)

    def oracle(self, before=None, **kwargs):
        return check_outputs(
            self.root, before or {}, cluster='prod-eu',
            started=datetime.fromisoformat('2026-10-27T09:05:10+07:00'),
            ended=datetime.fromisoformat('2026-10-27T09:06:20+07:00'), **kwargs,
        )

    def test_oracle_accepts_exact_pair(self):
        self.write_pair(DEFAULT_PREFIX)
        self.assertEqual(self.oracle(), [])

    def test_oracle_rejects_mismatch_that_generic_assertions_accept(self):
        md, yml = self.write_pair(DEFAULT_PREFIX, reference='EKS-Recon-nonexistent-2026-10-27-0905.yaml')
        yml.rename(self.root / 'EKS-Recon-other-2026-10-27-0906.yaml')
        self.check_result(1, passed=True)
        errors = self.oracle()
        self.assertIn('Markdown and YAML basenames differ', errors)
        self.assertIn('Machine artifact section does not name the actual YAML path', errors)

    def test_oracle_checks_cluster_and_timestamp(self):
        self.write_pair('EKS-Recon-prod-eu-2026-10-26-0905', yaml_text=YAML_REPORT.replace('name: prod-eu', 'name: other'))
        errors = self.oracle()
        self.assertIn('Filename timestamp is outside the agent run', errors)
        self.assertIn('YAML cluster.name does not match the target', errors)

    def test_oracle_preserves_existing_reports_on_repeat(self):
        self.write_pair('.eks-recon-report')
        before = inventory(self.root)
        self.write_pair(DEFAULT_PREFIX)
        self.assertEqual(self.oracle(before), [])
        (self.root / '.eks-recon-report.md').write_text('overwritten', encoding='utf-8')
        self.assertTrue(self.oracle(before))

    def test_oracle_checks_custom_prefix_and_collision(self):
        self.write_pair(CUSTOM_PREFIX)
        self.assertEqual(self.oracle(prefix=CUSTOM_PREFIX), [])
        self.assertTrue(self.oracle(prefix='reports/another'))
        before = inventory(self.root)
        self.assertEqual(self.oracle(before, prefix=CUSTOM_PREFIX, collision=True), [])
        (self.root / (CUSTOM_PREFIX + '.md')).write_text('overwritten', encoding='utf-8')
        self.assertTrue(self.oracle(before, prefix=CUSTOM_PREFIX, collision=True))

    def test_oracle_requires_collision_precondition(self):
        self.assertTrue(self.oracle(collision=True))
        self.assertTrue(self.oracle(prefix=CUSTOM_PREFIX, collision=True))


if __name__ == "__main__":
    unittest.main()
