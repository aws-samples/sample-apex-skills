---
title: "ecs-devops"
description: "Use when someone is deploying, releasing, or shipping software to Amazon ECS — phrased as \"blue/green deployment on ECS\", \"canary deployment for my ECS service\", \"set up CI/CD for ECS\", \"GitHub Actions deploy to Fargate\", \"my ECS deployment is stuck\", \"ECS deployment circuit breaker\", \"ECS task sets\", or \"migrate off CodeDeploy blue/green\". Covers strategy selection (rolling/blue-green/linear/canary), lifecycle hooks, circuit-breaker and alarm rollback, and pipelines (CodePipeline, GitHub Actions, ECR scanning) — scoped per launch type (EC2, Fargate, Managed Instances, ECS Anywhere). Trigger even if \"deployment strategy\" is never said — any release-safety, traffic-shifting, rollback, or pipeline decision for an ECS service qualifies. Skip for EKS/Kubernetes (use eks-* skills) and greenfield ECS architecture with no release angle (use ecs-architect for design and ecs-build for Terraform generation incl. deployment config blocks). For ECS monitoring stacks use ecs-observability; for GPU/ML on ECS use ecs-genai."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-devops/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-devops/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-devops/SKILL.md). Edit the source, not this page.
:::


# ECS DevOps — Deployment Strategies and CI/CD

Advisory guidance for shipping software to Amazon ECS safely: choosing a deployment strategy (rolling, native blue/green, linear, canary), configuring failure detection and rollback (circuit breaker, CloudWatch alarms, one-click rollback), and wiring CI/CD pipelines (CodePipeline, GitHub Actions, ECR scanning). Every capability is scoped by launch type — EC2, Fargate, ECS Managed Instances, and ECS Anywhere (EXTERNAL) — because the strategy menu is not the same on each.

> **The accuracy bar (non-negotiable for this skill).** ECS deployment capabilities changed rapidly between mid-2025 and mid-2026 (native blue/green Jul 2025, linear/canary Oct 2025, NLB for linear/canary Feb 2026, pause/continue May 2026, configurable circuit breaker Jul 2026). Never state a strategy/load-balancer/launch-type support combination you cannot cite to an AWS-published source — stale claims in this domain are usually *plausible but wrong*. When in doubt, defer to the live [ECS service deployment options page](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service-options.html).

## When to Use This Skill

**Activate when the user wants to:**
- Pick a deployment strategy for an ECS service (rolling vs blue/green vs canary vs linear)
- Configure or debug native ECS blue/green, linear, or canary deployments (lifecycle hooks, bake time, test traffic, weighted target groups)
- Set up the deployment circuit breaker, CloudWatch alarm rollback, or deployment pause/continue
- Roll back a bad ECS deployment, or understand why a deployment is stuck or failed
- Build a CI/CD pipeline that deploys to ECS (CodePipeline, GitHub Actions, ECR push + scan + deploy)
- Migrate from the CodeDeploy blue/green controller to ECS-native strategies
- Understand the external deployment controller / task sets
- Know which strategies work on Fargate vs EC2 vs Managed Instances vs ECS Anywhere

**Don't use this skill for:**
- EKS or Kubernetes deployments of any kind → use the `eks-*` skills (`eks-best-practices` for strategy, `eks-build` for artifacts)
- ECS monitoring, logging, metrics, tracing, or alerting *stack selection* → `ecs-observability` (this skill covers alarms only as deployment-failure triggers)
- GPU / ML / GenAI workloads on ECS → `ecs-genai`
- ECS security posture, IAM hardening, or compliance → `ecs-security`
- Auditing the operational health of a live ECS cluster → `ecs-operation-review`
- Greenfield ECS architecture / launch-type selection with no deployment or pipeline angle → `ecs-architect`

If a routed sibling skill is not installed yet, don't dead-end the user: answer from general knowledge (staying within this skill's cited facts where they apply) and note that a dedicated skill is pending.

### Sibling Skill Disambiguation

| User Intent | Correct Skill | Why |
|---|---|---|
| "Set up canary deployments for my ECS service" | `ecs-devops` | Release strategy and traffic shifting |
| "Alert me when my ECS service errors spike" | `ecs-observability` | Monitoring stack, not deployment safety (this skill covers alarms only as rollback triggers) |
| "Which launch type should my new ECS app use?" | `ecs-architect` | Architecture decision, no release angle |
| "Harden the IAM roles my pipeline uses" | `ecs-security` | Security posture, not pipeline mechanics |
| "Is my ECS cluster healthy / well configured?" | `ecs-operation-review` | Live operational audit |
| "Deploy an LLM inference container to ECS" | `ecs-genai` | GPU/ML workload specifics |
| "Blue/green on EKS" | `eks-best-practices` | Kubernetes, not ECS |

---

## Deployment Controller and Strategy Model

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service-options.html
> GA dates in this skill follow AWS **What's New post dates**; the ECS doc-history page can log the same launch a few days earlier (e.g., blue/green Jul 15 vs Jul 17, 2025) — both are AWS sources, this skill standardizes on What's New except where it explicitly cites doc history.

- `deploymentController.type` has three values — `ECS`, `CODE_DEPLOY`, `EXTERNAL`.
- Under the **`ECS` controller**, `deploymentConfiguration.strategy` selects one of four built-in strategies — `ROLLING` (default), `BLUE_GREEN` (GA Jul 17, 2025), `LINEAR` and `CANARY` (GA Oct 30, 2025).
- The **`CODE_DEPLOY` controller** is the older blue/green path. For **new** adoptions, AWS's stated recommendation is the native ECS blue/green deployment ([deployment-type-bluegreen](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-bluegreen.html)). It remains fully supported with **no announced end-of-life** — staying on CodeDeploy indefinitely is a valid steady state for existing estates; migrate when you want something native adds (Service Connect, richer hooks, simpler pipelines), not by default.
- The **`EXTERNAL` controller** hands the whole deployment process to your own tooling via task-set APIs — see [references/controllers-and-migration.md](references/controllers-and-migration).
- Since **July 15, 2025** the deployment controller is **updatable in place** on an existing service — you can migrate a service between controller types without recreating it ([doc history](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/document_history.html)).

### Strategy Selector

| You need | Strategy | Why |
|---|---|---|
| Default, no load balancer, cost-sensitive, stateful, or ECS Anywhere | `ROLLING` | Only strategy with no load-balancer requirement; min/max percent controls capacity during rollout |
| Instant cutover with near-instant rollback window | `BLUE_GREEN` | All-at-once weighted-target-group flip; blue kept running through bake time |
| Gradual equal-step traffic shift (e.g., 10% at a time) | `LINEAR` | `stepPercent` + per-step bake time; hooks fire at every step |
| Small validation slice, then full cutover | `CANARY` | Two-step shift (canary % → 100%) with canary bake time |
| Keep an existing CodePipeline CodeDeploy integration working | `CODE_DEPLOY` controller | Fully supported steady state (no announced EOL); AWS recommends native for new workloads |
| Your own deployment engine (custom orchestration) | `EXTERNAL` controller | Task-set APIs, you own everything |

Blue/green, linear, and canary all run blue and green revisions simultaneously — plan for up to **2× capacity** (EC2 cluster headroom or Fargate/Managed Instances spend) during deployments ([deployment-type-blue-green](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-blue-green.html)).

### Load Balancer Support Matrix (current state)

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service-options.html and https://aws.amazon.com/about-aws/whats-new/2026/02/amazon-ecs-nlb-linear-canary-deployments/
>
> ⚠️ **Stale-claim trap:** "linear/canary support only ALB and Service Connect" was true only from Oct 2025 to Feb 2026. **NLB support for linear and canary launched Feb 4, 2026.** If you have seen the older claim (including in earlier internal material), it is obsolete — state the matrix below with its verification date.

| Strategy | ALB | NLB | Service Connect | No LB / headless |
|---|---|---|---|---|
| `ROLLING` | ✅ | ✅ | ✅ | ✅ |
| `BLUE_GREEN` | ✅ | ✅ since launch (Jul 2025) — traffic-shift stages take ~10 min longer on NLB | ✅ | ⚠️ Works on EC2/Fargate/Managed Instances (**not documented for ECS Anywhere — do not recommend it there**), but ECS replaces blue with green **without managed traffic shifting** |
| `LINEAR` | ✅ | ✅ since Feb 4, 2026 | ✅ | ❌ Not documented as supported |
| `CANARY` | ✅ | ✅ since Feb 4, 2026 | ✅ | ❌ Not documented as supported |
| `CODE_DEPLOY` controller | ✅ | ⚠️ All-at-once only (`CodeDeployDefault.ECSAllAtOnce`) | ❌ | ❌ Load balancer required |
| `EXTERNAL` controller | ✅ (one target group per task set) | ✅ | ❌ | ✅ Load balancer is optional on task sets — when omitted, you manage all traffic yourself |

Sources: [blue/green implementation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/blue-green-deployment-implementation.html) · [NLB nuance](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-blue-green.html) · [CodeDeploy controller](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-bluegreen.html) · [external controller](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-external.html) · [Service Connect deployment support](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect-concepts-deploy.html)

### Launch-Type Scoping (applies to everything in this skill)

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateService.html and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html

- The `launchType` enum has **four values: `EC2 | FARGATE | EXTERNAL | MANAGED_INSTANCES`**. `FARGATE_SPOT` is **not** a launch type — it is a capacity provider ("a capacity provider strategy must be used" for Fargate Spot). To use ECS Managed Instances you specify a `capacityProviderStrategy` and omit `launchType` — `launchType` and `capacityProviderStrategy` are mutually exclusive on `CreateService`, so a request that sets both is rejected. The `MANAGED_INSTANCES` enum value exists because launch type appears in API responses and task metadata; it is not how you *select* Managed Instances ([API_CreateService](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateService.html)).
- **EC2 launch type:** all four strategies and both failure-detection methods. Service Connect needs ECS agent ≥ 1.67.2 on a current ECS-optimized AMI; image-digest resolution needs agent ≥ 1.31.0 for ECR-hosted images and ≥ 1.70.0 for all other registries ([Service Connect deploy](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect-concepts-deploy.html), [rolling deployment](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-ecs.html)).
- **Fargate:** all four strategies; no `DAEMON` scheduling; Service Connect needs Linux platform version ≥ 1.4.0. Circuit breaker GA covered both EC2 and Fargate ([GA announcement](https://aws.amazon.com/about-aws/whats-new/2020/12/amazon-ecs-announces-the-general-availability-of-ecs-deployment-circuit-breaker/)).
- **ECS Managed Instances** (GA Sep 30, 2025): fully managed EC2-based compute consumed **via capacity providers only** ([Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html)). **Strategy support: all four native strategies (`ROLLING`, `BLUE_GREEN`, `LINEAR`, `CANARY`) via the `ECS` controller** — the native strategy pages scope by load balancer/Service Connect, not away from Managed Instances ([blue/green implementation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/blue-green-deployment-implementation.html)). Failure-detection support (circuit breaker, alarms) on Managed Instances is **inferred from the docs scoping those features only by deployment controller — not explicitly documented for Managed Instances as of 2026-07-10; verify before relying on it** (same evidence posture as the ECS Anywhere caveat below). **`CODE_DEPLOY` and `EXTERNAL` controllers on Managed Instances are not clearly documented:** both are task-set-based, and the developer guide documents task-set `launchType` as `EC2 | FARGATE | EXTERNAL` ([external controller](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-external.html)) while the [CreateTaskSet API reference](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateTaskSet.html) lists `MANAGED_INSTANCES` in the enum — the two pages disagree, so do not claim controller support beyond `ECS` for Managed Instances; say the docs are inconsistent and verify.
- **ECS Anywhere (`EXTERNAL` launch type):** no service load balancing, no service discovery, no `awsvpc` network mode, no capacity providers, and Service Connect is explicitly unsupported on external container instances. Net effect — **no managed traffic shifting is possible, so rolling update (min/max percent) is the practical deployment strategy on ECS Anywhere.** Blue/green-family support without traffic management is not documented for Anywhere — do not claim it. Circuit-breaker support on the `EXTERNAL` launch type is **not explicitly documented** — the docs scope the circuit breaker only by deployment controller, and the [GA announcement](https://aws.amazon.com/about-aws/whats-new/2020/12/amazon-ecs-announces-the-general-availability-of-ecs-deployment-circuit-breaker/) names EC2 and Fargate — verify before relying on it. ([ECS Anywhere](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html), [Service Connect deploy](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect-concepts-deploy.html))

---

## Rolling Update Quick Reference

> Facts verified 2026-07-10 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-ecs.html and https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentConfiguration.html

- `minimumHealthyPercent` — lower bound on running-and-healthy tasks during deployment, as % of desired count, **rounded up**. Default 100% for replica services. Example: min 50% + desired 4 → the scheduler may stop 2 tasks before starting replacements; min 75% + desired 2 → it cannot stop any first.
- `maximumPercent` — upper bound on running tasks, as % of desired count, **rounded down**. Example: max 200% + desired 4 → 4 new tasks can start before any old stop; max 125% + desired 3 → no task can start first. Daemon services: `maximumPercent` must be 100; default min-healthy is 0% via CLI/SDK/API but **50% via the console** ([API_DeploymentConfiguration](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentConfiguration.html)).
- **Zero-downtime recipe:** `minimumHealthyPercent=100, maximumPercent=200` — requires headroom for 2× tasks during the rollout (applies on EC2 only if the cluster has spare capacity; on Fargate/Managed Instances it is a spend question).
- Misconfigured min/max that prevents both stopping and starting **stalls the deployment** and emits a service event — check service events first when a rolling deployment hangs.
- **Version consistency:** ECS resolves image tags to digests at deployment time (first started task pins the digests); 3+ digest-resolution failures with circuit breaker enabled fail and roll back the deployment. Configurable per container via `versionConsistency`.
- **Always pair rolling with failure detection** (on EC2/Fargate/Managed Instances; see the ECS Anywhere caveat above) — circuit breaker for "tasks can't start / can't get healthy", CloudWatch alarms for "metrics regressed". Circuit breaker is rolling-only; alarms work with any strategy under the `ECS` controller; usable together; **whichever trips first fails the deployment** ([alarm-based detection](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-alarm-failure.html)).

```bash
aws ecs update-service --cluster prod --service web \
  --deployment-configuration \
  'minimumHealthyPercent=100,maximumPercent=200,deploymentCircuitBreaker={enable=true,rollback=true,resetOnHealthyTask=true,thresholdConfiguration={type=BOUNDED_PERCENT,value=50}},alarms={alarmNames=[web-5xx-alarm],enable=true,rollback=true}'
```

**For circuit breaker thresholds, alarm gotchas, and the full rollback ladder, see:** [Failure Detection & Rollback](references/failure-detection-and-rollback)

---

## Native Blue/Green, Linear, and Canary Quick Reference

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-blue-green.html and https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateService.html

All three are "blue/green-family": ECS stands up the green revision, optionally routes **test traffic** to it (Service Connect default test header: `x-amzn-ecs-blue-green-test`), shifts production traffic via weighted listener-rule target groups (all-at-once for `BLUE_GREEN`, stepped for `LINEAR`/`CANARY`), then holds both revisions through **bake time** before cleaning up blue. Rollback during bake time is a near-instant weight flip — no task relaunch.

Required plumbing (ALB/NLB path): a production listener rule pre-configured with two target groups weighted 1 and 0, plus per-load-balancer `advancedConfiguration` on the service (`alternateTargetGroupArn`, `productionListenerRule`, optional `testListenerRule`, and an infrastructure IAM role carrying `AmazonECSInfrastructureRolePolicyForLoadBalancers`) ([CodeDeploy-to-native migration overview](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/migrate-codedeploy-to-ecs-bluegreen.html)).

Minimal, correct `deploymentConfiguration` shapes (`ECS` controller — [API_CreateService](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateService.html)):

```jsonc
// Blue/green — all-at-once shift, 15-minute bake
"deploymentConfiguration": {
  "strategy": "BLUE_GREEN",
  "bakeTimeInMinutes": 15
}

// Canary — 10% first, bake 30 min on the canary slice, then 100%, then 15-min final bake
"deploymentConfiguration": {
  "strategy": "CANARY",
  "canaryConfiguration": { "canaryPercent": 10.0, "canaryBakeTimeInMinutes": 30 },
  "bakeTimeInMinutes": 15
}

// Linear — 20% steps (20/40/60/80/100), 10-min bake per step, 15-min final bake
"deploymentConfiguration": {
  "strategy": "LINEAR",
  "linearConfiguration": { "stepPercent": 20.0, "stepBakeTimeInMinutes": 10 },
  "bakeTimeInMinutes": 15
}
```

Valid ranges: `stepPercent` 3.0–100.0; `stepBakeTimeInMinutes` 0–1440 ([linear deployment](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-linear.html)). Do **not** put `deploymentCircuitBreaker` in blue/green-family configs — the circuit breaker is rolling-only (see below).

- **Lifecycle stages** (shared by all three): RECONCILE_SERVICE → PRE_SCALE_UP → SCALE_UP → POST_SCALE_UP → TEST_TRAFFIC_SHIFT → POST_TEST_TRAFFIC_SHIFT → PRE_PRODUCTION_TRAFFIC_SHIFT → PRODUCTION_TRAFFIC_SHIFT → POST_PRODUCTION_TRAFFIC_SHIFT → BAKE_TIME → CLEAN_UP. Hooks attach to all stages except SCALE_UP, BAKE_TIME, CLEAN_UP; TEST_TRAFFIC_SHIFT and PRODUCTION_TRAFFIC_SHIFT (exactly those two — not the PRE_/POST_ variants) accept Lambda hooks only ([how it works](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/blue-green-deployment-how-it-works.html)).
- For linear/canary, PRE_PRODUCTION_TRAFFIC_SHIFT / PRODUCTION_TRAFFIC_SHIFT hooks fire at **every** traffic step; each production shift step may last up to 24 h.
- **Pause/continue** (GA May 19, 2026): `PAUSE`-type lifecycle hooks on rolling *and* blue/green-family deployments (the rolling scope comes from the [What's New](https://aws.amazon.com/about-aws/whats-new/2026/05/amazon-ecs-pause-continue-deployments/); the doc page illustrates only blue/green-family stages; ECS Anywhere support is not documented as of 2026-07-10); resume or abort with `aws ecs continue-service-deployment --hook-id <id> --action CONTINUE|ROLLBACK` ([pause hooks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/pause-lifecycle-hooks.html)).
- **Timeouts:** each lifecycle stage max 24 h (timeout → fail + roll back); CloudFormation adds a 36 h whole-deployment cap; overall deployment limit 30 days.

**For full lifecycle-hook config, test-traffic routing, pause/continue details, and deployment-speed tuning, see:** [Deployment Strategies Deep Dive](references/deployment-strategies)

---

## Failure Detection — Circuit Breaker vs CloudWatch Alarms

> Facts verified 2026-07-10 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html and https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentAlarms.html
>
> ⚠️ **Scope wording trap:** one sentence on the [alarm-detection page](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-alarm-failure.html) reads "only supported for … the rolling update (ECS) deployment controller" — that "rolling update (ECS)" is the doc's name for the **controller**, not a strategy restriction. The API reference and the blue/green service definition (below) make the controller-vs-strategy distinction explicit.

| | Deployment circuit breaker | CloudWatch alarm detection |
|---|---|---|
| Detects | Task-launch failures + health-check failures (ELB, Cloud Map, container health checks) | Any metric regression you can alarm on (5xx, latency, queue depth) |
| Scope | **Rolling only**, under the `ECS` controller — the API attaches the rolling-only note to `deploymentCircuitBreaker` specifically ([API_DeploymentConfiguration](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentConfiguration.html)) | **Controller-scoped, not strategy-scoped**: any strategy under the `ECS` controller (not CODE_DEPLOY/EXTERNAL) — [API_DeploymentAlarms](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentAlarms.html) restricts only "when the DeploymentController is set to ECS", and AWS's own blue/green service definition sets `alarms` with `"strategy": "BLUE_GREEN"` ([deploy-blue-green-service](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deploy-blue-green-service.html)); blue/green-family adds hooks + bake time on top |
| Trigger config | `deploymentCircuitBreaker={enable,rollback,resetOnHealthyTask,thresholdConfiguration}` | `alarms={alarmNames=[...],enable=true,rollback=true}` |
| Combinable | Yes — first method to trip fails the deployment; rollback runs if the tripping method has rollback enabled | Yes (same) |

Jul 1, 2026 knobs ([What's New](https://aws.amazon.com/about-aws/whats-new/2026/07/amazon-ecs-circuit-breaker-settings/)):
- `thresholdConfiguration.type`: `BOUNDED_PERCENT` (default; value default 50; threshold = ceil(value% × desired count) clamped to min 3 / max 200), `UNBOUNDED_PERCENT` (same formula, no clamps), or `COUNT` (fixed number).
- `resetOnHealthyTask`: `true` (default) counts **consecutive** failures (counter resets on a healthy task); `false` counts **cumulative** failures across the deployment.

Alarm-detection gotchas: ECS polls alarms via `DescribeAlarms` (CloudWatch API throttling can cause a missed rollback — mitigate by also enabling the circuit breaker and alerting on `SERVICE_DEPLOYMENT_FAILED`, both covered in this skill), and an alarm already in ALARM state at deployment start is **ignored for that deployment** — deliberately, so you can deploy a fix ([alarm detection](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-alarm-failure.html)).

## The Rollback Ladder (fastest first)

1. **Bake-time weight flip** (blue/green-family only) — while blue is still running, rollback is a listener-weight change; near-instant, no task relaunch.
2. **One-click manual rollback** (any strategy **under the `ECS` deployment controller**, while the deployment is in a stoppable state — `PENDING`, `IN_PROGRESS`, `STOP_REQUESTED`, `ROLLBACK_REQUESTED`, or `ROLLBACK_IN_PROGRESS`; GA May 2025): `aws ecs stop-service-deployment --service-deployment-arn <arn> --stop-type ROLLBACK` — rolls back to the previous service revision **even if rollback was never configured** on the service. Find the ARN with `aws ecs list-service-deployments`. For CodeDeploy-controller services or deployments that already reached `COMPLETED`, use rung 4 instead ([stop-service-deployment](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/stop-service-deployment.html)).
3. **Automatic rollback** — circuit breaker trips (rolling only), an alarm trips (any `ECS`-controller strategy), or a lifecycle-hook/stage-timeout failure (blue/green-family); target is the most recent `COMPLETED` deployment. If no COMPLETED deployment exists, the circuit breaker does not launch new tasks and the *failed* deployment stalls — clean up manually.
4. **Manual re-deploy** — `UpdateService` back to the previous task-definition revision (universal fallback under the `ECS` and CodeDeploy controllers; under `EXTERNAL`, `UpdateService` cannot change the task definition — roll back by shifting your own task sets).

> ❌ **`--force-new-deployment` is NOT a rollback.** It starts a new deployment with **no service-definition changes** — a restart/re-pull (e.g., pick up a newer image behind the same mutable tag, refresh image digests, move to a newer Fargate platform version). It redeploys the *same* task definition; it does not return you to the previous revision. This is a common misconception — reach for `stop-service-deployment --stop-type ROLLBACK` or a previous task-def revision instead ([UpdateService](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_UpdateService.html#ECS-UpdateService-request-forceNewDeployment)).

**For rollback targets, EventBridge deployment events, and stoppable deployment states, see:** [Failure Detection & Rollback](references/failure-detection-and-rollback)

---

## CI/CD Quick Reference

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/codepipeline/latest/userguide/integrations-action-type.html and the aws-actions GitHub repos linked below

| Pipeline | Mechanism | Deploys via | Input contract |
|---|---|---|---|
| CodePipeline "Amazon ECS" (standard) action | Rolling-style deploy of a new image to the service | ECS APIs | `imagedefinitions.json` |
| CodePipeline "ECS (Blue/Green)" action (`CodeDeployToECS`) | CodeDeploy-controller blue/green | CodeDeploy | `imageDetail.json` + AppSpec + task-def templates |
| GitHub Actions (official `aws-actions/*`) | Render + register task def, update service; optional CodeDeploy blue/green | ECS or CodeDeploy APIs | Task-definition JSON in repo |
| ECS-native BLUE_GREEN / LINEAR / CANARY from any pipeline | Plain `aws ecs update-service` — the service's configured strategy governs the deployment | ECS `UpdateService` | Task-definition revision |

- **There is no dedicated CodePipeline action for ECS-native blue/green/linear/canary (as of 2026-07-10).** AWS's migration guidance is to switch pipelines from CodeDeploy `CreateDeployment` to the ECS `UpdateService` API ([CodeDeploy-to-native migration overview](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/migrate-codedeploy-to-ecs-bluegreen.html)).
- GitHub Actions building blocks (all official, `aws-actions` org): `configure-aws-credentials` (OIDC — no long-lived keys), `amazon-ecr-login`, `amazon-ecs-render-task-definition` (inject the new image URI), `amazon-ecs-deploy-task-definition` (register + deploy; `wait-for-service-stability`; CodeDeploy blue/green via `codedeploy-appspec`/`codedeploy-application`/`codedeploy-deployment-group`; actively maintained — v2.6.3, Jul 2026).
- **ECR scanning in the pipeline:** basic scanning (OS-package CVEs, on-push filters) or enhanced scanning via Amazon Inspector (OS + language packages, continuous rescans, ECS image-usage context, Inspector pricing applies). Gate deploys on scan findings via EventBridge ([basic](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-basic-enabling.html) · [enhanced](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced.html)).
- **Launch-type caveat:** pipeline mechanics (register task def → update service) are identical for EC2, Fargate, and Managed Instances — **except ECS Anywhere, which is rolling-only: never attach CodeDeploy blue/green actions or native blue/green-family expectations to an Anywhere service** ([ECS Anywhere](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html)).

**For full pipeline walkthroughs, a GitHub Actions workflow skeleton, and scan-gating patterns, see:** [CI/CD Pipelines](references/cicd-pipelines)

---

## Top Guardrails (the high-cost mistakes)

1. **Don't treat `--force-new-deployment` as a rollback** — it re-deploys the same task definition (restart/re-pull). Use `stop-service-deployment --stop-type ROLLBACK`.
2. **Don't repeat the pre-Feb-2026 LB matrix** — linear/canary support NLB since Feb 4, 2026. Always state support matrices with a verification date.
3. **Don't configure the circuit breaker on blue/green-family services** — the circuit breaker is rolling-only. CloudWatch alarm detection is *not* — it works with any `ECS`-controller strategy. Blue/green-family safety = hooks + bake time + stage timeouts + (optionally) alarms.
4. **Don't ship rolling deployments with no failure detection** — a bad deployment can stay "in progress" indefinitely. Enable circuit breaker + alarms with rollback (on EC2/Fargate/Managed Instances; see the Anywhere caveat in Launch-Type Scoping), and alert on the `SERVICE_DEPLOYMENT_FAILED` EventBridge event.
5. **Don't recommend blue/green-family strategies on ECS Anywhere** — no ELB, no Service Connect, therefore no managed traffic shifting. Rolling only.
6. **Don't call `FARGATE_SPOT` a launch type** — it is a capacity provider; the launch-type enum is `EC2 | FARGATE | EXTERNAL | MANAGED_INSTANCES`, and Managed Instances itself is selected via `capacityProviderStrategy`, not `launchType`.
7. **Don't start a blue/green-family rollout without 2× capacity headroom** — blue and green run simultaneously until CLEAN_UP.
8. **Don't build new CodeDeploy-controller integrations** — AWS recommends native strategies for new adoptions; the controller is updatable in place since Jul 2025, so migration does not require service recreation. (But do not call CodeDeploy "deprecated" or push working existing CodeDeploy estates to migrate — it is a supported steady state with no announced EOL.)
9. **Don't forget both target groups must be associated with the production/test listener rules** — otherwise blue/green deployments fail with an invalid-networking-configuration rollback ([migration steps page](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/migrate-code-deploy-to-ecs-blue-green.html) — a distinct page from the migration overview).

---

## Detailed References

This skill uses **progressive disclosure** — essentials live in this file; load a reference when the task needs depth.

| Reference | Load when the task is about… |
|---|---|
| [deployment-strategies.md](references/deployment-strategies) | Configuring rolling min/max, blue/green/linear/canary end-to-end (target groups, listener rules, infrastructure role), lifecycle hooks, test traffic, pause/continue, deployment-speed tuning (health checks, deregistration delay, grace period) |
| [failure-detection-and-rollback.md](references/failure-detection-and-rollback) | Circuit breaker thresholds and worked examples, CloudWatch alarm detection and gotchas, the rollback ladder in detail, stop-service-deployment, EventBridge deployment events |
| [cicd-pipelines.md](references/cicd-pipelines) | CodePipeline ECS actions (standard + blue/green), GitHub Actions workflows for ECS, OIDC credentials, ECR image scanning in pipelines, launch-type notes for pipelines (incl. ECS Anywhere) |
| [controllers-and-migration.md](references/controllers-and-migration) | CodeDeploy controller specifics, migrating CodeDeploy → native blue/green (three approaches, CloudFormation path), the external deployment controller and task sets |

---

## Sources

- [Amazon ECS service deployment options](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service-options.html) · [Rolling update](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-ecs.html) · [Blue/green deployment](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-blue-green.html) · [How blue/green works](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/blue-green-deployment-how-it-works.html) · [Linear deployment](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-linear.html) · [Canary deployment](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/canary-deployment.html)
- [Deployment circuit breaker](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html) · [CloudWatch alarm failure detection](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-alarm-failure.html) · [Pause lifecycle hooks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/pause-lifecycle-hooks.html) · [Stopping a service deployment](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/stop-service-deployment.html)
- [CodeDeploy blue/green (legacy controller)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-bluegreen.html) · [Migrate CodeDeploy to native blue/green](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/migrate-codedeploy-to-ecs-bluegreen.html) · [External deployment controller](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-external.html)
- [ECS CreateService API](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateService.html) · [ECS UpdateService API](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_UpdateService.html) · [ECS document history](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/document_history.html)
- What's New: [built-in blue/green (Jul 2025)](https://aws.amazon.com/about-aws/whats-new/2025/07/amazon-ecs-built-in-blue-green-deployments/) · [linear & canary (Oct 2025)](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-ecs-built-in-linear-canary-deployments/) · [NLB for linear/canary (Feb 2026)](https://aws.amazon.com/about-aws/whats-new/2026/02/amazon-ecs-nlb-linear-canary-deployments/) · [pause/continue (May 2026)](https://aws.amazon.com/about-aws/whats-new/2026/05/amazon-ecs-pause-continue-deployments/) · [configurable circuit breaker (Jul 2026)](https://aws.amazon.com/about-aws/whats-new/2026/07/amazon-ecs-circuit-breaker-settings/) · [1-click rollbacks (May 2025)](https://aws.amazon.com/about-aws/whats-new/2025/05/amazon-ecs-1-click-rollbacks-service-deployments/)
- [CodePipeline integrations](https://docs.aws.amazon.com/codepipeline/latest/userguide/integrations-action-type.html) · [CodePipeline image file reference](https://docs.aws.amazon.com/codepipeline/latest/userguide/file-reference.html) · [ECS blue/green action reference](https://docs.aws.amazon.com/codepipeline/latest/userguide/action-reference-ECSbluegreen.html)
- GitHub Actions: [amazon-ecs-deploy-task-definition](https://github.com/aws-actions/amazon-ecs-deploy-task-definition) · [amazon-ecs-render-task-definition](https://github.com/aws-actions/amazon-ecs-render-task-definition) · [amazon-ecr-login](https://github.com/aws-actions/amazon-ecr-login) · [configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials)
- [ECR basic scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-basic-enabling.html) · [ECR enhanced scanning (Inspector)](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced.html)
- [ECS Anywhere](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html) · [ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html) · [Service Connect deployment considerations](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect-concepts-deploy.html)

---

*This skill is provided as sample code for educational and demonstration purposes only. Verify point-in-time capability claims against the linked AWS documentation before acting on them. See the project's README and LICENSE for full terms.*
