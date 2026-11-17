#!/usr/bin/env python3
"""No AWS account id in misc/evals/.

Every git-tracked file under misc/evals/ is scanned for a 12-digit number,
the shape of an AWS account id. Only the values below pass, each with its
reason: a real account belongs in the reader's own settings (the eval
runner reads it at run time, misc/evals/README.md Step 0), never in the repo.

Run directly with:

    python3 misc/tests/test_no_account_ids.py
"""

import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCOPE = "misc/evals"
ACCOUNT_RE = re.compile(rb"\b[0-9]{12}\b")

# Allowed anywhere under SCOPE.
ALLOWED = {
    b"123456789012": "the example account id in the AWS documentation",
    b"111122223333": "the example account id in the AWS IAM documentation",
    b"602401143452": "a public AWS service account: the Amazon EKS add-on "
                     "image registry in us-west-2 (inside an image name)",
}
# Fixture placeholders, allowed only in the file that uses them.
FIXTURE_IDS = {
    b"111111111111": ("misc/evals/eks-cost-intelligence/evals.json", "a made-up caller account"),
    b"222222222222": ("misc/evals/eks-cost-intelligence/evals.json", "a made-up payer account"),
    b"111222333444": ("misc/evals/eks-upgrade-check/evals.json", "a made-up cluster account"),
    b"555666777888": ("misc/evals/eks-upgrade-check/evals.json", "a made-up cluster account"),
    b"987654321098": ("misc/evals/eks-upgrade-check/evals.json", "a made-up cluster account"),
    b"999888777666": ("misc/evals/eks-upgrade-check/evals.json", "a made-up cluster account"),
    b"999900001111": ("misc/evals/eks-recon/files/eval-5/prior.yaml", "a made-up cluster account"),
}


def account_ids(repo: Path) -> list[str]:
    """Each 12-digit number under SCOPE that is not allowed, as path:line: value."""
    files = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", "--", SCOPE],
        capture_output=True, check=True,
    ).stdout.split(b"\0")
    found = []
    for rel in filter(None, files):
        path = rel.decode()
        try:
            data = (repo / path).read_bytes()
        except FileNotFoundError:  # deleted in the work tree
            continue
        for n, line in enumerate(data.splitlines(), 1):
            for value in ACCOUNT_RE.findall(line):
                if value in ALLOWED or (value in FIXTURE_IDS and FIXTURE_IDS[value][0] == path):
                    continue
                found.append(f"{path}:{n}: {value.decode()}")
    return found


class NoAccountIdTests(unittest.TestCase):
    def test_no_account_id_under_misc_evals(self):
        found = account_ids(REPO)
        self.assertEqual(found, [], "12-digit account ids in misc/evals/ (read the "
                         "account at run time instead):\n" + "\n".join(found))


if __name__ == "__main__":
    unittest.main()
