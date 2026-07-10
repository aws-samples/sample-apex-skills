# ECS DevOps — Failure Detection & Rollback

> **Part of:** [ecs-devops](../SKILL.md)
> **Purpose:** Deployment circuit breaker (including the Jul 2026 configurable thresholds), CloudWatch alarm-based failure detection, and every rollback path for ECS deployments

**For strategy configuration, see:** [deployment-strategies.md](deployment-strategies.md)

> Facts in this file verified 2026-07-09 against the AWS documentation URLs cited inline.

---

## Table of Contents

1. [Deployment Circuit Breaker](#deployment-circuit-breaker)
2. [Configurable Thresholds (Jul 2026)](#configurable-thresholds-jul-2026)
3. [CloudWatch Alarm-Based Detection](#cloudwatch-alarm-based-detection)
4. [Combining Both Methods](#combining-both-methods)
5. [The Rollback Ladder](#the-rollback-ladder)
6. [What --force-new-deployment Actually Does](#what---force-new-deployment-actually-does)
7. [Observability of Deployments](#observability-of-deployments)

---

## Deployment Circuit Breaker

Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html (verified 2026-07-09)

- **Scope:** rolling update under the `ECS` deployment controller **only**. Not blue/green-family (those rely on hooks, bake time, and stage timeouts), not CodeDeploy, not external. Launch types: the GA announcement names EC2 and Fargate ([GA What's New, Dec 2020](https://aws.amazon.com/about-aws/whats-new/2020/12/amazon-ecs-announces-the-general-availability-of-ecs-deployment-circuit-breaker/)); the current doc scopes the feature only by deployment controller and says nothing about launch types ([circuit breaker](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html)). **Circuit-breaker support on the `EXTERNAL` launch type (ECS Anywhere) is not explicitly documented — verify before relying on it.** If it does apply there, note that stage-2 detection reduces to ECS container health checks only (no ELB and no service discovery/Cloud Map on Anywhere — [ECS Anywhere](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html)).
- **Two-stage detection:**
  - Stage 1 — tasks failing to reach `RUNNING` count toward the threshold (task-launch failures: image pull errors, missing secrets, ENI/placement failures…).
  - Stage 2 — once at least one task is RUNNING, health-check failures count, across **ELB health checks, AWS Cloud Map service health checks, and ECS container health checks**.
- **Rollback target:** the most recent deployment in `COMPLETED` state. During rollback that deployment moves back to `IN_PROGRESS` (and is not re-rollback-eligible until COMPLETED again). **If no COMPLETED deployment exists** (e.g., first-ever deployment fails), the circuit breaker does not launch new tasks and the deployment stalls — clean up manually.
- **Version-consistency interplay:** with circuit breaker enabled, 3+ failed image-digest-resolution attempts fail the deployment and trigger rollback ([rolling deployment](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-ecs.html)).

CLI shape (rolling only):

```bash
aws ecs update-service --cluster prod --service web \
  --deployment-configuration \
  'deploymentCircuitBreaker={enable=true,rollback=true,resetOnHealthyTask=false,thresholdConfiguration={type=COUNT,value=5}}'
```

History: GA Dec 2020; monitoring-responsiveness improvement Jan 2024 ([What's New](https://aws.amazon.com/about-aws/whats-new/2024/01/amazon-ecs-deployment-monitoring-responsiveness-services/)); configurable settings Jul 1, 2026 ([What's New](https://aws.amazon.com/about-aws/whats-new/2026/07/amazon-ecs-circuit-breaker-settings/)).

## Configurable Thresholds (Jul 2026)

Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html (verified 2026-07-09; launched Jul 1, 2026)

`deploymentCircuitBreaker.thresholdConfiguration`:

| `type` | Formula | Notes |
|---|---|---|
| `BOUNDED_PERCENT` (default) | threshold = ceil(value% × desired count), **clamped to min 3 / max 200** | `value` default 50, valid 1–100 |
| `UNBOUNDED_PERCENT` | same formula, **no clamps** | For very large services where the 200 cap is too tight |
| `COUNT` | threshold = `value` (fixed number of failed tasks) | Deterministic; good for small services |

Worked examples from the AWS doc (value 50, BOUNDED_PERCENT): desired 1 → threshold 3 (floor clamp); desired 25 → 13 (ceil); desired 400 or 800 → 200 (cap). UNBOUNDED_PERCENT, desired 800, value 50 → 400. ECS continuously uses the **latest** desired count during a deployment (autoscaling mid-deploy moves the threshold).

`deploymentCircuitBreaker.resetOnHealthyTask`:
- `true` (default) — **consecutive** failure counting; the failure counter resets whenever a healthy task starts. A deployment that limps (fail, fail, healthy, fail, fail…) may never trip.
- `false` — **cumulative** counting across the whole deployment; stricter, better for catching intermittent-failure deployments.

## CloudWatch Alarm-Based Detection

Sources: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-alarm-failure.html and https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentAlarms.html (verified 2026-07-10)

- Config: `deploymentConfiguration.alarms={alarmNames=[...],enable=true,rollback=true}`. **Scope is controller-based, not strategy-based: any strategy under the `ECS` deployment controller** (not CODE_DEPLOY/EXTERNAL). [API_DeploymentAlarms](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentAlarms.html) restricts alarms only to "when the DeploymentController is set to ECS", and AWS's blue/green service definition configures `alarms` alongside `"strategy": "BLUE_GREEN"` ([deploy-blue-green-service](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deploy-blue-green-service.html), verified 2026-07-10). One sentence on the alarm-detection page says "only supported for … the rolling update (ECS) deployment controller" — "rolling update (ECS)" there is the doc's label for the *controller*; do not read it as rolling-only. Contrast: the rolling-only restriction genuinely applies to the **circuit breaker** ([API_DeploymentConfiguration](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentConfiguration.html) attaches its rolling-only note to `deploymentCircuitBreaker`, not `alarms`).
- **Bake time:** alarm monitoring starts after all target-revision tasks are running/healthy and old revisions are scaled to zero, and continues for a bake period (the doc states only that the default bake time is "less than 5 minutes" — AWS does not publish an exact value). The deployment stays `IN_PROGRESS` until the bake completes — raise CloudFormation/pipeline timeouts accordingly.
- **Gotchas (both documented):**
  - ECS polls alarms via `DescribeAlarms`, which counts against CloudWatch API quotas — heavy account-wide `DescribeAlarms` usage can throttle ECS's polling, causing a **missed alarm and a skipped rollback**.
  - If an alarm is already in `ALARM` state when the deployment starts, ECS **ignores the alarm configuration for that deployment** — deliberately, so you can deploy a fix for the very thing that is alarming.
- Recommended alarm metrics (from the doc): ALB `HTTPCode_ELB_5XX_Count` / `HTTPCode_ELB_4XX_Count`, service `CPUUtilization` / `MemoryUtilization`, SQS `ApproximateNumberOfMessagesNotVisible`. Choose metrics that regress quickly when a bad revision ships. (For designing the broader alarm/dashboard stack, route to the `ecs-observability` skill.)

Launch-type note: alarm detection is metric-driven; the docs scope it only by deployment controller, and EC2/Fargate are covered explicitly. Managed Instances support is **inferred, not explicitly documented as of 2026-07-10 — verify** (same posture as the ECS Anywhere circuit-breaker caveat above). On ECS Anywhere there is no ELB, so any alarm use there must rest on service/application metrics, not ALB metrics.

## Combining Both Methods

Sources: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-ecs.html and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-alarm-failure.html (verified 2026-07-09)

- Circuit breaker and alarms can be used **separately or together**. When both are configured, the deployment fails **as soon as either criterion is met** — first to trip wins.
- Rollback happens if the **tripping method** has rollback enabled — enable rollback on both unless you have a reason not to.
- Division of labor: circuit breaker catches "tasks can't start / can't get healthy"; alarms catch "tasks are healthy but the application regressed" (error rates, latency, backlog).

## The Rollback Ladder

Ordered fastest-first. Sources cited per rung (verified 2026-07-09).

1. **Bake-time weight flip** (blue/green-family only). While blue still runs, rollback is a listener-rule weight change back to blue — near-instant, no task relaunch. Triggered automatically by hook failures and stage timeouts, or manually (rung 2). ([how blue/green works](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/blue-green-deployment-how-it-works.html))
2. **`stop-service-deployment` with ROLLBACK** (any strategy under the `ECS` controller; GA May 5, 2025 — [What's New](https://aws.amazon.com/about-aws/whats-new/2025/05/amazon-ecs-1-click-rollbacks-service-deployments/)):
   ```bash
   aws ecs list-service-deployments --cluster prod --service web
   aws ecs stop-service-deployment \
     --service-deployment-arn <arn> --stop-type ROLLBACK
   ```
   Rolls back to the previous service revision **even if rollback was never configured** on the service. Stoppable states: `PENDING`, `IN_PROGRESS` (→ `ROLLBACK_REQUESTED`), `STOP_REQUESTED`, `ROLLBACK_REQUESTED`, `ROLLBACK_IN_PROGRESS`. ([stop-service-deployment](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/stop-service-deployment.html), verified 2026-07-10). Note: the [API_StopServiceDeployment](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_StopServiceDeployment.html) `stopType` enum lists `ABORT | ROLLBACK`, while its prose says the valid value is `ROLLBACK` — use `ROLLBACK`.
3. **Automatic rollback** — circuit-breaker trip (rolling only), alarm trip (any `ECS`-controller strategy), lifecycle-hook FAILED/ROLLBACK, pause-hook timeout with ROLLBACK action, or a 24 h stage timeout (blue/green-family). Target: most recent `COMPLETED` deployment. ([circuit breaker](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html), [pause hooks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/pause-lifecycle-hooks.html))
4. **Manual re-deploy of the previous task-definition revision** via `UpdateService` — the universal fallback under the `ECS` and CodeDeploy controllers. It does **not** work under the `EXTERNAL` controller: there `UpdateService` changes only desired count and health-check grace period, so roll back by shifting traffic/scale back to your previous task set ([deployment-type-external](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-external.html); see [controllers-and-migration.md](controllers-and-migration.md)). CodeDeploy-controller rollback reroutes traffic back to the original task set. ([CodeDeploy ECS steps](https://docs.aws.amazon.com/codedeploy/latest/userguide/deployment-steps-ecs.html))

## What --force-new-deployment Actually Does

Sources: https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_UpdateService.html#ECS-UpdateService-request-forceNewDeployment and https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ecs-service.html#cfn-ecs-service-forcenewdeployment (verified 2026-07-10)

`aws ecs update-service --force-new-deployment` starts a new deployment **with no service-definition changes**. It is a restart/re-pull, **not a rollback**:

- Legitimate uses: pull a newer image behind the same mutable tag (`my_image:latest`), move Fargate tasks onto a newer platform version, restart the application fleet, re-establish image digests (updated digests apply to newly launched tasks only).
- Why it can't roll back: it redeploys the **same task definition** the service already points at. If that revision is the broken one, forcing "redeploys the outage".
- Prefer immutable tags + a new task-definition revision over mutable-tag force-redeploys — force-redeploying `latest` makes what's running unauditable.
- For an actual rollback, use rung 2 or 4 above.

## Observability of Deployments

Sources: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service_deployment_events.html (verified 2026-07-09)

- `aws ecs describe-services` exposes per-deployment `rolloutState` (`IN_PROGRESS` → `COMPLETED` / `FAILED`) and `rolloutStateReason`. A `FAILED` deployment launches no new tasks.
- ECS emits **EventBridge service-deployment state-change events** — alert on `eventName = SERVICE_DEPLOYMENT_FAILED`. Rollback-initiated deployments carry a `reason` field indicating the rollback.
- `aws ecs describe-service-deployments` shows deployment/hook detail (including `lifecycleHookDetails` with pause-hook `hookId`s).
- Pause hooks emit `ECS Hook State Change` events with status `HOOK_AWAITING_ACTION` — the trigger for approval workflows.
- Building the dashboards/alerting stack around these events is `ecs-observability` territory; this skill owns which events matter for release safety.
