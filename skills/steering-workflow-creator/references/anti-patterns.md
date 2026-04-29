# Anti-Patterns in Steering Workflows

A catalogue of drift observed between `steering/workflows/design.md` and `steering/workflows/upgrade.md` — the two existing workflows in this repo — plus a few more the convention was designed to head off before they appeared. Each entry shows a bad fragment, a good fragment, and one sentence on why.

Authors: read this file when you finish a draft. The linter will quote these entries in its error messages, so fixing them once here is a fix everywhere.

A note on tone: "bad" doesn't mean "the author was wrong." Some of these inconsistencies are artifacts of the workflows being written at different times, for different audiences, before any convention existed. The convention exists now; new drafts should conform to it.

---

## 1. `--` instead of em-dash

**Bad** (from `upgrade.md`):

```
> **Lifecycle:** Day 2 -- Operate
```

**Good** (from `design.md`):

```
> **Lifecycle:** Day 0 — Architect
```

Why: `--` is a typewriter-era workaround. Modern markdown renderers and terminals all handle `—` (U+2014) cleanly. Pick one and stick to it — the convention picks em-dash because `design.md` got there first and it's more readable at a glance.

---

## 2. Missing `Access Model` in the header block

**Bad** (from `design.md`):

```
> **Part of:** [APEX EKS Hub](../eks.md)
> **Lifecycle:** Day 0 — Architect
> **Skill:** `eks-best-practices`
```

**Good** (pattern from `upgrade.md`, applied):

```
> Part of: [APEX EKS Hub](../eks.md)
> Lifecycle: Day 0 — Architect
> Skill: eks-best-practices
> Access Model: advisory
```

Why: Access Model is a contract with the user about what the agent will and won't do on their behalf. Omitting it makes a read-only review workflow indistinguishable from a mutating execution workflow in the header. The convention promotes it from optional to required.

---

## 3. Missing `## Defaults` section

**Bad** (from `upgrade.md`): no `## Defaults` section exists. Default behaviors are scattered throughout phases.

**Good** (from `design.md`):

```markdown
## Defaults

| Setting | Default |
|---------|---------|
| Account model | Single account |
| Compute strategy | Karpenter |
| ...
```

Why: when defaults live inside phases, two phases can silently disagree about what the default is. Centralizing them in a table forces the disagreement to be visible and resolvable.

---

## 4. Missing `## Quality Checklist` section

**Bad** (from `upgrade.md`): no self-grading rubric. The workflow produces plans and reports but never scores them before handoff.

**Good** (from `design.md`):

```markdown
## Quality Checklist

| Dimension | Weight (Full) | Weight (Focused) | What to Check |
|---|---|---|---|
| Security | 20% | Score if in scope | IAM model defined, ... |
| Reliability | 20% | Score if in scope | Multi-AZ topology, PDBs, ... |
...

### Scoring Rules
| Score | Status | Action |
|---|---|---|
| 80-100% | Pass | Present to user |
| 60-79% | Gaps found | Fix identified gaps, re-check |
```

Why: workflows produce recommendations the user acts on. Without a scoring pass, the agent has no forcing function to catch its own weakly-justified output. `design.md` has one; `upgrade.md` ought to.

---

## 5. Inconsistent STOP-gate syntax

**Bad** (from `upgrade.md`):

```
STOP on ERROR findings -- present them and ask user to resolve before continuing.
```

**Good** (convention):

```
**STOP.** ERROR findings must be resolved before proceeding. Present them to the user and wait for resolution.
```

Why: a consistent bold-STOP-period marker makes gates greppable for the linter and visually unmissable for the agent. Inline `STOP` mid-sentence blends into surrounding prose. Pick one form (`**STOP.** `) and use it everywhere.

---

## 6. Unicode-vs-ASCII arrow drift inside the same repo

**Bad** (both exist, inside the same repo):

```
# design.md
→ Single platform team? Platform + tenant teams? Federated?
```

```
# upgrade.md
Phase 1: Gather Context        -> Read cluster state, detect IaC
```

**Good:** pick one per medium. In prose and user-facing tables, use `→` (U+2192). In ASCII-art diagrams inside code blocks, `->` is acceptable because terminal fonts render `→` inconsistently. The convention pins: prose = `→`, code-block diagrams = `->`.

Why: readers flipping between workflows notice the inconsistency before they notice the content. Pin the choice and move on.

---

## 7. Phase structure without a `Source:` annotation

**Bad** (both `design.md` and `upgrade.md`): phases don't declare whether they draw from knowledge, live data, or both. The agent has to infer.

**Good** (convention):

```markdown
### Phase 2: Pre-flight Validation

Source: live

Run read-only checks against the cluster. CLI fallback for each check is named inline.
```

Why: the `Source:` annotation is a half-second for the author and saves the agent from misreading intent. A phase that looks advisory but is actually checking live state will silently use stale knowledge in a bad moment.

---

## 8. Missing CLI fallback on `live` phases

**Bad**: a phase says "use MCP tools to check add-on status" and stops there. When MCP is unavailable, the agent invents a CLI command and often gets it wrong.

**Good:**

```markdown
### Check 4: Add-on Compatibility

Source: live

MCP:  list_eks_resources(resource_type="addon", cluster_name="<cluster>")
CLI fallback:
  aws eks describe-addon-versions --addon-name <name> \
    --kubernetes-version <target> --query '...'
```

Why: every `live` phase has to survive MCP being absent. Named fallbacks keep behavior deterministic; hand-waved fallbacks invite hallucinated commands. Covered in detail in `tool-routing.md`.

---

## 9. Duplicated reconnaissance logic inside the workflow

**Bad**: a workflow describes how to detect Karpenter, how to spot the IaC tool, how to enumerate add-ons — effectively re-implementing `eks-recon` inline.

**Good**: the workflow delegates to `eks-recon` for the detection, reads the resulting YAML, and moves on.

Why: reconnaissance is reusable. Inline detection logic drifts faster than anything else in the repo because it's the part authors copy-paste and tweak. Centralize it in the discovery skill — for EKS that's `eks-recon`; for future services, an analogous skill.

---

## 10. `inclusion: manual` on a workflow file

**Bad:**

```yaml
---
name: design
description: ...
inclusion: manual
---
```

**Good:**

```yaml
---
name: design
description: ...
---
```

Why: `inclusion: manual` is for hub files like `steering/eks.md` that the agent loads only when routing into the service. Workflows are loaded from hub routing tables and command shims — they don't need (and shouldn't carry) the `inclusion` key. Stripping it keeps the distinction between hub and workflow legible.
