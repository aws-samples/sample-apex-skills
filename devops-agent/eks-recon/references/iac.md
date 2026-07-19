# Module: IaC (Infrastructure as Code)

> **Part of:** [eks-recon](../SKILL.md)
> **Purpose:** Detect IaC tooling - Terraform, CloudFormation, CDK, eksctl, Crossplane, ACK

## Table of Contents

- [Access Model](#access-model)
- [Detection Strategy](#detection-strategy)
- [Detection Capabilities](#detection-capabilities)
  - [1. Tag-Based Detection (AWS API)](#1-tag-based-detection-aws-api)
  - [2. eksctl Tag Detection (AWS API)](#2-eksctl-tag-detection-aws-api)
  - [3. Crossplane and ACK Detection (Kubernetes API)](#3-crossplane-and-ack-detection-kubernetes-api)
- [Output Schema](#output-schema)
- [Confidence Determination](#confidence-determination)
- [Edge Cases](#edge-cases)

---

## Access Model

This reference reads facts from two sources, both read-only:

- **AWS control-plane APIs** (EKS) — cluster tags via `describe-cluster`, used to infer the
  managing IaC tool (Terraform, CloudFormation, CDK, eksctl). Requires the read-only
  permissions in `references/iam-policy.json`.
- **Kubernetes API** (via the Agent Space EKS access entry) — in-cluster IaC control planes
  (Crossplane compositions/CRDs, ACK `services.k8s.aws` CRDs). Requires `authenticationMode`
  to include `API` and the `AmazonAIOpsAssistantPolicy` access entry to be present. RBAC verbs
  needed: `get`, `list`.

**Honest limitation — workspace-file IaC detection is NOT available in the Agent Space.** The
Claude Code version of this module scans a local repository filesystem (`.tf`, CFN
`.yaml`/`.json`, `cdk.json`, `Pulumi.yaml`, eksctl `ClusterConfig`, etc.) to detect IaC. The
DevOps Agent has **no shell and no filesystem access** — there is no repo to scan. IaC
detection here is therefore limited to **live-cluster signals only**:

- **cluster tags** (AWS API) — Terraform/CloudFormation/CDK/eksctl tag stamps, and
- **in-cluster CRDs** (Kubernetes API) — Crossplane and ACK control planes.

Terraform module source/version, state backend, tfvars, CFN template paths, CDK/Pulumi
project files, and eksctl config files cannot be observed without the repository, so those
`workspace.*` sub-facts are recorded as `unconfirmed` in the report's Coverage section — never
as `false`. State this limitation in the report so a null IaC result is not misread as
"no IaC exists".

If the Kubernetes API is unreachable (access entry absent), report the AWS-API tag facts and
mark the Crossplane/ACK sub-facts as `unconfirmed` — never as `false`.

> **Reference pseudocode note.** Code blocks labeled *reference pseudocode (kubernetes client)*
> below illustrate the resource, fields, and RBAC verbs for each K8s-API read. They are **not
> executable** in the Agent Space and are not an operational path — do not emit
> `kubectl ... | jq` pipelines. The agent reads these resources through its
> Kubernetes-API capability.

---

## Detection Strategy

Because there is no filesystem to scan, IaC detection runs against live-cluster signals only:

```
1. Cluster tags        -> Terraform / CloudFormation / CDK stamps (AWS API)
2. eksctl tag          -> alpha.eksctl.io/cluster-name (AWS API)
3. Crossplane / ACK    -> in-cluster CRDs (Kubernetes API)
```

**Confidence scoring (evidence-strength metadata, not a verdict):**
- **High**: in-cluster CRDs present (Crossplane/ACK), or a definitive tool tag (`aws:cloudformation:stack-id`, `alpha.eksctl.io/cluster-name`)
- **Medium**: generic managed-by tag present (e.g. `managed-by: terraform`)
- **Low**: only weak/ambiguous tag hints suggest an IaC tool
- **Unknown**: no live-cluster evidence found (workspace files would be the missing corroboration — unavailable in Agent Space)

---

## Detection Capabilities

### 1. Tag-Based Detection (AWS API)

IaC tools often stamp identifying tags on the resources they create. Read the cluster tags and
match against known tool signatures.

**Via AWS API** — read cluster tags:
```bash
aws eks describe-cluster --name <cluster-name> --region <region> \
  --query 'cluster.tags' --output json
```

**Example output (Terraform-managed cluster):**
```json
{
    "Environment": "production",
    "terraform": "true",
    "managed-by": "terraform"
}
```

**Example output (CloudFormation-managed cluster):**
```json
{
    "aws:cloudformation:stack-name": "eks-production-cluster",
    "aws:cloudformation:stack-id": "arn:aws:cloudformation:us-west-2:123456789012:stack/eks-production-cluster/abc123",
    "aws:cloudformation:logical-id": "EKSCluster"
}
```

**Common IaC tags:**
- Terraform: `terraform`, `tf-*`, `managed-by: terraform`
- CloudFormation: `aws:cloudformation:stack-name`, `aws:cloudformation:stack-id`
- CDK: `aws:cdk:*`
- Pulumi: `pulumi:*`

Record `tags.terraform_managed: bool` and `tags.cfn_stack_id` (the `aws:cloudformation:stack-id`
value, or `null` if absent). Add each tag-evidenced tool to `tools_detected`.

### 2. eksctl Tag Detection (AWS API)

eksctl stamps clusters with the `alpha.eksctl.io/cluster-name` tag.

**Via AWS API** — read the eksctl tag:
```bash
aws eks describe-cluster --name <cluster-name> --region <region> \
  --query 'cluster.tags."alpha.eksctl.io/cluster-name"' --output text
```

Presence of `alpha.eksctl.io/cluster-name` (value equals the cluster name) ⇒ record
`tags.eksctl_created: true` and add `eksctl` to `tools_detected`. Absence returns `None` ⇒
`tags.eksctl_created: false`.

### 3. Crossplane and ACK Detection (Kubernetes API)

Detect in-cluster IaC control planes. Crossplane and AWS Controllers for Kubernetes (ACK)
manage AWS infrastructure from inside the cluster via CRDs, often applied through GitOps.

**Via Kubernetes API** — detect Crossplane:

- **Resource:** `Composition`, group/version `apiextensions.crossplane.io/v1`; and
  `CompositeResourceDefinition` (XRD), same group. Also enumerate CRDs
  (`CustomResourceDefinition`, `apiextensions.k8s.io/v1`) and match names under `crossplane.io`.
- **Fields to extract:** presence/count of Compositions and XRDs; matched `crossplane.io` CRD names.
- **RBAC verbs:** `get`, `list` on `compositions.apiextensions.crossplane.io`,
  `compositeresourcedefinitions.apiextensions.crossplane.io`, and `customresourcedefinitions.apiextensions.k8s.io`.

**Via Kubernetes API** — detect ACK:

- **Resource:** `CustomResourceDefinition`, group/version `apiextensions.k8s.io/v1`, matched by
  CRD group suffix `services.k8s.aws` (e.g. `eks.services.k8s.aws`, `iam.services.k8s.aws`).
- **Fields to extract:** matched `services.k8s.aws` CRD groups.
- **RBAC verbs:** `get`, `list` on `customresourcedefinitions.apiextensions.k8s.io`.

Record `crossplane.detected: bool` (compositions or `crossplane.io` CRDs present) and
`ack.detected: bool` (any `services.k8s.aws` CRD present). For ACK, record the matched CRD
groups in `ack.controllers`. Add `Crossplane` / `ACK` to `tools_detected` when present.

*Reference pseudocode (kubernetes client), not executable:*
```python
apiext = client.ApiextensionsV1Api()
custom = client.CustomObjectsApi()

crds = [c.metadata.name for c in apiext.list_custom_resource_definition().items]
crossplane_crds = [n for n in crds if n.endswith("crossplane.io")]
ack_groups = sorted({n.split(".", 1)[1] for n in crds if ".services.k8s.aws" in n})

comps = custom.list_cluster_custom_object(
    "apiextensions.crossplane.io", "v1", "compositions")
crossplane_detected = bool(comps["items"]) or bool(crossplane_crds)
ack_detected = bool(ack_groups)
```

---

## Output Schema

This is the **single canonical schema** for the IaC module — it carries every IaC fact
(plus the shared `cluster:` block from `references/cluster-basics.md`). Use `null` where a
fact was not detected; never omit a key. Where a fact could not be checked (workspace files
in Agent Space, or Kubernetes API unreachable), record it as `unconfirmed` in the report's
Coverage section rather than emitting a misleading `false`.

```yaml
iac:
  tools_detected: list    # ALL IaC tools with evidence, flat — no "primary". e.g. ["terraform","cdk"]
                          # (Terraform | CloudFormation | CDK | eksctl | Pulumi | Crossplane | ACK | CLI | unknown)
  confidence: string      # high | medium | low — evidence-strength metadata (fact), not a verdict
  evidence:               # object form (canonical)
    type: string          # cluster_tags | in_cluster_crds
    details: string       # what was found (tags / CRD groups / reason for determination)

  workspace:
    # NOTE: workspace-file detection is UNAVAILABLE in the Agent Space (no filesystem).
    # The per-tool sub-facts below that require reading repository files (Terraform module
    # source/version/state_backend, CFN template paths, CDK/Pulumi/eksctl config files) are
    # recorded as `unconfirmed` in the report's Coverage section — never as false.
    # Terraform / OpenTofu
    terraform:
      detected: bool          # from tags only (managed-by/terraform tag); workspace files unconfirmed
      files: list             # unconfirmed — no filesystem in Agent Space
      module_source: string   # unconfirmed — requires repository access
      module_version: string  # unconfirmed — requires repository access
      state_backend: string   # unconfirmed — requires repository access
      opentofu_detected: bool # unconfirmed — requires repository access

    # CloudFormation
    cloudformation:
      detected: bool          # from tags (aws:cloudformation:*); template paths unconfirmed
      templates: list         # unconfirmed — no filesystem in Agent Space
      stack_name: string      # from aws:cloudformation:stack-name tag, null if absent

    # CDK
    cdk:
      detected: bool          # from tags (aws:cdk:*); project files unconfirmed
      language: string        # unconfirmed — requires repository access
      cdk_json_path: string   # unconfirmed — requires repository access

    # eksctl
    eksctl:
      detected: bool          # from alpha.eksctl.io/cluster-name tag
      config_files: list      # unconfirmed — no filesystem in Agent Space

    # Pulumi
    pulumi:
      detected: bool          # from tags (pulumi:*); project files unconfirmed
      project_path: string    # unconfirmed — requires repository access
      language: string        # unconfirmed — requires repository access

    # Crossplane (in-cluster control plane) — detectable via Kubernetes API
    crossplane:
      detected: bool

    # AWS Controllers for Kubernetes (ACK) — detectable via Kubernetes API
    ack:
      detected: bool
      controllers: list       # matched services.k8s.aws CRD groups, e.g. ["eks.services.k8s.aws"]

  tags:
    terraform_managed: bool
    eksctl_created: bool      # alpha.eksctl.io/cluster-name tag present
    cfn_stack_id: string      # aws:cloudformation:stack-id tag, null if absent
```

---

## Confidence Determination

| Scenario | Confidence | Reasoning |
|----------|------------|-----------|
| In-cluster CRDs present (Crossplane/ACK) | High | Direct live evidence via Kubernetes API |
| Definitive tool tag (`aws:cloudformation:stack-id`, `alpha.eksctl.io/cluster-name`) | High | Tool stamped the cluster itself |
| Generic managed-by tag (e.g. `managed-by: terraform`) | Medium | Tags can be manually added; workspace files unavailable to corroborate |
| Only weak/ambiguous tag hints | Low | Tags can be manually added |
| No live-cluster evidence found | Unknown | Might be CLI-created, or IaC exists in a repo the Agent cannot scan |

---

## Edge Cases

### Multiple IaC Tools Detected

If multiple tools are evidenced (e.g., Terraform tag + ACK CRDs):
- Report ALL detected tools flatly in `tools_detected` — do not pick a "primary" or rank them
  by likelihood. Presence of each tool's evidence is the fact.
- Each tool's per-tool `detected` flag and evidence appear in `workspace`.

### Workspace Files Not Observable

The Agent Space has no filesystem, so repository-based IaC (Terraform `.tf`, CFN templates,
CDK/Pulumi projects, eksctl configs) cannot be scanned. A null `workspace.*` file fact means
"not observable here", not "no IaC". Record these as `unconfirmed` in the Coverage section and
state the limitation in the report.

### GitOps-Managed IaC

IaC may be applied via GitOps (ArgoCD/Flux deploying Crossplane or ACK). This is detected by
capability 3 (Crossplane and ACK Detection): record `workspace.crossplane.detected` /
`workspace.ack.detected` and add `Crossplane` / `ACK` to `tools_detected` when present.

### No IaC (CLI-Created)

If no live-cluster IaC evidence is found:
- Cluster may have been created via `aws eks create-cluster` or console, OR the IaC lives in a
  repository the Agent cannot scan.
- Record `tool: CLI/Console` as a fact (no IaC evidence detected in-cluster). State the fact
  only; draw no conclusion, and note that workspace-file corroboration is unavailable.
