---
title: "Module: Networking"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/references/networking.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-recon/references/networking.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/references/networking.md). Edit the source, not this page.
:::

# Module: Networking

> **Part of:** [ecs-recon](../)
> **Purpose:** Discover networking configuration, load balancing, and service-to-service connectivity for ECS services

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [Network Mode from Task Definition](#1-network-mode-from-task-definition)
  - [awsvpc Configuration from Service](#2-awsvpc-configuration-from-service)
  - [Load Balancer Enumeration](#3-load-balancer-enumeration)
  - [Service Connectivity Mechanisms](#4-service-connectivity-mechanisms)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Prerequisites

- **Service name(s) required:** Yes (one or more services to inspect)
- **AWS APIs used:**
  - `ecs:DescribeServices` — service network configuration, load balancers, service registries, Service Connect config
  - `ecs:DescribeTaskDefinition` — network mode from task definition
  - `elbv2:DescribeTargetGroups` — target group details including load balancer ARNs
  - `elbv2:DescribeLoadBalancers` — load balancer type (ALB vs NLB)
- **CLI commands:** `aws ecs describe-services`, `aws ecs describe-task-definition`, `aws elbv2 describe-target-groups`, `aws elbv2 describe-load-balancers`
- **IAM permissions:** Read-only (`ecs:DescribeServices`, `ecs:DescribeTaskDefinition`, `elasticloadbalancing:DescribeTargetGroups`, `elasticloadbalancing:DescribeLoadBalancers`)

---

## Detection Strategy

Run detections in this order to build the networking picture from task definition up to external connectivity:

```
1. Network Mode           -> Get from task definition (awsvpc | bridge | host | none)
2. awsvpc Configuration   -> Get subnets, security groups, public IP from service (awsvpc only)
3. Load Balancers         -> Enumerate associated LBs, follow target group ARN to determine type
4. Service Connectivity   -> Detect Service Connect, Service Discovery, App Mesh
```

**Why this order matters:**
- Network mode determines whether awsvpc config exists — bridge/host/none have no awsvpc configuration
- awsvpc config contains subnet and security group assignments critical for connectivity
- Load balancer discovery requires following target group ARNs through to the load balancer itself to determine type (ALB vs NLB)
- Service-to-service connectivity mechanisms (Service Connect, Service Discovery, App Mesh) are independent of load balancers and represent internal mesh configuration

**Key decision logic:**
- If `networkMode` in task definition is `awsvpc` → extract `networkConfiguration.awsvpcConfiguration` from service
- If `networkMode` is `bridge`, `host`, or `none` → no awsvpc config exists, skip step 2
- If `loadBalancers` array on service is non-empty → follow each target group ARN to determine LB type
- If `serviceConnectConfiguration` on the PRIMARY deployment is present and enabled → Service Connect is active
- If `serviceRegistries` array is non-empty → Service Discovery is active
- If task definition has a proxy configuration with App Mesh → App Mesh is active

---

## Detection Commands

### 1. Network Mode from Task Definition

Retrieve the network mode declared in the active task definition. This determines whether awsvpc networking applies to this service.

**MCP (future):**
```
ecs_describe_task_definition(
  task_definition="<task-definition-arn>"
)
-> Extract networkMode
```

**CLI (get task definition ARN from service, then describe it):**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].taskDefinition'
```

```bash
aws ecs describe-task-definition \
  --task-definition <task-definition-arn> \
  --query 'taskDefinition.networkMode'
```

**Example output:**
```json
"awsvpc"
```

**Interpret the result:**
- `"awsvpc"` — tasks get their own ENI, subnets, and security groups; step 2 applies
- `"bridge"` — tasks share the host's network via Docker bridge; no awsvpc config
- `"host"` — tasks share the host's network namespace directly; no awsvpc config
- `"none"` — tasks have no external connectivity; no awsvpc config
- If not specified, defaults to `"bridge"` on EC2 launch type (Fargate requires `awsvpc`)

### 2. awsvpc Configuration from Service

When the network mode is `awsvpc`, the service's `networkConfiguration` contains subnet, security group, and public IP assignment details.

**MCP (future):**
```
ecs_describe_services(
  cluster="<cluster-name>",
  services=["<service-name>"]
)
-> Extract networkConfiguration.awsvpcConfiguration
```

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].networkConfiguration.awsvpcConfiguration'
```

**Example output:**
```json
{
  "subnets": [
    "subnet-0a1b2c3d4e5f00001",
    "subnet-0a1b2c3d4e5f00002"
  ],
  "securityGroups": [
    "sg-0a1b2c3d4e5f00001",
    "sg-0a1b2c3d4e5f00002"
  ],
  "assignPublicIp": "DISABLED"
}
```

**Interpret the result:**
- `subnets` — VPC subnets where task ENIs are placed
- `securityGroups` — security groups attached to the task ENI
- `assignPublicIp` — `ENABLED` or `DISABLED`; controls whether tasks get a public IP (relevant for Fargate in public subnets)
- If `subnets` is an empty list → report as `"none_configured"`
- If `securityGroups` is an empty list → report as `"none_configured"`

### 3. Load Balancer Enumeration

Services can be fronted by one or more load balancers. The service describes its load balancer associations by target group ARN, container name, and port. To determine the load balancer type (ALB vs NLB), follow the target group ARN through to the load balancer.

**Step 3a: Get load balancer associations from service**

**MCP (future):**
```
ecs_describe_services(
  cluster="<cluster-name>",
  services=["<service-name>"]
)
-> Extract loadBalancers[]
```

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].loadBalancers'
```

**Example output:**
```json
[
  {
    "targetGroupArn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/my-tg/1234567890abcdef",
    "containerName": "web",
    "containerPort": 8080
  }
]
```

**Step 3b: Describe target group to get load balancer ARNs**

**MCP (future):**
```
elbv2_describe_target_groups(
  target_group_arns=["<target-group-arn>"]
)
-> Extract LoadBalancerArns
```

**CLI:**
```bash
aws elbv2 describe-target-groups \
  --target-group-arns <target-group-arn> \
  --query 'TargetGroups[0].LoadBalancerArns'
```

**Example output:**
```json
[
  "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-alb/1234567890abcdef"
]
```

**Step 3c: Describe load balancer to determine type**

**MCP (future):**
```
elbv2_describe_load_balancers(
  load_balancer_arns=["<load-balancer-arn>"]
)
-> Extract Type
```

**CLI:**
```bash
aws elbv2 describe-load-balancers \
  --load-balancer-arns <load-balancer-arn> \
  --query 'LoadBalancers[0].Type'
```

**Example output:**
```json
"application"
```

**Interpret the result:**
- `"application"` → report type as `"ALB"`
- `"network"` → report type as `"NLB"`
- The load balancer ARN format also hints at the type (`/app/` for ALB, `/net/` for NLB) but always confirm with the describe call

### 4. Service Connectivity Mechanisms

Detect whether the service uses Service Connect, Service Discovery, or App Mesh for service-to-service communication.

**Step 4a: Detect Service Connect**

Service Connect is configured per deployment — the configuration lives on the `Deployment` object, not the top-level `Service`. To read the active configuration, extract it from the PRIMARY deployment.

**MCP (future):**
```
ecs_describe_services(
  cluster="<cluster-name>",
  services=["<service-name>"]
)
-> Extract deployments[?status=='PRIMARY'] | [0].serviceConnectConfiguration
```

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query "services[0].deployments[?status=='PRIMARY'] | [0].serviceConnectConfiguration"
```

**Example output (enabled):**
```json
{
  "enabled": true,
  "namespace": "production",
  "services": [
    {
      "portName": "http",
      "clientAliases": [
        {
          "port": 80,
          "dnsName": "web-api"
        }
      ]
    }
  ]
}
```

**Example output (not configured):**
```json
null
```

**Interpret the result:**
- If `serviceConnectConfiguration` from the PRIMARY deployment is present and `enabled` is `true` → Service Connect is active
- If `null` or `enabled` is `false` → Service Connect is not configured

**Step 4b: Detect Service Discovery**

Service Discovery is indicated by the `serviceRegistries` array on the service.

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].serviceRegistries'
```

**Example output (configured):**
```json
[
  {
    "registryArn": "arn:aws:servicediscovery:us-east-1:123456789012:service/srv-abc123def456",
    "containerName": "web",
    "containerPort": 8080
  }
]
```

**Example output (not configured):**
```json
[]
```

**Interpret the result:**
- If `serviceRegistries` is a non-empty array → Service Discovery is active
- If empty array or `null` → Service Discovery is not configured

**Step 4c: Detect App Mesh**

App Mesh integration is detected via a proxy configuration in the task definition. The Envoy sidecar is injected as a proxy.

**CLI:**
```bash
aws ecs describe-task-definition \
  --task-definition <task-definition-arn> \
  --query 'taskDefinition.proxyConfiguration'
```

**Example output (App Mesh configured):**
```json
{
  "type": "APPMESH",
  "containerName": "envoy",
  "properties": [
    {
      "name": "AppPorts",
      "value": "8080"
    },
    {
      "name": "ProxyEgressPort",
      "value": "15001"
    },
    {
      "name": "ProxyIngressPort",
      "value": "15000"
    },
    {
      "name": "IgnoredUID",
      "value": "1337"
    },
    {
      "name": "EgressIgnoredIPs",
      "value": "169.254.170.2,169.254.169.254"
    }
  ]
}
```

**Example output (no App Mesh):**
```json
null
```

**Interpret the result:**
- If `proxyConfiguration` is present and `type` is `"APPMESH"` → App Mesh is active
- If `null` or absent → App Mesh is not configured

---

## Output Schema

```yaml
networking:
  services:
    - service_name: string
      network_mode: string        # awsvpc | bridge | host | none
      awsvpc_config:              # Present only when network_mode is awsvpc
        subnets: list[string] | "none_configured"
        security_groups: list[string] | "none_configured"
        assign_public_ip: string  # ENABLED | DISABLED
      load_balancers:
        - type: string            # "ALB" | "NLB"
          target_group_arn: string
          container_name: string
          container_port: int
      service_connectivity:
        service_connect: bool
        service_discovery: bool
        app_mesh: bool
```

**Field details:**
- `network_mode` — always present; one of `awsvpc`, `bridge`, `host`, `none`
- `awsvpc_config` — present **only** when `network_mode` is `awsvpc`; omitted for bridge/host/none
- `subnets` / `security_groups` — report actual IDs as a list; report `"none_configured"` if the list is empty
- `assign_public_ip` — `"ENABLED"` or `"DISABLED"`
- `load_balancers` — empty list `[]` when no load balancer is associated
- `type` — `"ALB"` (Application Load Balancer) or `"NLB"` (Network Load Balancer)
- `service_connectivity` — all three flags always reported as `true` or `false`

---

## Edge Cases

Handle these scenarios to ensure accurate networking reporting.

### Bridge mode (no awsvpc_config)

Services using `bridge`, `host`, or `none` network modes do not have `networkConfiguration.awsvpcConfiguration` in the service description.

**How to handle:**
- Report `network_mode` as the actual value (`bridge`, `host`, or `none`)
- **Omit** the `awsvpc_config` field entirely from the output (do not report it as null or empty)
- Load balancers and service connectivity are still reported normally — they operate independently of the network mode

**Detection:**
```bash
aws ecs describe-task-definition \
  --task-definition <task-definition-arn> \
  --query 'taskDefinition.networkMode'
```

If the result is not `"awsvpc"`, skip the awsvpc configuration step entirely.

### No load balancers associated

A service may have no load balancer associations. This is common for background workers, batch processors, or services that receive traffic only via Service Connect or Service Discovery.

**How to handle:**
- Report `load_balancers: []` (empty list)
- Do not report this as an error — it is a valid configuration
- Check service connectivity mechanisms, which may provide internal routing without a load balancer

**Detection:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].loadBalancers'
```

If the result is `[]` or `null`, report an empty load balancer list.

### No connectivity mechanism configured

A service may have no load balancer, no Service Connect, no Service Discovery, and no App Mesh. This means the service has no external routing or internal mesh.

**How to handle:**
- Report `load_balancers: []`
- Report `service_connectivity: { service_connect: false, service_discovery: false, app_mesh: false }`
- This is valid for internal services that are accessed directly by IP or via other custom mechanisms

### Empty subnets or security groups reported as "none_configured"

When `awsvpc` mode is used but the subnets or security groups list is empty, report explicitly.

**How to handle:**
- If `awsvpcConfiguration.subnets` is `[]` → report `subnets: "none_configured"`
- If `awsvpcConfiguration.securityGroups` is `[]` → report `security_groups: "none_configured"`
- This is an unusual configuration that may indicate a misconfiguration — report it factually without judgment

**Example output for empty security groups:**
```yaml
networking:
  services:
    - service_name: worker-svc
      network_mode: awsvpc
      awsvpc_config:
        subnets:
          - subnet-0a1b2c3d4e5f00001
        security_groups: "none_configured"
        assign_public_ip: DISABLED
      load_balancers: []
      service_connectivity:
        service_connect: false
        service_discovery: false
        app_mesh: false
```

### Multiple load balancers on a single service

A service can route to multiple target groups (and therefore multiple load balancers). Each load balancer association targets a specific container and port combination.

**How to handle:**
- Follow each target group ARN independently through describe-target-groups and describe-load-balancers
- Report each load balancer association as a separate entry in the `load_balancers` list
- Different entries may point to different LB types (one ALB, one NLB)

**Example output:**
```yaml
load_balancers:
  - type: "ALB"
    target_group_arn: "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/web-tg/abc123"
    container_name: web
    container_port: 8080
  - type: "NLB"
    target_group_arn: "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/grpc-tg/def456"
    container_name: grpc
    container_port: 9090
```

### Networking configuration retrieval failure

If any networking API call fails (access denied, throttling, resource not found):

**How to handle:**
- Report the error with the specific API call and affected service
- Use the unavailable output schema
- Do NOT terminate the remaining reconnaissance — continue with other services

```yaml
networking:
  unavailable: true
  reason: "elbv2:DescribeTargetGroups failed for service 'web-api': AccessDeniedException"
```

### Target group not associated with any load balancer

In rare cases, a target group referenced by a service may not be associated with any load balancer (orphaned target group or target group used by a different mechanism).

**How to handle:**
- If `DescribeTargetGroups` returns an empty `LoadBalancerArns` list, skip the load balancer type determination
- Report the entry with the target group ARN, container name, and port, but set `type` to `"unknown"`
- This indicates the target group exists but is not currently fronted by a load balancer

```yaml
load_balancers:
  - type: "unknown"
    target_group_arn: "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/orphan-tg/xyz789"
    container_name: web
    container_port: 8080
```
