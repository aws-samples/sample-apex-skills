# Evals — eks-security

## What these evals target

These inputs exercise the discovery-driven EKS security & compliance scope: choosing the OS/AMI + identity + workload + image + runtime + audit + compliance-accelerator stack for regulated workloads (HIPAA, PCI-DSS, FedRAMP, GDPR). `triggering.json` checks that security/compliance/hardening/audit-prep prompts activate the skill while adjacent EKS concerns (architecture, build, ops-review, recon, cost, upgrade, GenAI-workload, account-level security) do not. `evals.json` checks task usefulness on three canonical scenarios (HIPAA greenfield, Auto-Mode-vs-CIS-AMI trade-off, PCI existing-cluster hardening) including the accuracy guardrails (HIPAA-eligible-not-compliant, IRSA-not-legacy, Auto-Mode-no-custom-AMI).

## Neighbour-skill disambiguation

`eks-security` owns the security/compliance/hardening/regulated-workload lane. It hands off to siblings that own the cluster's *non-security* lifecycle (architecture, build, ops review, discovery, cost, upgrade) and to `eks-genai` for ML-workload-specific security. The discriminator: if the driver is a compliance regime, audit, hardening, or a security control (identity, network policy, image trust, runtime detection, audit logging), it's this skill; otherwise route to the sibling.

<!-- SIBLING_MAP_START -->
- **`eks-best-practices`** (general EKS architecture/config advice — compute, networking, IAM, cost — no security/compliance driver) — negatives 13, 20 ("Karpenter vs managed node groups + subnet/CIDR planning", "reduce my EKS bill with Spot/Graviton/consolidation").
- **`eks-design`** (architecture design documents, Mermaid diagrams, ADRs) — negative 14 ("generate an EKS architecture design document with diagrams and ADRs").
- **`eks-operation-review`** (operational-excellence audit of a live cluster with GREEN/AMBER/RED scoring) — negative 15 ("run an operational excellence review and score it").
- **`eks-recon`** (cluster discovery / inventory of what is running) — negative 16 ("what Kubernetes version and add-ons is my cluster running").
- **`eks-genai`** (GenAI/GPU workload guidance, including ML-specific security like model-artifact provenance) — negative 17 ("self-hosting Llama 3 on GPUs — secure model artifacts and pick GPU vs Inferentia").
- **`eks-build`** (generating deployable EKS Terraform / Helm) — negative 18 ("generate the Terraform and Helm values to build a cluster").
- **`account-security`** (org-wide AWS account security with no EKS-specific angle — SCPs, IAM Identity Center, multi-service GuardDuty) — negative 19 ("org-wide SCPs, Identity Center, GuardDuty across every account").
- **`eks-upgrade-check`** (upgrade readiness — deprecated APIs, add-on compatibility) — negative 21 ("is my cluster ready to upgrade from 1.30 to 1.33").
- **`eks-mcp-server`** (EKS MCP server setup in an AI assistant) — negative 22 ("configure the EKS MCP server so it can read my cluster").
- **`eks-well-architected-review`** (deterministic Well-Architected review of a live EKS cluster — five pillars, fixed jq detections, severity-weighted 0-100 per pillar plus a coverage gate) — negative 23 ("score our EKS cluster across all five W…").
<!-- SIBLING_MAP_END -->

The discriminator that separates `eks-security` from all neighbours: a **security control or compliance regime is the driver**, not cluster architecture, build, cost, discovery, or upgrade.

## Live-MCP caveat

The `evals.json` tasks are advisory and **do not require a live cluster or MCP server** — each prompt carries enough context (regime, sensitivity, OS strategy, timeline, topology, skill, ops tolerance, current baseline) to be answered from the skill's knowledge alone. No MCP availability is needed to run these evals.

## How to run

From `misc/evals/`:
- `make validate-eks-security` — frontmatter + 64/1024-char limits (deterministic)
- `make triggering-eks-security` — triggering accuracy score (LIVE)
- `make task-eks-security` — task evals with grader (LIVE)
- `make process-eks-security` — process assertions against latest trajectory (deterministic)
- `make artifact-eks-security` — artifact validation against outputs/ (deterministic)
- `make composite-eks-security` — weighted composite score + letter grade (deterministic)

See `misc/evals/README.md` for the full capability catalogue (A–K) and `.skilleval.yaml` for weight configuration.
