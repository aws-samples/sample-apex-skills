---
name: eks-design
description: Use when designing EKS architecture. Generates architecture design documents including system architecture with Mermaid diagrams, Architecture Decision Records (ADRs), security architecture, and architecture validation reports. Translates requirements into tailored EKS architecture designs guided by AWS Well-Architected best practices. Output populates the project design folder and feeds into eks-build for code generation. Covers cluster architecture, compute strategy, networking model, security posture, addon selection, observability, cost optimization, and upgrade strategy. Also use when (1) reviewing EKS architecture decisions, (2) choosing between EKS compute options, (3) planning EKS networking or security, (4) evaluating EKS deployment models, (5) optimizing EKS cost and scalability, or (6) generating architecture documentation for an EKS project.
---

# EKS Design

Generate architecture design documents for production-ready EKS deployments. All output is structured for direct handoff to `eks-build` for code generation.

## When to Use

- Designing a new EKS cluster architecture from requirements
- Reviewing or validating existing EKS architecture decisions
- Choosing between EKS compute options (Karpenter, MNG, Auto Mode, Fargate)
- Planning EKS networking or security architecture
- Evaluating EKS deployment models (Standard, Auto Mode, Outposts, Anywhere)
- Optimizing EKS cost and scalability
- Generating architecture documentation, ADRs, or Mermaid diagrams for EKS
- Creating design artifacts that feed into `eks-build` for implementation

## Don't Use

- Generating Terraform code or Helm charts (use `eks-build`)
- EKS cluster reconnaissance or discovery (use `eks-recon`)
- Terraform module design or testing (use `terraform-skill`)
- Detailed reference material on autoscaling, networking, security, observability, cost, reliability, or upgrades (use `eks-best-practices`)

## Design Output Format

**Design documents describe WHAT and WHY — never HOW.**

| USE in design output | DO NOT USE in design output |
|---------------------|----------------------------|
| Decision tables (compare options) | YAML manifests (K8s, Helm, Kustomize) |
| Mermaid diagrams (architecture, flows) | Bash/CLI commands (aws, kubectl, helm) |
| ASCII flow diagrams (sequences, pipelines) | JSON/HCL (IAM policies, Terraform) |
| Bullet summaries (components, integration) | Code snippets (Python, Go, PromQL, SQL) |
| DO/DON'T lists (security, operations) | Step-by-step deployment procedures |

**Rule:** If you find yourself writing a code block, stop and convert it to a table, diagram, or description. Implementation code belongs in `eks-build`.

**How to use references:** Skill references contain decision frameworks, comparison tables, and architecture patterns. Use them to INFORM your design decisions — do not copy reference content into design documents. Synthesize knowledge into project-specific recommendations.

**Internet search (MANDATORY before generating):** Before writing any design content, you MUST search the internet to determine the latest EKS version, tool versions (Karpenter, ArgoCD, Kyverno, etc.), and AWS service updates. Do NOT use version numbers from reference files — they are illustrative only and may be outdated. Always verify the chosen EKS version is in standard support (not extended or EOL). Never rely solely on cached knowledge for version numbers.

## Design Workflow

> **MANDATORY: The validation loop (Stages 3-4) is NOT optional.** Every design MUST be scored after generation. If the score is below threshold, you MUST fix the gaps and re-score. Do NOT skip to Stage 5 (Handoff) without a passing score. Do NOT present the design to the user as "complete" until it passes. The scoring loop is what separates a draft from a validated design.

### Stage 1: Input Assessment

Analyze available inputs (requirements documents, meeting notes, technical assessments) to extract:

- **Business context**: Project scope, stakeholders, success criteria, timeline, budget
- **Technical context**: Existing VPC/network, compliance requirements, tooling preferences
- **Constraints**: Air-gapped, proxy, private registry, multi-account, regulatory

**Output**: `appendices/input-assessment-analysis.md`

**Rules**:
- All information must come from verifiable sources — never invent or assume
- Focus on WHAT (requirements), not HOW (architecture) — no technology selections yet
- Document gaps honestly rather than filling with assumptions

### Stage 2: Architecture Generation

Generate EKS architecture based on requirements. Use the decision frameworks below and search the internet for latest AWS best practices when requirements don't match existing patterns.

Refer to `eks-best-practices` skill for detailed reference material on autoscaling, networking, security, observability, cost optimization, reliability, and cluster upgrades.

**Process**:
1. Select EKS deployment model (Standard, Auto Mode, Fargate, Outposts, Anywhere)
2. Select compute strategy using the Compute Selection Matrix
3. Select networking model (VPC CNI mode, ingress pattern)
4. Select addon management pattern (Pattern 1, 2a, or 2b — see eks-build)
5. Design security posture (IAM model, PSA levels, secrets, encryption)
6. Design observability stack
7. Design upgrade strategy
8. Document each significant decision as an ADR

**Output depends on what the user asked for:**

- **Comprehensive design** (user asks for "full design", "system architecture", or doesn't specify a focus): Generate `architecture/system-architecture.md` covering ALL requirements (compute, networking, addons, security, observability, multi-tenancy, upgrades, cost, DR, constraints). Structure the document with: (1) Executive summary and requirements recap, (2) Cluster architecture overview with Mermaid diagrams (cluster topology, VPC/subnet layout, addon architecture, data flow), (3) Component specifications for cluster, node groups, addons, networking, security, and observability, (4) Integration points with external systems (CI/CD, registries, monitoring), (5) Customization requirements (air-gapped, proxy, private registry, compliance).
- **Focused design** (user asks for "security design", "CI/CD design", "networking design", etc.): Generate `architecture/<focus>-architecture.md` as the PRIMARY document, going deep on that specific domain. Do NOT force comprehensive coverage when the user asked for a focused design.
- **Comprehensive + supplementary**: When generating a comprehensive design, optionally also generate a `<focus>-architecture.md` deep-dive if a domain is complex enough (e.g., HIPAA security, multi-tenant CI/CD).

**ADRs**: `architecture/architecture-decision-records/ADR-*.md`. Every significant technology choice must have an ADR. Each ADR follows the format: Context → Decision → Alternatives Considered → Rationale → Consequences → Research Sources. Name files `ADR-001-compute-strategy.md`, `ADR-002-networking-model.md`, etc. For comprehensive designs, produce 7-9+ ADRs. For focused designs, produce ADRs relevant to the focus area.

### Stage 3: Architecture Validation (MANDATORY — DO NOT SKIP)

**You MUST run this stage after generating any design documents.** Score the design against five validation dimensions. If the score is below 85/100, you MUST fix the identified gaps before proceeding. This is the quality gate between "draft" and "validated design."

**Validation dimensions** (each scored per [references/architecture-validation.md](references/architecture-validation.md)):

| Dimension | Points | What to Evaluate |
|-----------|--------|-----------------|
| Requirements Coverage | /25 | Every requirement has an architectural solution |
| Component Integration | /20 | All interfaces defined and compatible, data flows documented |
| Service Limits | /15 | AWS service limits assessed with mitigation for high-risk items |
| Technical Feasibility | /20 | Technology choices validated, EKS-specific checks pass |
| Documentation Completeness | /20 | All required docs present, **narrative quality** (not just tables), ADR quality, diagrams rendered to PNG and embedded in docx/pptx |

**Output**: `appendices/iterations/score-sheet-iteration-1.md`

**Scoring thresholds**:
- **>= 85/100**: PASSED — proceed to Stage 4
- **70-84**: CONDITIONAL — fix identified gaps, re-score as next iteration
- **< 70**: FAILED — significant rework needed

**How to score**: For each dimension, evaluate every criteria in the scoring matrix (see reference), assign points with specific justification, document gaps, and calculate the total. Be honest — inflated scores lead to weak designs that fail during build.

### Stage 4: Quality Review & Iteration (MANDATORY — DO NOT SKIP)

**You MUST run this stage after Stage 3 passes.** Apply weighted scoring across architecture quality dimensions. If the score is below 90/100, you MUST fix the gaps and re-score. Do NOT skip to handoff with a score below 90.

**Scoring dimensions** (weighted):

| Dimension | Weight | What to Evaluate |
|-----------|--------|-----------------|
| Architecture & Design | 30% | Patterns, component design, integration, technology choices |
| Security | 25% | IAM, pod security, network security, encryption, secrets |
| Reliability & Operations | 20% | HA, PDBs, health probes, upgrades, observability, security tool monitoring |
| Cost & Scalability | 15% | Right-sizing, Spot/Graviton, consolidation, service limits |
| Implementation Readiness | 10% | Handoff completeness, ADR quality, build skill compatibility |

**Output**: `appendices/iterations/score-sheet-iteration-X.md`

**Iteration rules**:
- Maximum 5 iterations to reach 90/100
- Each iteration must show measurable progress (score must increase)
- If the same gap persists across 2 iterations, escalate to the user
- Final iteration content is promoted to root-level folders
- Every score sheet must include: score per dimension, delta from previous iteration, specific gaps, and recommended fixes

**The validation loop pattern:**
```
Generate design -> Score (Stage 3) -> Below 85? -> Fix gaps -> Re-score
                                    -> Above 85? -> Score (Stage 4) -> Below 90? -> Fix gaps -> Re-score
                                                                     -> Above 90? -> Proceed to Stage 5
```

### Stage 5: Finalize & Handoff

**COMPLETION CHECKLIST — every item must be done before handoff.** Walk through this list at the end. If any item is unchecked, go back and complete it.

- [ ] Internet search for latest EKS version, tool versions, and AWS service updates (not from cached knowledge)
- [ ] Architecture documents generated — `architecture/system-architecture.md` (or `architecture/<focus>-architecture.md` for focused designs) exists with narrative prose + diagrams
- [ ] ADRs generated — `architecture/architecture-decision-records/ADR-*.md` files exist (minimum 6 for comprehensive, domain-relevant for focused)
- [ ] Security architecture generated — `architecture/security-architecture.md` exists (if applicable)
- [ ] Stage 3 validation scored — `appendices/architecture-integration-validation.md` exists with score >= 85/100
- [ ] Stage 4 quality review scored — `appendices/iterations/score-sheet-iteration-*.md` exists with Stage 4 score >= 90/100
- [ ] Every section has narrative prose — no table-only or bullet-only sections (0/5 narrative = auto-fail)
- [ ] Mermaid diagrams rendered to PNG — `diagrams/*.png` files exist (high-res, 4x scale, white background)
- [ ] AGENTS.md created — lists which design files the build agent must read
- [ ] README.md created — provides human-readable navigation
- [ ] docx/pptx offered to user — asked if they want Word/PowerPoint versions (only generate if confirmed)
- [ ] If docx/pptx generated: rendered PNGs from `diagrams/` embedded in documents (not Mermaid code blocks)

**If any item is unchecked, STOP and complete it before proceeding.** The files are the proof — if the score sheet doesn't exist, you skipped validation. If `diagrams/*.png` doesn't exist, you skipped rendering.

Generate handoff artifacts for `eks-build`:

1. **AGENTS.md** — machine-readable instructions listing which design files the build agent must read
2. **README.md** — human-readable navigation guide
3. Verify output structure matches specification
4. **Render Mermaid diagrams to PNG** — extract every Mermaid code block from the architecture markdown files, save each as a `.mmd` file, then convert to PNG in `diagrams/`. Install and convert: `npm install -g @mermaid-js/mermaid-cli && mmdc -i diagram.mmd -o diagrams/<name>.png -b white -s 4`. If `mmdc` doesn't work, **search the internet for how to use mermaid-cli to convert .mmd to .png**. Requirements: 4x scale, white background, auto-sized canvas (no fixed width/height). Use descriptive kebab-case names (e.g., `defense-in-depth-layers.png`, `pod-identity-flow.png`).
5. **Ask the user** if they want Word (.docx) and PowerPoint (.pptx) versions. Only generate if confirmed — the `docx` and `aws-pptx` skills handle generation. When generating, embed the rendered PNGs from `diagrams/` into the documents.

**Output**: `AGENTS.md`, `README.md`, `diagrams/*.png`, optionally `.docx` and `.pptx`

## Output Structure

All design output goes to `projects/<project-name>/design/`:

```
projects/<project-name>/design/
├── README.md                                # Navigation guide
├── AGENTS.md                                # Build agent instructions
├── architecture/
│   ├── system-architecture.md               # Cluster architecture with Mermaid diagrams
│   ├── architecture-decision-records/
│   │   ├── ADR-001-[decision-name].md
│   │   └── ADR-00X-[decision-name].md
│   └── security-architecture.md             # Security posture design
├── diagrams/                                # Rendered Mermaid diagrams (high-res PNG)
│   ├── cluster-topology.png
│   ├── network-architecture.png
│   └── addon-dependencies.png
├── generate-docx.js                         # DOCX generator script (optional — user must confirm)
├── generate-pptx.js                         # PPTX generator script (optional — user must confirm)
├── system-architecture.docx                 # Word document (optional — with embedded diagrams)
├── system-architecture.pptx                 # PowerPoint deck (optional — with embedded diagrams)
└── appendices/
    ├── input-assessment-analysis.md         # Stage 1 output
    ├── architecture-integration-validation.md # Stage 3 output
    └── iterations/                          # Quality iteration history
        ├── score-sheet-iteration-1.md
        └── score-sheet-iteration-X.md
```

**Detailed file descriptions**: See [references/output-structure.md](references/output-structure.md).

## EKS Architecture Decision Framework

### When to Use EKS

| Requirement | EKS | ECS | Lambda |
|-------------|-----|-----|--------|
| **Kubernetes ecosystem** | Native K8s | AWS-proprietary | No |
| **Portable across clouds** | Standard K8s API | AWS-only | AWS-only |
| **Long-running services** | Yes | Yes | 15 min limit |
| **Minimal ops overhead** | Medium | Low | Lowest |
| **GPU/ML workloads** | Best support | Limited | No |
| **Complex networking** | Full control | Medium | Limited |
| **Team has K8s expertise** | Required | Not required | Not required |

### EKS Deployment Models

| Model | Operational Overhead | Use When |
|-------|---------------------|----------|
| **EKS Standard** | Medium-High | Need full customization |
| **EKS Auto Mode** | Low | Want minimal ops, standard workloads |
| **EKS with Fargate** | Low | Batch, low-density workloads |
| **EKS on Outposts** | High | Data residency, low-latency edge |
| **EKS Anywhere** | Highest | Air-gapped, custom hardware |

### Compute Selection Matrix

Refer to `eks-best-practices` skill for detailed compute comparison tables, Karpenter configuration patterns, and Auto Mode specifics.

| Factor | Fargate | MNG | Karpenter | Auto Mode | Self-Managed |
|--------|---------|-----|-----------|-----------|-------------|
| **Best for** | Batch, small scale | Stable, predictable | Dynamic, varied | Minimal ops | Custom AMI/kernel |
| **Spot support** | No | Yes | Yes (native) | Yes | Yes |
| **GPU support** | No | Yes | Yes | Yes | Yes |
| **DaemonSets** | No | Yes | Yes | Yes | Yes |
| **Node SSH** | No | Yes | Yes | No | Yes |

**Quick decision guide:**
- **Default**: Karpenter — best balance of flexibility, cost, and automation
- **Zero ops**: EKS Auto Mode — AWS manages everything
- **Serverless/batch**: Fargate — no nodes, per-pod billing
- **Predictable**: MNG — familiar ASG model
- **Custom**: Self-managed — full control, highest overhead

### Networking Quick Reference

Refer to `eks-best-practices` skill for detailed networking patterns including VPC CNI deep-dives, subnet planning, service mesh options, and private cluster configurations.

| VPC CNI Mode | Use When | Pod Density |
|-------------|----------|-------------|
| **Secondary IP** (default) | Most workloads | Limited by ENI x IPs per ENI |
| **Prefix Delegation** | >30 pods/node, IP-constrained | 4-16x more pods |
| **Custom Networking** | Pods need different CIDR | Same as underlying mode |

| Ingress Pattern | Best For |
|----------------|----------|
| **ALB (via LBC)** | HTTP/HTTPS web apps, WAF, Cognito |
| **NLB (via LBC)** | TCP/UDP, gRPC, low latency, static IPs |
| **Gateway API** | Multi-team, new deployments (recommended) |
| **VPC Lattice** | Cross-VPC service-to-service, IAM auth |

### Security Essentials

Refer to `eks-best-practices` skill for detailed security architecture patterns including IAM deep-dives, pod security standards, network policies, and secrets management.

| IAM Approach | Use When |
|-------------|----------|
| **Pod Identity** | New workloads (EKS 1.24+) — simpler, session tags, role chaining |
| **IRSA** | Older clusters, Fargate |

**Key rules:**
- Use Pod Identity for new workloads
- Use EKS access entries (API mode) over aws-auth ConfigMap
- Move VPC CNI permissions from node role to Pod Identity/IRSA
- Never use wildcard conditions in IRSA trust policies
- Never attach application permissions to node IAM roles

### Cost Optimization Quick Wins

Refer to `eks-best-practices` skill for detailed cost optimization strategies, Spot instance patterns, and right-sizing guidance.

| Action | Savings | Effort |
|--------|---------|--------|
| **Graviton (arm64)** | 20-40% | Low |
| **Spot for non-critical** | 60-90% | Low |
| **Karpenter consolidation** | 20-30% | Low |
| **VPA right-sizing** | 15-30% | Medium |
| **gp3 over gp2** | 20% on EBS | Low |
| **VPC endpoints** | Eliminate NAT costs | Low |

### EKS Capabilities

EKS Capabilities are AWS-managed features installed and updated as part of the EKS platform. Evaluate managed vs self-managed for each:

| Capability | What It Does | When to Use Managed | When to Self-Manage |
|-----------|-------------|--------------------|--------------------|
| **ArgoCD** | GitOps continuous delivery | Multi-account hub-and-spoke, IAM IDC integration, minimal ops | Custom plugins, air-gapped, existing ArgoCD investment |
| **ACK** | Manage AWS resources via K8s CRDs | Standard AWS resource management (S3, RDS, IAM) | Specific controller version pinning, custom config |
| **KRO** | Platform abstractions via ResourceGroupDefinitions | Golden path templates, multi-resource compositions | Early adoption, custom reconciliation logic |

**Combined pattern:** ArgoCD deploys ACK resources + KRO compositions via GitOps, providing a single workflow for both infrastructure and applications.

## Required ADR Categories

Every EKS design must produce ADRs for these decision areas (at minimum):

| ADR Category | Decision | Common Alternatives |
|-------------|----------|-------------------|
| **Deployment Model** | Standard vs Auto Mode vs Fargate | Operational overhead vs control |
| **Compute Strategy** | Karpenter vs MNG vs Auto Mode | Flexibility vs predictability |
| **Networking Model** | CNI mode, ingress pattern | Pod density, traffic routing |
| **Addon Pattern** | Pattern 1 vs 2a vs 2b | Terraform-only vs GitOps |
| **Security Model** | Pod Identity vs IRSA, PSA levels | Simplicity vs compatibility |
| **Observability** | AWS-managed vs open source | Cost vs flexibility |
| **Upgrade Strategy** | In-place vs blue-green | Risk vs cost |
| **Container Registry** | Centralized ECR vs tenant-managed vs enterprise (Artifactory/Harbor) | Isolation vs simplicity |
| **EKS Capabilities** | Self-managed addons vs EKS managed capabilities (ArgoCD, ACK, KRO) | Control vs operational overhead |

Additional ADRs as needed for: multi-tenancy, multi-account, service mesh, compliance framework, DR strategy.

## AGENTS.md Specification

Generate `AGENTS.md` as a machine-readable handoff to `eks-build`:

```xml
<agent name="eks-build">
  <required-reading>
    <file path="architecture/system-architecture.md" purpose="Cluster architecture, component specs, networking, security posture" />
    <file path="architecture/security-architecture.md" purpose="Security controls, IAM model, encryption, pod security" />
  </required-reading>
  <optional-reading>
    <file path="architecture/architecture-decision-records/" purpose="ADRs for all technology choices" />
    <file path="appendices/architecture-integration-validation.md" purpose="Validation results and service limit analysis" />
  </optional-reading>
  <design-decisions>
    <decision key="pattern" value="[1|2a|2b]" />
    <decision key="compute" value="[karpenter|mng|auto-mode|fargate]" />
    <decision key="iam-model" value="[pod-identity|irsa|mixed]" />
    <decision key="air-gapped" value="[true|false]" />
    <decision key="proxy" value="[true|false]" />
    <decision key="private-registry" value="[true|false]" />
    <decision key="compliance" value="[standard|strict]" />
  </design-decisions>
</agent>
```

## Detailed References

This skill uses **progressive disclosure** — essential guidance is above, detailed reference material is loaded on demand:

- **[Output Structure](references/output-structure.md)** — Read when you need detailed file descriptions, naming conventions, and organization principles for the design output folder
- **[Architecture Validation](references/architecture-validation.md)** — Read when running Stage 3 or Stage 4 validation; contains the full scoring matrix, criteria details, and report format

For detailed topic-specific reference material (autoscaling, networking, security, observability, cost, reliability, upgrades, container registry, Terraform examples), refer to the `eks-best-practices` skill which maintains canonical copies of all decision matrices and deep-dive guidance.
