---
title: "Section 04 — Services & Deployment Safety"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/services-deployment.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-operation-review/references/services-deployment.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/services-deployment.md). Edit the source, not this page.
:::

# Section 04 — Services & Deployment Safety

## Purpose
Assess deployment safety — the single richest vein of ECS production incidents. Covers the deployment **circuit breaker** with automatic rollback, **CloudWatch-alarm-based rollback**, ECS **native blue/green** and **canary/linear** strategies, and rolling-update `minimumHealthyPercent` / `maximumPercent` tuning. This section rates the *safety of the deployment configuration that exists*; designing pipelines and choosing a rollout strategy is **`ecs-devops`**.

## Checks to Execute

### 4.1 — Deployment Circuit Breaker with Rollback (rolling update)

**What to check (services using the rolling-update `ECS` deployment controller):**
- `deploymentConfiguration.deploymentCircuitBreaker.enable`.
- `deploymentConfiguration.deploymentCircuitBreaker.rollback`.
- **Threshold tuning (configurable since July 2026):** `deploymentConfiguration.deploymentCircuitBreaker.thresholdConfiguration` — the `type` (`BOUNDED_PERCENT` default, `UNBOUNDED_PERCENT`, or `COUNT`) and `value`. The default is `BOUNDED_PERCENT` / `50` (clamped to a min of 3 and max of 200 failures). Many reviewers check only "is it enabled?" and never confirm the threshold matches the app's real startup behavior.

**How to check:**
1. `aws ecs describe-services --cluster <c> --services <s>` → `deploymentConfiguration.deploymentCircuitBreaker` (including `thresholdConfiguration`).

**Rating:**
- 🟢 GREEN: Circuit breaker enabled **and** `rollback: true` — failed deployments auto-roll-back to the last COMPLETED revision; threshold either left at the sensible default or tuned to the service's measured startup profile.
- 🟡 AMBER: Circuit breaker enabled but `rollback: false` (deployment fails but stays failed — manual intervention needed), **or** a long-startup app (JVM warm-up, model loading) left on a threshold that risks false-tripping where a tuned `COUNT`/`UNBOUNDED_PERCENT` would fit better.
- 🔴 RED: Circuit breaker disabled on a production rolling-update service — a bad deploy retries in perpetuity, consuming resources without surfacing failure.
- ⬜ UNKNOWN: Service uses a different deployment controller (blue/green — rate in 4.3) or cannot describe the service.

**Key talking point:** Without the circuit breaker, a failing rolling deployment retries indefinitely using service throttling logic; the breaker detects failure and (with rollback) restores the last healthy revision automatically. As of **July 2026** the failure threshold is configurable via `thresholdConfiguration` — set a lower threshold for faster rollbacks in dev/test, or allow more tolerance for apps with expected startup failures before they stabilize; you can also count failures consecutively or cumulatively. See [deployment circuit breaker](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html), [configurable circuit breaker settings launch](https://aws.amazon.com/about-aws/whats-new/2026/07/amazon-ecs-circuit-breaker-settings/), and the [original launch post](https://aws.amazon.com/blogs/containers/announcing-amazon-ecs-deployment-circuit-breaker/).

---

### 4.2 — CloudWatch-Alarm Rollback & Bake Time

**What to check:**
- `deploymentConfiguration.alarms` — whether CloudWatch alarms gate the deployment with `enable: true`, `rollback: true`.

**How to check:**
1. `aws ecs describe-services` → `deploymentConfiguration.alarms.alarmNames`, `enable`, `rollback`.

**Rating:**
- 🟢 GREEN: Deployment-gating alarms configured (e.g., latency/5xx) with rollback, giving a bake period that catches regressions the health check misses.
- 🟡 AMBER: Alarms defined but rollback off, or alarms exist but don't cover key SLIs.
- 🔴 RED: No alarm-based rollback on a customer-facing service where the health check alone can't detect functional regressions.
- ⬜ UNKNOWN: Cannot read deployment configuration.

**Key talking point:** Alarm-based rollback extends the deployment with a **bake time** during which the primary deployment stays IN_PROGRESS; if alarms stay OK it completes, otherwise ECS sets the deployment to FAILED and (with `rollback: true`) restores the last completed deployment. Only available when `deploymentController` is `ECS` (rolling update). Verified 2026-07-09. See [how CloudWatch alarms detect ECS deployment failures](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-alarm-failure.html) and the [automate rollbacks with CloudWatch alarms](https://aws.amazon.com/blogs/containers/automate-rollbacks-for-amazon-ecs-rolling-deployments-with-cloudwatch-alarms/) blog.

---

### 4.3 — Deployment Strategy Fit (rolling vs native blue/green vs canary/linear)

**What to check:**
- Deployment controller/strategy: rolling (`ECS`), ECS-native blue/green, canary, or linear; or external CodeDeploy (`CODE_DEPLOY`).
- For blue/green: presence of lifecycle hooks and a configured bake time.

**How to check:**
1. `aws ecs describe-services` → `deploymentController.type` and (for native strategies) the deployment strategy / lifecycle-hook / bake-time configuration.

**Rating:**
- 🟢 GREEN: Strategy matches risk profile — customer-facing critical services use native blue/green or canary/linear with a bake time and (optionally) lifecycle hooks for validation; low-risk services use rolling with the circuit breaker.
- 🟡 AMBER: Rolling update on a high-blast-radius service where progressive delivery (canary/linear/blue-green) would reduce risk.
- 🔴 RED: No safe-deploy mechanism at all on a critical service (rolling with no circuit breaker and no progressive strategy).
- ⬜ UNKNOWN: Cannot determine service criticality — flag for manual review.

**Key talking point:** ECS added **native blue/green** deployments (July 2025) and **built-in canary and linear** strategies (Oct 2025) with lifecycle hooks (Lambda or **pause** hooks), configurable bake time, and managed rollback — no CodeDeploy required. **Load-balancer support differs by strategy:** blue/green worked with ALB, NLB, and Service Connect from its July 2025 launch; the linear/canary strategies launched (Oct 2025) with **ALB or Service Connect only**, and **NLB support for linear/canary was added Feb 2026** — so all three now cover ALB, NLB, and Service Connect. If auditing a pre-Feb-2026 mental model, don't assume NLB linear/canary was always available. **Pause and continue controls** (May 2026) let a `PAUSE` lifecycle hook halt progression for manual approval / integration tests / external validation (timeout up to 14 days, with a continue-or-roll-back timeout action) across rolling, blue/green, linear, and canary strategies; resume via the `ContinueServiceDeployment` API. Strategy design/selection → **`ecs-devops`**. Verified 2026-07-09. See [ECS blue/green deployments](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-blue-green.html), [built-in blue/green launch](https://aws.amazon.com/about-aws/whats-new/2025/07/amazon-ecs-built-in-blue-green-deployments/), [linear/canary launch](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-ecs-built-in-linear-canary-deployments/), [NLB for linear/canary](https://aws.amazon.com/about-aws/whats-new/2026/02/amazon-ecs-nlb-linear-canary-deployments/), and [pause/continue controls](https://aws.amazon.com/about-aws/whats-new/2026/05/amazon-ecs-pause-continue-deployments/).

---

### 4.4 — Rolling-Update Capacity Bounds (minimumHealthyPercent / maximumPercent)

**What to check:**
- `deploymentConfiguration.minimumHealthyPercent` and `maximumPercent`.
- Whether the values allow a controlled rollout at the service's `desiredCount`.

**How to check:**
1. `aws ecs describe-services` → `deploymentConfiguration.minimumHealthyPercent`, `maximumPercent`, and `desiredCount`.

**Rating:**
- 🟢 GREEN: Values give a zero-/low-downtime rollout appropriate to the launch type (e.g., Fargate services commonly use `minimumHealthyPercent: 100`, `maximumPercent: 200`).
- 🟡 AMBER: Defaults left unexamined for a small `desiredCount` where they permit deep dips, or a value that conflicts with AZ rebalancing (`maximumPercent: 100` disables rebalancing — see Section 05).
- 🔴 RED: `minimumHealthyPercent: 0` on a customer-facing service (full outage window during every deploy), or bounds that can't launch a replacement (e.g., `maximumPercent: 100` on constrained EC2 capacity causing stuck deployments).
- ⬜ UNKNOWN: Cannot read deployment configuration.

**Key talking point:** `maximumPercent` caps how far above desired count ECS scales during a deploy; `minimumHealthyPercent` sets how far below it may dip. On Fargate these are usually 200/100 for zero-downtime; on constrained EC2, `maximumPercent: 100` can wedge a deployment. Note `maximumPercent: 100` also disables AZ rebalancing. See [ECS task health and replacement deep dive](https://aws.amazon.com/blogs/containers/a-deep-dive-into-amazon-ecs-task-health-and-task-replacement/) and [service parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-options.html).

---

### 4.5 — Deployment Failure Signal / Alerting

**This is the single scoring home for deployment-failure alerting** (the `SERVICE_DEPLOYMENT_FAILED` signal). Observability check 6.4 defers here — do not double-score; 6.4 owns health/capacity alerting only.

**What to check:**
- Whether failed deployments surface anywhere actionable (EventBridge rules on ECS deployment state-change events — `SERVICE_DEPLOYMENT_FAILED` — or CloudWatch alarms).

**How to check:**
1. `aws events list-rules` and inspect for ECS deployment state-change event patterns (best-effort; may be UNKNOWN).

**Rating:**
- 🟢 GREEN: Deployment failures routed to an alerting channel via EventBridge/alarms.
- 🟡 AMBER: Some signal but no routing to on-call.
- 🔴 RED: No deployment-failure signal — failures discovered only by customer impact.
- ⬜ UNKNOWN: Cannot enumerate EventBridge rules — suggest user verify.
