---
name: eks-ingress-migration
description: Assess a live EKS cluster's NGINX/Ingress estate and plan migration to Gateway API, the AWS Load Balancer Controller (ALB Ingress), or AWS Transform (ATX). Discovers ingress controllers and routes, scores migration difficulty 0–100 with a separate re-architecture gate, and generates per-cluster reports plus ready-to-apply manifests. Use when someone asks "how hard is it to move off nginx ingress?", "assess my ingress migration", "migrate nginx to ALB or Gateway API", "ingress migration audit", or "nginx ingress retirement plan". Not for upgrade readiness (eks-upgrade-check), operational audits (eks-operation-review), general cluster discovery (eks-recon), or general ingress configuration advice (eks-best-practices).
---

# EKS Ingress Migration Skill

## Overview

This skill assesses your live EKS cluster's current Ingress architecture and evaluates migration options. It discovers what ingress controllers are running, maps the routing topology, identifies risks, and presents the findings so your team can decide the best migration path.

**This is an assessment tool, not a decision-maker.** The skill presents findings and options — the migration strategy and readiness decision belongs to the user's DevOps team.

**Migration options assessed:**

| Option | Status | Notes |
|--------|--------|-------|
| Gateway API (HTTPRoute + Gateway) | ✅ Assessed | Official Kubernetes successor to Ingress. AWS LB Controller supports it (L7 ≥ v2.14, L4 ≥ v2.13; built-in on EKS Auto Mode). |
| AWS Load Balancer Controller (ALB Ingress) | ✅ Assessed | Stay on Ingress API but swap NGINX→ALB. Gets WAF, Cognito, Shield. |
| AWS Transform (ATX) — Automated | ✅ Included | TD included. For customers with ATX access — fully automated manifest rewriting. |

## Workflow

```
Pre-flight → Assess (7 sections) → Current Architecture Topology → Dual Report (md + html) → Export Materials
```

1. **Pre-flight** — Discover cluster, validate permissions
2. **Assessment** — Run 7 sections, collect findings and topology data
3. **Current Architecture** — Compile topology data into JSON for the HTML report's interactive 3D view (nodes, controllers, ingresses, services)
4. **Dual Report** — Automatically generate both:
   - **Markdown** (detailed) — full findings, ratings, options, CLI commands
   - **HTML** (visual summary) — interactive dashboard with 3D Routing Diagram view, collapsible sections
   - Both lead with the **Migration Difficulty Score (0–100)** — a deterministic roll-up of the per-finding Impact ratings (high = easy to leave NGINX, low = hard / high business impact). See `references/report-generation.md` Step 1.
5. **Export Materials** — Generate ready-to-apply YAML files:
   - `current/` — existing Ingress resources (clean, no status fields)
   - `target/gateway-api/` — Gateway API resources (GatewayClass, Gateway, HTTPRoute) in apply order
   - `target/alb/` — ALB Controller Ingress resources (converted annotations)

**Important:** After assessment completes, proceed directly to report generation and manifest export. Do NOT pause to ask the user — generate all outputs automatically.

## What Gets Assessed

| Area | Key Checks |
|------|------------|
| Ingress Discovery | Controllers, **versions/EOL/CVE**, IngressClass, inventory, **EKS Auto Mode** detection |
| Ingress Resource Analysis | Annotations, path rules, TLS, backends — conversion complexity |
| DNS & Certificates | external-dns, cert-manager, ACM — Gateway API source support |
| Traffic & Routing | Routing patterns, advanced features, mapping to HTTPRoute |
| Migration Risk | Downtime risk, feature gaps, rollback plan |

## Report Structure (5 Navigation Pages)

| Nav Page | Contains |
|----------|----------|
| Overview | Cluster info table, 3D Routing Diagram, **Migration Difficulty Score (headline gauge + Score Breakdown)**, Executive Summary, Impact Indicator (rubric, before Assessment Summary) |
| Assessment Summary | Assessment Summary table (Impact-ordered), Current Configuration, Ingress Discovery |
| Routing Topology | Routing table (per-route line items + Impact), Traffic & Routing |
| Migration Approach | Migration Options (Option 1 Gateway API, Option 2 ALB, Option 3 ATX — consistent panels + per-option download buttons), Blockers, Recommendations |
| Analysis | Ingress Resource Analysis, DNS & Certificates Analysis, Migration Risk |
| References | Export Materials (generated manifests + download buttons), AWS Reference Links |

## Reference Files

Before executing checks for any section, read the corresponding reference file from the `references/` directory.

| User Request | Reference File |
|---|---|
| Full migration assessment | ALL files in order (skip gateway-api.md, alb-migration.md, atx-guide.md) |
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

## Tool Usage Rules

1. **Do NOT call any tools when this skill is first activated.** Wait for the user to ask.
2. **Do NOT hardcode or guess cluster names.** Always discover by listing first.
3. **Do NOT retry a failed MCP tool call more than once.**
4. **Always load the relevant reference file before executing checks.**
5. **Only rate based on what was actually observed — never assume.**
6. If a check fails or returns no data, mark UNKNOWN.
7. Every high-impact (4–5) finding must have a specific, actionable recommendation.
8. **Collect topology data during assessment** — every Ingress host, path, backend, controller, namespace, and the nodes (EC2 instances). This feeds the 3D Routing Diagram view.
9. **Do NOT paste raw YAML/config in findings.** Summarize what was found.
10. **Use tables for all structured data.** No prose lists of facts.
11. **No filler text.** Go straight to content.
12. **Every finding cell: max 2 sentences.**
13. **No ASCII art diagrams.** The HTML has the 3D routing diagram.
14. **No ID column in tables.** Remove all "ID" columns.
15. **Multi-value cells:** use `<br>` for line breaks, not commas.
16. **Executive Summary must be bullet points** — precise and comprehensive.

## Skill Home Directory

All relative paths in this skill are relative to **this skill's directory** (the directory containing this `SKILL.md`).

When the skill says `references/ingress-discovery.md`, read `<skill-dir>/references/ingress-discovery.md`.
When the skill says `tools/report_to_html.py`, run `<skill-dir>/tools/report_to_html.py`.

Reports are written to `~/ingress_migration/`.

The assessment logic (`references/*.md`), the HTML report tool (`tools/report_to_html.py`), and the ATX Transform Definition and before/after samples (`references/atx/`, `references/samples/`) all live inside this skill directory. The skill does not require a project-root `.mcp.json` — live-cluster access is provided by the EKS MCP server (see the `eks-mcp-server` skill for setup).

## Prerequisites

1. **AWS credentials configured** with EKS read access
2. **Python 3.10+** installed (report tool uses only stdlib — no pip packages needed)
3. **EKS MCP server** for live-cluster reads (`list_k8s_resources`, etc.) — apex ships no project-root `.mcp.json`; see the `eks-mcp-server` skill for setup. Falls back to `aws` CLI + `kubectl` where possible.
4. **AWS CLI** or AWS MCP tools available (for `eks`, `acm`, `route53`, `iam`, `elbv2` calls)
5. **Required AWS Permissions:**
   - `eks:DescribeCluster`, `eks:ListClusters`, `eks:ListAddons`, `eks:DescribeAddon`
   - `elasticloadbalancing:DescribeLoadBalancers`, `elasticloadbalancing:DescribeTargetGroups`
   - `iam:GetRole`, `iam:ListAttachedRolePolicies`
   - `acm:ListCertificates`
   - `route53:ListHostedZones`

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

- If **0 clusters found** → STOP. Tell the user no EKS clusters exist in this account.
- If **1 cluster found** → Confirm and proceed with that cluster.
- If **multiple clusters found** → Show the table. Ask: "Assess all clusters, or select specific ones?"

**Action 3 — For each selected cluster, describe it**

```
aws eks describe-cluster --name <cluster> --region <region> --output json
```

**Action 4 — Validate permissions (per cluster)**

| Check Command | Required IAM Permission |
|---------------|------------------------|
| `aws eks list-addons --cluster-name <cluster> --region <region>` | `eks:ListAddons` |
| `list_k8s_resources(kind="Ingress", api_version="networking.k8s.io/v1")` | K8s RBAC: `get`/`list` on `ingresses` |
| `list_k8s_resources(kind="IngressClass", api_version="networking.k8s.io/v1")` | K8s RBAC: `get`/`list` on `ingressclasses` |
| `list_k8s_resources(kind="Deployment", api_version="apps/v1", namespace="kube-system")` | K8s RBAC: `get`/`list` on `deployments` |

**Optional permissions** (degrades gracefully if missing):

| Check Command | Required Permission | If Missing |
|---------------|---------------------|------------|
| `aws acm list-certificates --region <region>` | `acm:ListCertificates` | Mark 4.3 UNKNOWN |
| `aws route53 list-hosted-zones` | `route53:ListHostedZones` | Mark 4.1 UNKNOWN |
| `aws iam get-role` | `iam:GetRole` | Mark UNKNOWN |

**Action 5 — Verify MCP connectivity**

```
list_k8s_resources(cluster_name="<cluster>", kind="Node", api_version="v1")
```

**Action 6 — Cluster health gate (read-only) — REQUIRED before assessing**

An assessment of an unhealthy cluster is misleading. Verify, read-only:
1. **Nodes Ready:** `kubectl get nodes` — flag any not `Ready` (Auto Mode may have 0 nodes until a workload schedules; note that separately).
2. **Ingress controllers healthy:** for each controller Deployment, confirm `availableReplicas > 0` and no pods in `ImagePullBackOff` / `ErrImagePull` / `CrashLoopBackOff`. **If a controller itself is unhealthy, surface it as the first finding** — its routing claims cannot be trusted.
3. **Egress sanity (if pods can't pull):** cluster-wide `ImagePullBackOff` usually means broken node egress. Optionally inspect the node subnets' route table for a `blackhole` default route (deleted NAT gateway) via `aws ec2 describe-route-tables`. Report it as an environment caveat — do not attempt to fix it (read-only).

**Action 7 — Detect EKS Auto Mode (read-only)**

```
aws eks describe-cluster --name <cluster> --query 'cluster.computeConfig' --output json
```
Auto Mode is enabled when `computeConfig.enabled = true`. On Auto Mode, recognize the **managed** load-balancing IngressClass `eks.amazonaws.com/alb` (parameters `apiGroup: eks.amazonaws.com`, `kind: IngressClassParams`) and `loadBalancerClass: eks.amazonaws.com/nlb` — these are built-in, not a self-managed AWS LB Controller. Record Auto Mode status in Current Configuration; it changes Migration Options guidance (ALB path needs no LBC install).

### Steps 1–7: Run Assessment (per cluster)

For each cluster, run the full assessment:
1. Read each steering file in order
2. Execute the checks
3. Score each item by Impact (1–5) per the Impact Indicator
4. **Collect topology data** — Ingress resources, controllers, backend services, and Node information (instance IDs, instance types)

### Step 8: Current Architecture Topology (per cluster)

1. Compile topology data collected during Steps 1–7
2. Write JSON: `~/ingress_migration/<cluster>-topology.json`
3. Briefly show topology summary, then proceed to Step 9

**Topology JSON schema:**

> **CRITICAL — controller naming contract:** Every `controllers[].name` MUST be exactly equal to the value used in `ingresses[].controller` (i.e. the IngressClass name: `nginx`, `alb`, `nginx-legacy`, etc.). The 3D view links each ingress to its controller by exact name match — if they differ, the ingress will render **unlinked** (the renderer no longer falls back to the first controller). Use `displayName` for the human-readable deployment name (e.g. `ingress-nginx-controller`); the 3D label prefers `displayName` when present.

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

### Step 9: Generate Dual Report (per cluster)

Read `references/report-generation.md` and produce a **markdown report per cluster**:

`~/ingress_migration/EKS-Ingress-Migration-<cluster>-<YYYY-MM-DD>-<HHMM>.md`

After ALL cluster markdown reports are written, generate a **single combined HTML report**:

```bash
python3 tools/report_to_html.py \
  ~/ingress_migration/report-cluster-a.md ~/ingress_migration/report-cluster-b.md \
  --topology ~/ingress_migration/cluster-a-topology.json ~/ingress_migration/cluster-b-topology.json \
  --manifests ~/ingress_migration/cluster-a-manifests ~/ingress_migration/cluster-b-manifests \
  -o ~/ingress_migration/EKS-Ingress-Migration-<YYYY-MM-DD>-<HHMM>.html
```

The HTML report has a **cluster dropdown** in the left nav — selecting a cluster switches all content and the 3D routing diagram.

**Always generate both.** Markdown files are the source of truth; the HTML is for presentation.

### Step 10: Export Materials (per cluster)

For each cluster that has Ingress resources, generate manifest files:

**Output directory:** `~/ingress_migration/<cluster>-manifests/`

```
<cluster>-manifests/
├── current/
│   └── <namespace>-<ingress-name>.yaml
└── target/
    ├── 00-gateway-api-crds.yaml
    ├── 01-gatewayclass.yaml
    ├── 02-gateway.yaml
    ├── 03-httproute-<name>.yaml
    └── 04-referencegrant-<name>.yaml  (only if needed)
```

**Rules:**
1. `current/` — Each Ingress as clean YAML (strip status, managedFields, resourceVersion, uid, creationTimestamp, generation)
2. `target/gateway-api/` — Generated Gateway API manifests in numbered apply order with comments
3. `target/alb/` — Generated ALB Controller Ingress manifests (annotation-converted)
4. `00-gateway-api-crds.yaml` — Comment-only file with install command
5. All manifests must be valid `kubectl apply -f` ready
6. Skip clusters with 0 Ingress resources (nothing to export)
7. For ALB target, apply annotation mapping from `references/alb-migration.md`

## Rating Rubric

Score every finding by **Impact 1–5** using the **Impact Indicator** rubric (defined in the report, before Assessment Summary). Weigh security/reputation, business/revenue, and the nature & effort to remediate.

| Impact | Band | Meaning |
|--------|------|---------|
| 🟡 1–2 | Low | Hardening gap / best-practice; no revenue/downtime impact; hours–1 day, single-scope. |
| 🟠 3–4 | Medium | Limited-reputation breach or short-downtime revenue loss; tech debt hard to reverse; area/single-cluster scope. |
| 🔴 5 | High | Major/reputational breach or prolonged downtime; needs re-design/re-architecture (may need approval). |
| ⬜ Unknown | — | Cannot determine — state what to check and why. |

> Easy-to-deploy prerequisites (e.g. installing CRDs) are **Low** even if they block a path. Never use GREEN/AMBER/RED.

## Migration Difficulty Score

Every report leads with a single **Migration Difficulty Score (0–100)** plus a separate **Re-architecture Gate** badge:

- **High score = little change (easy); low score = much change (hard).** It is a relative *effort index* from the per-finding Impact ratings — not a manday estimate (we cannot know who implements).
- **Deduction model, no artificial cap.** Start at 100, subtract weighted points per finding (Impact 5→10, 4→6, 3→4, 2→2, 1→1), cap per category, `score = max(0, 100 − Σ)`. The score is **never** locked at a ceiling — a single hard route no longer flattens it.
- **Re-architecture Gate (separate, informational):** routes needing redesign/approval (Lua/snippet/mirror, TLS passthrough/mTLS, cross-namespace ownership) are reported as a `⛔ N routes` badge next to the score — they do not overwrite the number. Score = "how much work?"; gate = "does anything need a redesign decision?".
- **Clean routes count at 0 effort:** an Ingress already on the ALB controller, Gateway API, or a supported 3rd-party controller contributes 0 and is excluded from the Volume work-count, so "X of N already done" is visible and lifts the score.
- **Feature-gap is tiered:** features with no native ALB annotation but a standard workaround — **CORS** (app middleware), **IP allowlist** (Security Group / WAF), **rate-limit** (WAF) — are **Impact 2** (performance/hardening) or **3** (business-logic-entangled), never 4–5. Only no-workaround features (Lua/snippet/mirror/regex-capture) score heavy.
- Bands: 90–100 TRIVIAL · 80–89 EASY · 70–79 MODERATE · 60–69 HARD · 0–59 VERY HARD.
- The score is **derived from the findings, not a separate judgement** — it never overrides the team's choice of migration path. Full deterministic algorithm, category weights, gate logic, tiering rules, and the mandatory Score Breakdown table live in `references/report-generation.md` Step 1.

## Report Output

All files go to `~/ingress_migration/` organized by cluster:

```
~/ingress_migration/
├── <cluster>/
│   ├── report.md                    # Detailed markdown report
│   ├── topology.json                # Topology data for 3D view
│   └── manifests/
│       ├── current/                 # Existing Ingress YAML (backup)
│       │   └── <ns>-<ingress>.yaml
│       └── target/
│           ├── gateway-api/         # Gateway API resources (apply order)
│           │   ├── 00-gateway-api-crds.yaml
│           │   ├── 01-gatewayclass.yaml
│           │   ├── 02-gateway.yaml
│           │   └── 03-httproute-<name>.yaml
│           └── alb/                 # ALB Controller Ingress (converted)
│               └── <ns>-<ingress>.yaml
└── EKS-Ingress-Migration-<YYYY-MM-DD>-<HHMM>.html  # Combined HTML (all clusters)
```

The single HTML report contains all clusters with a **dropdown selector** in the left nav. Switching clusters swaps the content and 3D routing diagram. The **References** section includes an **Export Materials** topic with download buttons for Gateway API and ALB Controller manifests.

**CLI usage:**
```bash
# Single cluster
python3 tools/report_to_html.py ~/ingress_migration/<cluster>/report.md \
  --topology ~/ingress_migration/<cluster>/topology.json \
  --manifests ~/ingress_migration/<cluster>/manifests/

# Multiple clusters — one HTML with dropdown
python3 tools/report_to_html.py \
  ~/ingress_migration/cluster-a/report.md ~/ingress_migration/cluster-b/report.md \
  --topology ~/ingress_migration/cluster-a/topology.json ~/ingress_migration/cluster-b/topology.json \
  --manifests ~/ingress_migration/cluster-a/manifests ~/ingress_migration/cluster-b/manifests \
  -o ~/ingress_migration/EKS-Ingress-Migration-<YYYY-MM-DD>-<HHMM>.html
```
