---
title: "ECS DevOps — Deployment Strategies Deep Dive"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-devops/references/deployment-strategies.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-devops/references/deployment-strategies.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-devops/references/deployment-strategies.md). Edit the source, not this page.
:::

# ECS DevOps — Deployment Strategies Deep Dive

> **Part of:** [ecs-devops](../)
> **Purpose:** Full configuration detail for rolling, blue/green, linear, and canary deployments under the ECS deployment controller — lifecycle hooks, test traffic, pause/continue, and deployment-speed tuning

**For failure detection and rollback mechanics, see:** [failure-detection-and-rollback.md](failure-detection-and-rollback)
**For CodeDeploy-controller specifics and migration, see:** [controllers-and-migration.md](controllers-and-migration)

> Facts in this file verified 2026-07-09 against the AWS documentation URLs cited inline. Strategy/LB/launch-type support in this domain changed repeatedly between Jul 2025 and Jul 2026 — re-verify any support-matrix claim against the live [service deployment options page](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service-options.html) before repeating it.

---

## Table of Contents

1. [Rolling Update Mechanics](#rolling-update-mechanics)
2. [Blue/Green-Family Anatomy](#bluegreen-family-anatomy)
3. [Configuring Native Blue/Green](#configuring-native-bluegreen)
4. [Configuring Linear and Canary](#configuring-linear-and-canary)
5. [Lifecycle Hooks](#lifecycle-hooks)
6. [Test Traffic Routing](#test-traffic-routing)
7. [Pause and Continue](#pause-and-continue)
8. [Deployment Speed Tuning](#deployment-speed-tuning)
9. [Launch-Type Constraints Recap](#launch-type-constraints-recap)

---

## Rolling Update Mechanics

Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-ecs.html (verified 2026-07-10)

`ROLLING` is the default `deploymentConfiguration.strategy` under the `ECS` controller. The scheduler replaces old-revision tasks with new-revision tasks within the envelope defined by two percentages of the service's desired count:

| Parameter | Rounding | Default (replica) | Meaning |
|---|---|---|---|
| `minimumHealthyPercent` | Rounded **up** | 100% | Floor of running-and-healthy tasks during deployment or container-instance drain |
| `maximumPercent` | Rounded **down** | 200% | Ceiling of running tasks (old + new) during deployment |

Worked examples (from the AWS doc):
- min 50%, desired 4 → scheduler may stop 2 old tasks before starting 2 new (stop-first; fits in existing capacity).
- min 75%, desired 2 → 75% of 2 rounds up to 2 → cannot stop any task before a replacement is healthy.
- max 200%, desired 4 → 4 new tasks can start before 4 old stop (start-first; needs 2× headroom).
- max 125%, desired 3 → 125% of 3 rounds down to 3 → no new task can start before an old one stops.

Daemon services: `maximumPercent` must be 100; default `minimumHealthyPercent` is **0% via the CLI/SDKs/APIs but 50% via the AWS Management Console** ([API_DeploymentConfiguration](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentConfiguration.html), verified 2026-07-10). Fargate and ECS Managed Instances have no daemon scheduling, so this applies to the EC2 launch type (and ECS Anywhere) only.

Behavioral details worth knowing:
- **Unhealthy-task replacement:** during rolling deployments, unhealthy tasks are replaced within the same service revision they belong to, and when `maximumPercent` allows, replacements launch **before** the unhealthy tasks stop — preventing cascade failures under load ([deep-dive blog](https://aws.amazon.com/blogs/containers/a-deep-dive-into-amazon-ecs-task-health-and-task-replacement/)).
- **Stalls:** min/max values that prevent both stopping and starting stall the deployment and emit a service event — first place to look when a rolling deployment hangs.
- **Version consistency:** ECS resolves image tags to digests when the deployment starts (the first started task establishes digests for the revision). With circuit breaker enabled, 3+ digest-resolution failures fail and roll back the deployment. Opt out per container with `versionConsistency`. On the EC2 launch type, digest resolution requires container agent ≥ 1.31.0 (all registries ≥ 1.70.0).
- **Healthy counting without an LB** (verified 2026-07-09): tasks whose essential containers have no health check count toward min-healthy 40 seconds after reaching RUNNING; with an LB, target-group health must also pass ([API_DeploymentConfiguration](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentConfiguration.html)).

Zero-downtime recipe: `minimumHealthyPercent=100, maximumPercent=200`, plus failure detection (see [failure-detection-and-rollback.md](failure-detection-and-rollback)). On the EC2 launch type this needs spare cluster capacity for the extra tasks; on Fargate/Managed Instances it is purely a temporary-spend question.

---

## Blue/Green-Family Anatomy

Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/blue-green-deployment-how-it-works.html (verified 2026-07-09)

`BLUE_GREEN`, `LINEAR`, and `CANARY` share one machine. ECS creates the **green** service revision alongside the running **blue** revision, then walks these lifecycle stages:

```
RECONCILE_SERVICE -> PRE_SCALE_UP -> SCALE_UP -> POST_SCALE_UP
  -> TEST_TRAFFIC_SHIFT -> POST_TEST_TRAFFIC_SHIFT
  -> PRE_PRODUCTION_TRAFFIC_SHIFT -> PRODUCTION_TRAFFIC_SHIFT -> POST_PRODUCTION_TRAFFIC_SHIFT
  -> BAKE_TIME -> CLEAN_UP
```

- **Traffic shifting** happens by adjusting the weights on a listener rule that references two target groups (blue's and green's). `BLUE_GREEN` shifts 100% in one step; `LINEAR`/`CANARY` shift in steps (below).
- **Bake time** (`bakeTimeInMinutes`): after production traffic has fully shifted, blue keeps running until bake time expires — rollback during this window is a near-instant weight flip back to blue, with no task relaunch.
- **Timeouts:** each stage max 24 h (a stage timeout fails the deployment and triggers rollback); CloudFormation adds a 36 h whole-deployment limit; the overall deployment limit is 30 days.
- **Capacity:** blue and green run simultaneously until CLEAN_UP — plan for up to 2× task capacity during the deployment ([deployment-type-blue-green](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-blue-green.html)).
- **NLB nuance:** with a Network Load Balancer, TEST_TRAFFIC_SHIFT and PRODUCTION_TRAFFIC_SHIFT take roughly 10 minutes longer because ECS verifies it is safe to shift traffic.
- **Headless blue/green:** a service with no load balancer and no Service Connect can still use `BLUE_GREEN` — ECS replaces blue tasks with green but does **not** manage traffic shifting ([implementation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/blue-green-deployment-implementation.html)). This headless carve-out is documented for EC2/Fargate/Managed Instances — it is **not documented for ECS Anywhere**, so do not recommend headless blue/green there. Headless linear/canary is not documented as supported anywhere — do not claim it.

Launch-type scope: blue/green-family managed traffic shifting requires ALB, NLB, or Service Connect, so it is available on EC2, Fargate, and Managed Instances but **not ECS Anywhere** (no ELB, no Service Connect on external instances — [ECS Anywhere](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html), [Service Connect deploy](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect-concepts-deploy.html)).

---

## Configuring Native Blue/Green

Sources: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-blue-green.html and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/migrate-codedeploy-to-ecs-bluegreen.html (verified 2026-07-09)

Prerequisites (ALB path; NLB analogous — see [NLB resources](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/nlb-resources-for-blue-green.html), [ALB resources](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/alb-resources-for-blue-green.html)):

1. **Two target groups** — one for blue, one (alternate) for green.
2. **Production listener rule** pre-configured with both target groups **weighted 1 and 0**. Both target groups must be associated with the production (or test) listener rule, or the deployment rolls back with: "Both targetGroup and alternateTargetGroup must be associated with the productionListenerRule or testListenerRule."
3. Optional **test listener rule** (e.g., on port 8443, or header-matched) for pre-shift validation traffic.
4. **Infrastructure IAM role** the service can pass to ECS for ELB API calls, carrying the managed policy `AmazonECSInfrastructureRolePolicyForLoadBalancers` (policy published July 15, 2025 — [doc history](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/document_history.html)).

Minimal create-service (CLI, EC2/Fargate/Managed Instances — not ECS Anywhere):

```bash
aws ecs create-service \
  --cluster prod \
  --service-name web \
  --task-definition web:42 \
  --desired-count 4 \
  --deployment-controller type=ECS \
  --deployment-configuration '{
    "strategy": "BLUE_GREEN",
    "bakeTimeInMinutes": 15
  }' \
  --load-balancers '[{
    "targetGroupArn": "arn:aws:elasticloadbalancing:us-east-1:111122223333:targetgroup/web-blue/aaa",
    "containerName": "web",
    "containerPort": 8080,
    "advancedConfiguration": {
      "alternateTargetGroupArn": "arn:aws:elasticloadbalancing:us-east-1:111122223333:targetgroup/web-green/bbb",
      "productionListenerRule": "arn:aws:elasticloadbalancing:us-east-1:111122223333:listener-rule/app/web/ccc/ddd/eee",
      "testListenerRule": "arn:aws:elasticloadbalancing:us-east-1:111122223333:listener-rule/app/web/ccc/fff/ggg",
      "roleArn": "arn:aws:iam::111122223333:role/ecsInfrastructureRole"
    }
  }]'
```

Field shapes per [API_CreateService](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateService.html): `deploymentConfiguration.strategy`, `bakeTimeInMinutes`, `lifecycleHooks`, `canaryConfiguration`, `linearConfiguration`, plus the rolling-era `maximumPercent`/`minimumHealthyPercent`. Do **not** include `deploymentCircuitBreaker` in a blue/green-family config — circuit breaker is rolling-only ([circuit breaker](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html)).

Every subsequent deployment is then triggered by plain `aws ecs update-service --task-definition web:43 ...` — the configured strategy governs how it rolls out. This is also what your CI/CD pipeline calls (see [cicd-pipelines.md](cicd-pipelines)).

---

## Configuring Linear and Canary

Sources: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-linear.html and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/canary-deployment.html (verified 2026-07-09)

Both reuse the blue/green plumbing above (same target groups, listener rules, infrastructure role) and differ only in the production traffic-shift pattern:

```jsonc
// LINEAR — equal steps: 20% -> 40% -> 60% -> 80% -> 100%
"deploymentConfiguration": {
  "strategy": "LINEAR",
  "linearConfiguration": {
    "stepPercent": 20.0,            // Double, valid 3.0-100.0
    "stepBakeTimeInMinutes": 10     // valid 0-1440; skipped at the 100% step
  },
  "bakeTimeInMinutes": 15           // final bake before blue termination
}

// CANARY — two steps: canaryPercent -> 100%
"deploymentConfiguration": {
  "strategy": "CANARY",
  "canaryConfiguration": {
    "canaryPercent": 10.0,
    "canaryBakeTimeInMinutes": 30   // how long traffic holds at the canary weight
  },
  "bakeTimeInMinutes": 15
}
```

- Canary's shift is exactly two-step — the doc example is Step 1 = 10% green / 90% blue, Step 2 = 100% green — followed by the separate deployment bake time before blue terminates.
- PRE_PRODUCTION_TRAFFIC_SHIFT and PRODUCTION_TRAFFIC_SHIFT hooks fire at **every** traffic-shift step; each PRODUCTION_TRAFFIC_SHIFT step may last up to 24 h.
- LB support: ALB, NLB (since **Feb 4, 2026** — [What's New](https://aws.amazon.com/about-aws/whats-new/2026/02/amazon-ecs-nlb-linear-canary-deployments/)), or Service Connect. Not ECS Anywhere.

Canary best practices, per the AWS canary page (verified 2026-07-09):
- Start with 5–10% canary traffic; smaller for mission-critical apps — but ensure the canary slice receives statistically meaningful volume.
- Evaluation periods of 10–30 minutes are typical; wire alarm-based auto-rollback and comparative blue-vs-green dashboards (including business metrics, not just infrastructure metrics).
- Keep database schema/data migrations backward compatible across blue and green.
- Test rollback procedures regularly; deploy during staffed hours.

---

## Lifecycle Hooks

Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/blue-green-deployment-how-it-works.html (verified 2026-07-09)

- Hooks attach to lifecycle stages via `deploymentConfiguration.lifecycleHooks`. Supported on all stages **except** SCALE_UP, BAKE_TIME, and CLEAN_UP.
- Two hook types: **Lambda** hooks and **pause** hooks (`targetType: PAUSE`, see below). TEST_TRAFFIC_SHIFT and PRODUCTION_TRAFFIC_SHIFT accept **Lambda hooks only**.
- Lambda hooks must complete — or return `IN_PROGRESS` — within 15 minutes per invocation, and are re-invoked until they return `SUCCEEDED` or `FAILED`. A `FAILED` (or hook-initiated ROLLBACK) rolls back the whole deployment.
- Hook use cases: pre-shift smoke tests against the test-traffic endpoint, synthetic checks at each linear/canary step, change-ticket validation before production shift.
- Official sample patterns: https://github.com/aws-samples/sample-amazon-ecs-blue-green-deployment-patterns
- Contrast with CodeDeploy-controller hooks (per-deployment AppSpec, 1-hour limit, `PutLifecycleEventHookExecutionStatus`) — see [controllers-and-migration.md](controllers-and-migration).

---

## Test Traffic Routing

Sources: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/blue-green-deployment-how-it-works.html and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect-blue-green.html (verified 2026-07-09)

- During TEST_TRAFFIC_SHIFT, the green revision can receive validation traffic before any production traffic moves — via the `testListenerRule` (e.g., requests carrying a test header) on ALB/NLB.
- **Service Connect:** when no custom rules are configured, requests carrying the default header `x-amzn-ecs-blue-green-test` route to green during the test phase.
- Pattern: a PRE_PRODUCTION_TRAFFIC_SHIFT Lambda hook runs integration tests against the test endpoint and returns FAILED to abort before customers see the new revision.

---

## Pause and Continue

Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/pause-lifecycle-hooks.html (verified 2026-07-09; GA May 19, 2026 — [What's New](https://aws.amazon.com/about-aws/whats-new/2026/05/amazon-ecs-pause-continue-deployments/))

- `targetType: PAUSE` lifecycle hooks work on **rolling and blue/green-family** deployments, all commercial + GovCloud (US) Regions — both the rolling scope and the Region scope come from the [What's New](https://aws.amazon.com/about-aws/whats-new/2026/05/amazon-ecs-pause-continue-deployments/); the doc page itself illustrates only blue/green-family stages. ECS Anywhere support is not documented as of 2026-07-10.
- When a pause hook is reached, ECS generates a `hookId`, emits an EventBridge `ECS Hook State Change` event (`HOOK_AWAITING_ACTION`), and waits. Retrieve the hookId via `DescribeServiceDeployments` (`lifecycleHookDetails`), then:

```bash
aws ecs continue-service-deployment --hook-id <id> --action CONTINUE   # or --action ROLLBACK
```

- Constraints: max 10 pause + 10 Lambda hooks per service; pause hooks **cannot** be placed at TEST_TRAFFIC_SHIFT or PRODUCTION_TRAFFIC_SHIFT; default timeout 1,440 min (24 h), max 20,160 min (14 days); timeout action `ROLLBACK` (default) or `CONTINUE`.
- Linear/canary: a PRE_PRODUCTION_TRAFFIC_SHIFT pause hook fires at **each step** with a fresh hookId — each step needs its own continue call.
- All hooks at the same stage run in parallel; any hook returning rollback rolls back the entire deployment.

---

## Deployment Speed Tuning

Sources cited per row (verified 2026-07-09). These apply to services behind an ELB on EC2, Fargate, or Managed Instances (ECS Anywhere has no service load balancing).

| Lever | Default | Tuning guidance | Source |
|---|---|---|---|
| Target-group health check | `HealthCheckIntervalSeconds` 30, `HealthyThresholdCount` 5 | For fast-stabilizing services: interval 5 s, threshold 2. Newly registered targets need only one passing check to count healthy | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/load-balancer-healthcheck.html |
| Deregistration delay | `deregistration_delay.timeout_seconds` 300 | ~5 s for sub-second-response services; do **not** set low for long-lived requests (uploads, streaming) | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/load-balancer-connection-draining.html |
| Health-check grace period | `healthCheckGracePeriodSeconds` unset | Set for slow-starting containers behind an LB so ECS doesn't kill warming tasks (up to 2,147,483,647 s) | https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateService.html |
| Task launch speed | — | Cache images (`ECS_IMAGE_PULL_BEHAVIOR: prefer-cached` — EC2 launch type only, agent-level setting) + binpack; consider `bridge` mode when awsvpc ENI-attach latency dominates | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-recommendations.html |
| Rolling headroom | `maximumPercent` 200 | Keep at 200 so replacements start before old tasks stop | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-ecs.html |

Note (verified 2026-07-09): the standalone ECS Best Practices Guide deployment chapter now redirects into the developer guide — cite developer-guide URLs, not `bestpracticesguide/` paths.

---

## Launch-Type Constraints Recap

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateService.html, https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html, https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html

| | EC2 | Fargate | Managed Instances | ECS Anywhere (EXTERNAL) |
|---|---|---|---|---|
| ROLLING | ✅ | ✅ | ✅ | ✅ (the practical strategy) |
| BLUE_GREEN / LINEAR / CANARY (managed shifting) | ✅ | ✅ | ✅ | ❌ no ELB, no Service Connect |
| Circuit breaker (rolling) / alarms (any `ECS`-controller strategy) | ✅ | ✅ | ⚠️ inferred from controller-only scoping — not explicitly documented as of 2026-07-10; verify ([details](failure-detection-and-rollback)) | ⚠️ circuit breaker not explicitly documented for the EXTERNAL launch type — verify ([details](failure-detection-and-rollback)); alarms per metric availability |
| DAEMON scheduling | ✅ (max% must be 100) | ❌ | ❌ | ✅ |
| Selected via | `launchType: EC2` or capacity provider | `launchType: FARGATE` or FARGATE/FARGATE_SPOT capacity providers | `capacityProviderStrategy` only (omit `launchType`) | `launchType: EXTERNAL` (capacity providers unsupported) |

- `launchType` enum: `EC2 | FARGATE | EXTERNAL | MANAGED_INSTANCES`. `launchType` and `capacityProviderStrategy` are mutually exclusive on `CreateService` (a request setting both is rejected); the `MANAGED_INSTANCES` enum value appears in API responses/task metadata, but you *select* Managed Instances via `capacityProviderStrategy` only. `FARGATE_SPOT` is a capacity provider, not a launch type.
- ECS Anywhere additionally: no `awsvpc` network mode (use `bridge`/`host`/`none`), no service discovery, no EFS, no App Mesh. OS support narrows on August 7, 2026 to AL2023, Ubuntu 20/22/24, RHEL 9.
