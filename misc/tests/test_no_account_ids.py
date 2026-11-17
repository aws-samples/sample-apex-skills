#!/usr/bin/env python3
"""No AWS account id in misc/evals/: the scan in
misc/evals/scripts/check_hygiene.py (account_ids(), with its allowed values
and reasons), which the CI hygiene job runs. Needs a git checkout.

Run directly with:

    python3 misc/tests/test_no_account_ids.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "evals", "scripts"))

import check_hygiene  # noqa: E402


class NoAccountIdTests(unittest.TestCase):
    def test_no_account_id_under_misc_evals(self):
        found = check_hygiene.account_ids()
        self.assertEqual(found, [], "12-digit account ids in misc/evals/ (read the "
                         "account at run time instead):\n" + "\n".join(found))


if __name__ == "__main__":
    unittest.main()
