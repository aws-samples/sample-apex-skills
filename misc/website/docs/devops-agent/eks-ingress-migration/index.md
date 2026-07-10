---
title: "eks-ingress-migration"
description: "EKS ingress migration assessment — discovers NGINX/Ingress estate, scores migration difficulty 0-100 with re-architecture gate, and generates per-cluster markdown reports for Gateway API, ALB Controller, or ATX migration paths."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-ingress-migration/SKILL.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-ingress-migration/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-ingress-migration/SKILL.md). Edit the source, not this page.
:::


# EKS Ingress Migration — DevOps Agent Port

> This skill runs fully autonomously within an AWS DevOps Agent Space — no interactive prompts, no hard-stops, no user confirmation gates. It proceeds through discovery and assessment to completion without pausing.

## Overview

This skill assesses your live EKS cluster's current Ingress architecture and evaluates migration options. It discovers what ingress controllers are running, maps the routing topology, identifies risks, and presents the findings so your team can decide the best migration path.

**This is an assessment tool, not a decision-maker.** The skill presents findings and options — the migration strategy and readiness decision belongs to the user's DevOps team.

**Migration options assessed:**

| Option | Status | Notes |
|--------|--------|-------|
| Gateway API (HTTPRoute + Gateway) | Assessed | Official Kubernetes successor to Ingress. AWS LB Controller supports it (L7 v2.14+, L4 v2.13+; built-in on EKS Auto Mode). |
| AWS Load Balancer Controller (ALB Ingress) | Assessed | Stay on Ingress API but swap NGINX to ALB. Gets WAF, Cognito, Shield. |
| AWS Transform (ATX) — Automated | Included | TD included. For customers with ATX access — fully automated manifest rewriting. |

## Workflow

```
Pre-flight → Assess (7 sections) → Markdown Report
```

1. **Pre-flight** — Discover cluster, validate permissions, verify Kubernetes API connectivity
2. **Assessment** — Run 7 sections, collect findings and score each by Impact (1-5)
3. **Markdown Report** — Generate per-cluster markdown report with Migration Difficulty Score

## What Gets Assessed

| Area | Key Checks |
|------|------------|
| Ingress Discovery | Controllers, **versions/EOL/CVE**, IngressClass, inventory, **EKS Auto Mode** detection |
| Ingress Resource Analysis | Annotations, path rules, TLS, backends — conversion complexity |
| DNS & Certificates | external-dns, cert-manager, ACM — Gateway API source support |
| Traffic & Routing | Routing patterns, advanced features, mapping to HTTPRoute |
| Migration Risk | Downtime risk, feature gaps, rollback plan |

## Reference Files

Before executing checks for any section, read the corresponding reference file from the `references/` directory.

| User Request | Reference File |
|---|---|
| Full migration assessment | ALL files in order EXCEPT: `porting-notes.md` (maintainer-only, excluded from upload zip) |
| What ingress controllers do I have? | `references/ingress-discovery.md` |
| Analyze my Ingress resources | `references/ingress-resources.md` |
| DNS / certs / TLS | `references/dns-certificates.md` |
| Routing complexity | `references/traffic-routing.md` |
| Migration risks | `references/migration-risk.md` |
| Migration plan | `references/migration-plan.md` |
| Generate report | `references/report-generation.md` |
| Gateway API migration path / prerequisites | `references/gateway-api.md` |
| ALB Controller migration path | `references/alb-migration.md` |
| AWS Transform (ATX) automated path | `references/atx-guide.md` |

## Prerequisites

1. **AWS IAM permissions** — see `references/iam-policy.json` for the minimum policy
2. **Kubernetes RBAC** — the agent identity needs:
   - `get`/`list` on `ingresses`, `ingressclasses` (networking.k8s.io/v1)
   - `get`/`list` on `deployments`, `daemonsets`, `services`, `pods` (apps/v1, v1)
   - `get`/`list` on `nodes` (v1)
   - `get`/`list` on `gateways`, `httproutes`, `gatewayclasses`, `grpcroutes` (gateway.networking.k8s.io/v1) — if CRDs installed
   - `get`/`list` on `configmaps` (v1) — ingress controller configuration discovery
   - `get`/`list` on `serviceaccounts` (v1) — IRSA verification for DNS/cert management
   - `get`/`list` on `endpoints` (v1), `endpointslices` (discovery.k8s.io/v1) — backend health verification
   - `get`/`list` on `clusterissuers`, `issuers` (cert-manager.io/v1) — if CRDs installed
   - `get`/`list` on `customresourcedefinitions` (apiextensions.k8s.io/v1) — CRD detection

## Assessment Workflow

### Input

The user provides an **AWS Account ID** (12-digit number). The skill discovers all EKS clusters across regions and assesses each one.

If the user provides a cluster name instead, skip discovery and assess that single cluster.

### Step 0: Pre-flight

**Action 1 — Verify account access**

```
aws sts get-caller-identity --output json
```

Confirm the account ID matches what the user provided.

**Action 2 — Discover all EKS clusters across regions**

Enumerate the account's enabled regions, then scan each for clusters:

```
aws ec2 describe-regions --query 'Regions[].RegionName' --output text
```

For each region:
```
aws eks list-clusters --region <region> --output json
```

Compile a discovery table:

| # | Cluster | Region | Version | Status |
|---|---------|--------|---------|--------|
| 1 | cluster-a | ap-southeast-1 | 1.29 | ACTIVE |
| 2 | cluster-b | us-east-1 | 1.28 | ACTIVE |

- If **0 clusters found** — produce an Assessment Error report (see error contract below).
- If **1 cluster found** — proceed with that cluster automatically.
- If **multiple clusters found** — assess ALL clusters. Produce one report file per cluster (`EKS-Ingress-Migration-<cluster>-<YYYY-MM-DD>.md`). Additionally write a discovery summary file `EKS-Ingress-Migration-Summary-<YYYY-MM-DD>.md` containing the discovery table and per-cluster score/band (or ERROR for clusters where assessment failed).

**Action 3 — For each discovered cluster, describe it**

```
aws eks describe-cluster --name <cluster> --region <region> --output json
```

**Action 4 — Validate permissions (per cluster)**

| Check Command | Required IAM Permission |
|---------------|------------------------|
| `aws eks list-addons --cluster-name <cluster> --region <region>` | `eks:ListAddons` |
| List Ingress resources (networking.k8s.io/v1) | K8s RBAC: `get`/`list` on `ingresses` |
| List IngressClass resources (networking.k8s.io/v1) | K8s RBAC: `get`/`list` on `ingressclasses` |
| List Deployments (apps/v1, namespace kube-system) | K8s RBAC: `get`/`list` on `deployments` |

**Optional permissions** (degrades gracefully if missing):

| Check Command | Required Permission | If Missing |
|---------------|---------------------|------------|
| `aws acm list-certificates --region <region>` | `acm:ListCertificates` | Mark 4.3 UNKNOWN |
| `aws route53 list-hosted-zones` | `route53:ListHostedZones` | Mark 4.1 UNKNOWN |
| `aws iam get-role` | `iam:GetRole` | Mark UNKNOWN |

**Action 5 — Verify Kubernetes API connectivity**

Verify Kubernetes API connectivity by listing nodes. If nodes cannot be listed, produce an Assessment Error report for this cluster (see error contract below) and continue to the next cluster if assessing multiple.

**Action 6 — Cluster health gate (read-only) — REQUIRED before assessing**

An assessment of an unhealthy cluster is misleading. Verify, read-only:
1. **Nodes Ready:** Check node status — flag any not `Ready` (Auto Mode may have 0 nodes until a workload schedules; note that separately).
2. **Ingress controllers healthy:** for each controller Deployment, confirm `availableReplicas > 0` and no pods in `ImagePullBackOff` / `ErrImagePull` / `CrashLoopBackOff`. **If a controller itself is unhealthy, surface it as the first finding** — its routing claims cannot be trusted.
3. **Egress sanity (if pods can't pull):** cluster-wide `ImagePullBackOff` usually means broken node egress. Optionally inspect the node subnets' route table for a `blackhole` default route (deleted NAT gateway) via `aws ec2 describe-route-tables`. Report it as an environment caveat — do not attempt to fix it (read-only).

**Action 7 — Detect EKS Auto Mode (read-only)**

```
aws eks describe-cluster --name <cluster> --query 'cluster.computeConfig' --output json
```
Auto Mode is enabled when `computeConfig.enabled = true`. On Auto Mode, recognize the **managed** load-balancing IngressClass `eks.amazonaws.com/alb` (parameters `apiGroup: eks.amazonaws.com`, `kind: IngressClassParams`) and `loadBalancerClass: eks.amazonaws.com/nlb` — these are built-in, not a self-managed AWS LB Controller. Record Auto Mode status in Current Configuration; it changes Migration Options guidance (ALB path needs no LBC install).

### Steps 1-7: Run Assessment (per cluster)

For each cluster, run the full assessment:
1. Read each steering file in order
2. Execute the checks
3. Score each item by Impact (1-5) per the Impact Indicator
4. **Collect topology data** — Ingress resources, controllers, backend services

## Rating Rubric

Score every finding by **Impact 1-5** using the **Impact Indicator** rubric (defined in the report, before Assessment Summary). Weigh security/reputation, business/revenue, and the nature & effort to remediate.

| Impact | Band | Meaning |
|--------|------|---------|
| 1-2 | Low | Hardening gap / best-practice; no revenue/downtime impact; hours-1 day, single-scope. |
| 3-4 | Medium | Limited-reputation breach or short-downtime revenue loss; tech debt hard to reverse; area/single-cluster scope. |
| 5 | High | Major/reputational breach or prolonged downtime; needs re-design/re-architecture (may need approval). |
| Unknown | - | Cannot determine — state what to check and why. |

> Easy-to-deploy prerequisites (e.g. installing CRDs) are **Low** even if they block a path. Never use GREEN/AMBER/RED.

## Migration Difficulty Score

Every report leads with a single **Migration Difficulty Score (0-100)** plus a separate **Re-architecture Gate** badge:

- **High score = little change (easy); low score = much change (hard).** It is a relative *effort index* from the per-finding Impact ratings — not a manday estimate (we cannot know who implements).
- **Deduction model, no artificial cap.** Start at 100, subtract weighted points per finding (Impact 5->10, 4->6, 3->4, 2->2, 1->1), cap per category, `score = max(0, 100 - sum)`. The score is **never** locked at a ceiling — a single hard route no longer flattens it.
- **Re-architecture Gate (separate, informational):** routes needing redesign/approval (Lua/snippet/mirror, TLS passthrough/mTLS, cross-namespace ownership) are reported as a gate badge next to the score — they do not overwrite the number. Score = "how much work?"; gate = "does anything need a redesign decision?".
- **Clean routes count at 0 effort:** an Ingress already on the ALB controller, Gateway API, or a supported 3rd-party controller contributes 0 and is excluded from the Volume work-count, so "X of N already done" is visible and lifts the score.
- **Feature-gap is tiered:** features with no native ALB annotation but a standard workaround — **CORS** (app middleware), **IP allowlist** (Security Group / WAF), **rate-limit** (WAF) — default to **Impact 2** (performance/hardening) or **3** (business-logic-entangled). When the migration-path reference (e.g. alb-migration.md) rates a specific conversion as High, use that rating instead. Only no-workaround features (Lua/snippet/mirror/regex-capture) score heavy.
- Bands: 90-100 TRIVIAL, 80-89 EASY, 70-79 MODERATE, 60-69 HARD, 0-59 VERY HARD.
- The score is **derived from the findings, not a separate judgement** — it never overrides the team's choice of migration path. Full deterministic algorithm, category weights, gate logic, tiering rules, and the mandatory Score Breakdown table live in `references/report-generation.md` Step 1.

## Report Output

Write markdown report to working directory. Filename: `EKS-Ingress-Migration-<cluster>-<YYYY-MM-DD>.md`

## Report Structure

| Section | Contains |
|---------|----------|
| Overview | Cluster info table, Migration Difficulty Score + Score Breakdown, Executive Summary, Impact Indicator |
| Assessment Summary | Assessment Summary table (Impact-ordered), Current Configuration, Ingress Discovery |
| Routing Topology | Routing table (per-route line items + Impact), Traffic & Routing |
| Migration Approach | Migration Options (Gateway API, ALB, ATX — consistent panels), Blockers, Recommendations |
| Analysis | Ingress Resource Analysis, DNS & Certificates Analysis, Migration Risk |

## Error Contract

If a critical error prevents assessment (no clusters found, insufficient permissions, API unreachable), produce an Assessment Error report:

```markdown
## Assessment Error — EKS Ingress Migration

**Error:** <description>
**Impact:** <what could not be assessed>
**Resolution:** <specific IAM actions or configuration needed>
**Partial results:** <any data gathered before failure>
```

When assessing multiple clusters and one fails, emit the error report for that cluster and continue assessing the remaining clusters.

Write the error report to the per-cluster file: `EKS-Ingress-Migration-<cluster>-<YYYY-MM-DD>.md`. The Summary file shows ERROR in the score/band column for this cluster.
