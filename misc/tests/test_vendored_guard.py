#!/usr/bin/env python3
"""Tests for .github/scripts/vendored-guard.sh.

Each case builds a small git repo with a vendored folder (UPSTREAM.md), its
website mirror, a folder marked only by .vendor-sha and a plain skill, makes
one change on a branch, and runs the guard with the pull request fields the
workflow passes.

Run directly with:

    python3 misc/tests/test_vendored_guard.py

VENDORED_GUARD_SCRIPT points the tests at another copy of the script.
"""

import os
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.environ.get(
    "VENDORED_GUARD_SCRIPT", os.path.join(REPO_ROOT, ".github", "scripts", "vendored-guard.sh")
)

FILES = {
    "skills/eks-operation-review/UPSTREAM.md": "vendored\n",
    "skills/eks-operation-review/SKILL.md": "one\n",
    "misc/website/docs/skills/eks/eks-operation-review/UPSTREAM.md": "vendored\n",
    "misc/website/docs/skills/eks/eks-operation-review/index.md": "one\n",
    "skills/terraform-skill/.vendor-sha": "abc\n",
    "skills/terraform-skill/SKILL.md": "one\n",
    "skills/eks-recon/SKILL.md": "one\n",
}

PR = {
    "PR_AUTHOR": "someone",
    "HEAD_REF": "fix-docs",
    "HEAD_REPO": "aws-samples/sample-apex-skills",
    "BASE_REPO": "aws-samples/sample-apex-skills",
    "HAS_SYNC_LABEL": "false",
}

BOT = {"PR_AUTHOR": "github-actions[bot]", "HEAD_REF": "chore/vendor-update-terraform-skill"}


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class VendoredGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "user.name", "test")
        for path, text in FILES.items():
            self.write(path, text)
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "base")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, text):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)

    def run_guard(self, path, **fields):
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, check=True, capture_output=True, text=True
        ).stdout.strip()
        git(self.repo, "checkout", "-q", "-b", "pr")
        self.write(path, "two\n")
        git(self.repo, "commit", "-q", "-am", "change")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, check=True, capture_output=True, text=True
        ).stdout.strip()
        env = dict(os.environ, BASE_SHA=base, HEAD_SHA=head, **{**PR, **fields})
        return subprocess.run(
            ["bash", SCRIPT], cwd=self.repo, env=env, capture_output=True, text=True
        )

    def assert_fails_on(self, result, path, marker):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(f"::error file={path}::", result.stdout)
        self.assertIn(f"(see {marker})", result.stdout)
        self.assertIn("issues/189", result.stdout)

    def test_vendored_source_file_fails(self):
        result = self.run_guard("skills/eks-operation-review/SKILL.md")
        self.assert_fails_on(
            result, "skills/eks-operation-review/SKILL.md", "skills/eks-operation-review/UPSTREAM.md"
        )

    def test_mirror_file_fails(self):
        path = "misc/website/docs/skills/eks/eks-operation-review/index.md"
        result = self.run_guard(path)
        self.assert_fails_on(
            result, path, "misc/website/docs/skills/eks/eks-operation-review/UPSTREAM.md"
        )

    def test_vendor_sha_only_folder_fails(self):
        result = self.run_guard("skills/terraform-skill/SKILL.md")
        self.assert_fails_on(
            result, "skills/terraform-skill/SKILL.md", "skills/terraform-skill/.vendor-sha"
        )

    def test_non_vendored_change_passes(self):
        result = self.run_guard("skills/eks-recon/SKILL.md")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_bot_vendor_update_branch_passes(self):
        result = self.run_guard("skills/terraform-skill/SKILL.md", **BOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_bot_author_from_fork_fails(self):
        result = self.run_guard(
            "skills/terraform-skill/SKILL.md", **BOT, HEAD_REPO="someone/sample-apex-skills"
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_vendor_update_branch_by_a_person_fails(self):
        result = self.run_guard(
            "skills/terraform-skill/SKILL.md", HEAD_REF="chore/vendor-update-terraform-skill"
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_vendor_sync_label_passes(self):
        result = self.run_guard("skills/eks-operation-review/SKILL.md", HAS_SYNC_LABEL="true")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
