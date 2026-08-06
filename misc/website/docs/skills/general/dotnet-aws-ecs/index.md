---
title: "dotnet-aws-ecs"
description: "Generates IaC (CloudFormation or CDK) and a deployment guide to deploy a .NET workload to Amazon ECS Fargate on Linux containers with an Application Load Balancer. Produces a VPC, ECS cluster, task definition, ALB, and auto-scaling. NOT for Windows containers, EC2 launch type, or Kubernetes/EKS deployments."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/dotnet-aws-ecs/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/dotnet-aws-ecs/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/dotnet-aws-ecs/SKILL.md). Edit the source, not this page.
:::


:::caution[Third-party skill]
This skill is maintained by **Copyright (c) 2026 adisimon217** under the Apache-2.0 license. Upstream: [https://github.com/adisimon217/sample-appmod-skills](https://github.com/adisimon217/sample-appmod-skills)
:::


# Deploy .NET Workload to AWS ECS Fargate

## When to Use This Skill

**Use this skill when:**
- A .NET application (Web API, ASP.NET Core MVC/Razor, Blazor Server) is running locally and ready for cloud deployment
- The developer wants to deploy to ECS Fargate (serverless containers) on AWS
- The developer wants IaC that provisions everything in a single stack

**Do NOT use this skill for:**
- Applications that aren't yet running locally
- Windows container deployments
- EC2 launch type deployments
- Kubernetes/EKS deployments
- Serverless (Lambda) deployments

## Objective

Produce IaC (CloudFormation or CDK — user chooses) and a step-by-step deployment guide. The output provisions:

- VPC with public and private subnets (2 AZs) — **or** uses an existing VPC and subnets provided by the user
- Application Load Balancer (internet-facing or internal)
- ECS Cluster with Fargate service (2 tasks)
- ECR repository for the container image
- IAM roles (task execution + task role)
- Auto-scaling (CPU-based target tracking)
- CloudWatch log group

Keep it focused on compute and networking. No databases, caches, or auth services.

## Recommended MCP Server

This skill works best when the **AWS Knowledge MCP** server is configured. It provides access to up-to-date AWS documentation for ECS, CloudFormation, CDK, and related services.

- **URL**: `https://knowledge-mcp.global.api.aws`
- **Usage**: When generating IaC or resolving deployment issues, use the AWS Knowledge MCP to look up current resource property schemas, valid parameter values, and best practices (e.g., `search_documentation` for ECS task definition properties, Fargate platform versions, ALB listener rules, or CDK construct APIs).

If the MCP is not configured, the skill will still work using embedded guidance in the reference files, but results may not reflect the latest AWS service changes.

## Phases

### Phase 0 — Gather Information

Before generating anything, determine:

1. **Application details** — find the web project, read `.csproj` for TargetFramework, check `Program.cs` for health check path
2. **Container port** — check `ASPNETCORE_URLS`, `launchSettings.json`, or default (8080 for .NET 8+, 5000 for earlier)
3. **Existing Dockerfile** — if one exists alongside the project, use it; otherwise generate one in Phase 2

### Ask the Developer

- **IaC format**: "Do you prefer **CloudFormation** (YAML) or **CDK** (C#)?"
- **VPC selection**: "Would you like to deploy into a **new VPC** (default) or an **existing VPC**?"
  - If the user chooses **existing VPC**, ask for the VPC ID and subnet IDs (2 public, 2 private).
  - Optionally, if the AWS CLI is available and an AWS profile is configured, offer to retrieve the list of existing VPCs and their subnets by running:
    ```bash
    aws ec2 describe-vpcs --query "Vpcs[*].{VpcId:VpcId,Name:Tags[?Key=='Name']|[0].Value,CidrBlock:CidrBlock}" --output table
    ```
    Then, once the user selects a VPC:
    ```bash
    aws ec2 describe-subnets --filters "Name=vpc-id,Values=<vpc-id>" --query "Subnets[*].{SubnetId:SubnetId,AZ:AvailabilityZone,CidrBlock:CidrBlock,Name:Tags[?Key=='Name']|[0].Value,Public:MapPublicIpOnLaunch}" --output table
    ```
    **Important:** Always ask for user approval before running any AWS CLI commands.
- **ALB scheme**: "Should the load balancer be internet-facing or internal?"
- **Container health check**: "By default, the chiseled (minimal) Docker image is used for security. This means the ECS console will show container health as 'Unknown' since chiseled images have no shell or curl — the ALB health check still protects against unhealthy tasks. Would you like to enable the **ECS container health check** instead? This requires switching to a non-chiseled image (larger, but gives explicit 'Healthy' status in the ECS console)."
  - If the user chooses container health check: use the non-chiseled runtime image (`-noble`) in the Dockerfile and add a `HealthCheck` block to the task definition container. See [references/cloudformation-template-guide.md](references/cloudformation-template-guide) § "Container Health Check" and [references/dockerfile-guide.md](references/dockerfile-guide) § "Non-Chiseled Alternative".
  - If the user declines (default): use the chiseled image and do not add a container-level health check. After deployment, inform the user that "Unknown" container health in the ECS console is expected.
- **Target AWS region** (default to `ap-southeast-1` if not specified)
- **Environment name** (default to `dev` if not specified)

### Phase 1 — Generate IaC

Generate the ECS Fargate infrastructure based on the user's IaC choice.

Read [references/cloudformation-template-guide.md](references/cloudformation-template-guide) for CloudFormation structure, or [references/cdk-template-guide.md](references/cdk-template-guide) for CDK structure.

#### New VPC (default)

Both formats must include:
- VPC, subnets (2 public, 2 private), Internet Gateway, NAT Gateways, route tables
- ALB security group, ECS task security group
- Application Load Balancer (scheme per user choice), target group, HTTP listener
- ECR repository
- ECS cluster, task definition (Fargate, Linux, 256 CPU / 512 MiB), service (2 tasks)
- IAM roles: ECS Task Execution Role, ECS Task Role
- Auto-scaling: target tracking on CPU at 70%
- CloudWatch log group

#### Existing VPC

When the user opts to deploy into an existing VPC, the template must:
- Accept VPC ID and subnet IDs as parameters (no VPC/subnet/gateway/route resources are created)
- Still create all security groups, ALB, ECS, ECR, IAM, auto-scaling, and log group resources
- Reference the provided VPC/subnet IDs wherever the new-VPC template would reference `!Ref VPC` or `!Ref PublicSubnet1`, etc.

See the "Existing VPC Mode" sections in [references/cloudformation-template-guide.md](references/cloudformation-template-guide) and [references/cdk-template-guide.md](references/cdk-template-guide) for implementation details.

#### Output Location

- CloudFormation: `<project-root>/infra/ecs-fargate.yaml`
- CDK: `<project-root>/infra/EcsFargate.Cdk/`

### Phase 2 — Generate Dockerfile

If the application doesn't already have a Dockerfile, generate one.

Read [references/dockerfile-guide.md](references/dockerfile-guide) for the patterns.

Key points:
- Multi-stage build (SDK → chiseled-ubuntu runtime)
- Match base image to TargetFramework
- Expose the correct port
- Run as non-root user via `$APP_UID` (chiseled images have no shell/adduser)
- Place alongside the web project (same directory as the `.csproj`)
- Place `.dockerignore` at the Docker build context root, not inside the web project folder

### Phase 2.5 — Validate Docker Build Locally

After generating the Dockerfile, validate the Docker image builds successfully.

Read [references/dockerfile-guide.md](references/dockerfile-guide) § "Local Validation" for the procedure.

Key points:
- Check if Docker is installed locally; if not, skip validation and add a manual validation section to the deployment guide
- Run `docker build` from the build context root
- Run the container briefly to confirm the runtime starts (expect DB connection errors if no database is available — that's OK)
- Clean up all test containers and images after validation
- If the build fails, fix the Dockerfile and retry before proceeding

### Phase 3 — Generate Deployment Guide

Produce a markdown deployment guide with step-by-step CLI commands.

Read [references/deployment-guide-template.md](references/deployment-guide-template) for the structure.

The guide must cover:
1. Prerequisites (AWS CLI, Docker)
2. Deploy the infrastructure stack
3. Build and push the container image to ECR
4. Update the ECS service to pull the new image
5. Verify deployment (ALB URL, ECS service status, logs)
6. Cleanup (delete stack, delete ECR images)
7. Cost estimation
8. Next steps (HTTPS, custom domain, CI/CD)

#### Output Location

`<project-root>/infra/DEPLOYMENT.md`

## Constraints

- Single stack — not multiple stacks or nested stacks
- Use `!Sub` with `${EnvironmentName}` prefix for resource names (CloudFormation) or equivalent parameterization (CDK)
- All ECS tasks in private subnets, ALB in public subnets
- Default to 256 CPU / 512 MiB for dev — add comments noting production sizing
- 2 desired tasks with deployment circuit breaker enabled
- Do NOT include databases, caches, queues, or auth services
- Do NOT hardcode account IDs or regions
- Dockerfile lives alongside the `.csproj` (application source), NOT in the `infra/` folder

## Output Structure

```
<project-root>/
├── infra/
│   ├── ecs-fargate.yaml              # CloudFormation template (if chosen)
│   ├── EcsFargate.Cdk/               # CDK project (if chosen)
│   └── DEPLOYMENT.md                 # Step-by-step deployment guide
├── <WebProject>/
│   └── Dockerfile                    # If not already present (alongside .csproj)
```

## Reporting

After generation, summarize:
- What the stack provisions
- IaC format chosen
- VPC mode (new VPC or existing VPC with ID)
- ALB scheme (internet-facing or internal)
- Estimated monthly cost (dev environment)
- Any manual steps required
- Suggested next steps
