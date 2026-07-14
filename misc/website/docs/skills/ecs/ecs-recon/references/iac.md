---
title: "Module: IaC Detection"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/references/iac.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-recon/references/iac.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/references/iac.md). Edit the source, not this page.
:::

# Module: IaC Detection

> **Part of:** [ecs-recon](../)
> **Purpose:** Detect Infrastructure-as-Code tooling managing ECS resources

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [Resource Tag Inspection](#1-resource-tag-inspection)
  - [CloudFormation Stack Association](#2-cloudformation-stack-association)
  - [Naming Pattern Analysis](#3-naming-pattern-analysis)
- [Classification Logic](#classification-logic)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)
- [Sources](#sources)

---

## Prerequisites

- **Cluster ARN required:** Yes
- **Service ARNs required:** Yes (one or more services to inspect)
- **AWS APIs used:**
  - `ecs:ListTagsForResource` — retrieve tags on ECS clusters and services
  - `cloudformation:ListStacks` — enumerate CloudFormation stacks in the account
  - `cloudformation:ListStackResources` — enumerate all resources in a stack (paginated)
  - `cloudformation:DescribeStackResources` — reverse-lookup the stack owning a resource by physical resource ID
- **CLI commands:** `aws ecs list-tags-for-resource`, `aws cloudformation list-stacks`, `aws cloudformation list-stack-resources`, `aws cloudformation describe-stack-resources`
- **IAM permissions:** Read-only (`ecs:ListTagsForResource`, `cloudformation:ListStacks`, `cloudformation:ListStackResources`, `cloudformation:DescribeStackResources`)

---

## Detection Strategy

Run detections in this order — each step adds evidence and confidence:

```
1. Resource Tag Inspection       -> Check tags on ECS cluster and services for IaC tool markers
2. CloudFormation Stack Association -> Check if resources belong to a CloudFormation stack
3. Naming Pattern Analysis       -> Inspect resource names for tool-specific conventions
```

**Why this order matters:**
- Tags are the strongest single-call signal for the tools that DO tag: CloudFormation always applies `aws:cloudformation:*` tags, CDK adds `aws:cdk:path` (when metadata is enabled), and Copilot adds `copilot-*` tags
- **Terraform is the critical exception: Terraform applies NO default tags.** Unless the team configured `default_tags` on the AWS provider or tagged resources explicitly, a fully Terraform-managed estate is invisible to tag-based detection. Expect `undetermined: true` to frequently mean "Terraform or console-managed" — do not read it as "no IaC"
- Stack association confirms CloudFormation-family tools (CDK, Copilot, raw CloudFormation) with high confidence
- Naming patterns provide supporting evidence when tags are stripped or absent, but carry lower confidence alone
- Each step is independent — a failure in one does not block the others

**Key decision logic:**
- Start with tags because they provide the strongest signal with a single API call per resource
- Stack association narrows ambiguity between CDK, Copilot, and raw CloudFormation (all use stacks under the hood)
- Naming patterns are a last resort — they can corroborate tag-based evidence or provide low-confidence detection when no tags exist
- Multiple tools CAN be detected simultaneously (e.g., Terraform managing the cluster, CDK managing services)
- If no evidence matches any known tool → report `undetermined: true`

---

## Detection Commands

### 1. Resource Tag Inspection

Retrieve tags from ECS clusters and services. IaC tools apply distinctive tags to resources they manage.

**CLI:**
```bash
aws ecs list-tags-for-resource \
  --resource-arn <cluster-or-service-arn>
```

**Example output (Terraform-managed resource):**
```json
{
  "tags": [
    {
      "key": "terraform:managed",
      "value": "true"
    },
    {
      "key": "tf-workspace",
      "value": "production"
    },
    {
      "key": "Environment",
      "value": "prod"
    }
  ]
}
```

**Example output (CDK-managed resource):**
```json
{
  "tags": [
    {
      "key": "aws:cdk:path",
      "value": "MyStack/MyService/Service"
    },
    {
      "key": "aws-cdk:auto-delete-objects",
      "value": "true"
    }
  ]
}
```

**Example output (Copilot-managed resource):**
```json
{
  "tags": [
    {
      "key": "copilot-application",
      "value": "my-app"
    },
    {
      "key": "copilot-environment",
      "value": "production"
    },
    {
      "key": "copilot-service",
      "value": "api"
    }
  ]
}
```

**Example output (CloudFormation-managed resource):**
```json
{
  "tags": [
    {
      "key": "aws:cloudformation:stack-id",
      "value": "arn:aws:cloudformation:us-east-1:123456789012:stack/my-ecs-stack/abc12345"
    },
    {
      "key": "aws:cloudformation:stack-name",
      "value": "my-ecs-stack"
    },
    {
      "key": "aws:cloudformation:logical-id",
      "value": "EcsService"
    }
  ]
}
```

**Example output (no IaC tags):**
```json
{
  "tags": [
    {
      "key": "Environment",
      "value": "staging"
    },
    {
      "key": "Team",
      "value": "platform"
    }
  ]
}
```

**Tag patterns to match:**

> Facts verified 2026-07-14 against https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-resource-tags.html — CloudFormation automatically applies the stack-level tags `aws:cloudformation:logical-id`, `aws:cloudformation:stack-id`, and `aws:cloudformation:stack-name` (the `aws:` prefix is reserved for AWS use). Terraform's AWS provider applies NO tags by default — `terraform:*` / `tf-*` keys only exist when a team configured them deliberately.

| Tool | Tag Key Pattern | Confidence | Origin |
|------|----------------|------------|--------|
| Terraform | Key starts with `terraform:` | High | Team convention (Terraform emits no default tags) |
| Terraform | Key starts with `tf-` | High | Team convention (Terraform emits no default tags) |
| CDK | Key is `aws:cdk:path` | High | Tool-emitted (when CDK path metadata is enabled) |
| CDK | Key starts with `aws-cdk:` | High | Tool-emitted (specific constructs) |
| Copilot | Key is `copilot-application` | High | Tool-emitted |
| Copilot | Key is `copilot-environment` | High | Tool-emitted |
| Copilot | Key is `copilot-service` | High | Tool-emitted |
| CloudFormation | Key is `aws:cloudformation:stack-id` | High | Service-applied (automatic) |
| CloudFormation | Key is `aws:cloudformation:stack-name` | High | Service-applied (automatic) |
| CloudFormation | Key is `aws:cloudformation:logical-id` | High | Service-applied (automatic) |

**Interpret the result:**
- If any tag matches a pattern in the table above → record the tool with `confidence: "high"` and evidence type `"resource_tags"`
- If tags are present but none match known patterns → proceed to step 2 (stack association)
- If tags cannot be retrieved (access denied) → record the error but continue to subsequent steps
- Check tags on BOTH the cluster ARN and each service ARN — different resources may be managed by different tools

### 2. CloudFormation Stack Association

Check whether ECS resources are managed by CloudFormation stacks. This catches resources that have CloudFormation-style tags (which may already be detected in step 1) and confirms CDK or Copilot usage when their characteristic stack naming is present.

> Facts verified 2026-07-14 against https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_ListStacks.html — `IMPORT_COMPLETE` and `IMPORT_ROLLBACK_COMPLETE` are valid `StackStatusFilter` values. A stack created via resource import that was never subsequently updated stays in `IMPORT_COMPLETE`; omitting it from the filter silently skips those stacks and produces a false `undetermined`.

**CLI (list active stacks):**
```bash
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE UPDATE_ROLLBACK_COMPLETE IMPORT_COMPLETE IMPORT_ROLLBACK_COMPLETE \
  --query 'StackSummaries[].{Name:StackName,Id:StackId}'
```

**Example output:**
```json
[
  {
    "Name": "my-app-production-api",
    "Id": "arn:aws:cloudformation:us-east-1:123456789012:stack/my-app-production-api/abc123"
  },
  {
    "Name": "CdkEcsStack",
    "Id": "arn:aws:cloudformation:us-east-1:123456789012:stack/CdkEcsStack/def456"
  }
]
```

> Facts verified 2026-07-14 against https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_DescribeStackResources.html — `DescribeStackResources` returns only the first 100 resources of a stack; the API reference says to use `ListStackResources` instead for larger stacks. Large CDK stacks routinely exceed 100 resources, so enumerating with `describe-stack-resources` silently misses ECS resources. Use the paginated `list-stack-resources` for enumeration; reserve `describe-stack-resources --physical-resource-id` for the reverse lookup.

**CLI (list stack resources to find ECS resources — paginated, use for enumeration):**
```bash
aws cloudformation list-stack-resources \
  --stack-name <stack-name> \
  --query 'StackResourceSummaries[?ResourceType==`AWS::ECS::Cluster` || ResourceType==`AWS::ECS::Service` || ResourceType==`AWS::ECS::TaskDefinition`]'
```

The AWS CLI auto-paginates `list-stack-resources`, so all resources are returned even for stacks with hundreds of resources.

**Example output (stack containing ECS resources):**
```json
[
  {
    "LogicalResourceId": "EcsCluster",
    "PhysicalResourceId": "arn:aws:ecs:us-east-1:123456789012:cluster/prod-api",
    "ResourceType": "AWS::ECS::Cluster",
    "ResourceStatus": "CREATE_COMPLETE"
  },
  {
    "LogicalResourceId": "ApiService",
    "PhysicalResourceId": "arn:aws:ecs:us-east-1:123456789012:service/prod-api/api-service",
    "ResourceType": "AWS::ECS::Service",
    "ResourceStatus": "CREATE_COMPLETE"
  }
]
```

**CLI (cheaper exact reverse lookup — find the stack that owns a known service):**

Instead of enumerating every stack, ask CloudFormation directly which stack owns a resource by its physical resource ID:

```bash
aws cloudformation describe-stack-resources \
  --physical-resource-id <service-arn> \
  --query 'StackResources[].{Stack:StackName,LogicalId:LogicalResourceId,Type:ResourceType}'
```

- This works for ECS **service ARNs** (the service's physical resource ID is its ARN)
- **Caveat:** ECS **cluster** physical IDs are cluster names, not ARNs — pass the cluster name (not the ARN) as `--physical-resource-id` when reverse-looking-up a cluster
- If the resource is not part of any stack, the call returns an error (e.g., "Stack for <id> does not exist") — treat that as "not CloudFormation-managed", record the message in the `error` field, and continue
- Prefer this reverse lookup when investigating specific known services; fall back to stack enumeration only when surveying the whole account

**Interpret the result:**
- If a stack contains ECS resources matching our target cluster or service → record `"cloudformation"` with `confidence: "high"` and evidence type `"stack_association"` (stack membership is a fact, not a heuristic)
- If the stack additionally has CDK-style logical IDs (construct IDs with 8-hex-char suffixes like `MyConstructXXXXXXXX`) or CDK metadata resources → record `"cdk"` with `confidence: "high"` and evidence type `"stack_association"`
- If the stack name merely LOOKS like a tool convention (e.g., contains `Cdk`, or follows the `<app>-<env>-<svc>` shape Copilot uses) → that is a name heuristic, not tool-emitted evidence. Cap at `confidence: "medium"` — `<app>-<env>-<svc>` is also the most common human naming convention, so it must NOT yield high confidence on its own
- Raise Copilot to `confidence: "high"` only when corroborated by `copilot-*` tags or Copilot-characteristic logical resource IDs inside the stack
- Note: CDK and Copilot both deploy via CloudFormation stacks — the logical resource IDs (not just the stack name) help distinguish which tool generated the template

### 3. Naming Pattern Analysis

Inspect ECS resource names for patterns characteristic of specific IaC tools. This provides supplementary evidence when tags are absent or stripped.

**No additional API calls required** — use resource names already collected from prior commands (cluster name, service names, task definition family names).

**Copilot naming patterns:**
- Cluster: `<app>-<env>-Cluster-XXXXXXXXX`
- Service: `<app>-<env>-<svc>-Service-XXXXXXXXX`
- Task definition family: `<app>-<env>-<svc>`

**CDK naming patterns:**
- Cluster: Contains construct IDs like `MyStack-ClusterXXXXXXXX`
- Service: Contains CDK-generated suffixes with hex characters
- Task definition: CDK construct path fragments in the family name

**Terraform naming patterns:**
- Resources often follow user-defined conventions (no universal pattern)
- Names like `<project>-<env>-<resource>` without random suffixes are common in Terraform estates, but this is a generic human naming convention — console-created resources look identical. Generic name shapes are NOT evidence for Terraform and MUST NOT be recorded as such

**Example Copilot-style naming:**
```
Cluster: my-app-production-Cluster-vR5x8Kq2
Service: my-app-production-api-Service-aB3cD4eF
Task Definition Family: my-app-production-api
```

**Example CDK-style naming:**
```
Cluster: CdkEcsStack-ProdCluster3A4B5C6D
Service: CdkEcsStack-ApiServiceF7E8A9B0
Task Definition Family: CdkEcsStackApiTaskDef
```

**Interpret the result:**
- If naming matches Copilot convention (`<app>-<env>-<svc>-Service-XXXXXXXX`) → record `"copilot"` with `confidence: "medium"` and evidence type `"naming_pattern"`
- If naming matches CDK convention (construct-style suffixes) → record `"cdk"` with `confidence: "medium"` and evidence type `"naming_pattern"`
- Naming patterns alone provide `"medium"` confidence — they can be corroborated by tags or stack association to raise confidence
- Naming-pattern confidence is CAPPED at `"medium"` — generic patterns like `<app>-<env>-<svc>` overlap heavily with human naming conventions and must never produce `"high"` on their own
- If naming does not match any known pattern → do NOT record evidence for this step
- Terraform naming patterns are too varied to detect by name alone — Terraform detection relies on team-convention tags (`terraform:*`, `tf-*`, or provider `default_tags`), which many estates never configure. A Terraform-managed environment with no such tags will correctly land as `undetermined`

---

## Classification Logic

After running all three detection steps, classify IaC tools using this logic:

```
For each tool candidate (terraform, cloudformation, cdk, copilot):
  1. Collect all evidence items found across all detection steps
  2. Determine confidence:
     - "high"   → evidence from resource_tags, OR stack_association where the
                  resource verifiably belongs to the stack (membership fact)
     - "medium" → evidence from naming_pattern only, OR stack_association based
                  solely on a name-shape heuristic (e.g., stack named like
                  <app>-<env>-<svc> with no corroborating tags or logical IDs)
     - "low"    → no direct evidence, but inferred from related resources
     Generic name patterns (e.g., <app>-<env>-<svc>) are capped at "medium" —
     they overlap with common human naming conventions and never yield "high"
     alone.
  3. Each evidence item has:
     - type: "resource_tags" | "stack_association" | "naming_pattern"
     - detail: human-readable description of what was found

If NO evidence was found for ANY tool:
  → Set undetermined: true

If evidence IS found for one or more tools:
  → Report each detected tool with its evidence
  → Set undetermined: false
```

**Tool mapping from evidence:**

| Evidence Source | Indicator | Mapped Tool |
|----------------|-----------|-------------|
| Tag: `terraform:*` prefix | Terraform state management tags | `terraform` |
| Tag: `tf-*` prefix | Terraform workspace/module tags | `terraform` |
| Tag: `aws:cdk:path` | CDK construct path tag | `cdk` |
| Tag: `aws-cdk:*` prefix | CDK metadata tags | `cdk` |
| Tag: `copilot-application` | Copilot application tag | `copilot` |
| Tag: `copilot-environment` | Copilot environment tag | `copilot` |
| Tag: `copilot-service` | Copilot service tag | `copilot` |
| Tag: `aws:cloudformation:stack-id` | CloudFormation stack ownership | `cloudformation` |
| Tag: `aws:cloudformation:stack-name` | CloudFormation stack name | `cloudformation` |
| Tag: `aws:cloudformation:logical-id` | CloudFormation logical resource | `cloudformation` |
| Stack: ECS resources in active stack | Stack owns the ECS resource | `cloudformation` |
| Stack: CDK-pattern stack name | CDK-generated CloudFormation stack | `cdk` |
| Stack: Copilot-pattern stack name | Copilot-generated CloudFormation stack | `copilot` |
| Name: Copilot `<app>-<env>-<svc>-*` | Copilot naming convention | `copilot` |
| Name: CDK construct suffixes | CDK construct ID pattern | `cdk` |

**Important:** Evidence types are restricted to exactly these three values:
- `"resource_tags"` — evidence from tag inspection (step 1)
- `"stack_association"` — evidence from CloudFormation stack membership (step 2)
- `"naming_pattern"` — evidence from resource name analysis (step 3)

Any evidence that does not fit one of these types SHALL NOT be reported. If no valid evidence type can be assigned, that evidence item is discarded.

---

## Output Schema

```yaml
iac:
  detected_tools:
    - tool: string              # "terraform" | "cloudformation" | "cdk" | "copilot"
      confidence: string        # "high" | "medium" | "low"
      evidence:
        - type: string          # "resource_tags" | "stack_association" | "naming_pattern"
          detail: string        # Human-readable evidence description
  undetermined: bool            # true if no tool detected
  error: string | null          # Error message when a detection step failed (partial results); null when all steps ran cleanly
```

**Field details:**

| Field | Type | Description |
|-------|------|-------------|
| `detected_tools` | list | All IaC tools detected (may contain multiple) |
| `detected_tools[].tool` | string | Tool identifier: `"terraform"`, `"cloudformation"`, `"cdk"`, or `"copilot"` |
| `detected_tools[].confidence` | string | Detection confidence: `"high"`, `"medium"`, or `"low"` |
| `detected_tools[].evidence` | list | Supporting evidence items (at least one per tool) |
| `detected_tools[].evidence[].type` | string | Evidence category: `"resource_tags"`, `"stack_association"`, or `"naming_pattern"` |
| `detected_tools[].evidence[].detail` | string | Human-readable description of the evidence |
| `undetermined` | bool | `true` when no IaC tool could be identified; `false` when at least one tool detected. NOTE: `undetermined: true` often means "Terraform (which emits no default tags) or console-managed" — it is NOT proof that no IaC exists |
| `error` | string or null | Error message(s) recorded when one or more detection steps failed but others produced results; `null` when every step completed |

**Example output (multiple tools detected):**
```yaml
iac:
  detected_tools:
    - tool: "cdk"
      confidence: "high"
      evidence:
        - type: "resource_tags"
          detail: "Tag 'aws:cdk:path' found on service 'api-service' with value 'MyStack/ApiService/Service'"
        - type: "stack_association"
          detail: "Service belongs to CloudFormation stack 'CdkEcsStack' with CDK-pattern naming"
    - tool: "terraform"
      confidence: "high"
      evidence:
        - type: "resource_tags"
          detail: "Tag 'terraform:managed=true' found on cluster 'prod-cluster'"
  undetermined: false
  error: null
```

**Example output (undetermined):**
```yaml
iac:
  detected_tools: []
  undetermined: true
  error: null
```

**Example output (single tool, medium confidence):**
```yaml
iac:
  detected_tools:
    - tool: "copilot"
      confidence: "medium"
      evidence:
        - type: "naming_pattern"
          detail: "Service name 'my-app-production-api-Service-aB3cD4eF' matches Copilot naming convention"
  undetermined: false
  error: null
```

---

## Edge Cases

Handle these scenarios to ensure accurate IaC detection.

### Multiple tools detected

It is valid for different ECS resources to be managed by different IaC tools. For example, a cluster might be created by Terraform while services within it are deployed by CDK or Copilot.

**How to handle:**
- Report each detected tool with its own evidence list
- Do NOT assume a single tool manages the entire environment
- Each tool must have at least one evidence item — do not report a tool without supporting evidence
- The `undetermined` field is `false` when at least one tool is detected

**Example:**
```yaml
iac:
  detected_tools:
    - tool: "terraform"
      confidence: "high"
      evidence:
        - type: "resource_tags"
          detail: "Tag 'terraform:managed=true' found on cluster 'prod-cluster'"
    - tool: "copilot"
      confidence: "high"
      evidence:
        - type: "resource_tags"
          detail: "Tags 'copilot-application', 'copilot-environment', 'copilot-service' found on service 'api-service'"
  undetermined: false
  error: null
```

### No tags present on resources

Some resources may have no tags at all, or only non-IaC-related tags (e.g., `Environment`, `Team`). This does not mean IaC is absent — tags may have been stripped, and **Terraform does not tag by default at all**: without provider `default_tags` or explicit tags, Terraform-managed resources carry no Terraform marker.

**How to handle:**
- Continue to step 2 (stack association) and step 3 (naming patterns)
- If no evidence is found across all three steps → report `undetermined: true`
- Do NOT guess or infer a tool without matching evidence
- The absence of tags is not evidence for any particular tool
- When reporting `undetermined: true`, communicate it as "no detectable IaC markers — likely Terraform without tagging conventions, or console-managed", never as "no IaC in use"

**Example:**
```yaml
iac:
  detected_tools: []
  undetermined: true
  error: null
```

### Naming patterns without confirming tags

A resource name may match a Copilot or CDK naming convention, but without corresponding tags the detection is lower confidence.

**How to handle:**
- Report the tool with `confidence: "medium"` when only naming patterns are the evidence
- Use evidence type `"naming_pattern"` to make the basis clear
- If both naming pattern AND tags/stack association are present → confidence is `"high"` (use the strongest evidence type)
- Naming patterns alone are valid evidence but should be distinguished from tag-based or stack-based evidence

**Example:**
```yaml
iac:
  detected_tools:
    - tool: "copilot"
      confidence: "medium"
      evidence:
        - type: "naming_pattern"
          detail: "Cluster name 'my-app-production-Cluster-vR5x8Kq2' matches Copilot naming convention"
  undetermined: false
  error: null
```

### Evidence type restrictions

Only three evidence types are valid: `"resource_tags"`, `"stack_association"`, and `"naming_pattern"`. Any other evidence type (e.g., configuration file detection, API behavior inference, user input) SHALL NOT be reported.

**How to handle:**
- Discard any evidence that cannot be classified into one of the three valid types
- If the only available evidence does not fit a valid type → report `undetermined: true`
- Do NOT invent custom evidence types

### CloudFormation tags present with CDK or Copilot

Both CDK and Copilot deploy resources via CloudFormation, so their resources will have `aws:cloudformation:*` tags in addition to their own tool-specific tags. This creates overlapping evidence.

**How to handle:**
- If CDK-specific tags (`aws:cdk:path`, `aws-cdk:*`) are present alongside `aws:cloudformation:*` tags → report `"cdk"` (not `"cloudformation"`)
- If Copilot-specific tags (`copilot-application`, `copilot-environment`, `copilot-service`) are present alongside `aws:cloudformation:*` tags → report `"copilot"` (not `"cloudformation"`)
- Report `"cloudformation"` only when `aws:cloudformation:*` tags are present WITHOUT CDK or Copilot-specific tags
- Priority: Copilot tags > CDK tags > plain CloudFormation tags (most specific tool wins)

**Example (CDK with CloudFormation tags — report as CDK):**
```yaml
iac:
  detected_tools:
    - tool: "cdk"
      confidence: "high"
      evidence:
        - type: "resource_tags"
          detail: "Tag 'aws:cdk:path' found on service with value 'MyStack/Service/Resource'"
        - type: "stack_association"
          detail: "Service belongs to stack 'CdkEcsStack' (CDK-generated)"
  undetermined: false
  error: null
```

### API call failures (access denied or throttling)

If `ecs:ListTagsForResource` or CloudFormation APIs fail:

**How to handle:**
- Record the failure in the `error` field but continue remaining detection steps
- A tag retrieval failure does not prevent stack association or naming pattern checks
- If ALL detection steps fail → use the unavailable output schema:

```yaml
iac:
  unavailable: true
  reason: "ecs:ListTagsForResource failed: AccessDeniedException; cloudformation:ListStacks failed: AccessDeniedException"
```

- If only some steps fail, report what could be determined and record the failure in `error`:

```yaml
iac:
  detected_tools:
    - tool: "copilot"
      confidence: "medium"
      evidence:
        - type: "naming_pattern"
          detail: "Service name matches Copilot naming convention"
  undetermined: false
  error: "ecs:ListTagsForResource failed: AccessDeniedException — tag-based detection skipped"
```

---

## Sources

- https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_ListStacks.html (valid `StackStatusFilter` values, including `IMPORT_COMPLETE` and `IMPORT_ROLLBACK_COMPLETE`)
- https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_DescribeStackResources.html (100-resource limit; `PhysicalResourceId` reverse lookup; guidance to use `ListStackResources` for larger stacks)
- https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_ListStackResources.html (paginated stack resource enumeration)
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-resource-tags.html (automatic `aws:cloudformation:*` stack-level tags)
- https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_ListTagsForResource.html (tag retrieval for ECS clusters and services)
- https://registry.terraform.io/providers/hashicorp/aws/latest/docs/guides/resource-tagging (Terraform AWS provider applies no tags unless `default_tags` or per-resource tags are configured)
