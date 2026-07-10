# ECS DevOps — Controllers & CodeDeploy Migration

> **Part of:** [ecs-devops](../SKILL.md)
> **Purpose:** The CodeDeploy deployment controller (capabilities, constraints, when to keep it), the three migration paths to ECS-native blue/green, and the external deployment controller

**For native-strategy configuration, see:** [deployment-strategies.md](deployment-strategies.md)

> Facts in this file verified 2026-07-09 against the AWS documentation URLs cited inline.

---

## Table of Contents

1. [Controller Landscape](#controller-landscape)
2. [CodeDeploy Controller (CODE_DEPLOY)](#codedeploy-controller-code_deploy)
3. [CodeDeploy vs Native — Implementation Differences](#codedeploy-vs-native--implementation-differences)
4. [Migrating CodeDeploy → Native Blue/Green](#migrating-codedeploy--native-bluegreen)
5. [External Deployment Controller (EXTERNAL)](#external-deployment-controller-external)

---

## Controller Landscape

Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service-options.html (verified 2026-07-09)

| `deploymentController.type` | Who orchestrates | Strategies | Status |
|---|---|---|---|
| `ECS` | ECS scheduler | ROLLING, BLUE_GREEN, LINEAR, CANARY via `deploymentConfiguration.strategy` | Recommended for new services |
| `CODE_DEPLOY` | AWS CodeDeploy | Blue/green with all-at-once / canary / linear shifting via CodeDeploy deployment configurations | Supported; AWS recommends native instead ([deployment-type-bluegreen](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-bluegreen.html)). Not officially "deprecated" — don't overstate |
| `EXTERNAL` | Your tooling | Anything you build on task sets | Niche — custom deployment engines |

**The controller is updatable in place since July 15, 2025** ([doc history](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/document_history.html)) — an existing CODE_DEPLOY service can be switched to the ECS controller with `UpdateService`, no service recreation.

Launch-type scope: controllers are orthogonal to launch type, but their traffic-shifting prerequisites are not — CODE_DEPLOY **requires** an ALB/NLB, and EXTERNAL supports only ALB/NLB *when* load-balancing (LB is optional on task sets), so neither delivers traffic shifting on ECS Anywhere (no service load balancing — [ECS Anywhere](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html)). Service Connect is unsupported with both CODE_DEPLOY and EXTERNAL controllers ([Service Connect deploy](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect-concepts-deploy.html)).

## CodeDeploy Controller (CODE_DEPLOY)

Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-bluegreen.html (verified 2026-07-09)

- Traffic shifting via CodeDeploy **deployment configurations**: all-at-once, canary (e.g., `CodeDeployDefault.ECSCanary10Percent5Minutes`), linear (e.g., `CodeDeployDefault.ECSLinear10PercentEvery1Minutes`), or custom configurations ([CodeDeploy configs](https://docs.aws.amazon.com/codedeploy/latest/userguide/deployment-configurations.html)).
- Constraints:
  - **ALB or NLB required** — no Service Connect, no headless. With **NLB, only `CodeDeployDefault.ECSAllAtOnce`** is supported (no canary/linear over NLB — unlike native, which gained NLB linear/canary Feb 2026).
  - `DAEMON` scheduling unsupported.
  - Auto scaling is not blocked during a deployment, but scaling mid-deployment can fail it: the green task set gets up to 1 h to reach steady state, and a scaling event mid-traffic-shift allows only 5 min to re-reach steady state.
- Rollback: CodeDeploy reroutes traffic from the replacement task set back to the original task set (kept until the termination wait time elapses) ([deployment steps](https://docs.aws.amazon.com/codedeploy/latest/userguide/deployment-steps-ecs.html)).
- **Staying on CODE_DEPLOY indefinitely is a valid steady state.** The controller is fully supported with no announced end-of-life ([deployment-type-bluegreen](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-bluegreen.html) — AWS recommends native, but has not deprecated CodeDeploy). If an existing CodeDeploy blue/green estate works, migration is optional, not overdue: migrate when you *want* what native adds — Service Connect, richer lifecycle hooks, service-revision history, simpler pipelines (plain `UpdateService`) — and weigh that against the migration cost (hook rewrite, pipeline changes, listener-rule restructuring). Use native for **new** adoptions.

## CodeDeploy vs Native — Implementation Differences

Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/migrate-codedeploy-to-ecs-bluegreen.html (verified 2026-07-09)

| Dimension | CODE_DEPLOY controller | Native (`ECS` controller) |
|---|---|---|
| Deployment unit | **Task sets** (older construct) | **Service revisions / service deployments** (richer history) |
| Hook definition | Per-deployment AppSpec | On the service config (`lifecycleHooks`, changed via `UpdateService`) |
| Lambda hook contract | Calls `PutLifecycleEventHookExecutionStatus`; must finish within 1 h | Returns status in the Lambda response; `IN_PROGRESS` re-invocation, 15 min per invocation |
| Trigger | CodeDeploy `CreateDeployment` | ECS `UpdateService` |
| Traffic shift styles | All-at-once / canary / linear (CodeDeploy configs) | All-at-once (`BLUE_GREEN`) / `LINEAR` / `CANARY` (`deploymentConfiguration`) |
| Service Connect | ❌ | ✅ |
| Post-shift safety | Termination wait time | Bake time + stage timeouts + pause hooks |

## Migrating CodeDeploy → Native Blue/Green

Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/migrate-codedeploy-to-ecs-bluegreen.html (verified 2026-07-09)

Three documented approaches:

| # | Approach | Risk | Trade-off |
|---|---|---|---|
| 1 | **Reuse the same ELB resources** on the existing service | Higher (no parallel setup) | Simplest, no downtime; rollback = revert the service revision |
| 2 | **New service + existing LB** with new listeners/target groups, then a port swap | Low | Parallel testing before cutover |
| 3 | **New service + new LB** behind a reverse proxy (Route 53 weighted / CloudFront) | Low | Needs a proxy layer you may not have |

Approach 1 mechanics:
1. Rewrite the production listener's default rule to a **weighted two-target-group rule (weights 1 / 0)** — native blue/green requires the weighted-rule shape.
2. Create/assign the infrastructure role with `AmazonECSInfrastructureRolePolicyForLoadBalancers`.
3. `UpdateService`: set `deploymentController.type=ECS`, `deploymentConfiguration.strategy=BLUE_GREEN` (+ `bakeTimeInMinutes`, hooks), and the `advancedConfiguration` block on the load balancer (alternate target group, production/test listener rules, role ARN).
4. Failure mode to expect if step 1 is wrong: "Service deployment rolled back because of invalid networking configuration. Both targetGroup and alternateTargetGroup must be associated with the productionListenerRule or testListenerRule." ([migration page](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/migrate-code-deploy-to-ecs-blue-green.html))

Post-migration checklist (from the AWS guide):
- Switch CI/CD from CodeDeploy `CreateDeployment` to ECS `UpdateService` (see [cicd-pipelines.md](cicd-pipelines.md)).
- Move deployment monitoring from CodeDeploy deployments to ECS service deployments (`list-service-deployments`, EventBridge deployment events).
- Recreate AppSpec hooks as service `lifecycleHooks` (mind the different Lambda contract above).

CloudFormation users on the `AWS::CodeDeploy::BlueGreen` hook / `AWS::CodeDeployBlueGreen` transform have a dedicated migration path: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/migrate-codedeploy-to-ecs-bluegreen-cloudformation-template.html

Decision-support blog (CDK-focused, post-Jul-2025): [Choosing between Amazon ECS Blue/Green Native or AWS CodeDeploy in AWS CDK](https://aws.amazon.com/blogs/devops/choosing-between-amazon-ecs-blue-green-native-or-aws-codedeploy-in-aws-cdk/)

## External Deployment Controller (EXTERNAL)

Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-external.html (verified 2026-07-09)

**What it's for:** full third-party control of the deployment process — you build your own blue/green/canary engine on the task-set APIs. Used by teams with bespoke orchestration requirements that neither the ECS scheduler nor CodeDeploy satisfies.

API surface:
- `CreateTaskSet` — launch a new revision as a task set on the service.
- `UpdateTaskSet` — adjust a task set's `scale` only (a percent, 0–100, of the service's `desiredCount`).
- `UpdateServicePrimaryTaskSet` — promote a task set to primary.
- `DeleteTaskSet` — retire the old revision.
- `UpdateService` under EXTERNAL only changes desired count and health-check grace period — compute, load balancer, network, or task-definition changes require a **new task set**.

Constraints (all from the same page, verified 2026-07-09):
- **Load balancer is optional on task sets** (`CreateTaskSet` `loadBalancers` is not required — [API_CreateTaskSet](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateTaskSet.html)); headless task sets are allowed, in which case you own all traffic management. *When* load-balancing: **ALB or NLB only**, one ALB target group per task set. No Service Connect ([Service Connect deploy](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect-concepts-deploy.html)).
- `REPLICA` scheduling only — no DAEMON.
- No direct Application Auto Scaling integration with task sets — task sets derive `ComputedDesiredCount` from the service `DesiredCount` and their `scale` percent.
- Task-set `launchType` in the developer guide is documented as `EC2 | FARGATE | EXTERNAL`, while the [CreateTaskSet API reference](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateTaskSet.html) lists `EC2 | FARGATE | EXTERNAL | MANAGED_INSTANCES` — the two pages disagree (re-checked 2026-07-10: the CreateTaskSet API reference still lists MANAGED_INSTANCES while the developer guide does not). Do not assert Managed Instances task-set support either way; say the docs are inconsistent and verify empirically.
- None of the native safety net applies: no circuit breaker, no strategy-managed bake time — your engine owns failure detection and rollback (typically by flipping the primary task set back).

Rule of thumb: if the requirement can be expressed as rolling, blue/green, linear, or canary, use the `ECS` controller — EXTERNAL trades away every managed guardrail for control.
