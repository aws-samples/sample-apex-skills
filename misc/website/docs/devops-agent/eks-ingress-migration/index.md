---
title: "eks-ingress-migration"
description: "Assess a live EKS cluster's NGINX/Ingress estate and plan migration to Gateway API, the AWS Load Balancer Controller (ALB Ingress), or AWS Transform (ATX). Discovers ingress controllers and routes, scores migration difficulty 0–100 with a separate re-architecture gate, and generates per-cluster reports plus ready-to-apply manifests. Use when someone asks \"how hard is it to move off nginx ingress?\", \"assess my ingress migration\", \"migrate nginx to ALB or Gateway API\", \"ingress migration audit\", or \"nginx ingress retirement plan\". Not for upgrade readiness (eks-upgrade-check), operational audits (eks-operation-review), general cluster discovery (eks-recon), or general ingress configuration advice (eks-best-practices)."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-ingress-migration/SKILL.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-ingress-migration/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-ingress-migration/SKILL.md). Edit the source, not this page.
:::


# EKS Ingress Migration Skill

## Overview

This skill assesses your live EKS cluster's current Ingress architecture and evaluates migration options. It discovers what ingress controllers are running, maps the routing topology, identifies risks, and presents the findings so your team can decide the best migration path.

**This is an assessment tool, not a decision-maker.** The skill presents findings and options — the migration strategy and readiness decision belongs to the user's DevOps team.

**All operations are read-only** — this skill never modifies your cluster. It reports what the migration would require; the cluster owner performs every mutating step.

> **Execution model — autonomous with hard stops.** This skill runs autonomously and does
> NOT pause for interactive input. It proceeds only when the target cluster is unambiguous.
> If a gating criterion in Step 0 is not met, it performs a **HARD STOP**: it does NOT guess,
> auto-select, or partially assess — it emits the structured stop message and ends without
> producing a score. Once Step 0 passes, it runs the assessment, the report, and the export
> materials to completion without pausing.

**Migration options assessed:**

| Option | Status | Notes |
|--------|--------|-------|
| Gateway API (HTTPRoute + Gateway) | ✅ Assessed | Official Kubernetes successor to Ingress. AWS LB Controller supports it (L7 ≥ v2.14, L4 ≥ v2.13.3; built-in on EKS Auto Mode). |
| AWS Load Balancer Controller (ALB Ingress) | ✅ Assessed | Stay on Ingress API but swap NGINX→ALB. Gets WAF, Cognito, Shield. |
| AWS Transform (ATX) — Automated | ✅ Included | TD included. For customers with ATX access — fully automated manifest rewriting. |

## Workflow

```
Pre-flight → Assess (7 sections) → Routing Topology → Markdown Report (inline) → Export Materials (inline)
```

1. **Pre-flight** — Discover cluster, validate permissions
2. **Assessment** — Run 7 sections, collect findings and topology data
3. **Routing Topology** — Compile the collected topology data (nodes, controllers, ingresses, services) into the Routing Topology table and the machine-readable topology artifact
4. **Markdown Report** — Render the report for the assessed cluster inline in the response. It leads with the **Migration Difficulty Score (0–100)** — a deterministic roll-up of the per-finding Impact ratings (high = easy to leave NGINX, low = hard / high business impact). See `references/report-generation.md` Step 1.
5. **Export Materials** — Render ready-to-apply YAML inline, in apply order:
   - `current/` — existing Ingress resources (clean, no status fields)
   - `target/gateway-api/` — Gateway API resources (GatewayClass, Gateway, HTTPRoute) in apply order
   - `target/alb/` — ALB Controller Ingress resources (converted annotations)

**Important:** After assessment completes, proceed directly to report generation and manifest export. Do NOT pause to ask the user — produce all outputs automatically.

## What Gets Assessed

| Area | Key Checks |
|------|------------|
| Ingress Discovery | Controllers, **versions/EOL/CVE**, IngressClass, inventory, **EKS Auto Mode** detection |
| Ingress Resource Analysis | Annotations, path rules, TLS, backends — conversion complexity |
| DNS & Certificates | external-dns, cert-manager, ACM — Gateway API source support |
| Traffic & Routing | Routing patterns, advanced features, mapping to HTTPRoute |
| Migration Risk | Downtime risk, feature gaps, rollback plan |

## Report Structure (6 Section Groups)

The report is one inline markdown document. These six groups are its top-level sections, in this order.

| Section Group | Contains |
|----------|----------|
| Overview | Cluster info table, **Migration Difficulty Score (headline score + Score Breakdown)**, Executive Summary, Impact Indicator (rubric, before Assessment Summary) |
| Assessment Summary | Assessment Summary table (Impact-ordered), Current Configuration, Ingress Discovery |
| Routing Topology | Routing table (per-route line items + Impact), Traffic & Routing |
| Migration Approach | Migration Options (Option 1 Gateway API, Option 2 ALB, Option 3 ATX — consistent panels), Blockers, Recommendations |
| Analysis | Ingress Resource Analysis, DNS & Certificates Analysis, Migration Risk |
| References | Export Materials (generated manifests, rendered inline), AWS Reference Links |

## Reference Files

Before executing checks for any section, read the corresponding reference file from the `references/` directory.

| User Request | Reference File |
|---|---|
| Full migration assessment | ALL files in order (skip gateway-api.md, lbc-migrate-toolkit.md, alb-migration.md, atx-guide.md) |
| What ingress controllers do I have? | `references/ingress-discovery.md` |
| Analyze my Ingress resources | `references/ingress-resources.md` |
| DNS / certs / TLS | `references/dns-certificates.md` |
| Routing complexity | `references/traffic-routing.md` |
| Migration risks | `references/migration-risk.md` |
| Migration plan | `references/migration-plan.md` |
| Generate report | `references/report-generation.md` |
| Gateway API migration path / prerequisites | `references/gateway-api.md` |
| Gateway API automation (LBC Ingress → Gateway API `lbc-migrate` toolkit) | `references/lbc-migrate-toolkit.md` |
| ALB Controller migration path | `references/alb-migration.md` |
| AWS Transform (ATX) automated path | `references/atx-guide.md` |

## Tool Usage Rules

1. **Do NOT begin cluster API calls when this skill is first activated.** Start only when the user's request actually asks for an ingress assessment.
2. **Do NOT hardcode or guess cluster names.** Always discover by listing first.
3. **Do NOT retry a failed API call more than once.**
4. **Always load the relevant reference file before executing checks.**
5. **Only rate based on what was actually observed — never assume.**
6. If a check fails or returns no data, mark UNKNOWN. A read denied by RBAC or IAM is UNKNOWN — never a negative finding (see Degraded Reads below).
7. Every high-impact (4–5) finding must have a specific, actionable recommendation.
8. **Collect topology data during assessment** — every Ingress host, path, backend, controller, namespace, and the nodes (EC2 instances). This feeds the Routing Topology table and the topology artifact.
9. **Do NOT paste raw YAML/config in findings.** Summarize what was found. (Export Materials is the one place full YAML belongs.)
10. **Use tables for all structured data.** No prose lists of facts.
11. **No filler text.** Go straight to content.
12. **Every finding cell: max 2 sentences.**
13. **No ASCII art diagrams.** The Routing Topology table carries the per-route structure.
14. **No ID column in tables.** Remove all "ID" columns.
15. **Multi-value cells:** use `<br>` for line breaks, not commas.
16. **Executive Summary must be bullet points** — precise and comprehensive.
17. **Never execute a mutating command.** Cutover, CRD installs, `lbc-migrate` applies, and cleanup steps appear in the report as instructions for the cluster owner to run — this runtime has no shell and this skill is read-only regardless.

## Skill Files

All relative paths in this skill are relative to **this skill's directory** (the directory containing this `SKILL.md`).

| Path | Contents |
|---|---|
| `references/*.md` | Assessment logic, loaded on demand per the routing table above |
| `assets/samples/nginx/`, `assets/samples/alb/` | Before/after Ingress examples (ATX input and output) |
| `assets/atx/td_ingress-nginx-lbc/` | The AWS Transform Definition and its supporting documents |

There is no `tools/` directory and no report-conversion script — script execution is not
available in this runtime. Reports and manifests are rendered **inline in the response**;
this runtime cannot write files, so never state that output was saved to a path.

## Prerequisites

### Required IAM permissions (Agent Space role)

A ready-to-use policy document is at [`references/iam-policy.json`](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-ingress-migration/references/iam-policy.json) — attach it to your Agent Space execution role. It grants **read-only AWS control-plane access** only. It intentionally does **not** grant `eks:AccessKubernetesApi`: Kubernetes-API authentication comes from the EKS access entry, not from IAM.

| Service | Actions (read-only) | Purpose |
|---------|--------------------|---------|
| **EKS** | `ListClusters`, `DescribeCluster`, `ListAddons`, `DescribeAddon` | Cluster config, Auto Mode detection, add-on inventory |
| **EC2** | `DescribeRegions`, `DescribeInstances`, `DescribeRouteTables`, `DescribeSecurityGroups` | Region discovery, node facts for topology, egress sanity check, IP-allowlist workaround feasibility |
| **ELB** | `elasticloadbalancing:Describe*` | ALB/NLB inventory, target groups and target health (verifying whether a controller still serves traffic) |
| **ACM** | `ListCertificates`, `DescribeCertificate` | TLS certificate inventory for the ALB/Gateway path |
| **Route 53** | `ListHostedZones`, `ListResourceRecordSets` | DNS ownership and cutover feasibility |
| **IAM** | `GetRole`, `ListAttachedRolePolicies`, `ListOpenIDConnectProviders` | Controller IRSA role inspection |

### Kubernetes API access

Cluster reads come from an **EKS access entry** binding the Agent Space role to a cluster-access policy (`devops-agent/setup.sh` associates `AmazonAIOpsAssistantPolicy`); the cluster's `authenticationMode` must include `API`.

> **Do not assume the managed policy's coverage — verify it.** As of 2026-08-30, `AmazonAIOpsAssistantPolicy` is listed among the available cluster-access policies in the EKS reference but its rules are **not enumerated** there, unlike every other access policy on that page ([Review access policy permissions](https://docs.aws.amazon.com/eks/latest/userguide/access-policy-permissions.html)). So the exact API groups it grants are unconfirmed from an authoritative source. This skill therefore treats **every** Kubernetes read as possibly denied and fails closed (below) rather than relying on assumed coverage. To make the outcome deterministic, bind the supplementary read-only ClusterRole in `references/porting-notes.md`, which grants exactly the reads this skill needs, and confirm with `kubectl auth can-i`.

**Secret contents are never read.** TLS posture is inferred from the `secretName` references in `Ingress.spec.tls[]` plus the ACM inventory — the skill needs to know *that* a route terminates TLS from a Kubernetes Secret, never the key material. Do not request or read Secret data.

**These reads are the ones most likely to be denied.** The sibling `eks-recon` port records — unverified against AWS documentation — that the policy grants read-only `get`/`list` on built-in API groups only and no CRD groups. If that holds, each read below returns `403 Forbidden` without a supplementary ClusterRole:

| Read | API group | Needed for |
|---|---|---|
| `GatewayClass`, `Gateway`, `HTTPRoute` | `gateway.networking.k8s.io` | Gateway API adoption state, `gatewayApi` block in the topology artifact |
| `CustomResourceDefinition` | `apiextensions.k8s.io` | Whether Gateway API CRDs are installed, and their version |
| `ValidatingWebhookConfiguration` | `admissionregistration.k8s.io` | The ingress-nginx admission-webhook exposure tri-state (CVE-2025-1974) |
| `TargetGroupBinding` | `elbv2.k8s.aws` | AWS LB Controller route ownership |

See `references/porting-notes.md` for the supplementary ClusterRole that grants them.

### Degraded reads — fail closed, never fail clean

A denied or failed read is **never** evidence of absence:

- **Webhook exposure** — if `ValidatingWebhookConfiguration` or the controller's arguments cannot be read, the tri-state resolves to **Unverified**, which is treated as *exposed* for scoring. Never conclude "not exposed" from a denied read (`references/ingress-discovery.md` §1.4).
- **Gateway API state** — if the CRD or Gateway-resource reads are denied, report Gateway API adoption as **unconfirmed**, never as "not installed" / `crdsInstalled: false`.
- **Everything else** — mark the finding UNKNOWN and state which read was denied and what to grant.

## Assessment Workflow

### Input

The user provides an **AWS Account ID** (12-digit number), a cluster name, or neither. The skill discovers EKS clusters across the account's enabled regions and assesses the unambiguously-identified cluster.

**HARD STOP output format** — whenever a criterion below triggers a hard stop, output exactly this and end the run (produce no score, no report):

```
## Assessment Halted — <one-line reason>

**Criterion not met:** <which check failed>
**What was found:** <observed state>
**To proceed:** <the specific input needed, e.g. re-run naming the cluster + region>
```

### Step 0: Pre-flight

**Action 1 — Verify account access**

Resolve the caller identity. If the user supplied an account ID and it does not match the caller's account → **HARD STOP** (the agent is pointed at a different account than the user believes).

**Action 2 — Discover EKS clusters across regions**

Enumerate the account's enabled regions (EC2 `DescribeRegions`), then scan each with EKS `ListClusters`. Compile a discovery table:

| # | Cluster | Region | Version | Status |
|---|---------|--------|---------|--------|
| 1 | cluster-a | ap-southeast-1 | 1.29 | ACTIVE |
| 2 | cluster-b | us-east-1 | 1.28 | ACTIVE |

Then apply this decision table:

| Condition | Action |
|-----------|--------|
| User named a cluster | Confirm it exists in the discovery table, then proceed. If it does not exist → **HARD STOP**. |
| Exactly one cluster found, none named | Proceed. State which cluster is being assessed. |
| More than one cluster found, none named | **HARD STOP.** Show the discovery table. Do NOT auto-select by first/newest/largest or any other heuristic, and do NOT assess all of them. |
| Zero clusters found | **HARD STOP.** Report that no EKS clusters exist in the account's enabled regions. |

**Action 3 — Describe the selected cluster**

EKS `DescribeCluster`. Record name, version, platform version, region, status, endpoint access, account ID.

> **Account ID hygiene:** the account ID is sensitive. If the report will be shared outside the account, mask or omit it.

If cluster `status` is not `ACTIVE` → **HARD STOP**: a cluster mid-transition or FAILED cannot be assessed reliably.

**Action 4 — Validate permissions**

| Read | Required permission | If denied |
|---------------|------------------------|---|
| EKS `ListAddons` | `eks:ListAddons` | **HARD STOP** — core inventory unavailable |
| Kubernetes `Ingress` (`networking.k8s.io/v1`) | K8s RBAC `get`/`list` on `ingresses` | **HARD STOP** — the estate cannot be enumerated, so no score is defensible |
| Kubernetes `IngressClass` (`networking.k8s.io/v1`) | K8s RBAC `get`/`list` on `ingressclasses` | **HARD STOP** — controller/route binding cannot be established |
| Kubernetes `Deployment` (`apps/v1`, all namespaces) | K8s RBAC `get`/`list` on `deployments` | **HARD STOP** — controller presence/health cannot be established |

**Optional reads** (degrade gracefully — mark UNKNOWN, never absent):

| Read | Required permission | If missing |
|---------------|---------------------|------------|
| ACM `ListCertificates` | `acm:ListCertificates` | Mark 4.3 UNKNOWN |
| Route 53 `ListHostedZones` | `route53:ListHostedZones` | Mark 4.1 UNKNOWN |
| IAM `GetRole` | `iam:GetRole` | Mark UNKNOWN |
| `ValidatingWebhookConfiguration` | K8s RBAC on `admissionregistration.k8s.io` | Webhook tri-state → **Unverified** (treated as exposed) |
| Gateway API resources / CRDs | K8s RBAC on those CRD groups | Gateway API adoption → **unconfirmed** |

**Action 5 — Verify Kubernetes API reachability**

List `Node` (core/v1) for the target cluster. If the Kubernetes API is unreachable — no access entry, `authenticationMode` excludes `API`, or the endpoint is private and unreachable from the Agent Space → **HARD STOP**. Do not fall back to an AWS-control-plane-only assessment: the estate lives in the Kubernetes API, and a control-plane-only view would silently under-report routes.

**Action 6 — Cluster health gate (read-only) — REQUIRED before assessing**

An assessment of an unhealthy cluster is misleading. Verify, read-only:
1. **Nodes Ready:** list Nodes and flag any not `Ready` (Auto Mode may have 0 nodes until a workload schedules; note that separately).
2. **Ingress controllers healthy:** for each controller Deployment, confirm `availableReplicas > 0` and no pods in `ImagePullBackOff` / `ErrImagePull` / `CrashLoopBackOff`. **If a controller is unhealthy, verify before you conclude it is dead:** for ingress-nginx confirm **all** replicas are down (a multi-replica controller can serve while one pod crashloops); for the AWS LB Controller check the **ALB/target-group** state (the ALB keeps serving while the pod is down). A broken controller **with bound routes** is a **suspected active outage** — surface it **first, as an urgent flag, outside the migration score**; **with zero bound routes** it is **tech debt (1)**. Either way its routing claims cannot be trusted until verified.
3. **Egress sanity (if pods can't pull):** cluster-wide `ImagePullBackOff` usually means broken node egress. Optionally inspect the node subnets' route table for a `blackhole` default route (deleted NAT gateway) via EC2 `DescribeRouteTables`. Report it as an environment caveat — do not attempt to fix it (read-only).

**Action 7 — Detect EKS Auto Mode (read-only)**

Read `cluster.computeConfig` from EKS `DescribeCluster`. Auto Mode is enabled when `computeConfig.enabled = true`. On Auto Mode, recognize the **managed** load-balancing IngressClass `eks.amazonaws.com/alb` (parameters `apiGroup: eks.amazonaws.com`, `kind: IngressClassParams`) and `loadBalancerClass: eks.amazonaws.com/nlb` — these are built-in, not a self-managed AWS LB Controller. Record Auto Mode status in Current Configuration; it changes Migration Options guidance (ALB path needs no LBC install).

### Steps 1–7: Run Assessment

For the selected cluster, run the full assessment:
1. Read each reference file in order
2. Execute the checks
3. Score each item by Impact (0–5) per the Impact Indicator
4. **Collect topology data** — Ingress resources, controllers, backend services, and Node information (instance IDs, instance types)

### Step 8: Routing Topology

1. Compile the topology data collected during Steps 1–7.
2. Render the **Routing Topology** table (per-route line items + Impact) in the report.
3. Emit the topology artifact as one fenced `json` block in the report's References section, using the schema below. It is a machine-readable hand-off for other skills and for the Claude Code skill's HTML renderer — do NOT claim it was written to a file.

**Topology artifact schema:**

> **CRITICAL — controller naming contract:** Every `controllers[].name` MUST be exactly equal to the value used in `ingresses[].controller` (i.e. the IngressClass name: `nginx`, `alb`, `nginx-legacy`, etc.). Consumers join each ingress to its controller by exact name match — if they differ, the ingress is **unlinked** and its routes will appear to belong to no controller (there is no fallback to the first controller). The Routing Topology table must use the same names, so a reader can join the table and the artifact. Use `displayName` for the human-readable deployment name (e.g. `ingress-nginx-controller`).

```json
{
  "cluster": "name",
  "region": "ap-southeast-1",
  "nodes": [
    { "name": "ip-10-0-1-100.ec2.internal", "instanceId": "i-0abc123def456", "instanceType": "m5.xlarge", "zone": "ap-southeast-1a" }
  ],
  "controllers": [
    { "name": "nginx", "displayName": "ingress-nginx-controller", "namespace": "ingress-nginx", "version": "1.9.6", "type": "deployment" }
  ],
  "ingresses": [
    {
      "name": "my-app", "namespace": "default", "controller": "nginx",
      "hosts": ["app.example.com"],
      "paths": [{ "path": "/api", "pathType": "Prefix", "backend": "api-svc", "port": 80 }],
      "tls": true, "annotations": {"key": "value"}
    }
  ],
  "services": [
    { "name": "api-svc", "namespace": "default", "type": "ClusterIP", "ports": [80] }
  ],
  "gatewayApi": {
    "crdsInstalled": true,
    "gatewayClasses": [],
    "gateways": [],
    "httpRoutes": []
  }
}
```

If the Gateway API reads were denied, set `"gatewayApi": { "readStatus": "unconfirmed" }` rather than reporting `crdsInstalled: false`.

### Step 9: Generate the Report

Read `references/report-generation.md` and render the report **inline in your response**, following its template exactly.

Use this pattern as the report's **title**, not as a saved filename:

`EKS-Ingress-Migration-<cluster>-<YYYY-MM-DD>-<HHMM>`

There is one delivery path: the full markdown report, inline. Do NOT write files, do NOT run a conversion script, and do NOT offer an HTML rendering as something this skill produces. The interactive HTML dashboard (with the 3D routing diagram) exists only in the Claude Code build of this skill; if the user wants it, they run that build against the same cluster.

### Step 10: Export Materials

For a cluster that has Ingress resources, render the manifests inline as fenced `yaml` blocks in the report's References section, grouped and labelled by the target layout below. Nothing is written to disk — the labels are the grouping the cluster owner should reproduce locally.

```
current/
└── <namespace>-<ingress-name>.yaml
target/
├── gateway-api/
│   ├── 00-gateway-api-crds.yaml     (comment-only: install command)
│   ├── 01-gatewayclass.yaml
│   ├── 02-gateway.yaml
│   ├── 03-httproute-<name>.yaml
│   └── 04-referencegrant-<name>.yaml  (only if needed)
└── alb/
    └── <namespace>-<ingress-name>.yaml
```

**Rules:**
1. `current/` — Each Ingress as clean YAML (strip status, managedFields, resourceVersion, uid, creationTimestamp, generation)
2. `target/gateway-api/` — Gateway API manifests in numbered apply order with comments
3. `target/alb/` — ALB Controller Ingress manifests (annotation-converted)
4. `00-gateway-api-crds.yaml` — Comment-only, carrying the install command for the cluster owner to run
5. All manifests must be valid `kubectl apply -f` input **for the cluster owner** to apply — this skill never applies them
6. Skip clusters with 0 Ingress resources (nothing to export)
7. For the ALB target, apply the annotation mapping from `references/alb-migration.md`
8. **Volume guard (inline rendering has a practical size limit):** with **10 or fewer** Ingress resources, render all of them. Above 10, render the shared target resources (GatewayClass, Gateway) plus `current/` and `target/` for the **10 highest-Impact** routes, then list the remaining routes by namespace/name in a table and state that they follow the same conversion rules and can be rendered on request. Never silently truncate — the count rendered and the count deferred must both appear.

## Rating Rubric

Score every finding by **Impact 0–5** using the **Impact Indicator** rubric (defined in the report, before Assessment Summary). Set severity by **priority order: (1) business logic / revenue — the live traffic at stake · (2) security / reputation · (3) effort to remediate**. **Effort is NOT a severity driver** — never move a score because a fix looks easy or hard. **Presence is decided by estate state:** an absent controller / empty estate / orphaned dead config is a **non-event (0)**; a present-but-broken controller with **zero bound routes** is **tech debt (1) + cleanup note**, while broken **with bound routes** is a **suspected active outage** flagged urgently **outside** the 0–100 score. **Carve-out:** a running controller with a control-plane CVE (e.g. an admission-webhook RCE) is a security finding **even at zero routes**. Security anchors on exposure/blast-radius, business on live traffic.

| Impact | Band | Meaning |
|--------|------|---------|
| 🟢 0 | Non-event | Absent controller, empty estate, or orphaned/dead config — nothing to migrate. List it, deduct 0. *Not a non-event:* a reachable known-CVE/EOL controller (control-plane exposure survives zero routes), or a broken controller with bound routes (active outage — flag separately, outside the score). |
| 🟡 1–2 | Low | No revenue/downtime impact; hardening gap / best-practice; **or a present-but-broken controller with zero bound routes = tech debt (1)**. |
| 🟠 3–4 | Medium | Short-downtime revenue loss or moderately-important live flow; limited-reputation breach; tech debt hard to reverse. |
| 🔴 5 | High | Business-critical revenue loss / prolonged downtime on live traffic, or a major/reputational breach on a live path; needs re-design/re-architecture (may need approval). |
| ⬜ Unknown | — | Cannot determine — state what to check and why. |

> Easy-to-deploy prerequisites (e.g. installing CRDs) are **Low** even if they block a path — effort never sets severity. Never use GREEN/AMBER/RED.

## Migration Difficulty Score

Every report leads with a single **Migration Difficulty Score (0–100)** plus a separate **Re-architecture Gate** badge:

- **High score = little change (easy); low score = much change (hard).** It measures the *amount of the estate that must change*, rolled up from the per-finding Impact ratings — **not** a manday estimate and **not** a remediation-effort index (we cannot know who implements, and effort never sets severity).
- **Empty / non-migratable estate = 100.** No controller + no IngressClass + no Ingress → **100 / TRIVIAL** with a "nothing to migrate" note (cluster/node upgrades are out of scope, not counted as migration). This **also** applies when the only controller present is a healthy migration-*target* controller (e.g. AWS LB Controller) with nothing bound to migrate **and it is not CVE/EOL-affected** — a reachable vulnerable controller is a security finding even at zero routes, so do **not** short-circuit it (see `references/report-generation.md` §1.0-A). **Orphaned Ingress objects with no controller = dead config = 0** with a loud "Migration Crew Alert" note (headline is 100 / TRIVIAL only if there are no other live findings). See `references/report-generation.md` §1.0.
- **Presence vs. absence.** Absent controller = **0** (non-event). Present-but-broken (CrashLoopBackOff/unreachable) with **zero bound routes** = **1 tech-debt** deduction + mandatory cleanup note; **with bound routes** = **suspected active outage**, flagged urgently **outside** the 0–100 score. Neither replaces the migration-difficulty of that controller's config (its routes remain migratable). Verify "no traffic" by read-only evidence (all nginx replicas down; ALB/target-group state for the LBC) — if you cannot verify, treat the estate as live.
- **Deduction model, no artificial cap.** Start at 100, subtract weighted points per finding (Impact 5→10, 4→6, 3→4, 2→2, 1→1, non-event 0), cap per category, `score = max(0, 100 − Σ)`. The score is **never** locked at a ceiling — a single hard route no longer flattens it.
- **Re-architecture Gate (separate, informational):** routes **and non-route conditions** needing redesign/approval — routes (Lua/snippet/mirror, TLS passthrough/mTLS, cross-namespace ownership, **plus any Tier-B feature escalated to Tier-A** — e.g. CORS, or Basic-Auth→OIDC with non-interactive callers, on a closed/unmodifiable backend) plus conditions (no-rollback cutover, **EOL/CVE control-plane exposure**, Auto Mode LB ownership race) — are reported as a `⛔ N blocker(s) need(s) redesign / approval` badge next to the score (a *blocker* is any such route **or** condition); they do not overwrite the number. Score = "how much work?"; gate = "does anything need a redesign decision?".
- **Clean routes count at 0 effort:** an Ingress already on the ALB controller, Gateway API, or a supported 3rd-party controller contributes 0 and is excluded from the Volume work-count, so "X of N already done" is visible and lifts the score.
- **Feature-gap is tiered:** features with no native ALB annotation but a standard workaround — **CORS** (app middleware), **IP allowlist** (Security Group / WAF), **rate-limit** (WAF), **Basic Auth → OIDC** (app-level credential validation) — are **Impact 2** (performance/hardening) or **3** (business-logic-entangled) **while that workaround can be applied**. They **escalate to Tier-A (4–5)** only when the workaround cannot be applied — the backend is a closed third-party/SaaS app you cannot modify (no app-layer shim) and no platform layer replicates it — and the loss degrades a live business flow; for **Basic Auth → OIDC** escalation additionally requires **non-interactive callers**. No-workaround features (Lua/snippet/mirror/regex-capture) score heavy by default. See `report-generation.md` §1.3 for the rule.
- Bands: 90–100 TRIVIAL · 80–89 EASY · 70–79 MODERATE · 60–69 HARD · 0–59 VERY HARD.
- The score is **derived from the findings, not a separate judgement** — it never overrides the team's choice of migration path. Full deterministic algorithm, category weights, gate logic, tiering rules, and the mandatory Score Breakdown table live in `references/report-generation.md` Step 1.

## Report Output

Everything is delivered **inline in the response** — this runtime cannot write files, so no output path is ever reported as written. One report per assessed cluster, in this order:

| Order | Output | Form |
|---|---|---|
| 1 | Assessment report | Markdown, titled `EKS-Ingress-Migration-<cluster>-<YYYY-MM-DD>-<HHMM>` |
| 2 | Topology artifact | One fenced `json` block in the References section |
| 3 | Export materials | Fenced `yaml` blocks in the References section, labelled with their `current/` / `target/` grouping, subject to the Step 10 volume guard |

The report leads with the Migration Difficulty Score and the Re-architecture Gate badge. The interactive HTML dashboard and 3D routing diagram are **not** produced here — they belong to the Claude Code build of this skill.
