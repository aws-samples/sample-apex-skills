# GenAI-Assisted Platform Engineering

Amazon Q Developer accelerates both sides of the platform: developers generating application code, and platform engineers generating the platform's own artifacts (OAM components, Backstage templates, deployment manifests). Always human-in-the-loop.

## Two tracks

- **Code generation** (app developers) — snippets, functions, whole features in unfamiliar languages.
- **Platform generation** (platform engineers) — OAM component definitions, Backstage templates, deployment/IaC manifests, runbooks, automation.

The goal is to *accelerate adoption* of platform practices, not replace judgment.

## The reliable generation pattern

```
reference example  +  target schema/CRD  +  a precise prompt  →  generated artifact  →  human review (diff)  →  use
```

Examples from the platform:
- **Generate an OAM component** — "use the S3 OAM component definition as a template and create a `ddb-table` component from this DynamoDB ACK CRD; only required properties except `billingMode: PAY_PER_REQUEST`; 4 params; namespace `vela-system`." Deploy to `vela-system`; developers then self-serve via `type: ddb-table`.
- **Generate a Backstage template** — "use the S3 Backstage template's folder structure and stages to create a DynamoDB template; reference this OAM definition." Produces `template.yaml` + `skeleton/` (catalog-info + manifests).
- **Generate a deployment manifest** — "create an OAM Application using these KubeVela templates, in strict `dependsOn` order: DynamoDB table → service account → app → path-based ingress; default/required params; reference `src/` for context."

## Prompt engineering essentials

- Be specific: state the goal, the inputs, the constraints, and the expected output shape.
- Provide context: point at the reference file, the schema, and existing code (`src/`, `platform-meta/examples/`).
- Decompose complex tasks; iterate — GenAI is non-deterministic, so the same prompt may vary.
- Give acceptance criteria (error handling, tests, docs, conventions).

## platform-meta as ad-hoc RAG; Q Developer Customizations as the future

The platform keeps a `platform-meta` folder of component definitions and examples that serves as **context (RAG)** for Q when generating manifests — pointing Q at it makes generations follow platform conventions. The forward path is **Q Developer Customizations**: the platform team trains the model on its component knowledge, so developers get platform-aware generations without manually supplying context.

## The /dev feature agent

Q Developer's `/dev` agent does multi-step feature development (plan → discover → generate → edit → verify → loop) and returns a multi-file diff. Prompt it with the routes/behavior, the persistence layer, requirements (error handling, tests, docs), and references to existing services so it follows established patterns.

## Human-in-the-loop is non-negotiable

Expect hallucinations (non-existent methods) and missed integration steps (e.g. a new route not wired into `main`). Always `diff` generated artifacts against a validated version before registering/deploying. GenAI produces the skeleton; the engineer validates and finishes. Then it ships through the *same* golden path as hand-written code — `git push` → CI/CD → canary.
