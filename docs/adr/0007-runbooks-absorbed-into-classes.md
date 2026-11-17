# ADR 0007: Runbooks are absorbed into the classes and the skills

- **Status**: Accepted
- **Date**: 2026-11-17

## Context

[ADR 0001](0001-runbooks-live-in-apex.md) put every runbook under the apex skill, one folder per skill, at `skills/apex/runbooks/<skill>/`. Step 1 moved the seven steering workflows there. Each of the seven is one skill's procedure; none chains skills. ADR 0001 left open how thin each runbook gets, whether runbooks stay grouped by skill, and where a runbook that spans several skills goes.

[ADR 0005](0005-skill-classes.md) then gave skills build-time classes: shared text is written once in `classes/<class>/` and copied into every member skill. Read against the classes, a per-skill runbook holds three kinds of text:

- **Router text**: the stage of each skill, which skill a request goes to, what context carries from one skill to the next, and when to suggest a next skill. The router's own SKILL.md already holds most of it, so a runbook that repeats it is a second surface to maintain.
- **Shared engagement conventions**: how a skill runs a guided engagement with the user. Several runbooks share them: a Full, Scoped or Summary mode, ordered phases that name their source, the required inputs asked in one turn, a restate-and-confirm gate before a recommendation or an artifact, a self-check before presenting, and "recommend, don't enumerate".
- **The skill's own procedure**: its questions, defaults, checklists and scoring.

Twenty-two lines across four runbooks also point into another skill's folder (`../../../<skill>/`), against `apex.no-path-into-another-skill`. Sixteen of them sit in the vendored eks-operation-review runbook, which its sync script writes from upstream.

We have no runbook that chains several skills, and that is the kind a customer should be able to write for their own work.

## Decision

**Class level first.** Router text moves into a new class, `classes/router/`, with the router skill as its one member (a migration router is planned in step 5): its rules in `rules.md`, its stage families, routing tables, hand-off table and band tables in `references/routing.md`. The shared engagement conventions are written once in `classes/platform/references/runbook-guidance.md`, a reference with no rule ids, since the Platform class holds no rules of its own. Until the class sync is built, the router skill keeps its own copy of the routing text, as it does for the base rules, and the two say the same thing.

**Then skill by skill.** What is left of each runbook is that skill's own procedure, and it moves into the skill in that skill's rebuild: eks-design and eks-build in step 4, eks-genai, eks-platform-engineering and eks-security in step 5. Until then it stays in `runbooks/<skill>/`, and the router follows it with that skill. Each such runbook keeps the shared conventions it uses until its skill joins the Platform class, so no run loses them in between. The two owner-held skills go through their owners' issues: eks-operation-review (aws-samples/sample-apex-skills#520) keeps its synced runbook and its 16 pointer lines until its owner decides; the eks-upgrade-check runbook held only router text and shared rules, so it is removed now and nothing of it goes to aws-samples/sample-apex-skills#521.

**What a runbook is now.** A runbook is the customer's own procedure that chains skills: which skills, in what order, what to carry between them, and the customer's own gates. `skills/apex/runbooks/` keeps two dummy examples to copy and adapt, `example-eks-design-to-build.md` and `example-eks-recon-to-operation-review.md`, and the per-skill folders until their rebuilds. A runbook may only tighten a safety rule (`apex.tighten-only`).

**Pointer lines.** Four of ours now name the skill and its file in words, with no path; the other two went with the removed eks-upgrade-check runbook. The 16 in the vendored eks-operation-review runbook go to its owner's issue.

**Two held issues.**

- aws-samples/sample-apex-skills#245: the eks-build runbook keeps its generated baseline, managed node groups with Cluster Autoscaler, and says in the question that Karpenter is the eks-design and eks-best-practices default and EKS Auto Mode the least-operations choice. The [EKS Best Practices Guide](https://github.com/aws/aws-eks-best-practices), this repo's source of truth for EKS questions, says in `latest/bpg/scalability/data-plane.adoc`: "We recommend you use node autoscaling that reduces toil and integrates deeply with Kubernetes. Managed node groups and Karpenter are recommended for large scale clusters." and "We recommend customers use Karpenter when possible."; and in `latest/bpg/autoscaling/auto-mode.adoc`: "Auto Mode is geared towards users that want the benefits of Kubernetes and EKS but need to minimize operational burden around Kubernetes like upgrades and installation/maintenance of critical platform pieces like auto-scaling, load balancing, and storage." (both read at mainline edc514fa on 2026-11-17). Whether eks-build's generated default changes is still open.
- aws-samples/sample-apex-skills#171: the Terraform upgrade workflow is not a runbook, since it runs unattended on a schedule rather than with a user in a session; its shape is decided in step 5.

## Consequences

- Router text has one source, `classes/router/`; a second router skill takes it by joining the class.
- A skill copied out alone keeps its guided engagement once its rebuild moves its procedure in. This narrows [ADR 0003](0003-standalone-skills-are-a-weaker-tradeoff.md): a lone skill still loses routing, hand-offs and the customer's runbooks, but no longer its own procedure. ADR 0003 is not edited.
- [ADR 0002](0002-apex-command-routes-to-apex-skill.md) says the apex skill "routes to the right runbook and standalone skill" and "knows every runbook". It now routes to the standalone skill, and follows a runbook only for a customer's chain or a skill whose procedure has not moved yet. ADR 0002's decision stands and it is not edited.
- Until the rebuilds, a shared convention is written twice: in `runbook-guidance.md` and in the runbooks that still use it. Each copy in a runbook goes when its skill joins the Platform class.
- The router's hand-off row for eks-design names the design's decisions, not the runbook's question numbers, so it holds when the questionnaire moves into eks-design.
- `docs/design/skill-design.md` and `CONTRIBUTING.md` describe the new model; the [skill design notes](../design/skill-design.md#runbooks) carry the wider reasoning.
