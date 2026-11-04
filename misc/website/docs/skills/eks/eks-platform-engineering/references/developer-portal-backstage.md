---
title: "Developer Portal — Backstage"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-platform-engineering/references/developer-portal-backstage.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-platform-engineering/references/developer-portal-backstage.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-platform-engineering/references/developer-portal-backstage.md). Edit the source, not this page.
:::

# Developer Portal — Backstage

Backstage is the platform's front door: a self-service catalog plus software templates (the "scaffolder"). Developers interact with the platform here and rarely touch raw Kubernetes or AWS.

## Why Backstage

- Open-source, CNCF, plugin-based — extensible without forking.
- Software Templates encode golden paths with parameters and guardrails.
- Service Catalog gives a single pane of glass (components, APIs, docs, owners).
- Integrates with Keycloak SSO so it shares identity with every other tool.

## Anatomy of a software template

A Backstage template is a folder:

```
my-template/
├── template.yaml          # definition: parameters + steps (actions)
└── skeleton/              # scaffolded files, rendered with parameter values
    ├── catalog-info.yaml  # registers the new component in the catalog
    └── manifests/         # e.g. an OAM Application or ACK manifest
```

- **`template.yaml`** declares the form parameters the developer fills, then the ordered **steps/actions**: fetch skeleton → publish to Git → register in ArgoCD/catalog → trigger provisioning.
- **`skeleton/`** is the payload: the manifests and `catalog-info.yaml` that get committed to a new Git repo, rendered with the developer's parameter values.

## Worked example: environment template (illustrative)

Illustrative, not a drop-in: hosts, names and the `EKSCluster` spec fields are placeholders, and the fields must match the platform team's own kro `ResourceGraphDefinition` schema. It assumes the GitLab scaffolder module (`@backstage/plugin-scaffolder-backend-module-gitlab`) is installed and `integrations.gitlab` in `app-config.yaml` lists `gitlab.example.com` with a token.

```yaml
# template.yaml
apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata:
  name: eks-environment
  title: EKS environment
  description: VPC + EKS Auto Mode cluster + add-ons, synced by the hub ArgoCD
spec:
  owner: group:platform-team
  type: environment
  parameters:
    - title: Environment
      required: [name, owner, environment, region]
      properties:
        name:
          title: Cluster name
          type: string
        owner:
          title: Owner
          type: string
          ui:field: OwnerPicker
          ui:options:
            catalogFilter:
              kind: Group
        environment:
          title: Environment
          type: string
          enum: [dev, prod]
        region:
          title: AWS Region
          type: string
          default: us-west-2
    - title: Repository
      required: [repoUrl]
      properties:
        repoUrl:
          title: Repository location
          type: string
          ui:field: RepoUrlPicker
          ui:options:
            allowedHosts: [gitlab.example.com]
  steps:
    - id: fetch
      name: Render skeleton
      action: fetch:template
      input:
        url: ./skeleton
        values:
          name: ${{ parameters.name }}
          owner: ${{ parameters.owner }}
          environment: ${{ parameters.environment }}
          region: ${{ parameters.region }}
    - id: publish
      name: Publish to GitLab
      action: publish:gitlab
      input:
        repoUrl: ${{ parameters.repoUrl }}
        defaultBranch: main
    - id: register
      name: Register in catalog
      action: catalog:register
      input:
        repoContentsUrl: ${{ steps.publish.output.repoContentsUrl }}
        catalogInfoPath: /catalog-info.yaml
  output:
    links:
      - title: Repository
        url: ${{ steps.publish.output.remoteUrl }}
      - title: Open in catalog
        icon: catalog
        entityRef: ${{ steps.register.output.entityRef }}
```

The kro instance the skeleton carries beside its `catalog-info.yaml` (`skeleton/manifests/ekscluster.yaml`; a kro instance's `apiVersion` is `kro.run/` plus the RGD schema's `apiVersion`):

```yaml
apiVersion: kro.run/v1alpha1
kind: EKSCluster
metadata:
  name: ${{ values.name }}
  namespace: platform-environments
spec:
  name: ${{ values.name }}
  environment: ${{ values.environment }}
  region: ${{ values.region }}
```

The hub ArgoCD syncs the new repo (for example through an ApplicationSet SCM Provider generator over the platform's GitLab group); kro then creates what the platform's `EKSCluster` RGD declares (for example the cluster, add-on IAM and a GitOps Bridge cluster secret), and the hub `ApplicationSet` in `idp-architecture.md` installs the add-ons from that secret, so the secret must carry the `enable_` labels and `addons_repo_*` annotations that `ApplicationSet` reads.

## The self-service flow (every template follows this shape)

```
Developer fills Backstage form
   → template creates a new GitLab repo with rendered skeleton (manifests)
   → registers the repo/app in the catalog; ArgoCD picks it up (a template step or a hub generator)
   → ArgoCD syncs the manifests to the target cluster
   → controllers reconcile (KubeVela renders the app; ACK provisions AWS resources)
```

This is the same loop whether the artifact is an AWS resource (ACK manifest), an environment (kro composition), a CI/CD pipeline (kro `CICDPipeline`), or an ML serving endpoint (Ray Serve manifest). One repo per provisioned component is the default — it keeps GitOps reconciliation and ownership clean.

## Opinionated template conventions

- **Guardrails via fixed parameters / configuration tiers.** Pre-define profiles (e.g. an S3 "standard" config) so developers pick a vetted option rather than free-typing settings.
- **Namespace + region as parameters** with sensible defaults (e.g. `us-west-2`, team namespace).
- **Templates reference cluster-side definitions.** A template emits an OAM `Application` that references a `type` (e.g. `ddb-table`) whose component definition the platform team owns — the template is just the friendly form over it.
- **Register via `catalog-info.yaml`** so the new component appears in the catalog with its owner, links (source repo, ArgoCD app, dashboards), and docs.

## Catalog as the operational hub

Once registered, a component's catalog page links its source repo, its ArgoCD application (sync/health), its dashboards, and (for ML/data) execution details (Spark runs, Argo Workflow pipelines). This gives developers troubleshooting visibility without cluster access — directly answering the "fixing problems" adoption challenge.

## Generating templates with GenAI

**Kiro** (AWS's spec-driven agentic tool, the successor to Amazon Q Developer) can scaffold a whole new template from an existing one (e.g. "use the S3 template to make a DynamoDB template"). Pattern: point the agent at a reference template + the target resource's CRD/composition schema, generate, then `diff` against a validated version before registering. See `genai-platform-engineering.md`.
