---
name: new-skill
description: Meta contributor workflow. Onboards a new skill end-to-end — scope intake, optional skill-creator drafting, sibling-graph survey, repo fan-out diff, eval scaffold and finalization, and baseline PR prep. Bimodal — greenfield authoring or retrofit on an existing skill that skipped the process.
---

# New-Skill Onboarding Workflow

> Part of: [APEX Meta Hub](../apex.md)
> Lifecycle: Day 0 — Architect
> Skill: steering-workflow-creator | ../../skills/skill-creator/SKILL.md
> Access Model: mutating (with gates)

This workflow walks a contributor through adding a new skill to the repo — both its content and its obligations to the rest of the repo (catalogues, eval set, sibling disambiguation). It is bimodal. In greenfield mode the `skill-creator` skill drafts the skill first. In retrofit mode the skill already exists and the workflow focuses on the obligations the original contributor missed. Both modes converge on sibling-graph survey, repo fan-out, eval scaffold, and baseline.

### Access Model expansion

CAN: scaffold files under `misc/evals/<skill>/`, edit catalogue READMEs and sibling eval sets as proposed diffs at each STOP gate, invoke `skill-creator` to draft `skills/<skill>/SKILL.md`, run `make init-evals` and `make init-evals-finalize` locally, run `make validate-<skill>` and `make triggering-<skill>` for the baseline.

CANNOT: merge the PR, push to protected branches, bypass the hygiene gate in CI, author redundant knowledge skills to sit "behind" this workflow (the workflow orchestrates two existing brains — `skill-creator` for drafting and this repo's `misc/evals/` machinery for scaffolding — do not add a third).

## How to Route Requests

| User intent | Mode / Phase |
|---|---|
| "Add a new skill `<name>`" / "I want to create a skill for X" | Greenfield → Phase 1 → 2 → 3 → 4 → 5 → 6 |
| "Onboard `<name>` end to end, it doesn't exist yet" | Greenfield → Phase 1 → 2 → 3 → 4 → 5 → 6 |
| "Retrofit evals for `<name>` — the skill already exists but its eval set doesn't" | Retrofit → Phase 1 → 3 → 4 → 5 → 6 (skip Phase 2 — drafting) |
| "`<name>` exists on disk but it's missing catalogue entries / sibling map / eval scaffold" | Retrofit → Phase 1 → 3 → 4 → 5 → 6 |
| "Just scaffold evals for `<name>`, nothing else" | Out of scope → point the user at `make init-evals SKILL=<name>` and stop. Running only step 5 without the sibling survey and fan-out is exactly the honor-system failure this workflow exists to prevent. |

Detect mode in Phase 1 — if `skills/<name>/SKILL.md` exists, the mode is retrofit; if it doesn't, greenfield. Confirm with the user before branching.

## Phases

### Phase 1: Scope intake and mode detection

Source: knowledge

Goal of this phase: get crisp answers to the five scope questions below and decide whether to branch into Phase 2 (greenfield drafting) or skip straight to Phase 3 (retrofit). An unclear scope at this point produces a skill with a fuzzy description, which produces a triggering eval set with soft positives and soft negatives, which makes the scorecard noise — slow down here rather than paying for it later.

Required inputs — ask for all five in a single turn:

1. **Skill slug** (`<name>`) — lowercase, hyphenated, matches the target `skills/<name>/` directory.
2. **One-sentence scope** — what the skill covers and for whom. This becomes the seed for the `description:` frontmatter that the triggering eval scores against.
3. **Five example prompts the skill should trigger on** — positives. Ask for the phrasings a real user would type, not a tidy canonical form.
4. **Which kind of skill** — knowledge (static references), setup-bridge (one-shot env configuration), or discovery (reads live state and emits a structured report). Matches the three classes in `../../skills/steering-workflow-creator/references/tool-routing.md`.
5. **Target service and nearest service hub** — EKS, RDS, Lambda, or "service-agnostic / meta." Drives later fan-out (which service hub picks up the routing, which example file under `steering-workflow-creator/references/examples/` applies).

Mode detection:

- If `skills/<name>/SKILL.md` exists → **retrofit mode**. Skip Phase 2. Treat the existing skill as the spec; do not rewrite it unless the author explicitly asks.
- If `skills/<name>/` does not exist → **greenfield mode**. Proceed to Phase 2.

**STOP.** Restate the five answers plus the detected mode back to the author. Confirm before proceeding. If the scope is fuzzy ("a skill about security"), push back — narrower scope now saves rework later.

### Phase 2: Draft the skill via `skill-creator` (greenfield only)

Source: knowledge

Skip this phase in retrofit mode.

Goal of this phase: produce `skills/<name>/SKILL.md` plus any `references/`, `scripts/`, `assets/`, `agents/` subdirectories the skill needs. The orchestration is standard — load `../../skills/skill-creator/SKILL.md`, follow its drafting guide, and materialize the files. Do not re-implement drafting logic here.

The output should include at minimum:

- `skills/<name>/SKILL.md` with frontmatter (`name`, `description`, optional `license`) and a `# <Title>` H1, followed by the body.
- Any `references/*.md` files the skill points at via `@references/...`.
- Any `scripts/` files the skill references (keep minimal — scripts tend to rot; prefer prose).

Pay particular attention to the `description:` frontmatter. The triggering eval scores exactly this string — a vague description makes the skill fail its own eval. Aim for one tight sentence naming the domain + the concrete verbs users will type.

After drafting, run `make validate-<name>` from `misc/evals/` to confirm the frontmatter lints clean (64-char name cap, 1024-char description cap, YAML well-formed).

**STOP.** Present the draft SKILL.md. Author reviews and sharpens the `description:` before Phase 3. If the author wants deeper iteration on the skill content, loop inside Phase 2 — do not advance to Phase 3 until the skill is something the author is willing to ship.

### Phase 3: Survey the sibling graph

Source: knowledge

Goal of this phase: identify the 0-to-N skills whose descriptions overlap with `<name>` in surface vocabulary or domain. Neighbours become the fan-out targets in Phase 4 and the sources of the near-miss negatives in Phase 5. **Zero neighbours is a legitimate answer** — a meta-skill or a lone service entry may have no true siblings, and padding the sibling list with skills that do not actually compete for trigger routing produces noisy negatives that hurt the scorecard rather than helping.

Steps:

1. Enumerate every `skills/<peer>/SKILL.md` in the repo. Read each frontmatter `description:` line only — that's what the triggering eval sees.
2. For each peer, score overlap against `<name>`'s description on two axes: shared vocabulary (does a user prompt for `<name>` plausibly mention the peer's verbs?) and shared domain (same AWS service, same lifecycle phase). Ignore upstream-synced skills — `skill-creator` and `terraform-skill` are maintained externally and are excluded from this repo's eval matrix.
3. Propose a ranked list of candidates with a one-line rationale per candidate. Example: `- eks-upgrader — same service (EKS), adjacent lifecycle (Day 2), a prompt mentioning "upgrade" could land on either.`
4. Explicitly call out non-neighbours that a reader might expect to see on the list but are not siblings — this prevents the author from adding them reflexively. Example: `steering-workflow-creator is not a sibling of eks-best-practices — different domain (meta-authoring vs EKS knowledge), no vocabulary overlap.`

Heuristics for how many siblings to pick:

- A service-scoped knowledge skill typically has 1-3 siblings (other skills in the same service bucket).
- A service-scoped workflow-adjacent skill (discovery, setup-bridge) usually has 0-2 siblings.
- A meta-skill (authoring, linting, cross-service) may have 0 siblings. Do not invent cross-domain overlap to fill the list.

**STOP.** Present the ranked candidate list. Author confirms, edits, or zeroes it out. The confirmed list is the input to every subsequent phase — getting it wrong here propagates through fan-out, scaffold, and baseline.

### Phase 4: Fan out across the repo

Source: knowledge

Goal of this phase: find every place in the repo that lists, catalogues, or routes to skills, and produce a single concrete diff across all of them. **Do not ship a hardcoded file list inside this workflow** — teach the agent what kinds of places to survey and let it discover the instances. When someone adds a new skills index or service hub six months from now, the survey finds it without this file needing an edit.

Classes of places to survey. For each class, `grep` with a reasonable search, enumerate hits, and propose a diff:

- **Repo skill catalogues** — `skills/README.md`'s "Current Skills" table; any top-level `README.md` mention.
- **Contributor docs** — `CONTRIBUTING.md`'s "Current Skills" table and surrounding prose.
- **Service hubs** — `steering/<service>.md` routing tables, when the skill is service-scoped. For meta-skills, check `steering/apex.md`.
- **Steering workflows** — `steering/workflows/*.md`. If any existing workflow should start delegating to the new skill, flag it (do not silently rewrite another workflow's routing — that is a separate review).
- **Sibling eval sets** — for each neighbour confirmed in Phase 3, `misc/evals/<sibling>/README.md`'s SIBLING_MAP block and `misc/evals/<sibling>/triggering.json`. This is the update the `update_sibling_map.py` helper script handles in Phase 5; surface the planned edits here so the author can review what will be inserted.
- **Auto-generators** — `misc/update-steering-references.sh` and any sibling scripts. If the skill triggers a run of these, flag it.
- **Grep pass** — `grep -r "<name>" -l .` to catch anything the class list missed. Mentions in changelogs, screenshots, example output — each one decides on its own merits.

For each proposed edit, show the file, the line, the before, and the after. Use the Edit tool or the `update_sibling_map.py` helper (Phase 5) depending on the edit type. Do not apply anything yet — this phase produces a proposal, Phase 5 applies it.

**STOP.** Present the fan-out diff as a single review unit. Author confirms, amends, or removes entries before Phase 5 applies them. If the list is empty except for the skill catalogue, that is fine — short fan-out is better than fabricated fan-out.

### Phase 5: Scaffold evals, apply fan-out, finalize

Source: knowledge

Goal of this phase: materialize `misc/evals/<name>/`, apply the sibling-map updates from Phase 4, draft the 16-prompt triggering set plus 2-prompt task set, and confirm `make init-evals-finalize` passes locally before the author opens a PR.

Steps, in order:

1. **Scaffold.** Run `make init-evals SKILL=<name>` from `misc/evals/`. If the sibling list from Phase 3 is non-empty, pass `SIBLINGS="a,b,c"` — the Makefile renders a sibling-aware `README.md` and a pre-structured `triggering.json` skeleton with placeholder slots per sibling. If the list is empty, omit `SIBLINGS=` and the scaffold falls back to today's 2-entry template.
2. **Apply fan-out to siblings.** For each neighbour confirmed in Phase 3, invoke `python misc/evals/scripts/update_sibling_map.py --new-skill <name> --target-sibling <sibling> --scope "<one-line scope>" --negative-prompt "<prompt routing to new-skill>" [--negative-prompt "<prompt 2>"]`. The helper appends the negative prompts to the sibling's `triggering.json`, computes their indices, and inserts a new bullet into the sibling's SIBLING_MAP block with those indices spliced in. The helper handles only mechanical insertion — the agent composes the scope blurb and the negative-prompt phrasings, which are the creative part.
3. **Author the new skill's own triggering.json.** Expand to 16 prompts: 8 positives matching the example phrasings from Phase 1 (plus near-paraphrases), 8 negatives split across the Phase 3 siblings (phrased to sound like requests that should route to each named sibling). If the sibling list is empty, use catchall negatives (other services, unrelated domains) and note them under a `Generic / non-<service>` bucket in the SIBLING_MAP block.
4. **Author the new skill's evals.json.** Draft 2 realistic task prompts with ≥3 grader-checkable expectations each. Every assertion tagged `TODO: human review` until the author tunes it against a real `make task-<name>` run.
5. **Fill in the README.** Replace `<REPLACE>` markers: scope description, neighbour-skill disambiguation prose referencing the SIBLING_MAP bullets, live-MCP caveat (or "no live dependencies" if the skill is pure knowledge), how-to-run block.
6. **Finalize.** Run `make init-evals-finalize SKILL=<name>`. The target enforces the same hygiene pre-flight that CI runs — positive count ≥ 8, negative count ≥ 8, SIBLING_MAP parseable, every negative index attributed, evals.json shape. Exit 0 means Phase 5 is done; non-zero means fix the diagnostic and re-run. Do not advance on warnings.

**STOP.** Author confirms the finalize output is green. If `init-evals-finalize` passes but the author wants to edit any of the files, loop here — the hygiene gate is the floor, not the ceiling.

### Phase 6: Baseline and PR prep

Source: knowledge

Goal of this phase: produce the first baseline rows for the scorecard, update the contributor checklist, and leave the PR ready to open.

Steps:

1. **Baseline triggering.** Run `make triggering-<name>` from `misc/evals/` to produce a first live-model score. The row lands under `misc/evals/<name>/workspace/runs/<UTC>/metrics.json`. Commit nothing from `workspace/` — it is gitignored.
2. **Append history row.** Run `make score` to refresh the scorecard, which appends a compact row to `misc/evals/history/<name>.jsonl` (committed; 50-entry cap). The readme scorecard re-renders between its markers. Commit the updated `misc/evals/README.md` and the new history row as part of the PR.
3. **Baseline task axis (if applicable).** For skills that do not require a live cluster, run `make task-<name>` to produce the first `benchmark.json` and a `kind="task"` history row. Skills that require a live cluster (eks-recon-like) need the two-layer sandbox from `misc/evals/setup/bootstrap-readonly.sh` first; if that is not set up in the contributor's environment, skip this step and note it in the PR body.
4. **Run the Quality Checklist below.** Self-grade the work produced across all phases.
5. **Prepare the PR.** Walk the author through the Pre-PR checklist in `../../CONTRIBUTING.md` (the items are the same artefacts this workflow produces; the checklist exists so a hand-crafted path lands the same shape). Fill in the PR template checkbox confirming the workflow was followed.

CLI fallback: none — this phase is entirely knowledge-sourced and shell-based. The `claude -p` subprocess inside `make triggering-<name>` and `make task-<name>` talks to Bedrock / Anthropic, but those are the subject model calls, not calls this workflow makes directly.

**STOP.** Summarize what landed, what the scorecard shows, and the suggested PR title (`feat(skills): add <name> skill`). Hand off to the author. Do not open the PR yourself — that is the author's action.

## Defaults

| Default | Value | Override when |
|---|---|---|
| Sibling count | 0-3 skills selected from the Phase 3 candidate list | Author explicitly overrides with a different count |
| Triggering eval size | 16 prompts — 8 positives, 8 negatives | Author explicitly expands for a skill with broad scope |
| Task eval size | 2 prompts with ≥3 expectations each | Skill has no runnable tasks (knowledge-only edge case); note in README |
| Live-cluster baseline | Skipped in Phase 6 unless `misc/evals/.secrets/` is already populated | User has run `bootstrap-readonly.sh` and opts in |
| Fan-out auto-apply | Off — every edit is proposed and confirmed before applying | Never. The STOP gates exist because this is where PR #24 went wrong. |
| `SIBLINGS=` arg to `init-evals` | Passed when Phase 3 confirmed ≥ 1 neighbour | Omitted when Phase 3 returned zero siblings |

## Quality Checklist

Self-grade before handing off to the author. Each item is binary — passes or fails.

- [ ] Phase 1 scope summary restated verbatim, and the author confirmed all five inputs before Phase 2 started.
- [ ] Phase 2 produced a `SKILL.md` that passed `make validate-<name>`. Skipped in retrofit mode — that skip is itself a passing answer here.
- [ ] Phase 3 sibling list has explicit rationale per candidate, and non-neighbours that a reader would expect to see are explicitly ruled out.
- [ ] Phase 4 fan-out diff is concrete — every entry names a file, a line, and a before/after — not a generic "update the catalogue" bullet.
- [ ] Phase 5 `make init-evals-finalize SKILL=<name>` exited 0. The hygiene gate is the floor; no advancing on warnings.
- [ ] Phase 6 produced a `history/<name>.jsonl` row and (if applicable) a `benchmark.json`. The scorecard in `misc/evals/README.md` re-rendered cleanly.
- [ ] No redundant knowledge skill was authored "behind" this workflow. The only new skill in the PR is `<name>`.
- [ ] Sibling-map updates to neighbours are in this PR, not split off. Adding `rds-best-practices` means `eks-best-practices`'s SIBLING_MAP and triggering.json are updated in the same review unit.

Pass threshold: 7/8. Below 5/8 means rework before handing off — most likely the fan-out or sibling survey was done too shallowly.

## Conversation Style

- Be concise. Group related questions — Phase 1's five inputs go in one turn, not five.
- If the author has already answered some of Phase 1 upfront ("I want to add `rds-best-practices`, it's like `eks-best-practices` but for RDS"), skip the questions that are already answered and only ask what is missing.
- Explain the mode detection once ("`skills/<name>/` does not exist, so this is greenfield — Phase 2 will invoke `skill-creator` to draft the skill first").
- When a STOP gate fires, name the gate and the one concrete decision you need from the author, not a generic "please confirm" — the gates exist to produce decisions, not pauses.
- Zero-sibling outcomes are legitimate. Do not pad the sibling list to avoid an empty Phase 3 result.
- Use em-dashes in prose; arrows `→` in user-facing decision language, `->` only inside code blocks.
