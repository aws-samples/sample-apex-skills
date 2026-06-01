# Design Output Structure Specification

Single source of truth for the design output folder structure. All other documents reference this specification.

## Complete Folder Structure

```
projects/<project-name>/design/
├── README.md                                    # Navigation guide and project overview
├── AGENTS.md                                    # Build agent instructions (machine-readable)
├── architecture/
│   ├── system-architecture.md                   # Cluster architecture with Mermaid diagrams
│   ├── architecture-decision-records/
│   │   ├── ADR-001-[decision-name].md
│   │   └── ADR-00X-[decision-name].md
│   └── security-architecture.md                 # Security posture design
├── diagrams/                                    # Rendered Mermaid diagrams (high-res PNG)
│   ├── cluster-topology.png
│   ├── network-architecture.png
│   └── addon-dependencies.png
└── appendices/
    ├── input-assessment-analysis.md             # Stage 1: Input assessment output
    ├── architecture-integration-validation.md   # Stage 3: Validation report
    └── iterations/                              # Quality iteration history
        ├── score-sheet-iteration-1.md
        ├── score-sheet-iteration-X.md
        └── specification-package-iteration-X/   # Snapshot of iterated docs
            └── architecture/
                └── system-architecture.md
```

## File Descriptions

### README.md

- **Created**: Stage 5 (Finalize & Handoff)
- **Content**: Project summary, folder navigation, key decisions summary, deployment pattern selected, next steps for build phase

### AGENTS.md

- **Created**: Stage 5 (Finalize & Handoff)
- **Content**: XML-formatted instructions listing required and optional files for the build agent to read, plus key design decisions as machine-readable key-value pairs

### architecture/system-architecture.md

- **Created**: Stage 2 (Architecture Generation)
- **Content**:
  - EKS cluster architecture overview
  - Mermaid diagrams: cluster topology, VPC/subnet layout, addon architecture, data flow
  - Component specifications: cluster, node groups, addons, networking, security, observability
  - Integration points with external systems (CI/CD, registries, monitoring)
  - Customization requirements (air-gapped, proxy, private registry, compliance)

### architecture/architecture-decision-records/ADR-XXX-[name].md

- **Created**: Stage 2 (Architecture Generation)
- **Content**: Individual ADR per significant technology decision
- **Naming**: `ADR-001-compute-strategy.md`, `ADR-002-networking-model.md`, etc.
- **Format**: Context -> Decision -> Alternatives -> Rationale -> Consequences -> Research Sources

### architecture/security-architecture.md

- **Created**: Stage 2 (Architecture Generation)
- **Content**:
  - IAM strategy (Pod Identity vs IRSA, access entries, node roles)
  - Pod security (PSA levels per namespace, Kyverno/Gatekeeper policies)
  - Network security (security groups, network policies, private endpoint access)
  - Encryption (KMS envelope encryption, in-transit TLS)
  - Secrets management (External Secrets Operator, Secrets Store CSI, KMS)
  - Image security (ECR scanning, admission control, private registry)
  - Audit and compliance (control plane logging, GuardDuty, CloudTrail)

### appendices/input-assessment-analysis.md

- **Created**: Stage 1 (Input Assessment)
- **Content**:
  - Document inventory and classification
  - Business context analysis
  - Technical context analysis (existing infrastructure, constraints)
  - Information gap analysis (critical, important, nice-to-have)
  - Generation readiness assessment (score, go/no-go)

### appendices/architecture-integration-validation.md

- **Created**: Stage 3 (Architecture Validation)
- **Content**:
  - Requirements coverage assessment
  - Component integration validation
  - AWS service limits impact assessment
  - Technical feasibility assessment
  - Documentation completeness review
  - Overall validation score and recommendation
- **Format**: See [architecture-validation.md](architecture-validation.md)

### appendices/iterations/score-sheet-iteration-X.md

- **Created**: Stage 4 (Quality Review)
- **Content**:
  - Overall score (0-100) with weighted category breakdown
  - Critical issues identified
  - Improvement recommendations
  - Score progression tracking across iterations
  - Go/no-go recommendation

## Naming Conventions

- **File names**: kebab-case (`system-architecture.md`, not `SystemArchitecture.md`)
- **ADR numbering**: Zero-padded, sequential (`ADR-001`, `ADR-002`)
- **Iteration numbering**: Sequential integers (`iteration-1`, `iteration-2`)
- **Modified files in iterations**: `-improved` suffix (`system-architecture-improved.md`)

## Organization Principles

- **Flat at root**: Maximum 2-3 levels deep
- **Clear separation**: Each folder has distinct purpose
- **Quality iterations**: Stored in `appendices/iterations/`, final content promoted to root
- **No duplication**: Information lives in one place, referenced elsewhere

## File Creation by Stage

| File | Stage | Task |
|------|-------|------|
| `appendices/input-assessment-analysis.md` | 1 | Input Assessment |
| `architecture/system-architecture.md` | 2 | Architecture Generation |
| `architecture/architecture-decision-records/` | 2 | Architecture Generation |
| `architecture/security-architecture.md` | 2 | Architecture Generation |
| `appendices/architecture-integration-validation.md` | 3 | Architecture Validation |
| `appendices/iterations/score-sheet-iteration-X.md` | 4 | Quality Review |
| `AGENTS.md` | 5 | Finalize & Handoff |
| `README.md` | 5 | Finalize & Handoff |

## Optional Artifacts

When document export is requested, the following are generated alongside the core structure:

```
projects/<project-name>/design/
├── scripts/                                     # Optional: document generators
│   ├── generate-docx.sh                         # Word export script
│   └── generate-pptx.sh                         # PowerPoint export script
└── exports/                                     # Optional: generated documents
    ├── architecture-document.docx
    └── architecture-presentation.pptx
```

These are NOT part of the core design output and are only created on explicit user request.
