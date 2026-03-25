# Contributing to APEX EKS  

This guide explains how the repository is organized, where new content should go, and the process for submitting contributions.

---

## Repository Architecture

APEX EKS organizes content into three directories, each serving a distinct purpose in the agentic workflow. Understanding the distinction is critical — putting content in the wrong place degrades the agent's performance.

```
apex-eks/
├── steering/           → 🎯 HOW the agent behaves (conversation orchestration)
│   ├── commands/       →   Slash command definitions (harness-specific entry points)
│   └── workflows/      →   Structured engagement playbooks
├── skills/             → 📚 WHAT the agent knows (domain knowledge)
└── examples/           → 🏗️ HOW to try it (hands-on exercises)
```

---

## `skills/` — Domain Knowledge

**Purpose:** Self-contained packages of specialized knowledge that the AI agent loads on demand. Skills follow the [Agent Skills open standard](https://agentskills.io/).

**Think of skills as:** An expert's brain — the accumulated knowledge, decision frameworks, and best practices that a senior SA carries. The agent consults this knowledge regardless of what task it's performing.

### Characteristics

- **Reusable across workflows** — the same `eks-best-practices` skill is used whether the agent is designing a new cluster, reviewing an existing architecture, planning an upgrade, or troubleshooting an issue
- **Stateless** — no conversation flow, no "ask the user this, then do that." Pure knowledge.
- **Triggered by description match** — the agent reads the `description` field in SKILL.md frontmatter and decides whether to activate the skill based on the user's request
- **Progressive disclosure** — SKILL.md contains the essentials (~500 lines max), `references/` contains deep-dive material loaded only when needed

### Structure

```
skills/{skill-name}/
├── SKILL.md              # Required: frontmatter (name, description) + body
├── references/           # Optional: detailed reference docs (loaded on demand)
│   ├── topic-a.md
│   └── topic-b.md
├── scripts/              # Optional: executable code for deterministic tasks
└── assets/               # Optional: files used in output (templates, etc.)
```

### What Belongs in Skills

| ✅ Belongs | Example |
|-----------|---------|
| Decision frameworks | Compute selection matrix (Karpenter vs MNG vs Auto Mode vs Fargate) |
| Best practices | Security essentials (IAM, Pod Identity, PSA, network policies) |
| Reference tables | Upgrade sequence rules (control plane → add-ons → data plane) |
| Code patterns | Terraform module patterns and naming conventions |
| Quick wins | Cost optimization table (Graviton, Spot, consolidation) |

### What Does NOT Belong in Skills

| ❌ Does not belong | Why | Where it goes |
|-------------------|-----|---------------|
| "Ask the user these 8 phases of questions" | That's a conversation flow | `steering/workflows/` |
| A Terraform module that deploys a cluster | That's runnable infrastructure | `examples/` |
| A deploy.sh script that sets up a demo | That's a hands-on exercise | `examples/` |
| Checkpoint templates with STOP gates | That's agent behavior control | `steering/workflows/` |

### Current Skills

| Skill | What It Covers |
|-------|---------------|
| `eks-best-practices` | EKS architecture decisions, compute, networking, security, reliability, autoscaling, upgrades, cost, observability, ArgoCD, container registry, EKS Capabilities |
| `terraform-skill` | Terraform modules, testing (native + Terratest), CI/CD, security scanning |
| `skill-creator` | Meta-skill: how to create and package new skills |

---

## `steering/` — Conversation Orchestration

**Purpose:** Files that control how the agent interacts with the user — routing intent, sequencing steps, gathering requirements, enforcing checkpoints, and validating output.

**Think of steering as:** A senior SA's playbook — not what they know (that's skills), but how they run an engagement. The structured questionnaire they follow, the checkpoints they enforce, the quality gates they apply before delivering recommendations.

### Characteristics

- **Defines interaction patterns** — questionnaires, step-by-step procedures, STOP gates, checkpoint templates
- **Routes user intent** — "if the user says 'upgrade my cluster', activate the upgrade workflow"
- **References skills for knowledge** — steering files say "use the `eks-best-practices` skill's decision frameworks" but don't duplicate the knowledge
- **Workflow-specific** — each workflow file handles one lifecycle phase (design, upgrade, troubleshoot)
- **Has a hub** — `eks.md` is the central router that detects intent and dispatches to the right workflow

### Structure

```
steering/
├── eks.md                    # Hub: intent detection, routing, shared context
├── commands/                 # Slash command wrappers (harness-specific entry points)
│   └── apex/                 # Claude Code: symlinked into .claude/commands/apex/
│       ├── eks.md            # /apex:eks → routes via steering/eks.md
│       ├── eks-design.md     # /apex:eks-design → steering/workflows/design.md
│       └── eks-upgrade.md    # /apex:eks-upgrade → steering/workflows/upgrade.md
└── workflows/
    ├── design.md             # Day 0: Architecture questionnaire + quality check
    ├── upgrade.md            # Day 2: Pre-flight → plan → execute → validate
    └── troubleshoot.md       # Day 2: (future) Diagnosis workflows
```

### Why Hub + Workflows (Not Monolithic)

1. **Context efficiency** — the agent loads only the relevant workflow, not all of them
2. **Independent iteration** — improve the upgrade workflow without touching design
3. **Clear ownership** — different SAs can own different workflows
4. **Shared context** — the hub carries context between workflows (design decisions inform upgrade planning)

### What Belongs in Steering

| ✅ Belongs | Example |
|-----------|---------|
| Questionnaires | The 8-phase design questionnaire (Phase 1: Project Context → Phase 8: Confirm & Generate) |
| Pre-flight checklists | Upgrade pre-flight with STOP gates ("STOP if blocking PDBs found") |
| Quality gates | Scoring rubric (80% threshold across Well-Architected pillars) |
| Intent routing | "User says 'upgrade my cluster' → activate upgrade workflow" |
| Checkpoint templates | "✅ Step N complete. Validation: ... Ready for Step N+1?" |
| Mandatory warnings | "Once the control plane is upgraded, you CANNOT roll it back" |
| Conditional branches | "Terraform detected? → Terraform path. CLI-managed? → CLI path." |
| Slash command wrappers | Command files that map `/apex:eks-design` to the design workflow |

### What Does NOT Belong in Steering

| ❌ Does not belong | Why | Where it goes |
|-------------------|-----|---------------|
| EKS best practices content | That's domain knowledge | `skills/` |
| Terraform code patterns | That's domain knowledge | `skills/` |
| A deployable Terraform module | That's runnable infrastructure | `examples/` |

### The Key Test

If you removed all steering files, would the agent still *know* the right answers? **Yes** — skills provide the knowledge. But the agent wouldn't know *how to run the engagement* — it wouldn't follow the questionnaire, enforce checkpoints, or validate output quality.

---

## `examples/` — Hands-On Exercises

**Purpose:** Deployable, runnable scenarios that demonstrate APEX workflows in practice. They include infrastructure code, planted issues, test scripts, and documented test results.

**Think of examples as:** A workshop lab — the actual environment where someone can deploy infrastructure, run APEX against it, and see the agent in action. Examples are how we validate that steering + skills actually work, and how we deliver workshops to customers.

### Characteristics

- **Runnable** — `deploy.sh` creates infrastructure, `destroy.sh` tears it down
- **Self-contained** — each example includes everything needed to run the exercise
- **Demonstrates a workflow** — each example maps to a steering workflow (e.g., `examples/eks-upgrades/in-place/` demonstrates `steering/workflows/upgrade.md`)
- **Contains planted issues** — realistic problems for the agent to discover and fix
- **Documents test results** — conversation logs showing how the agent performed, with issue tables and fix tracking
- **Used for iteration** — test results drive improvements to steering files (test-01 → fix steering → test-02)

### Structure

```
examples/{scenario}/{variant}/
├── README.md              # Required: frontmatter (name, description, workflow) + exercise guide
├── manifests/             # Kubernetes manifests (planted issues, test resources)
├── scripts/
│   ├── deploy.sh          # Deploy the exercise environment
│   └── destroy.sh         # Clean up everything
├── static/                # Screenshots, diagrams
└── tests/
    ├── test-01.md         # Full conversation log from test run 1
    └── test-02.md         # Full conversation log from test run 2
```

Each example's `README.md` must include YAML frontmatter:

```yaml
---
name: In-Place EKS Upgrade
description: Deploy an EKS 1.30 cluster with planted issues and upgrade to 1.33.
workflow: steering/workflows/upgrade.md
---
```

- `name` — short label (required)
- `description` — one-line summary (required)
- `workflow` — which steering workflow this example demonstrates (optional)

### What Belongs in Examples

| ✅ Belongs | Example |
|-----------|---------|
| Deployable infrastructure | Terraform that creates an EKS 1.30 cluster |
| Planted issues | Kubernetes manifests with deprecated APIs, blocking PDBs, stale RBAC |
| Deploy/destroy scripts | `deploy.sh` that sets up the exercise environment |
| Test conversation logs | Issue tables (what went well, what failed, fixes made) |
| Screenshots | Agent behavior during test runs |

### What Does NOT Belong in Examples

| ❌ Does not belong | Why | Where it goes |
|-------------------|-----|---------------|
| Best practices documentation | That's domain knowledge | `skills/` |
| Conversation flow definitions | That's agent orchestration | `steering/` |
| Generic reference material | That's skill reference content | `skills/{name}/references/` |

---

## Decision Flowchart

When adding new content to the repo, follow this flowchart:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Where does this content go?                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │ Is it domain knowledge,       │
              │ best practices, or decision   │
              │ frameworks?                   │
              │                               │
              │ (Reusable across workflows,   │
              │  stateless, no user           │
              │  interaction flow)            │
              └───────────────┬───────────────┘
                    │                   │
                   YES                  NO
                    │                   │
                    ▼                   ▼
              ┌──────────┐    ┌───────────────────────────┐
              │ skills/  │    │ Does it define how the    │
              └──────────┘    │ agent interacts with the  │
                              │ user?                     │
                              │                           │
                              │ (Questionnaire, step-by-  │
                              │  step procedure, routing, │
                              │  checkpoints, STOP gates) │
                              └─────────────┬─────────────┘
                                  │                   │
                                 YES                  NO
                                  │                   │
                                  ▼                   ▼
                        ┌──────────────────┐  ┌─────────────────────┐
                        │ steering/        │  │ Is it runnable       │
                        │ workflows/       │  │ infrastructure or a  │
                        └──────────────────┘  │ hands-on exercise?   │
                                              │                     │
                                              │ (Terraform, deploy  │
                                              │  scripts, planted   │
                                              │  issues, test logs) │
                                              └──────────┬──────────┘
                                                │              │
                                               YES             NO
                                                │              │
                                                ▼              ▼
                                          ┌──────────┐  ┌──────────────┐
                                          │ examples/ │  │ Root level   │
                                          └──────────┘  │ (README.md,  │
                                                        │  PLAN.md,    │
                                                        │  etc.)       │
                                                        └──────────────┘
```

---

## Creating a New Skill

See the `skill-creator` skill in `skills/skill-creator/SKILL.md` for the full guide. Summary:

1. Understand the skill with concrete examples
2. Plan reusable contents (scripts, references, assets)
3. Initialize: `python skills/skill-creator/scripts/init_skill.py <name> --path skills/`
4. Edit SKILL.md and add references
5. Package: `python skills/skill-creator/scripts/package_skill.py skills/<name>`
6. Iterate based on real usage

## Creating a New Steering Workflow

1. Create `steering/workflows/<name>.md`
2. Add a header linking back to the hub: `> **Part of:** [APEX EKS Hub](../eks.md)`
3. Add an intent routing table at the top
4. Structure as phases with numbered checklists and STOP gates
5. Add the workflow to the hub's routing table in `steering/eks.md`
6. Create a corresponding command file in `steering/commands/apex/eks-<name>.md` with frontmatter (`name`, `description`) and an `@steering/workflows/<name>.md` execution context reference
7. Run `misc/update-steering-references.sh` to update the README
8. Test with a real scenario and document results in `examples/`

## Creating a New Example

1. Create `examples/<scenario>/<variant>/`
2. Add `README.md` with frontmatter (`name`, `description`, `workflow`) and exercise guide (overview, prerequisites, setup, expected outcome)
3. Add `scripts/deploy.sh` and `scripts/destroy.sh`
4. Add planted issues in `manifests/` or infrastructure code
5. Run the exercise with APEX and document results in `tests/`
6. Use test results to iterate on the corresponding steering workflow
7. Run `misc/update-examples-references.sh` to update the README

---

## Reporting Bugs / Feature Requests

We welcome you to use the GitHub issue tracker to report bugs or suggest features.

When filing an issue, please check existing open, or recently closed, issues to make sure somebody else hasn't already
reported the issue. Please try to include as much information as you can. Details like these are incredibly useful:

* A reproducible test case or series of steps
* The version of our code being used
* Any modifications you've made relevant to the bug
* Anything unusual about your environment or deployment


## Contributing via Pull Requests

Contributions via pull requests are much appreciated. Before sending us a pull request, please ensure that:

1. You are working against the latest source on the *main* branch.
2. You check existing open, and recently merged, pull requests to make sure someone else hasn't addressed the problem already.
3. You open an issue to discuss any significant work - we would hate for your time to be wasted.

To send us a pull request, please:

1. Fork the repository.
2. Modify the source; please focus on the specific change you are contributing. If you also reformat all the code, it will be hard for us to focus on your change.
3. Ensure local tests pass.
4. Commit to your fork using clear commit messages.
5. Send us a pull request, answering any default questions in the pull request interface.
6. Pay attention to any automated CI failures reported in the pull request, and stay involved in the conversation.

GitHub provides additional document on [forking a repository](https://help.github.com/articles/fork-a-repo/) and
[creating a pull request](https://help.github.com/articles/creating-a-pull-request/).


## Finding Contributions to Work On

Looking at the existing issues is a great way to find something to contribute on. As our projects, by default, use the default GitHub issue labels (enhancement/bug/duplicate/help wanted/invalid/question/wontfix), looking at any 'help wanted' issues is a great place to start.


## Code of Conduct

This project has adopted the [Amazon Open Source Code of Conduct](https://aws.github.io/code-of-conduct).
For more information see the [Code of Conduct FAQ](https://aws.github.io/code-of-conduct-faq) or contact
opensource-codeofconduct@amazon.com with any additional questions or comments.


## Security Issue Notifications

If you discover a potential security issue in this project we ask that you notify AWS/Amazon Security via our [vulnerability reporting page](http://aws.amazon.com/security/vulnerability-reporting/). Please do **not** create a public github issue.


## Licensing

See the [LICENSE](LICENSE) file for our project's licensing. We will ask you to confirm the licensing of your contribution.
