# Module: CI/CD Detection

> **Part of:** [ecs-recon](../SKILL.md)
> **Purpose:** Detect CI/CD tooling associated with ECS deployments

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [CodePipeline Detection](#1-codepipeline-detection)
  - [CodeDeploy Detection](#2-codedeploy-detection)
  - [Resource Tag Detection](#3-resource-tag-detection)
  - [Workspace File Detection](#4-workspace-file-detection)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)
- [Sources](#sources)

---

## Prerequisites

- **Cluster name required:** Yes
- **Service name(s) required:** Yes (for tag-based detection on service/task definition resources)
- **AWS APIs used:**
  - `codepipeline:ListPipelines` — enumerate CodePipeline pipelines in the account
  - `codepipeline:GetPipeline` — inspect pipeline stages for ECS deploy actions
  - `codedeploy:ListApplications` — enumerate CodeDeploy applications
  - `codedeploy:GetApplication` — check compute platform for ECS
  - `ecs:ListTagsForResource` — read tags on ECS resources for CI/CD indicators
- **CLI commands:** `aws codepipeline list-pipelines`, `aws codepipeline get-pipeline`, `aws deploy list-applications`, `aws deploy get-application`, `aws ecs list-tags-for-resource` (note: the CodeDeploy CLI service command is `deploy`, not `codedeploy`)
- **IAM permissions:** Read-only (`codepipeline:ListPipelines`, `codepipeline:GetPipeline`, `codedeploy:ListApplications`, `codedeploy:GetApplication`, `ecs:ListTagsForResource`)
- **All operations are read-only** — no resources are created, modified, or deleted

---

## Detection Strategy

Run detections in this order to identify CI/CD tooling from strongest signals to weakest:

```
1. CodePipeline Detection   -> Check for pipelines with ECS deploy actions
2. CodeDeploy Detection     -> Check for CodeDeploy applications with ECS compute platform
3. Resource Tag Detection   -> Check ECS resource tags for CI/CD indicators (GitHub Actions, GitLab CI, Jenkins)
4. Workspace File Detection -> Check local workspace for CI/CD configuration files (if available)
```

**Why this order matters:**
- CodePipeline is the strongest signal — a pipeline with an ECS deploy action is definitive evidence of AWS-native CI/CD
- CodeDeploy may be used standalone (without CodePipeline) for blue/green ECS deployments — checking it separately catches this case
- Resource tags provide heuristic evidence of third-party CI/CD tools (GitHub Actions, GitLab CI, Jenkins) — but only when the team's pipeline was written to apply such tags; the tools themselves emit none
- Workspace file detection is the weakest signal — CI/CD config files may exist in the repo but not actively deploy to the target cluster; this step also may not be available if the workspace is not accessible

**Key decision logic:**
- If CodePipeline pipelines have ECS deploy actions → report `codepipeline` with pipeline name as evidence at `confidence: "high"` (the deploy action is a fact returned by the API)
- If CodeDeploy applications target ECS compute platform → report `codedeploy` with application name as evidence at `confidence: "high"` (`computePlatform: "ECS"` is a fact returned by the API)
- If resource tags match the heuristic conventions below → report the corresponding tool with the tag as evidence at `confidence: "medium"` (tags are team conventions, not tool-emitted signatures)
- If workspace files match CI/CD patterns and reference ECS → report the corresponding tool with the file path as evidence at `confidence: "medium"` (a config file proves the pipeline exists, not that it deploys to THIS cluster); if the file names the target cluster/service explicitly → `confidence: "high"`
- If none of the above yield results → report `undetermined: true`
- Multiple CI/CD tools can be detected simultaneously (e.g., CodePipeline + GitHub Actions)

---

## Detection Commands

### 1. CodePipeline Detection

Check whether any CodePipeline pipelines in the account contain ECS deploy actions. This is the strongest indicator of AWS-native CI/CD for ECS.

> Facts verified 2026-07-14 against https://docs.aws.amazon.com/codepipeline/latest/userguide/action-reference-ECS.html and https://docs.aws.amazon.com/codepipeline/latest/userguide/action-reference-ECSbluegreen.html — the ECS standard deploy action uses provider `ECS`; the blue/green action uses provider `CodeDeployToECS`.

**CLI:**
```bash
aws codepipeline list-pipelines \
  --query 'pipelines[].name' \
  --output json
```

**Example output:**
```json
[
  "prod-ecs-deploy",
  "staging-ecs-pipeline",
  "unrelated-lambda-pipeline"
]
```

**For each pipeline, inspect for ECS actions:**
```bash
aws codepipeline get-pipeline \
  --name <pipeline-name> \
  --query 'pipeline.stages[].actions[?actionTypeId.provider==`ECS` || actionTypeId.provider==`CodeDeployToECS`].{name:name,provider:actionTypeId.provider,config:configuration}' \
  --output json
```

**Example output (pipeline with ECS deploy action):**
```json
[
  [
    {
      "name": "DeployToECS",
      "provider": "ECS",
      "config": {
        "ClusterName": "prod-cluster",
        "ServiceName": "api-service",
        "FileName": "imagedefinitions.json"
      }
    }
  ]
]
```

**Example output (pipeline with CodeDeploy blue/green ECS action):**
```json
[
  [
    {
      "name": "BlueGreenDeploy",
      "provider": "CodeDeployToECS",
      "config": {
        "ApplicationName": "AppECS-prod-cluster-api-service",
        "DeploymentGroupName": "DgpECS-prod-cluster-api-service"
      }
    }
  ]
]
```

**Interpret the result:**
- If a pipeline has an action with `provider: "ECS"` → the pipeline directly deploys to ECS using a rolling update
- If a pipeline has an action with `provider: "CodeDeployToECS"` → the pipeline deploys to ECS using CodeDeploy blue/green
- Match the `ClusterName` and `ServiceName` (or application name patterns) to verify the pipeline targets the cluster/service under investigation
- Report each matching pipeline as evidence for `codepipeline`

### 2. CodeDeploy Detection

Check for CodeDeploy applications configured with the ECS compute platform. This detects cases where CodeDeploy is used for ECS blue/green deployments, including scenarios where CodeDeploy is used without CodePipeline.

> Facts verified 2026-07-14 against https://docs.aws.amazon.com/codedeploy/latest/APIReference/API_ApplicationInfo.html — valid `computePlatform` values are `Server | Lambda | ECS | Kubernetes`.

**CLI:**
```bash
aws deploy list-applications \
  --query 'applications' \
  --output json
```

**Example output:**
```json
[
  "AppECS-prod-cluster-api-service",
  "AppECS-prod-cluster-worker-service",
  "AppLambda-my-function"
]
```

**For each application, check if it targets ECS:**
```bash
aws deploy get-application \
  --application-name <app-name> \
  --query 'application.{name:applicationName,computePlatform:computePlatform}' \
  --output json
```

**Example output (ECS application):**
```json
{
  "name": "AppECS-prod-cluster-api-service",
  "computePlatform": "ECS"
}
```

**Example output (non-ECS application):**
```json
{
  "name": "AppLambda-my-function",
  "computePlatform": "Lambda"
}
```

**Interpret the result:**
- If `computePlatform` is `"ECS"` → the application manages ECS blue/green deployments
- Filter out applications with `computePlatform` of `"Lambda"`, `"Server"`, or `"Kubernetes"` — those are not ECS-related
- The naming convention `AppECS-{cluster}-{service}` is common but not guaranteed — always verify with `computePlatform`
- Report each ECS-platform application as evidence for `codedeploy`

### 3. Resource Tag Detection

Check ECS resource tags for indicators of third-party CI/CD tools. Some teams configure their pipelines to tag deployed resources with metadata about the workflow that deployed them — this is a deliberate team practice, not built-in tool behavior.

**CLI (check service tags):**
```bash
aws ecs list-tags-for-resource \
  --resource-arn arn:aws:ecs:<region>:<account>:service/<cluster-name>/<service-name> \
  --query 'tags' \
  --output json
```

**CLI (check cluster tags):**
```bash
aws ecs list-tags-for-resource \
  --resource-arn arn:aws:ecs:<region>:<account>:cluster/<cluster-name> \
  --query 'tags' \
  --output json
```

**Example output (GitHub Actions tags):**
```json
[
  {
    "key": "github-actions-workflow",
    "value": "deploy.yml"
  },
  {
    "key": "github-actions-run-id",
    "value": "7891234567"
  },
  {
    "key": "Environment",
    "value": "production"
  }
]
```

**Example output (GitLab CI tags):**
```json
[
  {
    "key": "gitlab-ci-pipeline-id",
    "value": "123456"
  },
  {
    "key": "gitlab-ci-project",
    "value": "my-org/my-app"
  }
]
```

**Example output (Jenkins tags):**
```json
[
  {
    "key": "jenkins-build-url",
    "value": "https://jenkins.example.com/job/deploy-ecs/42"
  },
  {
    "key": "jenkins-job-name",
    "value": "deploy-ecs"
  }
]
```

**Heuristic CI/CD tag conventions:**

**Important:** none of these third-party tools automatically tag AWS resources. GitHub Actions, GitLab CI, Jenkins, and CircleCI do not emit any tags by themselves — the patterns below are TEAM CONVENTIONS that some pipelines apply deliberately (e.g., a deploy script that adds `deployed-by` or `jenkins-build-url` tags). Their exact keys vary between organizations. Treat any match as heuristic evidence with `confidence: "medium"` at best — never `"high"`.

| CI/CD Tool | Conventional Tag Key Patterns (team-defined, not tool-emitted) | Example Values |
|------------|-----------------|----------------|
| GitHub Actions | `github-actions-*`, `deployed-by: github-actions` | workflow name, run ID, SHA |
| GitLab CI | `gitlab-ci-*`, `deployed-by: gitlab-ci` | pipeline ID, project name |
| Jenkins | `jenkins-*`, `deployed-by: jenkins` | build URL, job name |
| CircleCI | `circleci-*`, `deployed-by: circleci` | workflow ID, job name |
| AWS CodeBuild | `codebuild-*`, `aws:codebuild:*` | project name, build ID |

**Interpret the result:**
- Scan all tag keys for prefixes or patterns matching the table above
- A single matching tag is sufficient to report that CI/CD tool, but at `confidence: "medium"` — these are conventions, not guaranteed tool signatures
- Multiple tags from the same tool, or a tag with a verifiable value (e.g., a `jenkins-build-url` pointing at a real Jenkins host), strengthen the case but still cap at `"medium"` when tags are the only evidence
- Tags from different CI/CD tools can coexist on the same resource — report each tool separately
- Generic tags (e.g., `Environment`, `Team`) are NOT CI/CD evidence — only match the specific patterns listed

### 4. Workspace File Detection

If the local workspace (repository checkout) is available, check for CI/CD configuration files that reference ECS deployments. This detection is opportunistic — the workspace may not be available in all execution contexts.

**Detection files to check:**

| CI/CD Tool | File Paths to Check |
|------------|-------------------|
| GitHub Actions | `.github/workflows/*.yml`, `.github/workflows/*.yaml` |
| GitLab CI | `.gitlab-ci.yml` |
| Jenkins | `Jenkinsfile`, `jenkins/Jenkinsfile` |
| AWS CodeBuild | `buildspec.yml`, `buildspec.yaml` |
| CircleCI | `.circleci/config.yml` |

**CLI (check for GitHub Actions workflows):**
```bash
find .github/workflows -name "*.yml" -o -name "*.yaml" 2>/dev/null | head -10
```

**CLI (check for other CI/CD files):**
```bash
ls -la .gitlab-ci.yml Jenkinsfile jenkins/Jenkinsfile buildspec.yml buildspec.yaml .circleci/config.yml 2>/dev/null
```

**If files are found, check for ECS references:**
```bash
grep -l "ecs\|amazon-ecs\|aws-actions/amazon-ecs" .github/workflows/*.yml 2>/dev/null
```

**Example output:**
```
.github/workflows/deploy.yml
.github/workflows/ecs-deploy-prod.yml
```

**Interpret the result:**
- CI/CD config file exists AND contains ECS references → report as evidence for that CI/CD tool
- CI/CD config file exists but does NOT contain ECS references → do NOT report as evidence (the pipeline may deploy something else)
- File path not found → tool not detected via workspace (does not rule out the tool — it may still be detected via tags or AWS services)

---

## Output Schema

```yaml
cicd:
  detected_tools:
    - tool: string              # "codepipeline" | "codedeploy" | "github_actions" | "gitlab_ci" | "jenkins" | "circleci" | "codebuild"
      confidence: string        # "high" | "medium" | "low"
      evidence:
        - type: string          # "pipeline_action" | "codedeploy_application" | "resource_tag" | "workspace_file"
          detail: string        # Human-readable description of the evidence
  undetermined: bool            # true if no CI/CD detected
  error: string | null          # Error message when a detection step failed (partial results); null when all steps ran cleanly
```

**Field details:**

| Field | Type | Description |
|-------|------|-------------|
| `cicd.detected_tools` | list | All CI/CD tools detected (may contain multiple entries) |
| `cicd.detected_tools[].tool` | string | Normalized tool identifier |
| `cicd.detected_tools[].confidence` | string | Detection confidence: `"high"`, `"medium"`, or `"low"` |
| `cicd.detected_tools[].evidence` | list | One or more evidence items supporting the detection |
| `cicd.detected_tools[].evidence[].type` | string | Evidence category |
| `cicd.detected_tools[].evidence[].detail` | string | Human-readable explanation of what was found |
| `cicd.undetermined` | bool | `true` when no CI/CD tools could be identified from any detection method |
| `cicd.error` | string or null | Error message(s) recorded when one or more detection steps failed but others produced results; `null` when every step completed |

**Evidence type values and confidence mapping:**

| Type | Source | Confidence |
|------|--------|------------|
| `pipeline_action` | CodePipeline pipeline contains an ECS or CodeDeployToECS action | `high` — API-returned fact |
| `codedeploy_application` | CodeDeploy application configured with ECS compute platform | `high` — API-returned fact |
| `resource_tag` | ECS resource tag matches a heuristic team-convention pattern | `medium` at best — conventions, not tool-emitted signatures |
| `workspace_file` | Local CI/CD config file contains ECS references | `medium`; `high` only if the file names the target cluster/service |

When a tool has multiple evidence items, its `confidence` is the highest confidence among them.

**Example output (multiple tools detected):**
```yaml
cicd:
  detected_tools:
    - tool: "codepipeline"
      confidence: "high"
      evidence:
        - type: "pipeline_action"
          detail: "Pipeline 'prod-ecs-deploy' has ECS deploy action targeting cluster 'prod-cluster', service 'api-service'"
    - tool: "github_actions"
      confidence: "medium"
      evidence:
        - type: "resource_tag"
          detail: "Service 'api-service' tagged with 'github-actions-workflow: deploy.yml' (team convention)"
        - type: "workspace_file"
          detail: "File '.github/workflows/deploy.yml' references ECS deployment"
  undetermined: false
  error: null
```

**Example output (undetermined):**
```yaml
cicd:
  detected_tools: []
  undetermined: true
  error: null
```

---

## Edge Cases

Handle these scenarios to ensure accurate CI/CD detection.

### Multiple CI/CD tools in use

An ECS environment may use multiple CI/CD tools simultaneously. For example, CodePipeline for production deployments and GitHub Actions for staging, or Jenkins for build and CodeDeploy for deployment.

**How to handle:**
- Report ALL detected tools — do not assume only one CI/CD tool is in use
- Each tool entry is independent with its own evidence list
- The same resource may have tags from multiple CI/CD tools
- Do NOT deduplicate or merge tools — report each detection as a separate item

**Example:**
```yaml
cicd:
  detected_tools:
    - tool: "codepipeline"
      confidence: "high"
      evidence:
        - type: "pipeline_action"
          detail: "Pipeline 'prod-ecs-deploy' has ECS deploy action"
    - tool: "codedeploy"
      confidence: "high"
      evidence:
        - type: "codedeploy_application"
          detail: "Application 'AppECS-prod-cluster-api-service' with ECS compute platform"
    - tool: "github_actions"
      confidence: "medium"
      evidence:
        - type: "resource_tag"
          detail: "Cluster tagged with 'github-actions-workflow: ci.yml' (team convention)"
  undetermined: false
  error: null
```

### CodeDeploy without CodePipeline

CodeDeploy can manage ECS blue/green deployments independently, triggered by direct API calls, custom scripts, or third-party CI/CD tools. The absence of a CodePipeline pipeline does not mean CodeDeploy is unused.

**How to handle:**
- Always run CodeDeploy detection independently of CodePipeline results
- If CodeDeploy applications with `computePlatform: "ECS"` are found but no CodePipeline pipeline references them → still report `codedeploy` as a detected tool
- This is a common pattern when teams use GitHub Actions or Jenkins to trigger CodeDeploy directly

**Example:**
```yaml
cicd:
  detected_tools:
    - tool: "codedeploy"
      confidence: "high"
      evidence:
        - type: "codedeploy_application"
          detail: "Application 'AppECS-prod-cluster-api-service' with ECS compute platform (no associated CodePipeline found)"
    - tool: "github_actions"
      confidence: "medium"
      evidence:
        - type: "resource_tag"
          detail: "Service tagged with 'github-actions-workflow: deploy.yml' (team convention)"
  undetermined: false
  error: null
```

### Workspace file detection unavailability

The local workspace may not be accessible during reconnaissance. This happens when:
- The skill is invoked without a repository checkout present
- The agent does not have filesystem access to the project directory
- The workspace does not contain CI/CD configuration (e.g., mono-repo with CI/CD in a different path)

**How to handle:**
- Treat workspace file detection as opportunistic — skip it silently if the workspace is not available
- Do NOT report an error or `unavailable` for this detection alone — other detection methods (CodePipeline, CodeDeploy, tags) may still succeed
- Do NOT report `undetermined: true` solely because workspace files could not be checked — only report undetermined when ALL detection methods yield no results
- If workspace detection is the ONLY method that would have found evidence (e.g., the only CI/CD is a Jenkinsfile with no resource tags), the result will correctly be `undetermined: true` — this is acceptable

### Tag-based evidence only

In some cases, resource tags are the only available evidence of CI/CD tooling. This happens when:
- The CI/CD tool is external to AWS (GitHub Actions, GitLab CI, Jenkins) and does not leave AWS service traces
- CodePipeline and CodeDeploy are not used
- Workspace files are unavailable

**How to handle:**
- Tag-based evidence alone is sufficient to report a detected CI/CD tool — do not require multiple evidence types
- Report the specific tag key and value that triggered the detection
- A single matching tag constitutes valid evidence, but cap the tool's `confidence` at `"medium"` — these tags are team conventions, not tool-emitted signatures

**Example (tag-only detection):**
```yaml
cicd:
  detected_tools:
    - tool: "gitlab_ci"
      confidence: "medium"
      evidence:
        - type: "resource_tag"
          detail: "Service 'worker-service' tagged with 'gitlab-ci-pipeline-id: 123456' (team convention)"
  undetermined: false
  error: null
```

### API access denied for CodePipeline or CodeDeploy

If `codepipeline:ListPipelines` or `codedeploy:ListApplications` returns an access-denied error:

**How to handle:**
- Do NOT fail the entire CI/CD detection module
- Skip the affected detection step and continue with remaining methods (tags, workspace files)
- If all AWS API detection steps fail but tag or workspace detection succeeds → report detected tools normally
- If all detection methods fail or are inaccessible → report `undetermined: true`
- Record the access-denied error in the `error` field for visibility but do not block other detections

**Example (partial detection with API errors):**
```yaml
cicd:
  detected_tools:
    - tool: "github_actions"
      confidence: "medium"
      evidence:
        - type: "resource_tag"
          detail: "Service tagged with 'github-actions-workflow: deploy.yml' (team convention)"
  undetermined: false
  error: "codepipeline:ListPipelines returned AccessDeniedException — CodePipeline detection skipped"
```

### No CI/CD detected

When no detection method finds any CI/CD evidence:

**How to handle:**
- Set `undetermined: true` and `detected_tools: []`
- This is a valid outcome — not every ECS environment has discoverable CI/CD tooling
- Common reasons: manual deployments via console, custom scripts without tagging, CI/CD system not detectable by read-only queries

**Example:**
```yaml
cicd:
  detected_tools: []
  undetermined: true
  error: null
```

---

## Sources

- https://docs.aws.amazon.com/codepipeline/latest/userguide/action-reference-ECS.html (ECS standard deploy action — provider `ECS`, `ClusterName`/`ServiceName` configuration)
- https://docs.aws.amazon.com/codepipeline/latest/userguide/action-reference-ECSbluegreen.html (blue/green deploy action — provider `CodeDeployToECS`, `ApplicationName`/`DeploymentGroupName` configuration)
- https://docs.aws.amazon.com/codedeploy/latest/APIReference/API_ApplicationInfo.html (`computePlatform` valid values: `Server | Lambda | ECS | Kubernetes`)
- https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_ListTagsForResource.html (tag retrieval for ECS clusters and services)
- https://awscli.amazonaws.com/v2/documentation/api/latest/reference/deploy/index.html (CodeDeploy CLI service command is `deploy`)
