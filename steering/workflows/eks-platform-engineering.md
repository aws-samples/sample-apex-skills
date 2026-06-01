---
name: eks-platform-engineering
description: Day 1 platform-engineering workflow. Guides building an Internal Developer Platform on EKS — golden paths, developer portal (Backstage), GitOps and progressive delivery, self-service infrastructure (ACK/KRO), tenancy, AI/ML golden paths, and measuring success with DORA.
---

# EKS Platform Engineering Workflow

> **Part of:** [APEX EKS Hub](../eks.md)
> **Lifecycle:** Day 1 — Build
> **Skill:** eks-platform-engineering | golden-paths.md, gitops-delivery.md
> **Access Model:** advisory

This workflow guides a platform team through designing and building an Internal Developer Platform (IDP) on EKS — the paved paths that let app, ML, and data teams self-serve. It produces an opinionated build plan and recommendations; it does not read or mutate a live cluster. All domain knowledge comes from the `eks-platform-engineering` skill; this workflow supplies the engagement structure.

## How to Route Requests

| User intent | Mode / Phase |
|---|---|
| "Build an Internal Developer Platform" / "give app teams self-service on EKS" | Full build plan → Phase 1 → 2 → 3 → 4 |
| "Design our golden paths / paved paths" | Scoped → Phase 1 (abbreviated) → 2 |
| "Set up Backstage / a developer portal" | Scoped → Phase 1 (abbreviated) → 2 (portal focus) |
| "Wire GitOps / progressive delivery / multi-stage promotion" | Scoped → Phase 2 (delivery focus) → 3 |
| "Let developers self-provision AWS infra (ACK/KRO)" | Scoped → Phase 2 → 3 (infrastructure abstraction) |
| "Extend the platform for AI/ML or data teams" | Scoped → Phase 2 → 3 (AI/ML golden paths) |
| "How do we measure if our platform is working?" | Summary → Phase 4 only |

If the request is a single platform-concept question rather than a build engagement, answer directly from the `eks-platform-engineering` skill and skip the phases.

## Phases

### Phase 1: Platform discovery and scope

Source: knowledge

Establish who the platform serves and what self-service to enable before choosing any tool. An unclear scope here produces a tool list nobody asked for, so slow down until the answers are crisp.

Required inputs — ask for these in a single turn:

- Consumer teams and rough count (app teams, ML/data teams, tenancy model).
- The top deployment pain today (ticket-driven infra, snowflake pipelines, no paved path).
- Which self-service capabilities to enable first (ship a service, provision infra, scaffold a repo, run an ML/data job).
- Existing stack to build on or replace (portal, GitOps engine, registry, CI, IaC).
- Constraints (air-gapped, compliance, multi-account, existing ArgoCD/Backstage investment).

If the user already has an `eks-recon` report or an architecture doc, read it first and skip questions it already answers — do not re-quiz them.

**STOP.** Restate the consumer teams, the first golden paths to build, and the existing stack. Confirm before selecting tools.

### Phase 2: Golden-path and tool-stack selection

Source: knowledge

Choose the opinionated stack for the golden paths confirmed in Phase 1. Load the skill's decision material rather than improvising: `../../skills/eks-platform-engineering/references/golden-paths.md` for the four core paths, plus the matching capability reference — `developer-portal-backstage.md`, `gitops-delivery.md`, `progressive-delivery.md`, and `infrastructure-abstraction.md`. Read `application-model-oam.md` only if the team wants to abstract Kubernetes YAML away from developers.

For each golden path in scope, present the recommended tool, the trade-off, and one alternative — do not hand the user a generic matrix to interpret. Default to the PEEKS stack in the Defaults table unless the user's existing investment or constraints override it.

**STOP.** Confirm the per-path tool choices before moving to architecture. Flag any choice that conflicts with a Phase 1 constraint.

### Phase 3: Platform architecture and tenancy

Source: knowledge

Frame how the chosen tools compose into a platform. Use `../../skills/eks-platform-engineering/references/idp-architecture.md` for the hub-and-spoke topology and `identity-and-tenancy.md` for tenant isolation, RBAC, and namespace/provisioning boundaries. If the platform serves ML or data teams, fold in `genai-platform-engineering.md` and `aiml-data-platform.md` for those golden paths.

Produce: the topology (hub control plane vs spoke workload clusters), where the portal, GitOps engine, and infra controllers run, and how a new tenant is onboarded end to end.

**STOP.** Confirm the topology and tenancy model before drafting the roadmap.

### Phase 4: Roadmap and measuring success

Source: knowledge

Turn the decisions into a phased rollout and a way to prove it works. Use `../../skills/eks-platform-engineering/references/measuring-success.md` for the DORA metrics and platform-adoption signals to instrument from day one.

Deliver: a sequenced build roadmap (portal → first golden path → GitOps → progressive delivery → self-service infra → measurement), the metrics to track, and the first milestone. Run the Quality Checklist before presenting.

**STOP.** Present the plan and wait for the user's reaction before chaining into a design or build follow-up.

## Defaults

| Default | Value | Override when |
|---|---|---|
| Developer portal | Backstage | Existing portal (Port, Cortex) already adopted |
| GitOps delivery | ArgoCD | Team is standardized on Flux |
| Progressive delivery | Argo Rollouts (canary + auto-rollback) | Service mesh already provides traffic shifting |
| Multi-stage promotion | Kargo | Single environment, no promotion needed |
| Self-service infrastructure | ACK + KRO compositions | Crossplane already in place |
| Application model | Plain manifests + Helm | Team wants to hide Kubernetes → add OAM/KubeVela |
| Topology | Hub-and-spoke (management + workload clusters) | Single cluster, single team |
| Tenancy | Namespace-per-team + RBAC + quotas + network policy | Hard multi-tenancy needs separate clusters |
| Success metrics | DORA + platform adoption rate | Org tracks a different delivery metric set |
| AI/ML golden paths | Off | Phase 1 names ML or data teams as consumers |

## Quality Checklist

Self-grade before presenting the plan. Each item is binary — passes or fails.

- [ ] Every Phase 1 consumer team and first golden path maps to a concrete recommendation in the plan.
- [ ] Each tool choice cites the trade-off and one alternative, not just the default.
- [ ] The topology names where the portal, GitOps engine, and infra controllers run.
- [ ] Tenant onboarding is described end to end, not left as "set up RBAC".
- [ ] The roadmap is sequenced with a named first milestone, not a flat feature list.
- [ ] Success metrics (DORA + adoption) are specified before any build starts.

Pass threshold: 5/6. Below 4/6 means rework — most often the plan defaulted to the tool stack without grounding it in this team's Phase 1 answers.

## Conversation Style

- Be concise. Group related questions — Phase 1's inputs go in one turn, not five.
- If given an `eks-recon` report or an existing architecture doc, read it first and only ask what is missing.
- Explain routing when activating a mode — say which golden paths you are scoping to and why.
- Recommend, don't enumerate. Name the default and the trade-off; reach for the full matrix in the skill only when the user pushes back.
- When a STOP gate fires, name the one decision you need before proceeding.
