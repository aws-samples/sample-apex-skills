---
title: "EKS Upgrade Readiness Check"
description: "Deploy an EKS 1.32 cluster with Karpenter v1.0.2 and planted upgrade issues, then run the APEX EKS upgrade-check skill to produce a scored readiness report showing NOT READY status."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/examples/eks-upgrades/in-place-karpenter-check/README.md
format: md
---

:::info[Source]
This page is generated from [examples/eks-upgrades/in-place-karpenter-check/README.md](https://github.com/aws-samples/sample-apex-skills/blob/main/examples/eks-upgrades/in-place-karpenter-check/README.md). Edit the source, not this page.
:::


# Assess Your EKS Cluster Upgrade Readiness with APEX EKS

A hands-on exercise that demonstrates the APEX EKS [Upgrade Check Workflow](../../../steering/workflows/eks-upgrade-check) in practice. Deploy a cluster at EKS 1.32 with planted issues, then run the readiness assessment to produce a scored report identifying blockers before you upgrade.

The upgrade-check workflow uses the [`eks-upgrade-check`](../../../skills/eks-upgrade-check/) skill to assess cluster readiness across 8 areas: version validation, breaking changes, deprecated APIs, add-on compatibility, node readiness, workload risks, AWS Upgrade Insights, and upgrade planning.

## Overview

```
EKS 1.32 → 1.33 (assessment target)
   │
   ├─ Karpenter v1.0.2 (INCOMPATIBLE — requires >= 1.5 for K8s 1.33)
   ├─ Blocking PDB (singleton-app with minAvailable: 1)
   └─ Deprecated endpoints API (RBAC grants watch on endpoints)
   
   ↓ Run /apex:eks-upgrade-check
   
   📊 Readiness Report: NOT READY (score ≤ 59)
      Hard blocker: Karpenter incompatibility
      HIGH: Blocking PDB on singleton-app
      Deprecated: endpoints API usage
```

## What This Demonstrates

This example exercises the **eks-upgrade-check** skill — a read-only assessment that produces a scored readiness report. It does NOT perform the upgrade itself. The skill:

1. Discovers your cluster and determines the target version (1.33)
2. Runs checks across 8 assessment areas
3. Calculates a weighted readiness score (0–100)
4. Identifies hard blockers that cap the score at ≤ 59 (NOT READY)
5. Produces a markdown report with prioritized remediation steps
6. Optionally converts to HTML with `md_to_html.py`

## Planted Issues

| # | Source | What It Does | Assessment Impact |
|---|--------|-------------|-------------------|
| 1 | `karpenter.tf` (Helm v1.0.2) | Deploys Karpenter at v1.0.2 via Terraform | **Hard blocker** — K8s 1.33 requires Karpenter >= 1.5 per the [compatibility matrix](https://karpenter.sh/docs/upgrading/compatibility/). Caps readiness score at ≤ 59. |
| 2 | `manifests/blocking-pdb.yaml` | Single-replica Deployment + PDB with `minAvailable: 1` | **HIGH workload risk** — nodes can never be drained because evicting the only pod violates the PDB. |
| 3 | `manifests/endpoints-watcher.yaml` | RBAC granting watch on the `endpoints` API | **Deprecated API** — the Endpoints API is deprecated in 1.33 in favor of EndpointSlices (`discovery.k8s.io/v1`). |

## Expected Assessment Results

The readiness report should show:

- **Overall Score**: ≤ 59 (NOT READY)
- **Hard Blocker Override**: Karpenter 1.0.2 incompatible with K8s 1.33
- **Add-on Compatibility**: Karpenter marked INCOMPATIBLE
- **Workload Risks**: Blocking PDB on `singleton-app` (HIGH severity)
- **Deprecated APIs**: `endpoints` API RBAC detected
- **Remediation**: Upgrade Karpenter to >= 1.5, fix PDB (scale replicas or use maxUnavailable), migrate to EndpointSlices

## Prerequisites

- AWS account with EKS permissions
- Terraform >= 1.5.7
- kubectl
- AWS CLI v2
- One of:
  - [Claude Code](https://claude.ai/code)
  - [Kiro IDE](https://kiro.dev/downloads/) or [Kiro CLI](https://kiro.dev/docs/cli/installation/)

## Setup and Deploy

The deploy script handles: APEX setup for your tool, Terraform deployment of the base cluster, and planting upgrade issues.

Run from this directory (`examples/eks-upgrades/in-place-karpenter-check/`):

```bash
chmod +x ./scripts/deploy.sh
./scripts/deploy.sh
```

**What it does:**

1. **APEX setup** — asks which tool (Claude Code or Kiro), symlinks skills and commands
2. **Deployment name** — asks for a suffix (default: `check`), cluster will be `ex-karpenter-<suffix>`
3. **Terraform apply** — deploys EKS 1.32 with Karpenter v1.0.2 on Fargate from `examples/infrastructure/karpenter/`
4. **Karpenter resources** — applies EC2NodeClass + NodePool, scales inflate to 3 replicas
5. **Plant issues** — applies blocking PDB and deprecated endpoints RBAC

## Run the Upgrade Check

<details>
<summary><strong>Claude Code</strong></summary>

Open Claude Code from the repo root (so Claude doesn't read this README):

```bash
cd ../../..
claude
```

Then use the slash command:

```
/apex:eks-upgrade-check
```

Or just ask: **"Is my cluster ready to upgrade to 1.33?"**

</details>

<details>
<summary><strong>Kiro CLI</strong></summary>

```bash
cd ../../..
kiro-cli chat
```

Then ask: **"Is my cluster ready to upgrade to 1.33?"**

</details>

## Walkthrough

<details>
<summary><strong>Claude Code</strong></summary>

| Step | Screenshot |
|------|-----------|
| Skill triggers on upgrade question | ![Skill trigger](pathname:///sample-apex-skills/examples/eks-upgrades/in-place-karpenter-check/static/cc/01-skill-trigger.png) |
| Discovers clusters in your region | ![Cluster discovery](pathname:///sample-apex-skills/examples/eks-upgrades/in-place-karpenter-check/static/cc/02-cluster-discovery.png) |
| Shows cluster summary table | ![Cluster summary](pathname:///sample-apex-skills/examples/eks-upgrades/in-place-karpenter-check/static/cc/03-cluster-summary.png) |
| Assessment result with score | ![Assessment result](pathname:///sample-apex-skills/examples/eks-upgrades/in-place-karpenter-check/static/cc/04-assessment-result.png) |
| HTML report view | ![HTML report](pathname:///sample-apex-skills/examples/eks-upgrades/in-place-karpenter-check/static/cc/05-html-report.png) |

The assessment correctly identified all 3 planted issues:

1. **Karpenter v1.0.2 incompatible** — hard blocker, score capped at 59%
2. **Blocking PDB on singleton-app** — drain-blocking PDB flagged under workload risks
3. **Endpoints API deprecation** — detected as a behavioral change for 1.33

Full sample output: [`sample-report.md`](static/cc/sample-report) | [`sample-report.html`](pathname:///sample-apex-skills/examples/eks-upgrades/in-place-karpenter-check/static/cc/sample-report.html)

<iframe src="/sample-apex-skills/examples/eks-upgrades/in-place-karpenter-check/static/cc/sample-report.html" width="100%" height="600px" style={{border:"1px solid var(--ifm-color-emphasis-300)", borderRadius:"8px"}}></iframe>


</details>

<details>
<summary><strong>Kiro</strong></summary>

| Step | Screenshot |
|------|-----------|
| Discovers clusters and asks which to assess | ![Cluster discovery](pathname:///sample-apex-skills/examples/eks-upgrades/in-place-karpenter-check/static/kiro/01-cluster-discovery.png) |
| Compiles findings summary | ![Findings summary](pathname:///sample-apex-skills/examples/eks-upgrades/in-place-karpenter-check/static/kiro/02-findings-summary.png) |
| Assessment result with score | ![Assessment result](pathname:///sample-apex-skills/examples/eks-upgrades/in-place-karpenter-check/static/kiro/03-assessment-result.png) |
| HTML report view | ![HTML report](pathname:///sample-apex-skills/examples/eks-upgrades/in-place-karpenter-check/static/kiro/04-html-report.png) |

The assessment correctly identified all 3 planted issues:

1. **Karpenter v1.0.2 incompatible** — hard blocker, score capped at 47%
2. **Drain-blocking PDB on singleton-app** — flagged under workload risks
3. **Single-replica deployment** — singleton-app flagged as availability risk

Full sample output: [`sample-report.md`](static/kiro/sample-report) | [`sample-report.html`](pathname:///sample-apex-skills/examples/eks-upgrades/in-place-karpenter-check/static/kiro/sample-report.html)

<iframe src="/sample-apex-skills/examples/eks-upgrades/in-place-karpenter-check/static/kiro/sample-report.html" width="100%" height="600px" style={{border:"1px solid var(--ifm-color-emphasis-300)", borderRadius:"8px"}}></iframe>


</details>

## Expected Outcome

By the end of this exercise, you should have:

1. **A readiness report** — markdown file with scored assessment across 8 areas
2. **Hard blocker identified** — Karpenter v1.0.2 flagged as incompatible with K8s 1.33
3. **Workload risks flagged** — blocking PDB detected with remediation guidance
4. **Deprecated API found** — endpoints RBAC usage identified
5. **NOT READY verdict** — score capped at ≤ 59 due to the Karpenter hard blocker
6. **Prioritized remediation** — ordered list of fixes before upgrade can proceed

## Cleanup

```bash
chmod +x ./scripts/destroy.sh
./scripts/destroy.sh
```

The destroy script: deletes planted manifests, terminates Karpenter EC2 instances, removes Karpenter K8s resources, and runs `terraform destroy`.

## Further Reading

- [APEX EKS Upgrade Check Workflow](../../../steering/workflows/eks-upgrade-check)
- [EKS Upgrade Check Skill](../../../skills/eks-upgrade-check/)
  - [Version Validation Reference](../../../skills/eks-upgrade-check/references/version-validation)
  - [Add-on Compatibility Reference](../../../skills/eks-upgrade-check/references/addon-compatibility)
  - [Workload Risks Reference](../../../skills/eks-upgrade-check/references/workload-risks)
  - [Report Generation Reference](../../../skills/eks-upgrade-check/references/report-generation)
- [Karpenter Compatibility Matrix](https://karpenter.sh/docs/upgrading/compatibility/)
- [EKS Version Release Notes](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html)
