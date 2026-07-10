---
title: "ECS DevOps — CI/CD Pipelines"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-devops/references/cicd-pipelines.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-devops/references/cicd-pipelines.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-devops/references/cicd-pipelines.md). Edit the source, not this page.
:::

# ECS DevOps — CI/CD Pipelines

> **Part of:** [ecs-devops](../)
> **Purpose:** Building deployment pipelines to ECS — CodePipeline actions, GitHub Actions with the official aws-actions, driving ECS-native strategies from any pipeline, and ECR image scanning gates

**For the strategies these pipelines trigger, see:** [deployment-strategies.md](deployment-strategies)

> Facts in this file verified 2026-07-09 against the AWS documentation and GitHub URLs cited inline.

---

## Table of Contents

1. [Choosing a Pipeline Shape](#choosing-a-pipeline-shape)
2. [CodePipeline — Standard ECS Action](#codepipeline--standard-ecs-action)
3. [CodePipeline — ECS Blue/Green Action (CodeDeployToECS)](#codepipeline--ecs-bluegreen-action-codedeploytoecs)
4. [Driving ECS-Native Strategies from Any Pipeline](#driving-ecs-native-strategies-from-any-pipeline)
5. [GitHub Actions with Official aws-actions](#github-actions-with-official-aws-actions)
6. [ECR Image Scanning in the Pipeline](#ecr-image-scanning-in-the-pipeline)
7. [Launch-Type Notes for Pipelines](#launch-type-notes-for-pipelines)

---

## Choosing a Pipeline Shape

| Situation | Recommended shape |
|---|---|
| AWS-native pipeline, rolling deployments | CodePipeline standard "Amazon ECS" action |
| AWS-native pipeline, existing CodeDeploy blue/green | Keep CodePipeline "ECS (Blue/Green)" action — a fully supported steady state (no announced EOL); migrate to native only when you want its benefits (see [controllers-and-migration.md](controllers-and-migration)) |
| AWS-native pipeline, ECS-native blue/green / linear / canary | CodePipeline + a stage that calls `aws ecs update-service` (CodeBuild/Lambda) — **no dedicated action exists as of 2026-07-10** |
| GitHub-hosted repo | Official `aws-actions/*` GitHub Actions with OIDC |
| Any strategy, any CI system | Render task definition → `RegisterTaskDefinition` → `UpdateService`; the service's configured strategy does the rest |

## CodePipeline — Standard ECS Action

Sources: https://docs.aws.amazon.com/codepipeline/latest/userguide/integrations-action-type.html and https://docs.aws.amazon.com/codepipeline/latest/userguide/file-reference.html (verified 2026-07-09)

- Deploy provider **"Amazon ECS"**: deploys a new image to the service; the service performs its configured `ECS`-controller deployment (rolling by default).
- **Input contract: `imagedefinitions.json`** — an artifact listing container name → image URI pairs, typically emitted by the build stage:

```json
[ { "name": "web", "imageUri": "111122223333.dkr.ecr.us-east-1.amazonaws.com/web:2f1c9a7" } ]
```

- Tutorial (ECR source → CodeBuild → ECS): https://docs.aws.amazon.com/codepipeline/latest/userguide/ecs-cd-pipeline.html
- Pair the service with circuit breaker + alarm rollback (EC2/Fargate/Managed Instances; see the ECS Anywhere caveat in [failure-detection-and-rollback.md](failure-detection-and-rollback)) so a bad image fails the pipeline stage rather than silently degrading; note the alarm bake time keeps the deployment `IN_PROGRESS` longer — set stage timeouts accordingly.

## CodePipeline — ECS Blue/Green Action (CodeDeployToECS)

Sources: https://docs.aws.amazon.com/codepipeline/latest/userguide/action-reference-ECSbluegreen.html and https://docs.aws.amazon.com/codepipeline/latest/userguide/file-reference.html (verified 2026-07-09)

- Deploy provider **"Amazon ECS (Blue/Green)"** (`CodeDeployToECS`): drives the **CodeDeploy controller**, not ECS-native blue/green.
- **Input contract:** `imageDetail.json` (emitted automatically by ECR source actions) **plus** an AppSpec file and a task-definition template.
- Tutorial (ECR source + blue/green): https://docs.aws.amazon.com/codepipeline/latest/userguide/tutorials-ecs-ecr-codedeploy.html
- Constraints inherited from the CodeDeploy controller: ALB or NLB required (no Service Connect); NLB restricts you to `CodeDeployDefault.ECSAllAtOnce`; canary/linear shifting only via CodeDeploy deployment configurations (see [controllers-and-migration.md](controllers-and-migration)).
- Keep using this action for existing integrations; for new services AWS recommends the native strategies ([deployment-type-bluegreen](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-bluegreen.html)).

## Driving ECS-Native Strategies from Any Pipeline

Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/migrate-codedeploy-to-ecs-bluegreen.html (verified 2026-07-09)

**There is no dedicated CodePipeline action for ECS-native BLUE_GREEN / LINEAR / CANARY (as of 2026-07-10).** AWS's own migration checklist says: update deployment scripts and CI/CD pipelines to use the Amazon ECS `UpdateService` API instead of the CodeDeploy `CreateDeployment` API. The pattern:

```bash
# 1. Register the new task definition revision (immutable image tag or digest)
TASKDEF_ARN=$(aws ecs register-task-definition --cli-input-json file://taskdef.json \
  --query 'taskDefinition.taskDefinitionArn' --output text)

# 2. Update the service — the strategy configured on the service (BLUE_GREEN/LINEAR/CANARY) governs the rollout
aws ecs update-service --cluster prod --service web --task-definition "$TASKDEF_ARN"

# 3. Wait / observe
aws ecs wait services-stable --cluster prod --services web
# or poll: aws ecs describe-service-deployments / list-service-deployments
```

In CodePipeline, run this from a CodeBuild action or a Lambda invoke action. Gate promotion with a pause lifecycle hook + `continue-service-deployment` for human approval, or Lambda hooks for automated verification (see [deployment-strategies.md](deployment-strategies)).

## GitHub Actions with Official aws-actions

Sources (all verified 2026-07-10): https://github.com/actions/checkout · https://github.com/aws-actions/configure-aws-credentials · https://github.com/aws-actions/amazon-ecr-login · https://github.com/aws-actions/amazon-ecs-render-task-definition · https://github.com/aws-actions/amazon-ecs-deploy-task-definition

Building blocks, in order:

1. **`aws-actions/configure-aws-credentials`** — assume an IAM role via GitHub OIDC; no long-lived access keys in repo secrets.
2. **`aws-actions/amazon-ecr-login`** — authenticate the runner to ECR for push/pull.
3. **`aws-actions/amazon-ecs-render-task-definition`** — inject the freshly built image URI into the task-definition JSON.
4. **`aws-actions/amazon-ecs-deploy-task-definition`** — register the rendered task definition and update the service. Key inputs: `task-definition`, `service`, `cluster`, `wait-for-service-stability`. Supports CodeDeploy blue/green via `codedeploy-appspec`, `codedeploy-application`, `codedeploy-deployment-group`. Actively maintained (v2.6.3, July 2026). For ECS-native blue/green-family services, this action's plain service update is sufficient — the service's configured strategy governs the rollout.

Workflow skeleton (rolling or native-strategy service; works for EC2, Fargate, and Managed Instances services — see launch-type notes below):

```yaml
name: deploy-to-ecs
on:
  push:
    branches: [main]
permissions:
  id-token: write   # OIDC
  contents: read
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: aws-actions/configure-aws-credentials@v6
        with:
          role-to-assume: arn:aws:iam::111122223333:role/github-deploy
          aws-region: us-east-1
      - id: ecr
        uses: aws-actions/amazon-ecr-login@v2
      - id: build
        run: |
          IMAGE="${{ steps.ecr.outputs.registry }}/web:${{ github.sha }}"
          docker build -t "$IMAGE" .
          docker push "$IMAGE"
          echo "image=$IMAGE" >> "$GITHUB_OUTPUT"
      - id: render
        uses: aws-actions/amazon-ecs-render-task-definition@v1
        with:
          task-definition: taskdef.json
          container-name: web
          image: ${{ steps.build.outputs.image }}
      - uses: aws-actions/amazon-ecs-deploy-task-definition@v2
        with:
          task-definition: ${{ steps.render.outputs.task-definition }}
          service: web
          cluster: prod
          wait-for-service-stability: true
```

Notes:
- Use the commit SHA (immutable) as the image tag — avoids the mutable-tag `--force-new-deployment` pattern entirely (see [failure-detection-and-rollback.md](failure-detection-and-rollback)).
- `wait-for-service-stability: true` makes the job fail when a circuit breaker or alarm rolls the deployment back — the pipeline reflects deployment reality.
- Pin action versions in regulated environments (major-version tags like `@v7` are mutable; pin a full tag or commit SHA there). The major tags above were current at verification (2026-07-10): `actions/checkout` v7.0.0, `aws-actions/configure-aws-credentials` v6.2.2, `amazon-ecr-login` v2.1.6, `amazon-ecs-render-task-definition` v1.9.0, `amazon-ecs-deploy-task-definition` v2.6.3 — re-check each repo's Releases page before copying.

## ECR Image Scanning in the Pipeline

Sources: https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-basic-enabling.html and https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced.html (verified 2026-07-09)

| | Basic scanning | Enhanced scanning (Amazon Inspector) |
|---|---|---|
| Coverage | OS-package CVEs only | OS **and** language-package vulnerabilities |
| Trigger | On push (per-repository filters); default-on for private registries | Continuous and/or on-push via registry-level scan filters; **manual scans not supported** |
| Cost | Included | Amazon Inspector pricing applies |
| Extras | Findings in ECR console/API | ECS/EKS image-usage context for prioritization; findings in ECR + Inspector; Security Hub / EventBridge integration |
| Gotcha | — | Images older than 14 days at enablement get `SCAN_ELIGIBILITY_EXPIRED` — re-push to scan |

Pipeline gating pattern: push → scan → EventBridge finding event → automation (fail the pipeline stage / block promotion on CRITICAL findings). Reference implementation: [ECR + Inspector scanning blog](https://aws.amazon.com/blogs/containers/container-scanning-updates-in-amazon-ecr-private-registries-using-amazon-inspector/). Deeper vulnerability-management policy (SLAs, suppression, registry hardening) is `ecs-security` territory; this reference covers the pipeline hook only.

## Launch-Type Notes for Pipelines

> Verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateService.html and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html

- The pipeline mechanics above (register task def → update service) are identical for **EC2, Fargate, and Managed Instances** services — launch type is a property of the service/capacity provider, not the pipeline. Remember: Managed Instances services use `capacityProviderStrategy` (no `launchType` field), and `FARGATE_SPOT` is a capacity provider.
- **ECS Anywhere (`EXTERNAL` launch type):** pipelines deploy the same way, but the service can only do rolling deployments (no ELB/Service Connect → no managed traffic shifting), so do not attach CodeDeploy blue/green actions or native blue/green-family expectations to Anywhere services. Runners/agents must reach the ECS control plane; the tasks themselves run on-premises.
- Fargate platform-version bumps ride along with new deployments; a `--force-new-deployment` (restart) is only needed when nothing else changes — prefer shipping a new task-definition revision from the pipeline.
