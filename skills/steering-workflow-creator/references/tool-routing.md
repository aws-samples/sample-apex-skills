# Tool Routing for Steering Workflows

Every phase of a steering workflow is, under the hood, a routing decision: where is the information I need *right now* coming from? The answer is always one of three sources. This file is the service-agnostic decision tree for picking among them. Once you internalize the tree, phase authoring becomes mechanical — you annotate each phase with its source, name a fallback if the source is live, and move on.

The tree doesn't care whether the service is EKS, RDS, Lambda, IAM, or something that doesn't exist yet. EKS-shaped examples live under `examples/eks.md` and siblings — do not leak service specifics into the rule itself.

---

## The three information sources

### Knowledge skill

Static domain knowledge, authored by a human, versioned in git, read from a skill's `SKILL.md` or `references/`. The `eks-best-practices` and `eks-upgrader` skills are current examples; every AWS service this repo eventually covers is expected to grow at least one knowledge skill of its own.

**Characteristics:**

- Deterministic — the same query returns the same text every time.
- Session-independent — doesn't need AWS credentials, kubeconfig, or any live connection.
- Cheap — reading a markdown file is a local operation.
- Opinionated — reflects the author's judgment of what "good" looks like.
- Potentially stale — the author has to keep it current; the file doesn't update itself.

**Best for:** decision frameworks, best practices, design rationale, "how should I think about X", architectural trade-offs, version-agnostic guidance.

### Live MCP tools

Whatever MCP server(s) the target service exposes for reading current state and (sometimes) mutating it. For EKS today that's the EKS MCP Server. Other AWS services will grow their own analogous tools; the routing logic doesn't change when they do.

**Characteristics:**

- Ground truth — reflects what is actually deployed right now.
- Session-dependent — needs the MCP server wired up and (usually) AWS credentials.
- Potentially failure-prone — network, auth, rate limits all apply.
- Can mutate — some tools are read-only, some are not; the workflow's Access Model dictates which are allowed.

**Best for:** current state, version numbers in the deployed cluster, inventory, real-time troubleshooting, any step where a wrong answer from cached knowledge would be worse than an error from a failed call.

### Skill-as-setup-bridge

A skill whose sole job is to get the user from "MCP is not available" to "MCP is available." The `eks-mcp-server` skill is the current example — it walks the user through configuring the EKS MCP Server, then hands off. Future services will have analogous bridges (`rds-mcp-server`, `lambda-mcp-server`, etc.) as those MCP servers come online.

**Characteristics:**

- One-shot — once setup succeeds, the skill's job is done for the session.
- User-in-the-loop — the user has to take actions outside the agent (install packages, add config, restart their client).
- Gated by environment — some users can't install arbitrary tooling, and the bridge should surface that early.

**Best for:** exactly one situation — a phase needs live data, MCP tools aren't available, and setup is plausible in this environment.

---

## The decision tree

Apply this tree to every phase. It takes three steps at most.

### Step 1: What is this phase asking about?

- **Advisory / best-practice / "how should I think about X"** → **knowledge skill.** Cheap, deterministic, session-independent. Prefer this *even when MCP is available* — MCP tells you what you have, skills tell you what's right. An architecture review, a design rationale, a "should I use Karpenter or MNG" question all belong here.
- **Current state / mutation / "what is actually deployed"** → **live MCP tools.** Skill knowledge cannot substitute for ground truth. Node versions, running pods, recent events, insight findings, upgrade history — all live.
- **A mix of the two** → split the phase. Use the knowledge skill to frame the decision, then use live tools to fill in specifics. Annotate the phase `Source: either` and spell out which parts come from which.

### Step 2: If live is needed, is MCP available?

Check at the start of any `live` phase:

- **MCP tools available** → call them directly. No fallback needed for this invocation.
- **MCP tools unavailable** → go to Step 3.

### Step 3: Route to the setup-bridge; if setup isn't feasible, fall back to CLI

- **Setup plausible in this environment** → route to the setup-bridge skill for this service (for EKS: `eks-mcp-server`). Let it walk the user through configuration. Once the user confirms setup is complete, retry Step 2.
- **Setup not plausible** (air-gapped env, user declines, no permissions to install tooling) → fall back to the workflow's documented **CLI fallback** for this phase. Declare reduced confidence in the output — CLI calls often return less structured data than MCP, and the gap matters for downstream scoring.
- **No CLI fallback documented** → the workflow is broken for this environment. Treat this as a bug to file, not a condition to handle. Every `live` phase MUST document a CLI fallback precisely so this case never happens.

---

## What the workflow author must do

Every workflow author has three non-negotiable tasks:

1. **Pick or create a discovery skill for Phase 1.** Phase 1 is almost always "gather context about the thing we're working on." For EKS, that's `eks-recon`. For a future RDS workflow, it will be the equivalent `rds-recon`-style skill — author one if it doesn't exist yet, using `eks-recon` as the pattern. Do not invent a bespoke discovery pass inside the workflow itself; that knowledge belongs in a skill where other workflows can reuse it.

2. **Annotate every phase with its source.** A one-line annotation near the `### Phase N: <name>` heading:

   ```
   Source: knowledge
   ```

   or

   ```
   Source: live
   ```

   or

   ```
   Source: either (prefer live when available; fall back to knowledge)
   ```

   This is for the agent's benefit as much as the reader's — it tells the agent which failure modes to expect and how to degrade. A phase with no annotation defaults to `knowledge`, which is the safer misread.

3. **Document a CLI fallback for every `live` phase.** Name the exact command. `aws eks describe-cluster --name <cluster> --query 'cluster.version'` beats "use the AWS CLI to get the cluster version" every time, because the second one makes the agent guess at syntax and the guess is often wrong. The fallback lives inline in the phase, not in a separate appendix — the agent should never have to hunt for it.

If any of these three tasks feels inconvenient, that's the signal the workflow hasn't thought through its own failure modes yet. Slow down, finish the routing design, then write the phases.

---

## Reduced-confidence declarations

When a `live` phase falls back to CLI (Step 3's last branch), the agent should tell the user what just happened and what it means:

> "MCP tools aren't available, and the `eks-mcp-server` setup isn't feasible right now. I ran the CLI fallback instead. Output is somewhat reduced compared to MCP — I got versions and counts, but not the richer per-resource context MCP would have provided. Downstream recommendations will be appropriately conservative."

Why: the user needs to know the output's provenance to decide how much to trust it. A workflow that silently degrades is worse than one that fails loudly — the user has no way to compensate for information they don't know is missing.

---

## Anti-routing patterns

A short list of mistakes the tree is designed to prevent:

- **Using MCP for advisory content.** If the question is "should I use X or Y", MCP has no answer — it only knows what's deployed, not what's good. Route to the knowledge skill.
- **Using knowledge for current state.** If the question is "what version am I on", knowledge has no answer — it only knows what's good, not what's deployed. Route to live.
- **Skipping the setup-bridge on MCP absence.** Jumping directly to CLI fallback without offering setup leaves the user worse off permanently. At least mention the bridge once per session.
- **Documenting CLI fallbacks as "see the AWS docs".** That's not a fallback, that's homework. Name the command.
- **Combining sources in a single paragraph without saying so.** If the phase mixes knowledge-sourced framing with live-sourced specifics, split the prose visibly so the agent (and reader) can tell which sentence came from where.

---

## Service-agnostic summary

The tree as a two-line summary an author can keep in their head:

> Advisory? Knowledge. Current-state or mutation? Live, via MCP, with the bridge as MCP's recovery path and a named CLI as the bridge's recovery path.

If a phase doesn't fit that summary, the phase probably wants to be two phases.
