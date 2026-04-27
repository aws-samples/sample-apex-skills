# Worked Example: EKS Tool Routing

This file shows how the service-agnostic tree in `../tool-routing.md` plays out for an EKS-flavored workflow. It is not a full workflow — it's an annotated slice that demonstrates how to pick the discovery skill, the setup-bridge, and the `knowledge | live | either` annotation on each phase.

When another AWS service is added (RDS, Lambda, IAM, …), **drop a sibling file here**, do not modify this one. Each service gets its own worked example. The rule itself stays service-agnostic in `tool-routing.md`.

---

## The EKS trio

Three skills in this repo map onto the three information sources:

| Role | Skill | What it is |
|---|---|---|
| Discovery / Phase 1 context | `eks-recon` | Reads cluster state and emits a structured YAML report. Works against MCP if available, CLI if not. |
| Advisory knowledge | `eks-best-practices`, `eks-upgrader` | Static authored references — decision frameworks, upgrade procedures, add-on compatibility notes. |
| Setup-bridge | `eks-mcp-server` | Walks the user through configuring the EKS MCP Server when it isn't already wired up. |

An EKS workflow author should assume all three exist and route into them. Do not reinvent reconnaissance logic inline, do not duplicate best-practice content, do not write your own MCP setup guide.

---

## Phase 1 — `Source: knowledge` (with live-assisted discovery via `eks-recon`)

Phase 1 of any EKS workflow gathers cluster context. The recommendation framework for "what to gather" is knowledge; the values themselves come from live tools via `eks-recon`.

**Annotation:**

```
Source: knowledge (context framework); discovery via eks-recon
```

**What the phase looks like in practice:**

- Enumerate the required context items (cluster name, region, version, compute strategy, IaC tool, etc.). This list is authored — it lives in the workflow itself, framed by `eks-recon`'s module structure.
- Delegate the actual gathering to `eks-recon` if the user hasn't already run it. Example directive inside the phase: *"If you haven't run `eks-recon` yet, run it first — I need the cluster-basics and compute modules. Otherwise, point me at the report."*
- Read the resulting YAML into context. Skip questions already answered by the report.

**Why not just call MCP tools directly?** Because reconnaissance is a reusable concern. `eks-recon` is where the detection patterns live (including how to tell Karpenter from MNG from Auto Mode). Duplicating that logic across every EKS workflow is exactly the drift this skill is built to prevent.

---

## Phase 2 — `Source: live` (with named CLI fallback)

A pre-flight check phase that inspects the deployed cluster for blockers. Version numbers, insight findings, add-on statuses, PDB audits — all ground truth, all live.

**Annotation:**

```
Source: live
```

**MCP path (preferred):**

```
# EKS MCP Server tools
get_eks_insights(cluster_name="<cluster>")
list_eks_resources(resource_type="addon", cluster_name="<cluster>")
list_k8s_resources(cluster_name="<cluster>", kind="PodDisruptionBudget", api_version="policy/v1")
```

**CLI fallback (named explicitly):**

```bash
aws eks list-insights --cluster-name <cluster> --filter 'statuses=ERROR,WARNING'
aws eks list-addons --cluster-name <cluster>
kubectl get pdb -A -o json
```

**What happens when MCP is unavailable:**

1. The agent detects MCP tools aren't in the available-tools list.
2. It offers the `eks-mcp-server` skill: *"MCP tools aren't available. I can walk you through setting up the EKS MCP Server (roughly five minutes), or I can proceed with CLI calls at reduced confidence. Which do you prefer?"*
3. On user approval, hand off to `eks-mcp-server` → user configures → agent retries MCP.
4. If the user declines setup or the environment blocks it, run the CLI fallback and announce reduced confidence per `../tool-routing.md`.

Why named commands, not "use the AWS CLI": the agent invents bad CLI syntax surprisingly often. Naming the exact command pins the behavior.

---

## Phase 3 — `Source: either`

A decision-framing phase that helps the user pick between two paths — say, in-place versus blue-green upgrade. The framework for the decision (trade-offs, criteria, reversibility) is authored knowledge. The inputs to the decision (current version, compute strategy, deployed add-ons) are live.

**Annotation:**

```
Source: either (framework from eks-upgrader; cluster specifics from live / Phase 1 report)
```

**What the phase looks like in practice:**

- Load `../../skills/eks-upgrader/SKILL.md` for the in-place-vs-blue-green decision framework.
- Pull the cluster specifics from the Phase 1 `eks-recon` report (or from live MCP calls if Phase 1 was skipped).
- Present the trade-off table with this cluster's values filled in — don't give the user a generic trade-off table they have to interpret themselves.

**Why `either` is not a cop-out:** splitting into two phases would force the user through a pure-reading phase before any customization, which reads as busywork. The `either` annotation tells the agent "you need both, weave them together," and tells the next author "don't split this without a reason."

---

## Cheat sheet for EKS-flavored phases

A quick lookup for the annotation you'd pick for common EKS phase types:

| Phase intent | Source | Notes |
|---|---|---|
| Gather cluster context | `knowledge` with `eks-recon` discovery | Framework authored; values live through the recon skill |
| Pre-flight / current-state checks | `live` | CLI fallback required |
| Pick an upgrade path / architecture option | `either` | Framework from knowledge; inputs from live |
| Generate a customized runbook | `knowledge` | Templates and procedures come from `eks-upgrader` references |
| Execute mutations | n/a | Workflows in this repo don't mutate directly — they advise. Access Model says why. |
| Post-action validation | `live` | CLI fallback required |

---

## When the user's environment is locked down

Not every user can install MCP tooling. Air-gapped environments, restricted laptops, customers running inside their own VPC with no outbound internet — all real. An EKS workflow should:

1. Detect the constraint early (Phase 1 can ask: *"Are you working in an air-gapped or locked-down environment?"*).
2. Skip the `eks-mcp-server` setup offer in that case — recommending a setup the user can't do is noise.
3. Route every `live` phase directly to the CLI fallback and carry the reduced-confidence notice end to end.

The three-way tree still applies; Step 3 just resolves immediately to CLI rather than to the bridge.

---

## Summary

For EKS workflows:

- Phase 1 uses `eks-recon` as the discovery skill.
- `live` phases prefer the EKS MCP Server, fall back to `eks-mcp-server` as the setup-bridge, fall back to named CLI commands.
- Advisory content comes from `eks-best-practices` and `eks-upgrader`.
- No phase writes its own reconnaissance logic, best-practice content, or MCP setup guide — all three already exist as skills.

For other AWS services, swap the skill names and the MCP server, keep the structure. Add a sibling file in this directory when you do.
