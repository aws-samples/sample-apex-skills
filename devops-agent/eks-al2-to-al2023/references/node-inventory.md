# Module: Node Inventory (AL2 footprint)

> **Part of:** [eks-al2-to-al2023](../SKILL.md)
> **Purpose:** Detect which nodes and node groups are on Amazon Linux 2 (AL2) vs Amazon Linux 2023 (AL2023), broken down by compute type, and capture the per-node-group launch-template and AMI facts that scope every later migration-risk check

This is the **first** module loaded. It establishes the **AL2 footprint** — the set of
node groups and nodes that still run the AL2 EKS-optimized AMI — which is the scope every
risk (`migration-risks.md`) and runbook path (`runbook.md`) narrows to. It reads facts only;
it never cordons, drains, or changes a node group.

## Table of Contents

- [Access Model](#access-model)
- [Detection Strategy](#detection-strategy)
- [Detection Capabilities](#detection-capabilities)
  - [1. Managed Node Group AMI Type](#1-managed-node-group-ami-type)
  - [2. Instance AMI Names (self-managed + verification)](#2-instance-ami-names-self-managed--verification)
  - [3. Launch Templates](#3-launch-templates)
  - [4. Node OS via Kubernetes API](#4-node-os-via-kubernetes-api)
  - [5. Karpenter / Auto Mode AMI family (CRD note)](#5-karpenter--auto-mode-ami-family-crd-note)
  - [6. JDK version signals (Java workloads)](#6-jdk-version-signals-java-workloads)
  - [7. Why is the AMI custom? (rebuild-complexity triage)](#7-why-is-the-ami-custom-rebuild-complexity-triage)
- [Lifting the limitation (supplementary ClusterRole)](#lifting-the-limitation-supplementary-clusterrole)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Access Model

This module reads facts from two sources, both read-only:

- **AWS control-plane APIs** (EKS + EC2) — node-group `amiType` / `releaseVersion` /
  `launchTemplate` (`eks:DescribeNodegroup`), running instance AMI IDs and their names
  (`ec2:DescribeInstances` → `ec2:DescribeImages`), and launch-template `ImageId` / userData /
  IMDS settings (`ec2:DescribeLaunchTemplates`, `ec2:DescribeLaunchTemplateVersions`). These
  require the read-only permissions in `references/iam-policy.json`. **All AL2-vs-AL2023
  detection for managed and self-managed node groups is possible via the AWS API alone.**
- **Kubernetes API** (via the Agent Space EKS access entry) — per-node `status.nodeInfo`
  (`osImage`, `kernelVersion`, `containerRuntimeVersion`) and node labels. Requires
  `authenticationMode` to include `API` and the `AmazonAIOpsAssistantPolicy` access entry to
  be present. RBAC verbs needed: `get`, `list` on `nodes`.

If the Kubernetes API is unreachable (access entry absent, or `authenticationMode` excludes
`API`), report whatever the AWS-API calls return — node-group `amiType`, instance AMI names,
launch-template facts — and mark every K8s-dependent sub-fact (per-node `osImage` /
`kernelVersion`, labels) as `unconfirmed` in the report's Coverage section, **never** as
`false` or a false AL2023-clean reading.

> **Reference declarative note.** The "**Via Kubernetes API**" blocks below describe the
> resource, group/version, fields, and RBAC verbs for each K8s-API read. They are **not**
> executable `kubectl ... | jq` pipelines and are not an operational path — the agent reads
> these resources through its Kubernetes-API capability, then applies the described
> classification logic. The "**Via AWS API**" blocks may show example `aws ...` calls.

---

## Detection Strategy

AL2-footprint detection layers three independent signals so no compute type is missed:

```
1. MNG amiType        -> authoritative AL2/AL2023 label for managed node groups
2. Instance AMI name  -> catches self-managed nodes with no node-group amiType
3. Node osImage/kernel -> in-cluster confirmation across ALL nodes (any compute type)
   + Launch templates  -> custom LT? -> drives nodeadm/bootstrap + IMDS risk in module 2
   + Karpenter/AutoMode -> AMI family lives in a CRD (may be 403 -> unconfirmed)
   + JDK signals (§6)  -> Java cgroup-v2 heap-sizing risk (weak; workload-level, operator-verify)
```

Signals 1-3 (+ LT / Karpenter) are the **OS-family** map. Signal 6 (JDK version signals, §6) is
a **separate, workload-level** risk signal — it does **not** classify node OS; it scopes the
cgroup-v2 Java risk in `migration-risks.md` Risk 1.

The three OS-family signals are cross-checked: a node group whose `amiType` says AL2 should have
instances on an `amazon-eks-node-*` AMI and nodes whose `osImage` contains `Amazon Linux 2`.
When signals disagree (e.g. a custom AMI baked from AL2023 attached to a node group whose
`amiType` still reads `CUSTOM`), report each signal as its own fact and mark the AMI family
`unconfirmed` rather than forcing a label.

---

## Detection Capabilities

### 1. Managed Node Group AMI Type

The authoritative AL2/AL2023 label for a managed node group (MNG) is its `amiType`.

**Via AWS API** — list node groups, then describe each for `amiType`, `releaseVersion`, and
`launchTemplate`:

```bash
# List managed node groups for the cluster
aws eks list-nodegroups --cluster-name <cluster-name> \
  --query 'nodegroups' --output text

# Describe each node group
aws eks describe-nodegroup --cluster-name <cluster-name> --nodegroup-name <ng-name> \
  --query 'nodegroup.{amiType:amiType,releaseVersion:releaseVersion,launchTemplate:launchTemplate,instanceTypes:instanceTypes,capacityType:capacityType,status:status}'
```

**`amiType` → OS family mapping:**

| `amiType` value | OS family |
|-----------------|-----------|
| `AL2_x86_64` | **AL2** |
| `AL2_ARM_64` | **AL2** |
| `AL2_x86_64_GPU` | **AL2** |
| `AL2023_x86_64_STANDARD` | **AL2023** |
| `AL2023_ARM_64_STANDARD` | **AL2023** |
| the AL2023 NVIDIA GPU amiType | **AL2023** |
| `BOTTLEROCKET_*` | Bottlerocket (out of AL2→AL2023 scope — see Edge Cases) |
| `CUSTOM` | unknown from `amiType` alone → resolve via the launch-template `ImageId` (section 3) + instance AMI name (section 2); mark `unconfirmed` if still unresolved |

> **UNVERIFIED — AL2023 NVIDIA GPU amiType enum spelling.** The exact enum string AWS uses
> for the AL2023 NVIDIA GPU AMI type (the AL2023 successor to `AL2_x86_64_GPU`) is **not
> verified here**. Do **not** hardcode a guessed value such as `AL2023_x86_64_NVIDIA`. Read
> the `amiType` string **verbatim** from `DescribeNodegroup` and classify any value that
> begins with `AL2023` as AL2023. Record the observed enum string as a fact.

- `releaseVersion` records the specific EKS AMI release the node group is pinned to (a fact;
  useful evidence for the report). For AL2 node groups this is an AL2 release that AWS stopped
  publishing new versions of on 2025-11-26 — see `migration-risks.md`.
- `launchTemplate` (present/absent, id, version) drives the nodeadm/bootstrap and IMDS
  hop-limit risks in `migration-risks.md`; capture it here and resolve its contents in
  section 3.

**Example (one AL2 node group):**
```json
{
  "amiType": "AL2_x86_64",
  "releaseVersion": "1.32.0-20251101",
  "launchTemplate": null,
  "instanceTypes": ["m5.large"],
  "capacityType": "ON_DEMAND",
  "status": "ACTIVE"
}
```

### 2. Instance AMI Names (self-managed + verification)

Self-managed node groups have **no** node-group `amiType`. Their OS family is read from the
AMI backing the running instances. This also cross-checks MNG results.

**Via AWS API** — find the cluster's instances by cluster tag, collect their AMI IDs, then
resolve each AMI's Name:

```bash
# Instances tagged for this cluster (self-managed + MNG nodes both carry the tag)
aws ec2 describe-instances \
  --filters "Name=tag:kubernetes.io/cluster/<cluster-name>,Values=owned,shared" \
            "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].{InstanceId:InstanceId,ImageId:ImageId,Lt:Tags[?Key==`aws:ec2launchtemplate:id`].Value|[0]}'

# Resolve AMI names
aws ec2 describe-images --image-ids <ami-id-1> <ami-id-2> \
  --query 'Images[].{ImageId:ImageId,Name:Name}'
```

**AMI Name → OS family mapping (EKS-optimized AMIs):**

| AMI Name pattern | OS family |
|------------------|-----------|
| `amazon-eks-node-<k8s>-*` (no `al2023`) | **AL2** |
| `amazon-eks-arm64-node-*`, `amazon-eks-gpu-node-*` | **AL2** |
| `amazon-eks-node-al2023-*` | **AL2023** |
| `bottlerocket-aws-k8s-*` | Bottlerocket (out of scope) |

- This signal **catches self-managed nodes** that never appear as an MNG `amiType`, and
  custom AMIs whose Name still follows the EKS-optimized naming.
- A custom-baked AMI with a non-standard Name resolves to neither pattern → record the AMI
  Name as a fact and mark the OS family `unconfirmed` (do not guess).

### 3. Launch Templates

Whether a node group uses a **custom launch template** — and whether that template pins an
`ImageId` — is the single biggest driver of migration effort: it decides the
nodeadm/NodeConfig userData rewrite and the IMDS hop-limit default (both in
`migration-risks.md`).

**Via AWS API** — read the launch template and the specific version the node group uses:

```bash
aws ec2 describe-launch-templates --launch-template-ids <lt-id> \
  --query 'LaunchTemplates[].{Id:LaunchTemplateId,Name:LaunchTemplateName,Default:DefaultVersionNumber,Latest:LatestVersionNumber}'

aws ec2 describe-launch-template-versions --launch-template-id <lt-id> --versions <version> \
  --query 'LaunchTemplateVersions[].LaunchTemplateData.{ImageId:ImageId,UserData:UserData,Metadata:MetadataOptions}'
```

- **`ImageId`** — if set, the template pins a specific AMI. Resolve its Name via
  `ec2:DescribeImages` (section 2 mapping) to classify AL2/AL2023. If absent, EKS supplies
  the AMI from the node group `amiType`.
- **`UserData`** — base64-encoded. When it contains `/etc/eks/bootstrap.sh`, this is AL2-style
  bootstrap that must be rewritten to nodeadm `NodeConfig` for AL2023 (see
  `migration-risks.md` → nodeadm/bootstrap). Record its presence as a fact; do not decode and
  emit secrets.
- **`MetadataOptions.HttpPutResponseHopLimit`** — records the IMDS hop limit set on the
  template (evidence for the IMDS risk). When the template does not set it, the default
  depends on whether a custom AMI is used — see `migration-risks.md` → IMDSv2 hop limit.

### 4. Node OS via Kubernetes API

In-cluster confirmation across **all** nodes regardless of compute type (MNG, self-managed,
Karpenter, Auto Mode). This confirms the AWS-API labels and is the only direct signal for
Karpenter/Auto Mode nodes when their CRDs are unreadable.

**Via Kubernetes API** — list nodes and read OS/runtime facts and identifying labels:

- **Resource:** `Node`, group/version `v1` (core), cluster-scoped.
- **Fields to extract:**
  - `status.nodeInfo.osImage` — **AL2** when it contains `Amazon Linux 2` **and NOT** `2023`
    (e.g. `Amazon Linux 2`); **AL2023** when it contains `Amazon Linux 2023`.
  - `status.nodeInfo.kernelVersion` — **AL2** when it contains `amzn2` (AL2 ships kernel
    `5.10`, string contains `amzn2`); **AL2023** kernels are `6.1` / `6.12` (string contains
    `amzn2023`). (Matches the upstream `eks-upgrade-check` node-readiness detection.)
  - `status.nodeInfo.containerRuntimeVersion` — records the containerd version (a fact).
  - `metadata.labels` — `eks.amazonaws.com/nodegroup` (MNG membership),
    `karpenter.sh/nodepool` (Karpenter-owned), `node.kubernetes.io/instance-type`. Use the
    label to attribute each node to a compute type.
- **RBAC verbs:** `get`, `list` on `nodes`.

**Classification precedence:** `osImage` and `kernelVersion` must agree; when both are
present and agree, that is the authoritative in-cluster OS family for the node. A node with no
`eks.amazonaws.com/nodegroup` label and no `karpenter.sh/nodepool` label is **self-managed**
(reconcile with sections 1–2). Nodes attributed to Karpenter/Auto Mode still get their OS
family from `osImage`/`kernelVersion` here even when the driving CRD (section 5) is 403.

### 5. Karpenter / Auto Mode AMI family (CRD note)

For Karpenter- and Auto-Mode-provisioned compute, the **desired** AMI family is declared in a
CustomResourceDefinition, not in a node-group `amiType`:

- **Karpenter `EC2NodeClass`** — group `karpenter.k8s.aws`; the `spec.amiFamily` /
  `spec.amiSelectorTerms` decide whether new nodes come up on AL2 or AL2023.
- **EKS Auto Mode `NodeClass`** — group `eks.amazonaws.com`; declares the managed AMI family.

**CRD read constraint.** Under the `AmazonAIOpsAssistantPolicy` access entry **alone**, these
CRD groups are **not** authorized — reads of `karpenter.k8s.aws`, `karpenter.sh`, and
`eks.amazonaws.com` return `403 Forbidden` (the managed policy grants only built-in API
groups; see SKILL.md § Kubernetes API Access). When the CRD read is blocked:

- Report the Karpenter/Auto-Mode desired AMI family as **`unconfirmed`** — never guess
  `AL2` or `AL2023`, and never record `false`.
- You may still classify the **running** Karpenter/Auto-Mode nodes' OS from
  `status.nodeInfo.osImage` / `kernelVersion` (section 4) — that is a separate, allowed
  signal. Report "N Karpenter nodes currently on AL2 (from node osImage); EC2NodeClass AMI
  family unconfirmed (CRD read blocked)". Distinguish the confirmed running-OS fact from the
  unconfirmed desired-AMI fact.
- To confirm the desired AMI family, a supplementary read-only ClusterRole granting
  `get`/`list` on those CRD groups is required (see SKILL.md).

**Fargate** — Fargate pods run on AWS-managed infrastructure with **no** customer AL2/AL2023
node AMI. **Fargate has no AL2 concern** — state this as a fact and exclude Fargate profiles
from the migration scope entirely.

### 6. JDK version signals (Java workloads)

The cgroup-v2 heap-sizing bug (`migration-risks.md` Risk 1) hits **JDK 8 before `8u372`** and
**JDK 11 before `11.0.16`**, so knowing which Java workloads run — and, where possible, their
JDK build — scopes that risk. A bare major-version tag (`:8` **or** `:11`) hides the sub-build
and so can never clear the risk on its own. This
section reads **signals** only; it does **not** run `java -version`, exec into any container, or
open a node shell. It classifies each Java workload as **at-risk-needs-operator-verify**,
**not-at-risk-newer-jdk**, or **unconfirmed** — it never guesses an exact build from a tag and
calls it confirmed.

> **Cardinal rule — absence of a *detectable signal* is NOT absence of Java.** A Java app can
> run inside an opaque/custom image with no JDK tag, no `JAVA_*` env in the manifest, and no
> readable JDK hint. When Java can neither be confirmed nor ruled out from the readable signals
> below, the classification is **`unconfirmed`** — **never** `does-not-apply` or a "clean"
> reading. This skill's RBAC cannot see inside the image, so silence is not safety.

> **.NET is a MANUAL review flag, NOT a detection output.** This section and the
> `java_workloads` schema detect **Java only**. `.NET` cgroup-v2 exposure is surfaced as a
> manual review flag in `migration-risks.md` Risk 1 and `runbook.md` Phase 0 — there is **no**
> `.NET` detection output here and no `.NET` counter. Do not claim `.NET` was detected or
> cleared; the operator reviews .NET runtimes by hand.

**Via Kubernetes API** — enumerate workload PodSpecs and read the Java-relevant fields:

- **Resource:** `Pod`, group/version `v1` (core), all namespaces; and `Deployment` /
  `DaemonSet` / `StatefulSet`, group/version `apps/v1`, all namespaces.
- **Fields to extract (all from the PodSpec — no exec):**
  - `spec.containers[].image` (and `spec.initContainers[].image`) — the image **ref + tag**.
    A `:8`, `:8-jre`, `:8uNNN`, `openjdk:8`, `eclipse-temurin:8`, or `amazoncorretto:8` tag
    signals **JDK 8** — but the tag is a **weak** signal: it may omit the sub-build (`:8` says
    nothing about `8u362` vs `8u372`) or lie outright (a `:8` tag rebuilt on a newer patch).
  - `spec.containers[].env[]` — Java-relevant environment variables **only when declared inline
    as `spec.containers[].env[].value`** in the PodSpec: `JAVA_VERSION` (some base images set it
    — a stronger hint than the tag, still not the running build), `JAVA_TOOL_OPTIONS`,
    `JDK_JAVA_OPTIONS`, and any `-XX` flags carried in those vars or in
    `spec.containers[].args` / `command` (e.g. a pre-set `-XX:+UseContainerSupport`,
    `-XX:-UseContainerSupport`, `-XX:MaxRAMPercentage`, or a legacy `-Xmx` — all evidence for
    Risk 1's operator guidance).
    > **Readable env = inline manifest `env[].value` ONLY.** The core API exposes only env
    > literally declared as `spec.containers[].env[].value`. Env baked into the image via the
    > Dockerfile `ENV`, flags hard-coded in the image `ENTRYPOINT`/`CMD`, and any value resolved
    > from `valueFrom.configMapKeyRef` / `secretKeyRef` or `envFrom` are **INVISIBLE** to this
    > skill (its RBAC has no `secrets`/`configmaps` read). An image-baked `JAVA_VERSION`,
    > `JAVA_TOOL_OPTIONS`, `-XX` flag, or `-Xmx` therefore is **not visible → `unconfirmed`**,
    > **never** treated as "clean". This is why the tag/inline-env read is a weak, partial signal.
  - `spec.containers[].resources.limits.memory` — a Java container **with** a memory limit is
    the one exposed to the heap-sizing bug (cross-reference for Risk 1).
- **RBAC verbs:** `get`, `list` on `pods`, `deployments.apps`, `daemonsets.apps`,
  `statefulsets.apps`.

**The hard limit (state it honestly).** The **exact JDK build** (e.g. `8u362` vs `8u372`) is
**usually NOT determinable from control-plane reads alone** — confirming it would require
`java -version` on a running container (exec) or a node shell, which this skill **cannot and
must not** do. So the honest output for the build is **`jdk_version: unconfirmed`** with the
reason, **never** a guess derived from the image tag.

**Decision (per Java workload):**

| Signal read | Classification |
|-------------|----------------|
| Inline manifest tag or `env[].value` strongly indicates **JDK 8** (`:8`, `:8uNNN`, `openjdk:8`, `amazoncorretto:8`, `eclipse-temurin:8`, `JAVA_VERSION=8...`), **JDK 11 with an unknown sub-build** (a bare `:11`, `openjdk:11`, `amazoncorretto:11`, `eclipse-temurin:11`, `JAVA_VERSION=11` — the major-version tag reveals nothing about the `11.0.x` sub-build), **OR any JDK major version below 15 (8, 11, 12, 13, 14)** — none of these is cgroup-v2-aware at every build, and 12/13/14 predate the JDK 15 "aware at every sub-build" line | **at-risk-needs-operator-verify** — flag for Risk 1. For JDK 8 the operator confirms the build is `< 8u372`; for JDK 11 the operator confirms it is `>= 11.0.16` (the cgroup-v2-aware JDK 11 build — older 11.x mis-sizes the heap); for **JDK 12/13/14** the operator verifies cgroup-v2 behavior directly (these majors are `< 15` and their cgroup-v2 memory-limit handling cannot be assumed safe). All via `java -version` (see operator commands below). A bare `:11`/`:12`/`:13`/`:14` tag is **exactly as weak as `:8`**: it says nothing about the sub-build/behavior, so it must **never** land clean. |
| Inline manifest tag/`env[].value` strongly indicates a JDK that is cgroup-v2-aware at **every** sub-build — **JDK 15 or newer** (`>= 15`), including LTS **17** and **21** (`:17`, `:21`, `amazoncorretto:17`, `eclipse-temurin:21`, `JAVA_VERSION=17...`) | **not-at-risk-newer-jdk** — record as a fact. Only **JDK >= 15** qualifies: JDK 15+ is cgroup-v2-aware at every build (kubernetes.io "About cgroup v2", <https://kubernetes.io/docs/concepts/architecture/cgroups/> "15 and later", as of 2026-07-20). Not counted `at_risk` or `unconfirmed`. **Any JDK major `< 15` — 8, 11, 12, 13, 14 — does NOT qualify here** and takes the **at-risk** row above (JDK 11 only `11.0.16+` is aware, and a bare tag cannot prove that; 12/13/14 predate the JDK 15 line entirely). |
| Java can neither be confirmed nor ruled out from readable signals — opaque/custom image name AND no inline `JAVA_*` `env[].value` (env may be image-baked / `valueFrom` / `envFrom` → invisible) | **unconfirmed** — record the image ref as a fact; **never** emit an OS-free "clean"/`does-not-apply` reading off undetectable Java |

> **Conflicting signals — strongest wins, but a conflict never lands clean.** When an image
> major-version tag and an inline `env[].value` disagree (e.g. a `:8` image tag alongside
> `JAVA_VERSION=17`, or a `:11` tag alongside `JAVA_VERSION=8`), the inline `env[].value`
> sub-build/version is the **stronger** signal — it is set explicitly in the manifest, whereas
> the tag can be stale or rebuilt on a different build. But a conflict is itself a reason for
> caution: classify a conflicting pair as **at-risk-needs-operator-verify** (the operator
> resolves it with `java -version`), **never** the clean `not-at-risk-newer-jdk` bucket.

These three classifications are **exhaustive and non-overlapping** over every workload signal 6
considers — every workload **not positively identifiable as non-Java** (a positively-identified
non-Java image, e.g. a pure `nginx`/`golang` image, is simply out of scope, not counted). An
opaque/unknown-sub-build image cannot be ruled out, so it stays in scope as `unconfirmed`:
`detected == at_risk + not_at_risk_newer_jdk + unconfirmed` (see the schema counters below).

**Operator verification commands (self-serve — these are OPERATOR steps the skill *advises*,
not skill actions).** For an **at-risk** or **unconfirmed** workload the operator resolves the
build directly:

```bash
# 1. See the actual image (and thus base) behind the pod
kubectl get pod <pod> -n <ns> -o jsonpath='{.spec.containers[*].image}'

# 2. Confirm the real JDK build (resolves at-risk "< 8u372?" and unconfirmed "is there Java at all?")
kubectl exec <pod> -n <ns> -c <container> -- java -version

# 3. See the JVM's RESOLVED heap sizing under the pod's cgroup-v2 limit (does MaxRAMPercentage/limit take effect?)
kubectl exec <pod> -n <ns> -c <container> -- java -XshowSettings:vm -version   # look at MaxHeapSize
```

This lets the common **unconfirmed** bucket actually resolve rather than staying a dead end.
This is a **read + advise** signal only. The remediation levers (bump to `8u372+`, verify
`-XX:+UseContainerSupport` is not disabled, size the heap with `-XX:MaxRAMPercentage` after
removing any residual `-Xmx`) are **operator steps** described in `migration-risks.md` Risk 1
and staged in `runbook.md` Phase 0 — this skill reports and advises; it never modifies a
workload.

### 7. Why is the AMI custom? (rebuild-complexity triage)

When section 1-3 resolve a node group to a **custom AMI** (`amiType: CUSTOM`, or an LT that pins
a non-EKS-optimized `ImageId`, or a self-managed AMI whose Name matches no EKS pattern), the OS
family is only half the picture. The **harder** question for migration effort is **why** the AMI
is custom — because that determines whether the AL2023 target can be **stock AL2023 + config**
or needs a **full custom image rebuild**. This is an **assess-and-present** step: surface the
signals and the options, do **not** prescribe one path.

**Signals to gather (facts, from reads already available — do not exec or open a node shell):**

- **Baked host agents / daemons** — DaemonSets that could instead run as pods, or binaries the
  AMI installs at build time (log shippers, security/observability agents). Cross-reference the
  `migration-risks.md` Risk 5 host-agent list: an agent baked into the AMI is often re-expressible
  as a **DaemonSet** or via **userData**, which favors stock AL2023.
- **Kernel modules / GPU / Neuron drivers** — `securityContext.privileged` DaemonSets, GPU/Neuron
  instance types (from `node.kubernetes.io/instance-type`), or an AMI Name hinting at drivers.
  Out-of-tree modules must be rebuilt for the AL2023 6.1/6.12 kernel and are the **strongest**
  pull toward a full image rebuild (or the AL2023 NVIDIA/Neuron EKS AMI, if one covers the need).
- **Compliance / hardening** — an AMI Name or tag suggesting a CIS/STIG/hardened baseline, or a
  golden-image pipeline. A hardened baseline usually means the AL2023 image must be re-hardened
  (rebuild), not swapped to stock.
- **Baked config / userData** — files, certs, or bootstrap logic baked in vs. supplied at boot.

**Present the options (env-shaped, not a default):**

| If the "why" is mostly… | Then AL2023 target likely… |
|-------------------------|----------------------------|
| Agents that can be DaemonSets / userData-installed | **Stock AL2023** EKS AMI + agents-as-DaemonSet/userData — lowest rebuild effort |
| Kernel modules / custom drivers / GPU-Neuron / hardening baseline | **Full custom AL2023 image rebuild** (or the matching AL2023 accelerated EKS AMI) — carry the rebuild pipeline forward |
| Mixed | Split: move what can move to stock AL2023, rebuild only the irreducible parts |

Report the gathered signals as **facts** and the options for the operator to weigh — never
assert which path they must take. Record any signal that could not be read as `unconfirmed` (e.g. a
build-time agent invisible from the control plane), not as "no reason found".

---

## Lifting the limitation (supplementary ClusterRole)

To confirm the **desired** Karpenter / Auto-Mode AMI family (the CRD reads that return `403`
under `AmazonAIOpsAssistantPolicy` alone — see section 5), bind the Agent Space role's
Kubernetes identity to this read-only ClusterRole via a `ClusterRoleBinding` to the same
subject the EKS access entry maps the role to (or associate a broader access policy). It grants
only `get`/`list` on the Karpenter/Auto-Mode CRD groups and on `customresourcedefinitions`:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: eks-al2023-migration-crd-readonly
rules:
  - apiGroups: ["karpenter.k8s.aws"]
    resources:
      - ec2nodeclasses
    verbs: ["get", "list"]
  - apiGroups: ["karpenter.sh"]
    resources:
      - nodepools
      - nodeclaims
    verbs: ["get", "list"]
  - apiGroups: ["eks.amazonaws.com"]
    resources:
      - nodeclasses
    verbs: ["get", "list"]
  - apiGroups: ["apiextensions.k8s.io"]
    resources:
      - customresourcedefinitions
    verbs: ["get", "list"]
```

Without this binding (or a broader access policy), the Karpenter/Auto-Mode desired-AMI facts
stay `unconfirmed` and the skill reports this ClusterRole as the fix in the Coverage section.
(This ClusterRole is surfaced at runtime in the Coverage section when Karpenter/Auto-Mode AMI
facts are unconfirmed.)

---

## Output Schema

The agent emits this shape (alongside the shared cluster block). Use `null` where a fact was
not detected; use `unconfirmed` counts (not `0`) where a read was blocked. Never omit a key.
This schema is the internal fact structure the markdown migration-readiness report is assembled
from — this skill emits a markdown report plus a runbook, not a separate YAML artifact.

```yaml
al2_footprint:
  scope_summary:
    node_groups_on_al2: int         # count of node groups (any compute type) confirmed on AL2
    nodes_on_al2: int               # count of nodes confirmed AL2 via osImage/kernel or AMI name
    unconfirmed: int                # compute whose OS family could not be confirmed (e.g. CRD 403)

  nodes:                            # per-node in-cluster facts (Kubernetes API), null if K8s unreachable
    total: int
    on_al2: int                     # osImage contains "Amazon Linux 2" not "2023", or kernel contains amzn2
    on_al2023: int                  # osImage contains "Amazon Linux 2023", or kernel 6.1/6.12
    other_or_unconfirmed: int       # Bottlerocket / unread / disagreeing signals
    list:
      - name: string
        os_image: string            # status.nodeInfo.osImage verbatim
        kernel_version: string      # status.nodeInfo.kernelVersion verbatim
        container_runtime: string   # status.nodeInfo.containerRuntimeVersion verbatim
        os_family: string           # al2 | al2023 | bottlerocket | unconfirmed
        compute_type: string        # managed | self-managed | karpenter | auto-mode
        nodegroup: string           # eks.amazonaws.com/nodegroup label, null if not MNG

  node_groups:
    managed:                        # from eks:DescribeNodegroup amiType (authoritative)
      count: int
      on_al2: int
      on_al2023: int
      list:
        - name: string
          ami_type: string          # amiType verbatim (e.g. AL2_x86_64, AL2023_x86_64_STANDARD)
          os_family: string         # al2 | al2023 | unconfirmed (CUSTOM unresolved)
          release_version: string
          launch_template:          # null if the node group uses no custom launch template
            id: string
            version: string
            image_id: string        # LaunchTemplateData.ImageId, null if EKS-supplied
            uses_bootstrap_sh: bool  # userData contains /etc/eks/bootstrap.sh
            imds_hop_limit: int      # MetadataOptions.HttpPutResponseHopLimit, null if unset
    self_managed:                   # instances with no MNG amiType, classified via AMI Name
      count: int
      on_al2: int
      on_al2023: int
      unconfirmed: int              # custom AMI Name matching neither pattern
    karpenter:
      node_count_on_al2: int        # running Karpenter nodes on AL2 (from node osImage) — a fact
      ec2nodeclass_ami_family: string  # al2 | al2023 | unconfirmed (CRD read blocked -> unconfirmed)
    auto_mode:
      node_count_on_al2: int
      nodeclass_ami_family: string  # unconfirmed when CRD read blocked
    fargate:
      profiles: int                 # Fargate has no AL2 concern — excluded from migration scope

  java_workloads:                   # cgroup-v2 JDK signals (section 6), null if K8s unreachable
                                    # Java only — .NET is a manual review flag, NOT detected here (no counter)
    detected: int                   # every workload NOT positively identifiable as non-Java:
                                    # readable Java signal (at_risk + not_at_risk_newer_jdk) PLUS
                                    # opaque images that cannot be ruled out (unconfirmed). Opaque
                                    # images are NEVER dropped from the denominator.
                                    # INVARIANT: detected == at_risk + not_at_risk_newer_jdk + unconfirmed
    at_risk: int                    # inline tag/env indicates JDK 8, OR JDK 11 with unknown sub-build -> needs operator verify
    not_at_risk_newer_jdk: int      # inline tag/env indicates JDK 15+ (incl. 17/21), cgroup-v2-aware at every build; recorded as a fact
    unconfirmed: int                # Java plausible but no readable JDK-version signal (opaque/baked/valueFrom)
    jdk_version: string             # always "unconfirmed" — exact build not readable from control-plane (no exec)
    list:
      - namespace: string
        workload: string            # e.g. deployment/name or pod/name
        image: string               # spec.containers[].image verbatim (weak JDK signal)
        java_signal: string         # how detected: image-tag | JAVA_VERSION-env | -XX-flag | none
        has_memory_limit: bool      # resources.limits.memory set -> exposed to the heap-sizing bug
        classification: string      # at-risk-needs-operator-verify | not-at-risk-newer-jdk | unconfirmed
```

---

## Edge Cases

### Karpenter / Auto Mode AMI family unconfirmed (CRD blocked)

When `karpenter.k8s.aws` / `eks.amazonaws.com` CRD reads return `403` under
`AmazonAIOpsAssistantPolicy` alone, the **desired** AMI family is `unconfirmed`. Still report
the **running** OS family of Karpenter/Auto-Mode nodes from `status.nodeInfo.osImage`
(section 4) — that is a confirmed, separate fact. Never guess the CRD's `amiFamily`, and never
record it as `false`. A supplementary ClusterRole is required to confirm it.

### Mixed AMIs in one cluster

A single cluster commonly runs several node groups on different AMI families at once (e.g.
`ng-a` on AL2, `ng-b` already on AL2023, plus Karpenter). Report each node group's OS family
independently — do not collapse to a single cluster-wide label. The migration scope is the
**subset** of node groups still on AL2; the AL2023 ones are already done and are reported as a
fact, not re-migrated.

### Bottlerocket nodes

Nodes on a `BOTTLEROCKET_*` `amiType` (or `bottlerocket-aws-k8s-*` AMI Name) run
**Bottlerocket**, which is **neither AL2 nor AL2023**. Bottlerocket is **out of AL2→AL2023
migration scope** — it is not affected by the AL2 EKS AMI deprecation. Report Bottlerocket
node counts as a fact and exclude them from the AL2 footprint and the runbook; do not classify
them as AL2 or AL2023.

### Node group `amiType: CUSTOM`

`CUSTOM` does not by itself reveal the OS family. Resolve it via the launch-template `ImageId`
(section 3) → AMI Name (section 2 mapping), cross-checked against the running nodes' `osImage`
(section 4). If none of those resolve to a known pattern, record the AMI Name / `osImage`
verbatim as facts and mark the OS family `unconfirmed` — do not guess.
