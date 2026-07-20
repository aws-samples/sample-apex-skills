# Upstream Provenance

This DevOps Agent port is **vendored** from an upstream repo. Do not edit files here directly — your changes will be overwritten by the next sync.

| Field | Value |
|---|---|
| Source repo | https://github.com/aws-samples/sample-eks-upgrade-skill.git |
| Source path | `DevOpsAgent/` |
| Refresh command | `./misc/sync-eks-upgrade-skill.sh` |
| License | See `skills/eks-upgrade-check/LICENSE` (shared with the CC skill) |

## Local modifications applied at sync time

1. **`DevOpsAgent/README.md` → `references/porting-notes.md`** — the README's "Differences" section serves as porting documentation. Renamed so setup.sh excludes it from the upload zip (matching the eks-recon/eks-security pattern).
2. **`iam-policy.json` extracted from upstream root README** — the IAM policy block is pulled out into `references/iam-policy.json` so every active port ships its own policy file (per the devops-agent README contract).

Everything else is byte-for-byte from upstream's `DevOpsAgent/` directory.

## To propose changes

Open a PR against the upstream repo:
https://github.com/aws-samples/sample-eks-upgrade-skill.git

Then re-run the sync script here.
