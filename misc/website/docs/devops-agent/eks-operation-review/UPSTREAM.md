---
title: "Upstream Provenance"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-operation-review/UPSTREAM.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-operation-review/UPSTREAM.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-operation-review/UPSTREAM.md). Edit the source, not this page.
:::

# Upstream Provenance

This DevOps Agent port is **vendored** from an upstream repo. Do not edit files here directly — your changes will be overwritten by the next sync.

| Field | Value |
|---|---|
| Source repo | https://github.com/aws-samples/sample-eks-operation-review-skill.git |
| Source path | `DevOpsAgent/` |
| Refresh command | `./misc/sync-eks-operation-review-skill.sh` |
| License | See `skills/eks-operation-review/LICENSE` (shared with the CC skill) |

## Local modifications applied at sync time

1. **`DevOpsAgent/README.md` → `references/porting-notes.md`** — the README's "Differences" section serves as porting documentation. Renamed so setup.sh excludes it from the upload zip (matching the eks-upgrade-check/eks-recon/eks-security pattern).

Unlike the eks-upgrade-check port, op-review's upstream `DevOpsAgent/` ships **no `assets/` directory and no `iam-policy.json`**, so those steps are skipped. Everything else is byte-for-byte from upstream's `DevOpsAgent/` directory.

## To propose changes

Open a PR against the upstream repo:
https://github.com/aws-samples/sample-eks-operation-review-skill.git

Then re-run the sync script here.
