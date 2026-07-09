# ECS Launch-Type and Topology Migration

> **Part of:** [ecs-architect](../SKILL.md)
> **Purpose:** Plan the transition from an older ECS topology to a modern one — EC2 launch type → capacity providers / Managed Instances, and Service Discovery → Service Connect. Covers exactly which transitions the API supports, the `launchType`-immutability trap, and cutover steps. Facts verified against AWS docs on **2026-07-09**.
>
> **Scope note:** This is *topology* migration for an ECS estate you already understand. For assessing an existing *application* and choosing replatform vs refactor, use `ecs-modernize`. To inventory the estate first, use the `ecs-recon` skill once available (or `aws ecs list-*`/`describe-*`).

---

## Table of Contents

1. [EC2 Launch Type → Capacity Providers / Managed Instances](#ec2-launch-type--capacity-providers--managed-instances)
2. [The launchType-Immutability Trap](#the-launchtype-immutability-trap)
3. [Supported UpdateService Transitions](#supported-updateservice-transitions)
4. [Service Discovery → Service Connect](#service-discovery--service-connect)
5. [Migration Playbook](#migration-playbook)
6. [Sources](#sources)

---

## EC2 Launch Type → Capacity Providers / Managed Instances

Older ECS services were created with a fixed `launchType` (`EC2` or `FARGATE`). Capacity providers (and Managed Instances, which is delivered as a capacity provider) are the modern replacement — they add managed scaling, Spot mixing, and (for Managed Instances) fully-managed EC2. Moving a service onto them is the "should I move off EC2 launch type?" question, which is the same decision surface as model selection.

**Why move:**
- Managed scaling + termination protection instead of hand-rolled ASG scaling.
- Spot/on-demand mixing via base/weight.
- Managed Instances: shed EC2 fleet ops entirely.

**Why it's not a trivial `update-service`:** see the trap below.

---

## The launchType-Immutability Trap

**`launchType` is immutable on an existing service.** The ECS `CreateService` API does not allow specifying both `launchType` and `capacityProviderStrategies` at once. Consequently, switching a service from a launch type to a capacity-provider strategy **through CloudFormation/CDK forces a service replacement** — CloudFormation deletes and recreates the service with the new configuration. This is an ECS API/CloudFormation constraint, not a CDK bug. ([aws-cdk-lib.aws_ecs — Service Replacement note](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs-readme.html))

**Escape hatch (CDK):** the CDK workaround is a targeted use of L1 escape hatches / property overrides on the underlying `CfnService` to stop CloudFormation from treating the change as a replacement — it does **not** mean pinning a capacity-provider value onto `launchType`. The `LaunchType` property only accepts `EC2 | FARGATE | EXTERNAL` ([AWS::ECS::Service](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ecs-service.html)); `FARGATE_SPOT` is **not** a launch type — it is a *capacity provider*. A service is also mutually exclusive here: it uses **either** a `launchType` **or** a `capacityProviderStrategy`, never both. So the escape hatch is about controlling CloudFormation's update/replacement behavior on the L1 resource, not about writing `FARGATE_SPOT` (or any CP) into `launchType`.

([aws-cdk-lib.aws_ecs — Service Replacement note / workaround](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs-readme.html) · [AWS::ECS::Service LaunchType allowed values](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ecs-service.html))

This is the precise, correct form of the field lore that "you can't migrate off `launchType: EC2` without recreating the service." Via **CloudFormation/CDK** you must either accept replacement or use the escape hatch to control replacement; via the **`UpdateService` API directly**, specific transitions are supported without recreation (next section).

---

## Supported UpdateService Transitions

AWS documents this as **service mutability** — `UpdateService` can move a service between compute types without recreation. The current supported matrix ([capacity-launch-type-comparison](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-launch-type-comparison.html)):

- **All launch type → capacity provider updates are supported**, including: EC2 launch type → Managed Instances / Fargate CP / EC2 ASG CP; Fargate launch type → Managed Instances / EC2 ASG CP / Fargate CP; External launch type → Managed Instances / Fargate CP / EC2 ASG CP.
- **All capacity provider → capacity provider updates are supported** (EC2 ASG CP ↔ Fargate CP ↔ Managed Instances, any direction).
- **Capacity provider → launch type is NOT supported**, except reverting to the launch type the service was **originally created with** (pass an empty `capacityProviderStrategy` list). You cannot use the empty-list trick to switch to a *different* launch type.
- **Launch type → launch type is NOT supported** (e.g. EC2 launch type → Fargate launch type) — migrate to the equivalent *capacity provider* instead.

**Two important caveats:**
- **Update the task definition first**: `requiresCompatibilities` must include the target (e.g. `MANAGED_INSTANCES`) and pass compatibility validation, or the `UpdateService` call fails.
- Changing capacity providers is supported for both rolling and blue/green deployments and does **not** by itself trigger a new deployment — so **existing tasks keep running on the old capacity until you force a new deployment** (`--force-new-deployment`) or otherwise cause task replacement. The `UpdateService` call updates the *configuration*; tasks actually move on the next deployment. Plan that forced deployment as an explicit migration step.

**Rule of thumb:** driving the change through the **API/CLI** follows the supported-transition list above with no recreation; driving it through **IaC** (CloudFormation/CDK) risks replacement unless you use the escape hatch. Plan the mechanism deliberately.

---

## Service Discovery → Service Connect

Service Connect is the recommended target for service-to-service connectivity (see [networking-and-eni-density.md](networking-and-eni-density.md#service-connect-vs-service-discovery)). The main win over Cloud Map DNS-based discovery is controlled cutover: DNS TTL means clients keep resolving old IPs until the TTL expires, whereas Service Connect applies config changes during a normal deployment (replacing client tasks) with automatic connection draining, so no traffic errors during endpoint version changes. ([Networking between ECS services in a VPC](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/networking-connecting-services.html))

**Cutover approach:**
1. Add Service Connect configuration to each service and task definition (logical name + port name mapping).
2. Deploy the **server** services first so their Service Connect endpoints exist.
3. Deploy **client** services with Service Connect enabled; the deployment replaces client tasks with ones configured to resolve the logical names.
4. Both mechanisms can coexist during transition; retire Cloud Map records once all clients use Service Connect.

Because config changes take effect only during deployments, gate the rollout with the deployment circuit breaker and standard deployment configuration, exactly like any other deploy. ([Interconnect Amazon ECS services](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/interconnecting-services.html))

---

## Migration Playbook

1. **Inventory first** (use the `ecs-recon` skill once available, or `aws ecs describe-*`): current launch types, ASG/capacity-provider config, network mode, service discovery mechanism.
2. **Decide the target model** ([model-selection-framework.md](model-selection-framework.md)): capacity providers on your ASG, or Managed Instances to shed fleet ops.
3. **Choose the mechanism**: API/CLI (supported-transition list, no recreation) vs IaC (accept replacement or use the escape hatch). Never let an unplanned IaC apply silently delete-and-recreate a production service.
4. **Design capacity** ([capacity-and-scaling.md](capacity-and-scaling.md)): base/weight, one resource profile per ASG, managed scaling + draining.
5. **Migrate connectivity**: Service Discovery → Service Connect via the cutover steps above (and App Mesh → Service Connect if applicable — App Mesh is discontinued Sept 30, 2026; see [networking-and-eni-density.md](networking-and-eni-density.md#service-connect-vs-service-discovery)). If any tasks are still on Fargate PV 1.3.0, fold in the PV 1.4.0 migration (task-ENI traffic + VPC-endpoint prep) before its June 30, 2026 end of support.
6. **Validate** with `ecs-operation-review`; quantify the cost delta with `ecs-cost-intelligence`.

---

## Sources

- [update-service CLI reference](https://docs.aws.amazon.com/cli/v1/reference/ecs/update-service.html) — supported launch-type ↔ capacity-provider transitions, Managed Instances requirement
- [Amazon ECS launch types and capacity providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-launch-type-comparison.html) — revert-to-launch-type semantics
- [aws-cdk-lib.aws_ecs module — Service Replacement note](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs-readme.html) — launchType immutability, replacement, escape hatch
- [AWS::ECS::Service (CloudFormation)](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ecs-service.html) — `LaunchType` allowed values `EC2 | FARGATE | EXTERNAL`; Managed Instances requires `capacityProviderStrategy`
- [Interconnect Amazon ECS services](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/interconnecting-services.html) · [Networking between ECS services in a VPC](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/networking-connecting-services.html)
