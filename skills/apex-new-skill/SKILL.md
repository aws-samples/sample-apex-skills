---
name: apex-new-skill
description: "Adds a new skill, or a class change, to the APEX skills repository (aws-samples/sample-apex-skills) end to end: reads the repo's classes and class tree to pick the skill's classes, writes SKILL.md front matter, drafts its SKILL_META line, authors the eval set and sibling-map updates, regenerates the docs with the repo's generators, runs the checks CI runs, drafts the ADR, the design-doc note and the fact check, asks before drafting a blog, then prepares the branch, explicit-path commit and pull request. Use when someone wants to contribute, add, onboard or submit a new skill to this repo, change a class under classes/, asks how to open a pull request for a new skill, or needs to retrofit a skill that landed without its eval set. Not for using the APEX skills on an EKS or ECS workload (use the matching skill), not for drafting or tuning skill content in general (use skill-creator), not for a doc sync alone (use update-docs), and not for editing vendored skills synced from upstream."
---

# Add a skill or a class change to the APEX repo

Reader: an agent helping a contributor, in any agent harness (Claude Code, Kiro, Codex or another). Every step below is a shell command or a file edit; no step needs a harness-specific tool. Run commands from the repo root of the contributor's fork.

This skill covers the repo's obligations around a new skill or a class change. For the skill's content (what it teaches, how its description triggers), use `skills/skill-creator/SKILL.md`: it is vendored from `anthropics/skills`, so read it, follow it, never edit it.

## Rules that apply to every step

| # | Rule | Why |
|---|---|---|
| 1 | Stage files by explicit path only: `git add skills/<name>/SKILL.md`, never `git add -A` or `git add .`. | Blanket staging sweeps unrelated files (local notes, reports, `.skill` packages) into a public pull request. |
| 2 | No internal or customer content: no customer names, account IDs, internal URLs, ticket numbers, credentials or private notes. | The repo is public (`aws-samples`), and a merged content skill ships to every install (see [references/repo-checks.md](references/repo-checks.md)). |
| 3 | `description` is at most 1024 characters, third person, says what the skill does, when to use it and when not to. No `<` or `>` in it. | `misc/validate-frontmatter.py` enforces the 1024 cap; skill-creator's `quick_validate.py` also rejects angle brackets. |
| 4 | Do not add a `license:` field to an in-house skill. | CONTRIBUTING.md, "Per-skill `license:` frontmatter": in-house skills "MUST NOT declare a `license:` field in their `SKILL.md` frontmatter"; the repo LICENSE (MIT-0) governs. |
| 5 | Never edit a vendored skill: a folder that holds `UPSTREAM.md` or `.vendor-sha` (today `skill-creator` and `terraform-skill`, among others). | The `vendored-guard` CI job fails a pull request that edits one outside a vendor sync, and the next sync overwrites local edits (`.github/scripts/vendored-guard.sh`). |
| 6 | Never hand-edit generated files (README marker blocks, the `skills/README.md` detail block, `misc/website/docs/skills/**`, `skills.json`, `llms.txt`). Run the generators. | The `docs-sync` CI job regenerates them and fails the pull request on any diff. |
| 7 | Read the repo's classes and generators from the files named in "Read the repo first", never from memory or from this skill. | The classes and the generator list change; this skill reads them each run so it stays right. |

Stop and ask the contributor before any push, and never push to `main`: CONTRIBUTING.md, "Releasing to npm", says main "takes changes only through pull requests".

## Read the repo first

Before step 1, read these and keep what they say for the rest of the run:

1. **The classes.** Each `classes/*/class.yaml`: its `name`, its `parents`, and any `checks` (each with a `status`). A class lists no members: a skill joins a class through its own front matter, `metadata.apex-classes`, a space-separated list of class names.
2. **The class tree.** `docs/design/skill-design.md`, section "The class tree", and the class table under "The classes": what each class is for.
3. **The Steward class** (`classes/steward/class.yaml`): `generators` (each `run`, then each `check`), `hand_kept` (files edited by hand, not generated) and `add_a_skill` (the CONTRIBUTING.md steps this skill walks).
4. **The README groups.** `README_GROUPS` in `misc/update-skills-references.sh`: the headings a skill can be listed under.

A `status: planned` generator or check is not built yet: name it to the contributor as not run, and do not run it.

## Mode

- `skills/<name>/SKILL.md` does not exist: greenfield. Run every step.
- It exists but has no `misc/evals/<name>/`: retrofit. Skip step 3 and treat the existing skill as the spec; do not rewrite it unless the contributor asks. Skip step 1's classes question and write no `metadata.apex-classes`: an existing skill joins its classes later, in a pull request of its own. In step 5 a retrofit only re-runs the generators: its `SKILL_META` line and catalogue entries already exist.
- The change is to a file under `classes/` and adds no skill: class change. Run step 2's survey only for the class's members (if no skill declares the class yet, say so; where its class.yaml comment names intended members, survey those, else say none are named), then step 5's generators (no staging, no wrapper check) and steps 6 to 8; while the class sync's status is `planned`, name it as not run.
- Only an eval scaffold asked for: point at `cd misc/evals && make init-evals SKILL=<name>` (`misc/evals/README.md`) and stop.

Say which mode applies in one line; in greenfield and retrofit modes, then ask the step 1 questions in a single turn.

## Step 1: Scope

Ask for whatever the contributor has not already said:

1. **Name** (`<name>`): lowercase, hyphenated, at most 64 characters, equal to the folder name. CONTRIBUTING.md: "Prefix skill names with the target service (`eks-`, `ecs-`) for auto-grouping in docs and README. Non-service skills use a descriptive name without prefix." Content skills (for example `graviton-migration`) take no prefix; repo maintenance skills that create or update APEX skills keep `apex-` (`apex-new-skill`). A skill for an AWS service with no skills here yet needs maintainer changes: CONTRIBUTING.md says to open an issue first, so draft the issue's title and body, hand them to the contributor to open, and stop until a maintainer answers.
2. **One-sentence scope**: what it covers and for whom. This seeds `description`.
3. **Five prompts it should trigger on**, phrased the way a real user types them.
4. **Kind**: knowledge (reference material), solution (a guided procedure plus its knowledge), setup (one-time configuration) or discovery (reads live state, reports facts).
5. **Target service**: EKS, ECS, another AWS service, or repo meta-tooling.
6. **Classes**: offer only classes with a `classes/<name>/class.yaml`; from those, offer the ones that fit the kind and the target service, each with its one-line purpose from the class table. Each class brings its parents; list them in the restate, not the front matter.

Restate the answers and the mode, and get a yes before writing files. Push back on a fuzzy scope ("a security skill"): a narrow scope gives a sharp description and a clean eval set.

## Step 2: Survey sibling skills

Read the `description` of every `skills/*/SKILL.md` (front matter only: that is what triggering sees). List the skills a prompt for `<name>` could plausibly land on, one line of rationale each (a service-scoped knowledge skill typically has 1 to 3; a discovery or setup skill 0 to 2; a meta-skill for authoring, linting or cross-service work may have 0), and name any skill a reader might expect on the list but which is not a sibling. Zero siblings is a valid answer. Skip skill-creator, terraform-skill and the `apex` router: CONTRIBUTING.md, Creating a New Skill, step 5, excludes them.

The confirmed list drives the description's "when not" clause, the near-miss negatives in step 4 and the sibling-map updates.

## Step 3: Write the skill (greenfield only)

Follow `skills/skill-creator/SKILL.md` (sections "Capture Intent" to "Writing Patterns") to draft. Lay it out as CONTRIBUTING.md's "Structure" block shows:

```
skills/<name>/
├── SKILL.md         # required: front matter (name, description) + body
├── references/      # optional: detail loaded on demand
├── scripts/         # optional: executable code for deterministic tasks
└── assets/          # optional: files used in output (templates, etc.)
```

- Front matter: `name` and `description`, plus `metadata.apex-classes` when the contributor picked classes in step 1 (for example `metadata: { apex-classes: "service script" }`; each name is the `name:` of a `classes/*/class.yaml`; name only the leaf classes, since their parents follow). No `license:` (rule 4). The validator allows `name`, `description`, `license`, `metadata`, `allowed-tools`; anything else fails CI.
- Body: CONTRIBUTING.md keeps SKILL.md to "the essentials (~500 lines max)"; move depth into `references/*.md` and link each file from SKILL.md by relative path (`references/topic.md`), so the skill works from any install location.
- A phased procedure the skill runs (STOP gates, user checkpoints) lives in its own `references/`, linked from SKILL.md. A customer runbook that chains skills is written by hand: CONTRIBUTING.md, "Creating a New Runbook".
- Source every threshold, limit and version claim in `references/` to an authoritative page (AWS docs, upstream project docs). Step 7's fact check lists them.
- Validate the front matter before moving on:

```bash
python3 skills/skill-creator/scripts/quick_validate.py skills/<name>
```

Show the draft to the contributor and sharpen `description` together before step 4: the triggering eval scores exactly that string.

## Step 4: Eval set

CONTRIBUTING.md's pre-PR checklist requires "`misc/evals/<name>/triggering.json` has ≥16 prompts (≥8 positives, ≥8 negatives)" and a sibling-map entry in each neighbour's eval set. The commands, file shapes and the CI hygiene floor are in [references/evals.md](references/evals.md). Read it now and follow it.

## Step 5: The SKILL_META line, the catalogues and the generators

1. **Draft the `SKILL_META` line** in `misc/update-pages.sh`, in the table between `SKILL_META="$(cat <<'META'` and `META`, in folder order. One line, tab-separated: `<folder>`, the page title (`<Name>: <what it does>`, as the other lines read), a summary under 160 characters in words taken from the skill's own SKILL.md, and the group, one of the `README_GROUPS` headings. A skill with no line fails `misc/update-skills-references.sh` and `./misc/update-pages.sh --check`. Show the line to the contributor before you write it.
2. **Catalogues:** CONTRIBUTING.md, Creating a New Skill, step 6: the routing row in `skills/apex/SKILL.md`, the skill's `LINES` entry in `misc/website/src/components/skillCatalog.ts`, and its name in `PORTS` in `misc/website/src/components/skillSearch.ts` only when it has a `devops-agent/<name>/` port (the Steward class lists both files under `hand_kept`).
3. **Generators:** `misc/update-pages.sh` lists sources with `git ls-files`, so stage the new skill first, each file by name. Show the contributor the list, then add what they confirm:

```bash
git ls-files --others skills/<name>/
git add skills/<name>/SKILL.md skills/<name>/references/<file>.md   # each file by name
```

Then run each Steward `generators` entry's `run` command whose status is `exists`, in order (in a class change this includes the class sync once it is built), and confirm the wrapper page exists:

```bash
ls misc/website/docs/skills/*/<name>/index.md   # must exist; if not, the skill was not staged
```

Then stage each generated path `git status --porcelain -uall` lists, by name. What each generator touches and the failure modes: [references/repo-checks.md](references/repo-checks.md).

After the generators, check hand-written prose for stale skill lists or counts (CONTRIBUTING.md, "Keeping skill docs in sync after changes", asks you to run the `update-docs` skill for this).

DevOps Agent port: whenever you create or update a skill, check in this order:

1. Would a port fit? `devops-agent/README.md`, section "Contributing": the skill must be Day 2 operational (upgrade checks, audits, assessments, not design or build workflows).
2. Does `devops-agent/<name>/` already exist?
3. If not, help create it (`SKILL.md` plus `references/`, markdown only), following that section.
4. If it exists, help update it to match the skill's change.

## Step 6: Run the checks

Run every check in [references/repo-checks.md](references/repo-checks.md), section "Checks", plus each Steward generator's `check` command and each class check with status `exists` for the skill's classes and their parents. Fix until each exits 0; a failure in a file this change did not touch is reported to the contributor, not fixed here. These are among the commands the `docs-sync` and `evals` CI jobs run.

## Step 7: Record the decision

For each new skill or class change, draft these three in the contributor's branch and show each one before it is staged:

1. **The ADR.** `docs/adr/NNNN-<slug>.md`, `NNNN` the next unused number in `docs/adr/`, (title line as the existing records use, `# ADR NNNN: <title>`; sections as `docs/adr/README.md` "Format" lists: Status, Date, Context, Decision, Consequences, and Open if anything is undecided). Status is `Proposed`: the maintainers accept it. Add its row to the table in `docs/adr/README.md`. Never edit an earlier record to change its decision: a new record supersedes it.
2. **The design-doc note.** An edit to `docs/design/skill-design.md` in the section the change belongs to: for a class change, its row in the class table under "The classes"; for a new skill, "The class tree" when it takes classes no skill had before; a new skill that takes no such class needs no note. Keep it to the facts the ADR decides.
3. **The fact check.** A `## Fact check` section for the pull request body: one line per version, price, limit or service-status claim the change adds, each with its live source and "checked on <date>". A claim with no live source is marked unverified, not left out.

Then ask the contributor one question: "Do you want a blog draft for this change?" Draft a blog only on a yes, built from the ADR and the merged facts above, and hand it to the contributor uncommitted. Published posts live in `misc/website/blog/` and follow its blog standard (CONTRIBUTING.md, "Writing a Blog Post"): never write the draft there.

## Step 8: Commit and open the pull request

Follow [references/pull-request.md](references/pull-request.md): fork, branch off the latest `main`, commit by explicit path; ask before pushing; prepare the title and body, with the template answered and the fact check in the body, and hand over: the contributor opens it.

## Before hand-off

Each item passes or fails, or, in a class change or a retrofit, is marked not applicable:

- [ ] Scope and classes restated and confirmed (step 1); siblings listed with rationale, non-siblings named (step 2).
- [ ] `skills/<name>/SKILL.md` passes `quick_validate.py`; no `license:` field; description at most 1024 characters with a "when not" clause; `metadata.apex-classes` names only classes under `classes/` (check each name with `ls classes/<class>/class.yaml`), none of them a parent of another it names (follow each `class.yaml`'s `parents:` up the tree; parents follow, `docs/design/skill-design.md` "The class tree").
- [ ] `misc/evals/<name>/` has `triggering.json` (8+ positives, 8+ negatives) and `evals.json` (2+ prompts, 3+ expectations each); each sibling's eval set updated in the same pull request.
- [ ] The `SKILL_META` line is in `misc/update-pages.sh`; the catalogues are updated; generators run after staging; wrapper `index.md` exists; all checks exit 0, or each failure in a file this change did not touch is reported, and each planned generator or check is named as not run.
- [ ] The ADR, the design-doc note (when step 7 calls for one) and the fact check are drafted; the blog was asked about, and drafted only on a yes.
- [ ] Every staged path was named explicitly; `git status --porcelain -uall` shows nothing unintended.
- [ ] No internal or customer content.
