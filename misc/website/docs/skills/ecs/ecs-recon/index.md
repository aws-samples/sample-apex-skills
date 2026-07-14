---
title: "ecs-recon"
description: "ECS environment reconnaissance and discovery. Detects compute and capacity providers, task definitions, deployment configuration, auto scaling, networking, security posture, observability, and IaC/CI-CD tooling. Use when someone asks about their ECS environment, wants to describe a cluster, inspect a service, or document task definitions — even without naming the skill. Applies to Amazon ECS, not Amazon EKS (use eks-recon). Discovers current state only — does not score, audit, or design. Skip for operational audits and GREEN/AMBER/RED scoring (ecs-operation-review), deployment-model design, launch-type selection, and ECS best practices (ecs-architect), deployment strategy design and CI/CD engineering (ecs-devops), GPU/ML workloads (ecs-genai), security and compliance (ecs-security), cost/TCO (ecs-cost-intelligence, once available), observability design (ecs-observability), and replatform/migration (ecs-modernize, once available)."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-recon/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/SKILL.md). Edit the source, not this page.
:::


# ECS Reconnaissance

Discover everything about an ECS environment. Run this skill to gather comprehensive context about clusters, services, and their tasks before making any decisions, changes, or recommendations. Standalone (`run-task`) and scheduled (EventBridge) tasks are not discovered — discovery enumerates workloads via `list-services`.

## When to Use This Skill

**Run this skill when the user:**
- Asks about their ECS environment ("what clusters do I have?", "describe my ECS setup")
- Wants to understand their service configuration ("what launch type?", "how is it deployed?")
- Plans to modify a service and needs current-state context first
- Asks to document or review their ECS resources
- Needs task definition details, scaling policies, or networking config
- Mentions an ECS cluster or service and seems to need context

**Also trigger this skill when:**
- Another workflow needs ECS environment information as input
- User mentions ECS and needs discovery before recommendations
- You need to understand the ECS setup before giving guidance

**Do NOT use this skill for:**
- **Cost scoring or efficiency analysis** — belongs to `ecs-cost-intelligence` (once available)
- **Security auditing or compliance scoring** — belongs to `ecs-security`
- **Best-practices evaluation or maturity ratings** — belongs to `ecs-operation-review`
- **Migration planning (replatform/refactor onto ECS)** — belongs to `ecs-modernize` (once available)
- **Amazon EKS requests** — belongs to `eks-recon`; this skill discovers ECS only
- Creating or modifying ECS resources (this is read-only)
- Producing architecture design documents or diagrams

---

## Access Model — READ-ONLY

This skill is strictly read-only. It **CAN** issue read-only calls (`aws ecs describe-*`/`list-*`, `application-autoscaling describe-*`, `elbv2 describe-*`, `cloudformation describe-*`/`list-*`, `codepipeline list-*`/`get-*`, `deploy list-*`/`get-*`, `sts get-caller-identity`, `logs describe-*`) to discover estate state, and **CAN** write the report file to the workspace. It **CANNOT** mutate any resource (no `create`, `update`, `delete`, `register`, `deregister`, `run-task`, or scale operations). If a detection would require a write, record the field as `unknown` instead.

---

## Prerequisites

### MCP Tools (Optional Supplement)

The Amazon ECS MCP server exists in **preview** ([ECS MCP server docs](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-mcp-introduction.html)), but its tools are diagnostics-shaped — all require a `cluster_name` and none enumerate clusters — so it cannot drive discovery. **CLI Mode is the primary path for this skill.** If the ECS MCP server is configured, its read tools may supplement drill-down diagnostics; it is in preview and subject to change — do not depend on it.

### Required for CLI Mode (Primary)

| Tool | Required For |
|------|-------------|
| `aws` CLI | All ECS discovery (`aws ecs`, `aws application-autoscaling`, `aws elbv2`, `aws cloudformation`) |

### Verifying Access

Before running reconnaissance, verify AWS credentials are available:

```bash
aws sts get-caller-identity
```

**IMPORTANT:** Never give up after checking only environment variables. AWS credentials can come from `~/.aws/credentials`, `~/.aws/config`, instance metadata, or ECS task roles — none of which appear in `env | grep AWS_`. Always try `aws sts get-caller-identity` before concluding credentials are unavailable.

---

## Reconnaissance Modes

| Mode | When to Use | What Happens |
|------|-------------|--------------|
| **Full Recon** | First engagement with ECS environment | Runs Overview Scan, then all drill-down modules |
| **Selective Recon** | Know what you need | Run specific modules (e.g., compute + networking) |
| **Targeted Query** | Quick answer | "Is this service using Fargate?" |

### How to Invoke

**Full reconnaissance:**
> "Run ECS reconnaissance in `us-west-2`"

**Selective reconnaissance:**
> "Run ECS recon but only check compute and auto scaling for service `api-prod`"

**Targeted query:**
> "What launch type does service `api-prod` use in cluster `production`?"

---

## Modules and Reference Loading

Load only the references needed for the user's request — this keeps context focused. `references/overview.md` is always loaded first for the Overview Scan phase; it provides the cluster/service inventory all other modules depend on. For targeted queries, load only the matching row(s); for full recon, load all references.

| Module | Intent / When to Use | Reference File |
|--------|---------------------|----------------|
| Overview | Always loaded first — account-wide inventory of clusters, services, tasks | [overview.md](references/overview) |
| Compute | Capacity providers, launch types, task counts, Fargate vs EC2 | [compute.md](references/compute) |
| Task Definitions | Container images, CPU/memory, family and revision | [task-definitions.md](references/task-definitions) |
| Deployment | Rolling update, CodeDeploy, circuit breaker, min/max percent | [deployment.md](references/deployment) |
| Auto Scaling | Scalable targets, target tracking, step scaling policies | [autoscaling.md](references/autoscaling) |
| Networking | Network mode, VPC config, load balancers, service connectivity | [networking.md](references/networking) |
| Security | Task roles, execution roles, ECS Exec, secrets references | [security.md](references/security) |
| Observability | Log drivers, Container Insights, CloudWatch log groups | [observability.md](references/observability) |
| IaC | Terraform, CloudFormation, CDK, Copilot detection | [iac.md](references/iac) |
| CI/CD | CodePipeline, CodeDeploy, GitHub Actions, GitLab CI detection | [cicd.md](references/cicd) |

---

## Quick Detection Reference

### CLI Commands (Current Default)

| Detection | CLI Command |
|-----------|-------------|
| List clusters | `aws ecs list-clusters --region <region>` |
| Describe clusters | `aws ecs describe-clusters --clusters <name> --include STATISTICS SETTINGS` |
| List services | `aws ecs list-services --cluster <name> --region <region>` |
| Describe services | `aws ecs describe-services --cluster <name> --services <svc> --region <region>` |
| Describe task definition | `aws ecs describe-task-definition --task-definition <arn> --query 'taskDefinition.{family:family,revision:revision,cpu:cpu,memory:memory,networkMode:networkMode,containerDefinitions:containerDefinitions[].{name:name,image:image,cpu:cpu,memory:memory,memoryReservation:memoryReservation,essential:essential}}'` (the `--query` projection excludes `containerDefinitions[].environment` — plaintext values there may contain credentials) |
| List tags | `aws ecs list-tags-for-resource --resource-arn <arn>` |
| Auto scaling targets | `aws application-autoscaling describe-scalable-targets --service-namespace ecs` |
| Auto scaling policies | `aws application-autoscaling describe-scaling-policies --service-namespace ecs` |
| Load balancer info | `aws elbv2 describe-target-groups --target-group-arns <arn>` |

---

## Running Reconnaissance

> **IMPORTANT: Load Reference Files**
>
> Before running each module, you MUST read its reference file (e.g., `references/compute.md`).
> References contain:
> - Detection order and rationale
> - Edge cases and how to handle them
> - CLI commands with example outputs
> - Output schema for structured reporting
>
> Skipping references produces shallow results. The main skill provides orchestration;
> the references provide detection intelligence.

**Never reproduce `containerDefinitions[].environment` values or non-awslogs `logConfiguration.options` in output or the report** — they routinely contain plaintext credentials.

### Step 1: Gather Prerequisites

```
Required:
- AWS region (or detect from context/CLI)
- AWS credentials (verified via sts get-caller-identity)

Optional:
- Specific cluster/service to target (default: discover all)
- Specific modules to run (default: all)
- Output file path (default: .ecs-recon-report.yaml)
```

**Region resolution order:**
1. User-provided region
2. `AWS_DEFAULT_REGION` or `AWS_REGION` environment variable
3. `aws configure get region`
4. If none available, ask the user

### Step 2: Check Tool Availability

CLI Mode is the primary path — the ECS MCP server (preview) offers no cluster-enumeration tools, so discovery always runs on the AWS CLI. If the ECS MCP server is configured, its read tools may optionally supplement drill-down diagnostics; record `tool_mode: mixed` in that case, otherwise `tool_mode: cli` (the normal value).

### Step 3: Run Overview Scan

Load `references/overview.md` and execute the Overview Scan:

1. **List all clusters** (paginated — collect all pages)
2. **List services per cluster** (paginated — collect all pages)
3. **Describe clusters** (get task counts, capacity providers, settings)
4. Present the overview map to the user

If only one cluster exists, auto-select it for drill-down. If multiple clusters exist, ask the user which to drill into (or run full recon if requested).

### Step 4: User Selection

After presenting the overview map:
- If user requested full recon: proceed with all modules on all clusters
- If user picks a specific cluster/service: scope drill-down to that target
- If targeted query: run only the relevant module

### Step 5: Run Drill-Down Modules

For each selected module:
1. **Load the reference file** — REQUIRED
2. **Run detection commands** following the reference's guidance:
   - Use the CLI commands from the reference (primary path)
   - ECS MCP server read tools (if configured) may supplement diagnostics
   - If detection is not possible, record as unavailable with reason
3. **Collect output** into report section using the reference's output schema

**Execution order:** Modules are independent — run them in any order. Each module is self-contained with its own detection commands and output schema.

### Step 6: Generate Report

Write report to `.ecs-recon-report.yaml` and present summary to user.

**Summarize facts, not verdicts** — this skill must not emit health/quality judgments (that is `ecs-operation-review`'s lane).

**Report sensitivity:** the report embeds account IDs, subnet/security-group IDs, IAM role ARNs, and secret ARNs. Treat it as sensitive — write it only inside the workspace, and do not commit it (recommend adding `.ecs-recon-report.yaml` to `.gitignore`).

---

## Report Generation

The final report follows this YAML schema:

```yaml
# ECS Reconnaissance Report
# Generated: 2026-01-15T10:30:00Z
# Account: 123456789012
# Region: us-west-2
# Modules: overview, compute, task_definitions, deployment, autoscaling, networking, security, observability, iac, cicd

metadata:
  account_id: string
  region: string
  timestamp: string  # ISO 8601 UTC
  tool_mode: string  # "cli" (normal) | "mixed" (ECS MCP server supplemented diagnostics)
  modules_run: list[string]
  coverage:
    regions: list[string]     # Regions covered (single-region per run)
    scope_note: string        # "services and their tasks only; standalone (run-task) and scheduled (EventBridge) tasks not discovered"
    clusters_discovered: int  # Clusters found in the Overview Scan
    clusters_drilled_down: int  # Clusters covered by drill-down modules

overview:
  clusters: list[ClusterSummary]

# Drill-down sections (present only if module was run)
compute: ComputeOutput | UnavailableOutput
task_definitions: TaskDefinitionsOutput | UnavailableOutput
deployment: DeploymentOutput | UnavailableOutput
autoscaling: AutoScalingOutput | UnavailableOutput
networking: NetworkingOutput | UnavailableOutput
security: SecurityOutput | UnavailableOutput
observability: ObservabilityOutput | UnavailableOutput
iac: IaCOutput | UnavailableOutput
cicd: CICDOutput | UnavailableOutput
```

### UnavailableOutput (for modules that could not complete)

```yaml
unavailable: true
reason: string  # Human-readable explanation (e.g., "Access denied on ecs:DescribeServices")
```

Module-level `unavailable: true` is reserved for **total module failure**. Each module's per-service entries may carry `error: string | null` — per-resource failures are recorded inline on the affected entry and recon continues with the rest.

### Example Report

```yaml
metadata:
  account_id: "123456789012"
  region: us-west-2
  timestamp: "2026-01-15T10:30:00Z"
  tool_mode: cli
  modules_run:
    - overview
    - compute
    - task_definitions
    - deployment
  coverage:
    regions:
      - us-west-2
    scope_note: "services and their tasks only; standalone (run-task) and scheduled (EventBridge) tasks not discovered"
    clusters_discovered: 1
    clusters_drilled_down: 1

overview:
  clusters:
    - name: production
      arn: arn:aws:ecs:us-west-2:123456789012:cluster/production
      status: ACTIVE
      services_count: 3
      running_tasks: 12
      stopped_tasks: 2  # int | null (null = not collected)
      capacity_providers:
        - FARGATE
        - FARGATE_SPOT
      services:
        - name: api-service
          status: ACTIVE
          desired_count: 4
          running_count: 4
          launch_type: not_applicable  # capacity provider strategy in use
        - name: worker-service
          status: ACTIVE
          desired_count: 2
          running_count: 2
          launch_type: FARGATE

compute:
  cluster:
    name: production
    capacity_providers:
      - name: FARGATE
        type: FARGATE
        status: ACTIVE
        auto_scaling_group_arn: null
      - name: FARGATE_SPOT
        type: FARGATE_SPOT
        status: ACTIVE
        auto_scaling_group_arn: null
    default_capacity_provider_strategy:
      - provider: FARGATE
        weight: 1
        base: 1
      - provider: FARGATE_SPOT
        weight: 3
        base: 0
  services:
    - name: api-service
      launch_type: not_applicable
      capacity_provider_strategy:
        - provider: FARGATE
          weight: 1
          base: 1
        - provider: FARGATE_SPOT
          weight: 3
          base: 0
      task_counts:
        running: 4
        desired: 4
        pending: 0
    - name: worker-service
      launch_type: FARGATE
      capacity_provider_strategy: []
      task_counts:
        running: 2
        desired: 2
        pending: 0

task_definitions:
  services:
    - service_name: api-service
      family: api-service
      revision: 42
      task_cpu: "1024"
      task_memory: "2048"
      network_mode: awsvpc
      containers:
        - name: api
          image: 123456789012.dkr.ecr.us-west-2.amazonaws.com/api:v1.5.0
          cpu: 896
          memory: 1792
          memory_reservation: null
          essential: true
        - name: envoy
          image: public.ecr.aws/appmesh/aws-appmesh-envoy:v1.27.0
          cpu: 128
          memory: 256
          memory_reservation: null
          essential: true

deployment:
  services:
    - service_name: api-service
      controller_type: ecs_rolling  # ecs_rolling | ecs_blue_green | ecs_linear | ecs_canary | code_deploy | external
      strategy: ROLLING  # ROLLING | BLUE_GREEN | LINEAR | CANARY | null (ECS controller + deploymentConfiguration.strategy decides the ecs_* controller_type; ROLLING or absent strategy -> ecs_rolling)
      minimum_healthy_percent: 100
      maximum_percent: 200
      bake_time_in_minutes: null
      circuit_breaker:
        enabled: true
        rollback_enabled: true
      alarms:
        alarm_names: []
        enable: false
        rollback: false
      deployments:
        - id: ecs-svc/1234567890
          status: PRIMARY
          desired_count: 4
          running_count: 4
          rollout_state: COMPLETED
```

---

## Integration with Other Workflows

### Cost Intelligence Workflow

The cost intelligence workflow can invoke ecs-recon to gather baseline context:

```
1. Run ecs-recon modules: overview, compute, autoscaling
2. Extract:
   - Cluster capacity providers → cost model
   - Service task counts → utilization baseline
   - Auto scaling config → scaling efficiency
```

### Security Audit Workflow

The security audit workflow can use ecs-recon for discovery:

```
1. Run ecs-recon modules: overview, security, networking
2. Extract:
   - Task roles → IAM analysis input
   - Secrets references → secrets management audit
   - Network config → isolation analysis
```

### Migration Workflow

The migration workflow can use ecs-recon to understand existing state:

```
1. Run ecs-recon modules: all
2. Extract:
   - Complete environment inventory
   - IaC tooling → migration tooling decisions
   - Deployment config → migration strategy input
```

---

## Sources

> Facts verified 2026-07-14 against the URLs below.

- [Amazon ECS MCP server (preview)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-mcp-introduction.html) — tool surface and preview status
- [API_Service](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_Service.html) — service fields (launch type, capacity provider strategy, deployment controller)
- [API_DeploymentConfiguration](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentConfiguration.html) — strategy, bake time, circuit breaker, alarms
- [Amazon ECS Developer Guide](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/Welcome.html)
