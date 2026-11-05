# Evals: eks-security

## What these evals target

eks-security runs three read-only security reviews of a live EKS cluster (C1 CVE and advisory review, C2 security event response, C3 posture check) and gives hardening and compliance guidance. `triggering.json` checks that CVE, advisory, "am I affected", incident, posture and compliance prompts activate the skill while adjacent EKS concerns (general knowledge and security practice, architecture, build, ops review, recon, cost, upgrade and version lag, GenAI workloads, a full Well-Architected review, account-level security) do not.

`evals.json` has nine cases:

| Id | Capability | What it checks |
|---|---|---|
| 1 to 3 | Hardening and compliance guidance | HIPAA greenfield baseline, Auto Mode vs CIS custom AMI, PCI existing-cluster priority (HIPAA-eligible not compliant, IRSA not legacy, Audit Manager maintenance mode) |
| 4 | C1 exposed | Add-on and agent below the fixed versions: verdict exposed, priority raised for no workaround, add-on update printed for the team, source URL and read time |
| 5 | C1 not exposed | Installed at the fixed versions: "not exposed" lines naming what was compared, against which source, read when; no false alarm |
| 6 | C1 unknown | Agent image on tag `latest`: unknown with reason and action, never "not exposed", coverage line 1 of 2 |
| 7 | C1 Auto Mode | AWS-managed components: no add-on update, nodes created before the fix date listed for rotation, NodePool `expireAfter` lever |
| 8 | C2 event | Compromised image that leaks the pod's credentials: scope, quick record, contain at once (pods kept in place, pod-scoped quarantine with its limits, session revocation), snapshot after isolation, read and propose only, exploitation checks stated as not covered |
| 9 | C3 posture | A reduced `posture.json`: coverage and score, verdict per containment layer, failed checks by SEC-POSTURE id with evidence, unknown never pass, `--admin-allow` for expected admins, fixes printed only |

## Fixtures

Cases 4 to 9 are offline: each prompt says not to run `aws`, `kubectl` or `collect.sh`, and the inputs are staged from `files/eval-<id>/` into the working directory.

| Path | Content |
|---|---|
| `files/eval-4/`, `eval-5/`, `eval-6/`, `eval-7/` | `inventory.json` (schema `eks-security/inventory@1`), `advisory-record.json` (schema `eks-security/advisory@1`) and `bulletin.txt`, a recorded excerpt of the public bulletin [2026-170-AWS](https://aws.amazon.com/security/security-bulletins/2026-170-aws/) quoted in `skills/eks-security/references/cve-advisory-review.md` |
| `files/eval-7/auto-mode-release-note.txt` | A mock release-note line that supplies the record's `fixed_at`; it is labelled as not an AWS publication |
| `files/eval-8/` | `event.md` (event notes) and `scope.json` (read-only scope facts) |
| `files/eval-9/` | `posture.json` (schema `eks-security/posture@1`), written by `posture_reduce.sh` from recorded scorer tokens |

Cluster names, account ids, instance ids and digests in the fixtures are made up. The C1 fixtures give the same verdicts when run through the skill's own scripts: `advisory_check.py` accepts each record against its `bulletin.txt`, and `match.py` returns exposed (4), not exposed (5), unknown at coverage 0.5 (6) and rotation pending for two nodes (7).

## Neighbour-skill disambiguation

eks-security owns live security reviews (an advisory verdict, an event response, a posture check) and the security, compliance and hardening lane. It hands off to eks-best-practices for knowledge with no live check (including how to stay informed and set a patch cadence), to eks-upgrade-check for upgrade readiness to a target version (version currency with no target version goes to eks-operation-review), to eks-recon for an inventory with no verdict, to eks-well-architected-review for a full five-pillar review, and to the other siblings for their non-security lanes.

<!-- SIBLING_MAP_START -->
- **`eks-best-practices`** (general EKS architecture, configuration and security operating practice with no live check: compute, networking, cost, how to follow bulletins and set a patch cadence) negatives 21, 28, 32 ("Karpenter vs managed node groups + subnet/CIDR planning", "reduce my EKS bill with Spot/Graviton/consolidation", "stay informed about EKS security bulletins and set a patch cadence").
- **`eks-design`** (architecture design documents, Mermaid diagrams, ADRs) negative 22 ("generate an EKS architecture design document with diagrams and ADRs").
- **`eks-operation-review`** (operational-excellence audit of a live cluster with GREEN/AMBER/RED scoring) negative 23 ("run an operational excellence review and score it").
- **`eks-recon`** (cluster discovery and inventory of what is running, no verdict) negatives 24, 34, 36 ("what Kubernetes version and add-ons is my cluster running", "list every add-on, AMI and image version for a handover document", "document the networking and security posture of our dev cluster").
- **`eks-genai`** (GenAI/GPU workload guidance, including ML-specific security like model-artifact provenance) negative 25 ("self-hosting Llama 3 on GPUs: secure model artifacts and pick GPU vs Inferentia").
- **`eks-build`** (generating deployable EKS Terraform / Helm) negative 26 ("generate the Terraform and Helm values to build a cluster").
- **`account-security`** (org-wide AWS account security with no EKS-specific angle: SCPs, IAM Identity Center, multi-service GuardDuty) negative 27 ("org-wide SCPs, Identity Center, GuardDuty across every account").
- **`eks-upgrade-check`** (upgrade readiness to a target version with no advisory: deprecated APIs, add-on compatibility) negatives 29, 33 ("is my cluster ready to upgrade from 1.30 to 1.33", "vpc-cni two minor versions behind latest, no advisory").
- **`eks-mcp-server`** (EKS MCP server setup in an AI assistant) negative 30 ("configure the EKS MCP server so it can read my cluster").
- **`eks-well-architected-review`** (deterministic Well-Architected review of a live EKS cluster: five pillars, fixed jq detections, severity-weighted 0-100 per pillar plus a coverage gate) negatives 31, 35 ("score our EKS cluster across all five Well-Architected pillars", "full Well-Architected review across all pillars").
<!-- SIBLING_MAP_END -->

The discriminator: a **security verdict on a live cluster, a security event, or a security control or compliance regime** is the driver. Knowledge with no check, version lag, inventory, cost, build and a full Well-Architected review go to the sibling.

## Live-MCP caveat

No case needs a live cluster or an MCP server. Cases 1 to 3 carry enough context to answer from the skill's guidance; cases 4 to 9 carry recorded inputs in `files/`.

## How to run

From `misc/evals/`:
- `make validate-eks-security`: frontmatter + 64/1024-char limits (deterministic)
- `make triggering-eks-security`: triggering accuracy score (LIVE)
- `make task-eks-security`: task evals with grader (LIVE)
- `make process-eks-security`: process assertions against latest trajectory (deterministic)
- `make artifact-eks-security`: artifact validation against outputs/ (deterministic)
- `make composite-eks-security`: weighted composite score + letter grade (deterministic)

See `misc/evals/README.md` for the full capability catalogue (A to K) and `.skilleval.yaml` for weight configuration.
