#!/usr/bin/env python3
"""Tests for .github/scripts/vendored-guard.sh.

Each case builds a small git repo with vendored folders (UPSTREAM.md, a
website mirror, a folder marked only by .vendor-sha and one with both
markers) and a plain skill, makes a change on a branch, and runs the guard
with the pull request fields the workflow passes.

Run directly with:

    python3 misc/tests/test_vendored_guard.py
"""

import os
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPO_ROOT, ".github", "scripts", "vendored-guard.sh")

FILES = {
    "skills/eks-operation-review/UPSTREAM.md": "vendored\n",
    "skills/eks-operation-review/SKILL.md": "one\n",
    "misc/website/docs/skills/eks/eks-operation-review/UPSTREAM.md": "vendored\n",
    "misc/website/docs/skills/eks/eks-operation-review/index.md": "one\n",
    "skills/terraform-skill/.vendor-sha": "abc\n",
    "skills/terraform-skill/SKILL.md": "one\n",
    "skills/eks-upgrade-check/UPSTREAM.md": "vendored\n",
    "skills/eks-upgrade-check/.vendor-sha": "abc\n",
    "skills/eks-upgrade-check/SKILL.md": "one\n",
    "skills/eks-recon/SKILL.md": "one\n",
}

PR = {
    "PR_AUTHOR": "someone",
    "HEAD_REF": "fix-docs",
    "HEAD_REPO": "aws-samples/sample-apex-skills",
    "BASE_REPO": "aws-samples/sample-apex-skills",
    "HAS_VENDOR_LABEL": "false",
}

BOT = {"PR_AUTHOR": "github-actions[bot]", "HEAD_REF": "chore/vendor-update-terraform-skill"}


class VendoredGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "test")
        for path, text in FILES.items():
            self.write(path, text)
        self.git("add", ".")
        self.git("commit", "-q", "-m", "base")
        self.base = self.rev("HEAD")
        self.git("checkout", "-q", "-b", "pr")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)

    def rev(self, ref):
        return subprocess.run(
            ["git", "rev-parse", ref], cwd=self.repo, check=True, capture_output=True, text=True
        ).stdout.strip()

    def write(self, path, text):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")

    def guard(self, base=None, **fields):
        env = dict(os.environ, BASE_SHA=base or self.base, HEAD_SHA=self.rev("HEAD"), **{**PR, **fields})
        return subprocess.run(["bash", SCRIPT], cwd=self.repo, env=env, capture_output=True, text=True)

    def run_guard(self, path, **fields):
        self.write(path, "two\n")
        self.commit()
        return self.guard(**fields)

    def assert_fails_on(self, result, path, marker):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(f"::error file={path}::", result.stdout)
        self.assertIn(f"(see {marker})", result.stdout)
        self.assertIn("issues/189", result.stdout)

    def assert_passes(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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

    def test_both_markers_points_at_upstream_md(self):
        result = self.run_guard("skills/eks-upgrade-check/SKILL.md")
        self.assert_fails_on(
            result, "skills/eks-upgrade-check/SKILL.md", "skills/eks-upgrade-check/UPSTREAM.md"
        )

    def test_non_vendored_change_passes(self):
        self.assert_passes(self.run_guard("skills/eks-recon/SKILL.md"))

    def test_bot_vendor_update_branch_passes(self):
        self.assert_passes(self.run_guard("skills/terraform-skill/SKILL.md", **BOT))

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

    def test_vendor_update_label_passes(self):
        self.assert_passes(self.run_guard("skills/eks-operation-review/SKILL.md", HAS_VENDOR_LABEL="true"))

    def test_rename_out_of_vendored_folder_fails(self):
        self.git("mv", "skills/eks-operation-review/SKILL.md", "skills/eks-recon/moved.md")
        self.commit()
        result = self.guard()
        self.assert_fails_on(
            result, "skills/eks-operation-review/SKILL.md", "skills/eks-operation-review/UPSTREAM.md"
        )

    def test_marker_deleted_with_edit_fails(self):
        os.remove(os.path.join(self.repo, "skills/eks-operation-review/UPSTREAM.md"))
        self.write("skills/eks-operation-review/SKILL.md", "two\n")
        self.commit()
        result = self.guard()
        self.assert_fails_on(
            result, "skills/eks-operation-review/SKILL.md", "skills/eks-operation-review/UPSTREAM.md"
        )

    def test_main_sync_after_fork_point_not_counted(self):
        self.write("skills/eks-recon/SKILL.md", "two\n")
        self.commit()
        self.git("checkout", "-q", "main")
        self.write("skills/eks-operation-review/SKILL.md", "synced\n")
        self.commit()
        main_tip = self.rev("HEAD")
        self.git("checkout", "-q", "pr")
        self.assert_passes(self.guard(base=main_tip))

    def test_sibling_folder_with_shared_prefix_passes(self):
        self.write("skills/eks-operation-review-extra/SKILL.md", "new\n")
        self.commit()
        self.assert_passes(self.guard())

    def test_unusual_file_names_fail(self):
        for name in ["notes\u2013draft.md", "a\tb.md", "a\\b.md", 'a"b.md', "a\nb.md"]:
            with self.subTest(name=repr(name)):
                path = f"skills/eks-operation-review/{name}"
                self.write(path, "new\n")
                self.commit()
                result = self.guard()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(f"::error file={path}::", result.stdout)
                self.git("reset", "-q", "--hard", self.base)

    def test_bad_base_sha_fails(self):
        self.write("skills/eks-recon/SKILL.md", "two\n")
        self.commit()
        result = self.guard(base="0" * 40)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
