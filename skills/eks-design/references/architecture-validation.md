# Architecture Validation Guide

Comprehensive validation of EKS architecture completeness, integration feasibility, and technical readiness before handoff to build.

## Table of Contents

- [Validation Framework](#validation-framework)
  - [Step 1: Requirements Coverage Assessment](#step-1-requirements-coverage-assessment)
  - [Step 2: Component Integration Validation](#step-2-component-integration-validation)
  - [Step 3: AWS Service Limits Assessment](#step-3-aws-service-limits-assessment)
  - [Step 4: Technical Feasibility Assessment](#step-4-technical-feasibility-assessment)
  - [Step 5: Documentation Completeness](#step-5-documentation-completeness)
- [Scoring Matrix](#scoring-matrix)
- [Validation Report Format](#validation-report-format)

## Validation Framework

### Step 1: Requirements Coverage Assessment

**Functional requirements**:
1. Extract ALL requirements from available inputs — every phase, every answer
2. Map each requirement to a specific section in `system-architecture.md`
3. Verify every requirement has both a narrative explanation AND an architectural solution
4. Document gaps — any requirement without a corresponding section is a FAIL

**CRITICAL — Comprehensive coverage check**: The `system-architecture.md` must address ALL of the following requirement areas. A design that only covers one domain (e.g., only security) while ignoring compute, networking, observability, etc. is INCOMPLETE and must score 0/25 on Requirements Coverage regardless of how thorough the single domain is.

**EKS-specific requirements coverage** (ALL mandatory unless marked conditional):

| # | Requirement Area | Architectural Solution | Mandatory? |
|---|-----------------|----------------------|-----------|
| 1 | Cluster creation | EKS cluster module, version, endpoint access | Yes |
| 2 | Node management | Compute strategy (Karpenter/MNG/Auto Mode), instance types, AMI | Yes |
| 3 | Networking | VPC CNI mode, subnets, ingress, DNS, IP planning | Yes |
| 4 | Security | IAM model, PSA, encryption, secrets, network policies | Yes |
| 5 | Addon deployment | Pattern selection (1/2a/2b), addon list with versions | Yes |
| 6 | Observability | Metrics, logs, traces stack decisions | Yes |
| 7 | Upgrades | Upgrade strategy, sequence, PDBs, disruption budgets | Yes |
| 8 | Cost & scalability | Cost strategies (Graviton, Spot, right-sizing), scaling guidance | Yes |
| 9 | DR & backup | Backup tiers, recovery scenarios, availability design | Yes |
| 10 | Multi-tenancy | Namespace isolation, RBAC, quotas, onboarding, cost attribution | If multi-tenant |
| 11 | Air-gapped | VPC endpoints, ECR pull-through, containerd mirrors | If air-gapped |
| 12 | Proxy | HTTP_PROXY injection, NO_PROXY list | If proxy required |
| 13 | Private registry | Image overrides, ImagePullSecrets | If private registry |
| 14 | Compliance | Policy engine, benchmark mapping, audit logging | If compliance required |

**Scoring rules for Requirements Coverage (/25)**:
- **0/25**: Design only covers 1-2 areas (e.g., only security) — automatic fail
- **5-10/25**: Design covers <50% of applicable areas
- **11-15/25**: Design covers 50-75% of applicable areas
- **16-20/25**: Design covers 75-95% of areas, some sections thin
- **21-25/25**: Design covers 95%+ of applicable areas with narrative + tables

**Coverage thresholds**:
- 95%+ requirements coverage to proceed
- 100% critical requirements coverage (no gaps in security, networking, compute)
- Every section must have narrative prose explaining WHY, not just configuration tables

### Step 2: Component Integration Validation

**Interface compatibility**:

| Source -> Target | Protocol | Auth | Data Format | Status |
|----------------|----------|------|-------------|--------|
| ALB -> EKS pods | HTTP/HTTPS | — | JSON/HTML | |
| EKS -> ECR | HTTPS | IRSA/PI | Container images | |
| EKS -> S3 | HTTPS | IRSA/PI | Objects | |
| ArgoCD -> Git | HTTPS/SSH | Token/Key | YAML manifests | |
| Karpenter -> EC2 | AWS API | IRSA/PI | Instance lifecycle | |
| External Secrets -> SM | AWS API | IRSA/PI | Secret values | |

**Data flow validation**:
1. Primary flows: Request -> ALB -> Pod -> Response
2. Addon flows: ArgoCD sync, Karpenter provisioning, External Secrets sync
3. Security flows: Authentication, authorization, audit logging
4. Monitoring flows: Metrics collection, log aggregation, alerting

### Step 3: AWS Service Limits Assessment

**Service inventory**: List all AWS services used in the architecture.

| Service | Usage | Criticality | Default Limit | Expected Usage | Risk |
|---------|-------|-------------|---------------|----------------|------|
| EKS | Cluster | High | 100 clusters/region | 1 | Low |
| EC2 | Nodes | High | Varies by type | [count] | [assess] |
| ENI | Pod networking | High | Varies by instance | [count] | [assess] |
| ALB/NLB | Ingress | High | 50/region | [count] | Low |
| ECR | Images | Medium | 10,000 repos | [count] | Low |
| S3 | State, backups | Medium | Unlimited | [count] | Low |
| IAM Roles | IRSA/PI | Medium | 1,000/account | [count] | [assess] |

**Risk levels**:
- **Low**: <50% of default limit
- **Medium**: 50-80% of default limit — request increase proactively
- **High**: >80% of default limit — requires mitigation before deployment

**EKS-specific limits to check**:
- Pods per node (ENI-based, check instance type)
- Managed node groups per cluster (30 default)
- Fargate profiles per cluster (10 default)
- EKS addons per cluster
- Security groups per ENI (5 default)
- IP addresses per subnet (for prefix delegation, this matters)

### Step 4: Technical Feasibility Assessment

**Technology validation**:

| Technology | Maturity | Team Expertise | Risk |
|-----------|----------|---------------|------|
| EKS [version] | GA | [assess] | |
| Karpenter [version] | GA | [assess] | |
| ArgoCD [version] | GA | [assess] | |
| Terraform [version] | GA | [assess] | |
| [each addon] | | | |

**EKS-specific feasibility checks**:
- [ ] Selected EKS version is currently supported
- [ ] Selected instance types are available in target region
- [ ] Selected addons are compatible with EKS version
- [ ] Karpenter version is compatible with EKS version
- [ ] VPC has sufficient IP space for nodes + pods (especially with prefix delegation)
- [ ] If air-gapped: all required VPC endpoints are available in target region
- [ ] If Graviton: all selected addons have arm64 images
- [ ] If GPU: selected GPU instance types are available in target AZs

### Step 5: Documentation Completeness

**Required documents checklist**:
- [ ] system-architecture.md — complete with all sections filled
- [ ] ADRs — one per required category (minimum 6)
- [ ] security-architecture.md — IAM, pod security, encryption, secrets, audit
- [ ] Mermaid diagrams — cluster topology, addon dependencies (minimum 2)
- [ ] Diagrams rendered to high-res PNG (4x scale, white background) in `diagrams/` folder
- [ ] If docx/pptx generated: all rendered PNGs embedded in the documents (not just Mermaid code blocks)

**ADR quality checklist**:
- [ ] Every ADR has at least 2 alternatives with pros/cons
- [ ] Every ADR has specific rationale (not generic "best practice")
- [ ] Every ADR has consequences (positive and negative)
- [ ] Every ADR has research sources

## Scoring Matrix

### Category Scoring

**1. Requirements Coverage (25 points)**

| Criteria | Points | Threshold |
|----------|--------|-----------|
| Functional requirements mapped | 10 | 95%+ = 10, 85-94% = 7, <85% = 4 |
| Non-functional requirements mapped | 10 | 95%+ = 10, 85-94% = 7, <85% = 4 |
| Constraint requirements addressed | 5 | All = 5, most = 3, gaps = 1 |

**2. Component Integration (20 points)**

| Criteria | Points | Threshold |
|----------|--------|-----------|
| Interfaces defined and compatible | 10 | All = 10, most = 7, gaps = 4 |
| Data flows documented | 5 | Complete = 5, partial = 3, missing = 1 |
| Integration patterns appropriate | 5 | All appropriate = 5, minor issues = 3 |

**3. Service Limits (15 points)**

| Criteria | Points | Threshold |
|----------|--------|-----------|
| All services identified | 5 | Complete = 5, most = 3, gaps = 1 |
| Limits analyzed | 5 | All = 5, high-risk only = 3, none = 0 |
| Mitigation for high-risk | 5 | All mitigated = 5, partial = 3, none = 0 |

**4. Technical Feasibility (20 points)**

| Criteria | Points | Threshold |
|----------|--------|-----------|
| Technology validation | 10 | All GA/validated = 10, some risk = 7, high risk = 4 |
| EKS-specific checks pass | 10 | All pass = 10, minor issues = 7, blockers = 0 |

**5. Documentation Completeness (20 points)**

| Criteria | Points | Threshold |
|----------|--------|-----------|
| Required documents present | 10 | All = 10, most = 7, major gaps = 4 |
| ADR quality | 5 | All pass checklist = 5, partial = 3, poor = 1 |
| Diagram quality | 5 | Mermaid in markdown + rendered PNGs in `diagrams/` + embedded in docx/pptx = 5, Mermaid only (no PNGs) = 3, missing = 0 |

### Overall Score

| Score | Status | Action |
|-------|--------|--------|
| 90-100 | Excellent | Proceed to build |
| 85-89 | Good | Proceed, minor improvements optional |
| 70-84 | Conditional | Address identified issues before proceeding |
| <70 | Failed | Significant rework needed |

**Minimum to proceed**: 85/100 with no critical failures in any category.

## Validation Report Format

```markdown
# Architecture Integration Validation Report

## Executive Summary

- **Overall Score**: X/100
- **Status**: [PASSED / CONDITIONAL / FAILED]
- **Key Findings**: [3-5 bullet points]
- **Recommendation**: [Proceed / Address issues / Rework]

## Requirements Coverage: X/25

[Details per criteria]

## Component Integration: X/20

[Details per criteria]

## Service Limits: X/15

[Details per criteria]

## Technical Feasibility: X/20

[Details per criteria]

## Documentation Completeness: X/20

[Details per criteria]

## Critical Issues

[List any blocking issues]

## Recommendations

[Prioritized improvement list]

## Next Steps

[Clear actions to address gaps or proceed to quality review]
```
