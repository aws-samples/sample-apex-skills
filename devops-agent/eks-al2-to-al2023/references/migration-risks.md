# Module: Migration Risks

> **Part of:** [eks-al2-to-al2023](../SKILL.md)
> **Purpose:** For the AL2 footprint from `node-inventory.md`, assess each known AL2→AL2023 migration-breaking behavior against what is actually running, and report each with a status rating and the evidence behind it

This is the fact-heavy reference. **Every version, date, and threshold below carries a source
URL and "as of 2026-07-19".** Items that could not be verified against an AWS EKS or Amazon
Linux 2023 doc are marked **UNVERIFIED** in-text — do not assert them as fact, and never
assert a version/date from memory. This module reads facts only; it recommends remediation but
never applies it.

## Table of Contents

- [Access Model](#access-model)
- [Timeline (the deprecation facts)](#timeline-the-deprecation-facts)
- [Risk 1: cgroup v2](#risk-1-cgroup-v2)
- [Risk 2: IMDSv2 hop limit](#risk-2-imdsv2-hop-limit)
- [Risk 3: bootstrap.sh → nodeadm / NodeConfig](#risk-3-bootstrapsh--nodeadm--nodeconfig)
- [Risk 4: VPC CNI version floor](#risk-4-vpc-cni-version-floor)
- [Risk 5: DaemonSet / kernel-module / log-shipper agents](#risk-5-daemonset--kernel-module--log-shipper-agents)
- [Other AL2023 behavioral changes (facts)](#other-al2023-behavioral-changes-facts)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Access Model

Both sources are read-only:

- **AWS control-plane APIs** — cluster K8s version (`eks:DescribeCluster`), node-group
  `amiType` / launch-template userData + IMDS settings (`eks:DescribeNodegroup`,
  `ec2:DescribeLaunchTemplateVersions`), and the VPC CNI add-on version
  (`eks:DescribeAddon --addon-name vpc-cni`). Requires `references/iam-policy.json`.
- **Kubernetes API** (via the Agent Space EKS access entry) — workload container images (for
  cgroup-v2 JDK/.NET risk), pod IMDS-credential usage signals, and DaemonSets (for the
  host-agent review). RBAC verbs: `get`, `list` on `pods`, `deployments.apps`,
  `daemonsets.apps`, `statefulsets.apps`. When the K8s API is unreachable, mark the
  K8s-dependent risks
  (`cgroup_v2` workload evidence, `host_agents`) `unconfirmed` in Coverage — never `false`.

> **Declarative note.** "**Via Kubernetes API**" blocks describe resource + group/version +
> fields + RBAC verbs; they are not executable `kubectl` pipelines. "**Via AWS API**" blocks
> may show example `aws ...` calls.

Each risk is reported with a **status rating**:

| Status | Meaning |
|--------|---------|
| `applies` | The condition is present in this cluster — it will affect the migration. |
| `does-not-apply` | The condition was checked and is absent (a confirmed clean fact). |
| `review` | Cannot be reduced to a version gate — a human must review the specific component against its own AL2023 support (honest "review this", not a claim it breaks). |
| `unconfirmed` | The evidence needed could not be read (e.g. K8s API unreachable, CRD 403). Never a false negative. |

---

## Timeline (the deprecation facts)

**All dates VERIFIED** against the EKS AL2 deprecation FAQ,
<https://docs.aws.amazon.com/eks/latest/userguide/eks-ami-deprecation-faqs.html> — as of
2026-07-19:

- AWS **stopped publishing** EKS-optimized AL2 and AL2-accelerated AMIs on **2025-11-26**
  (end of support). After this date there are **no new Kubernetes versions, no security
  patches, and no bug fixes** for the AL2 EKS-optimized AMIs.
- **Kubernetes 1.32 was the LAST EKS version to ship AL2 AMIs** (`AL2_x86_64`, `AL2_ARM_64`,
  `AL2_x86_64_GPU`). **K8s 1.33 and later ship AL2023 and Bottlerocket only** — you cannot
  create an AL2 managed node group on 1.33+.
- EKS AL2 AMI end-of-support is **independent of** the Kubernetes standard/extended support
  clock — a cluster on a still-supported K8s version can still be on an unsupported AL2 AMI.
- The base **Amazon Linux 2 OS** end-of-support is **2026-06-30**. Until then you can build a
  **custom** AMI from the AL2 base (kernel updates only), but this is a stopgap, not the
  EKS-optimized AL2 AMI.

> **Precision note (reconciling the upstream check).** The upstream
> `skills/eks-upgrade-check/references/node-readiness.md` loosely states "AL2 standard support
> ended June 2025" and "EKS 1.33+ does not publish AL2 AMIs". Use the **precise** facts above:
> the **EKS-optimized AL2 AMI** end of support is **2025-11-26** (K8s **1.32** was the last to
> ship it), and the **base AL2 OS** EOS is **2026-06-30**. This does not contradict the
> upstream check — it is the same deprecation stated precisely. Source:
> <https://docs.aws.amazon.com/eks/latest/userguide/eks-ami-deprecation-faqs.html> (as of
> 2026-07-19).

---

## Risk 1: cgroup v2

### Why this matters

**VERIFIED** — AL2023 uses **cgroup v2**; AL2 used **cgroup v1**. Source:
<https://docs.aws.amazon.com/eks/latest/userguide/eks-ami-deprecation-faqs.html> (as of
2026-07-19).

- **EKS breaking change:** at **Kubernetes 1.35 and later, cgroup v1 support is removed** — the
  kubelet **refuses to start on a cgroup v1 node** unless `failCgroupV1=false` is set. This
  makes the AL2→AL2023 move effectively mandatory before 1.35. Source:
  <https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html> (as of
  2026-07-19).
- **JDK 8 before 8u372** cannot detect container memory limits under cgroup v2 — the JVM sizes
  the heap from the **node's total memory**, not the pod's memory limit, causing `OutOfMemory`
  exceptions and pod restarts once on AL2023. Fix: **jdk8u372 or newer**, or a newer JDK.
  Source: <https://docs.aws.amazon.com/eks/latest/userguide/eks-ami-deprecation-faqs.html>
  (as of 2026-07-19).
- **UNVERIFIED — JDK 11 sub-version and .NET version.** The AWS FAQ names only **JDK 8
  (< 8u372)** explicitly and links the kubernetes.io "About cgroup v2" page for the full list
  of affected runtimes. The specific JDK 11 sub-version and the specific .NET version that
  gain cgroup-v2 awareness are **UNVERIFIED** here — do not assert them. Phrase the .NET risk
  as "**older .NET runtimes without cgroup v2 awareness (verify your runtime version)**" and
  the JDK 11 risk as "verify against the kubernetes.io cgroup v2 list". kubernetes.io "About
  cgroup v2": <https://kubernetes.io/docs/concepts/architecture/cgroups/> (as of 2026-07-19).
- **VERIFIED** — cgroup v2 requires **kernel >= 5.8**; AL2023 uses **6.1 / 6.12** so it meets
  this. Legacy cgroup v1 can be forced with the kernel arg
  `systemd.unified_cgroup_hierarchy=0`, **but AWS does not recommend or support** doing so.
  Source: <https://docs.aws.amazon.com/eks/latest/userguide/eks-ami-deprecation-faqs.html>
  (as of 2026-07-19).

### How to detect

**Via Kubernetes API** — enumerate workload container images and flag JDK-8/old-.NET images:

- **Resource:** `Pod`, group/version `v1` (core), all namespaces; and `Deployment` /
  `DaemonSet` / `StatefulSet`, group/version `apps/v1`, all namespaces.
- **Fields to extract:** `spec.containers[].image` (and `spec.initContainers[].image`). Flag
  images whose tag or base indicates **JDK 8 older than 8u372** (e.g. `openjdk:8`, `:8uNNN`
  where NNN < 372, `eclipse-temurin:8`, `amazoncorretto:8` on an old build) or an **older .NET
  runtime** (verify the runtime version — this is a review flag, not a version gate). Also flag
  containers that set a memory limit (`spec.containers[].resources.limits.memory`) since those
  are the ones exposed to the heap-sizing bug.
- **RBAC verbs:** `get`, `list` on `pods`, `deployments.apps`, `daemonsets.apps`,
  `statefulsets.apps`.

Image tags are an **imperfect** signal (a `:8` tag may already be 8u372+). Report the flagged
image as evidence and recommend the operator verify the actual JVM/.NET build; do not assert a
definite break from the tag alone.

### Status rating

- `applies` — one or more workload images match JDK 8 (< 8u372) or an older .NET runtime.
- `does-not-apply` — no JDK/.NET workloads found (a clean fact).
- `unconfirmed` — K8s API unreachable, so workload images could not be read.

### Remediation

Bump affected JVMs to **jdk8u372+** (or a newer JDK); verify .NET runtime versions for cgroup
v2 awareness. This is a **workload** fix that should land **before** the AMI swap.

---

## Risk 2: IMDSv2 hop limit

### Why this matters

**VERIFIED** — AL2023 **requires IMDSv2 by default**. For a **managed node group** the default
IMDS **hop limit varies by launch-template configuration**:

- **No launch template** → hop limit defaults to **1** → per AWS, "containers won't have access
  to the node's credentials using IMDS" (the extra network hop from a pod to IMDS is dropped).
- **Custom AMI supplied via a launch template** → `HttpPutResponseHopLimit` defaults to **2**
  (overridable in the template).

Source: <https://docs.aws.amazon.com/eks/latest/userguide/al2023.html> (as of 2026-07-19).

**Affected:** pods that reach the **node instance credentials via IMDS** (they need the extra
hop). Pods using IRSA or EKS Pod Identity are **not** affected — they do not use node IMDS
credentials.

### How to detect

**Via AWS API** — read the IMDS hop limit each AL2 node group will inherit:

```bash
# For a node group WITH a launch template, read its metadata options
aws ec2 describe-launch-template-versions --launch-template-id <lt-id> --versions <version> \
  --query 'LaunchTemplateVersions[].LaunchTemplateData.MetadataOptions.{HopLimit:HttpPutResponseHopLimit,Endpoint:HttpEndpoint,Tokens:HttpTokens}'
```

- **No launch template on the node group** (from `node-inventory.md` section 1) → the node will
  come up with hop limit **1** → flag `applies` (pods using node IMDS credentials will break).
- **Launch template present** → read `HttpPutResponseHopLimit`; if 1, `applies`; if >= 2,
  `does-not-apply` (for the hop-limit concern).

**Via Kubernetes API** (best-effort signal) — pods likely to use node IMDS credentials are
those **without** an IRSA/Pod-Identity service account. Reading which pods call IMDS is not
directly observable via the K8s API; report the hop-limit fact and recommend the operator
confirm which workloads rely on node IMDS credentials.

### Status rating

- `applies` — an AL2 node group has (or will default to) hop limit 1 and workloads may use
  node IMDS credentials.
- `does-not-apply` — hop limit already >= 2, or all workloads use IRSA/Pod Identity.
- `unconfirmed` — launch-template metadata options could not be read.

### Remediation

Raise the hop limit to **2** via a **custom launch template**, **or** move workloads to **EKS
Pod Identity / IRSA** instead of node IMDS credentials (the recommended long-term fix). Source:
<https://docs.aws.amazon.com/eks/latest/userguide/al2023.html> (as of 2026-07-19).

---

## Risk 3: bootstrap.sh → nodeadm / NodeConfig

### Why this matters

**VERIFIED** — AL2023 introduces **`nodeadm`** with a YAML config schema (`apiVersion:
node.eks.aws/v1alpha1`, `kind: NodeConfig`) that **replaces `/etc/eks/bootstrap.sh`** (the AL2
bootstrap script). For **self-managed nodes and custom launch templates**,
`apiServerEndpoint`, `certificateAuthority`, and the service `cidr` are now **REQUIRED** in
userData (on AL2 these were auto-discovered by `bootstrap.sh` via `DescribeCluster`; AL2023
requires them explicitly to avoid API throttling on scale-up). kubelet arguments move from
`--kubelet-extra-args` to the `NodeConfig` `spec.kubelet.config` / `spec.kubelet.flags`
fields. Source: <https://docs.aws.amazon.com/eks/latest/userguide/al2023.html> (as of
2026-07-19).

**NOT affected:** a managed node group **without** a launch template (EKS injects the config),
or **Karpenter** (Karpenter generates AL2023 userData itself).

**Minimal `NodeConfig` userData (AL2023):**

```yaml
apiVersion: node.eks.aws/v1alpha1
kind: NodeConfig
spec:
  cluster:
    name: <cluster-name>
    apiServerEndpoint: https://<cluster-endpoint>
    certificateAuthority: <base64-CA-data>
    cidr: <service-ipv4-cidr>        # e.g. 172.20.0.0/16
  kubelet:
    config:                          # replaces --kubelet-extra-args key/values
      maxPods: 110
    flags:                           # replaces --kubelet-extra-args flags
      - "--node-labels=role=worker"
```

> **Do NOT run `nodeadm init` yourself.** On AL2023 nodes `nodeadm` runs automatically via the
> `nodeadm-config` / `nodeadm-run` systemd services at boot. This skill only reports the
> userData rewrite requirement and provides the template above — it never executes `nodeadm`.

### How to detect

**Via AWS API** — from `node-inventory.md` section 3, a node group's launch-template userData:

- userData contains `/etc/eks/bootstrap.sh` → AL2-style bootstrap → **must** be rewritten to
  `NodeConfig` → `applies`.
- Self-managed nodes with a launch template → `applies` (require the three cluster fields).
- MNG with **no** launch template, or Karpenter-owned → `does-not-apply`.

The `apiServerEndpoint` and `certificateAuthority` values for the template come from
`eks:DescribeCluster` (`cluster.endpoint`, `cluster.certificateAuthority.data`); the service
`cidr` from `cluster.kubernetesNetworkConfig.serviceIpv4Cidr`.

### Status rating

- `applies` — a self-managed node group or MNG custom launch template uses `bootstrap.sh`
  userData.
- `does-not-apply` — MNG without a launch template, or Karpenter.
- `unconfirmed` — launch-template userData could not be read.

### Remediation

Rewrite launch-template userData to the `NodeConfig` schema above (operator action, staged in
the runbook). Do not run `nodeadm` manually.

---

## Risk 4: VPC CNI version floor

### Why this matters

**VERIFIED** — Amazon **VPC CNI 1.16.2 or greater is required** for AL2023 (and **eksctl
0.176.0+** if used to create AL2023 node groups). Source:
<https://docs.aws.amazon.com/eks/latest/userguide/al2023.html> (as of 2026-07-19).

> **UNVERIFIED — what specifically breaks below 1.16.2.** The AWS doc states 1.16.2 is
> "required for AL2023 support" but the **exact failure mode below that floor is UNVERIFIED**
> here — do not assert a specific breakage (e.g. "IP assignment fails"). Treat sub-1.16.2 as
> "below the AL2023-supported floor; upgrade before migrating".

### How to detect

**Via AWS API** — read the running VPC CNI add-on version and compare to the 1.16.2 floor:

```bash
aws eks describe-addon --cluster-name <cluster-name> --addon-name vpc-cni \
  --query 'addon.{name:addonName,version:addonVersion,status:status}'
```

- `addonVersion` (e.g. `v1.15.4-eksbuild.1`) below `1.16.2` → `applies`.
- `addonVersion` >= `1.16.2` → `does-not-apply`.
- If VPC CNI is **self-managed** (no EKS add-on), `eks:DescribeAddon` returns not-found — read
  the version from the `aws-node` DaemonSet container image via the Kubernetes API instead, or
  mark `unconfirmed` if the K8s API is unreachable.

### Status rating

- `applies` — VPC CNI below 1.16.2.
- `does-not-apply` — VPC CNI >= 1.16.2.
- `unconfirmed` — version could not be read.

### Remediation

Upgrade VPC CNI to **>= 1.16.2** before migrating (operator action, first step in the runbook
pre-flight). Source: <https://docs.aws.amazon.com/eks/latest/userguide/al2023.html> (as of
2026-07-19).

---

## Risk 5: DaemonSet / kernel-module / log-shipper agents

### Why this matters

This is a **review** risk, not a hard version gate. The AL2→AL2023 kernel jump
(**5.10 → 6.1 / 6.12**, VERIFIED —
<https://docs.aws.amazon.com/eks/latest/userguide/eks-optimized-ami.html>, as of 2026-07-19)
plus the OS changes below can affect node-level agents:

- **Out-of-tree kernel modules** — agents that build/load kernel modules (some observability
  or security agents; GPU drivers if **not** using the AL2023 NVIDIA AMI) may not have modules
  built for the 6.1/6.12 kernel.
- **Host-path readers** — log shippers and node agents that read host paths may need config or
  version updates: `/var/log` layout, **journald** vs **rsyslog**, the cgroup path change
  **v1 → v2**, and the package layout change (**dnf** vs **yum**).

This is honest "**review these**" guidance — it is a **fact** (these agents touch host
internals that changed) plus a **review flag**, not a claim that any specific agent breaks.
Each agent's AL2023 support must be verified with its own vendor.

### How to detect

**Via Kubernetes API** — enumerate DaemonSets and flag those that touch host internals:

- **Resource:** `DaemonSet`, group/version `apps/v1`, all namespaces.
- **Flag a DaemonSet for "review for AL2023 compatibility" when it has any of:**
  - a `spec.template.spec.volumes[].hostPath` volume (reads host paths — log/cgroup/package
    layout changed),
  - a container with `securityContext.privileged: true` (likely loads kernel modules /
    touches devices),
  - `spec.template.spec.hostNetwork: true` or `hostPID: true`.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, the matched signal(s), and
  container images (evidence for the operator to check the vendor's AL2023 support).
- **RBAC verbs:** `get`, `list` on `daemonsets.apps`.

### Status rating

- `review` — one or more DaemonSets match a host-internal signal. List them with the matched
  signal; recommend verifying each agent's AL2023 support with its vendor.
- `does-not-apply` — no DaemonSets touch host internals (a clean fact).
- `unconfirmed` — K8s API unreachable.

### Remediation

For each flagged agent, confirm AL2023 support with its vendor and upgrade to an AL2023-capable
version before the fleet-wide roll. Validate on the canary node first (see `runbook.md`).

---

## Other AL2023 behavioral changes (facts)

Report these as **notable facts** so the operator can review their own tooling. All VERIFIED as
noted; kube-proxy backend is **UNVERIFIED** and must not be asserted.

- **SELinux enabled, set to `permissive` by default** (not `enforcing`). Source:
  <https://docs.aws.amazon.com/linux/al2023/ug/selinux-modes.html> (as of 2026-07-19).
- **DNF** replaces **YUM**; **systemd-networkd** replaces `dhclient`; **Python 3** only (2.7
  removed); **no 32-bit userspace**; **no EPEL**; **`/tmp` is tmpfs**; **systemd timers**
  replace **cron**; **journald** replaces **rsyslog**; **gp3** is the default EBS volume type.
  Source: <https://docs.aws.amazon.com/linux/al2023/ug/compare-with-al2.html> (as of
  2026-07-19).
- **Kernel 6.1 / 6.12** (AL2 used **5.10**) and **containerd is the only supported runtime** on
  EKS AL2023. Source:
  <https://docs.aws.amazon.com/eks/latest/userguide/eks-optimized-ami.html> (as of 2026-07-19).
- **UNVERIFIED — kube-proxy nftables / iptables-nft requirement.** No AWS EKS doc was found
  requiring a kube-proxy backend switch (e.g. to `nftables` or `iptables-nft`) for AL2023. **Do
  NOT assert** that AL2023 requires a kube-proxy backend change. If asked, report it as
  UNVERIFIED and unconfirmed by AWS docs as of 2026-07-19.

---

## Output Schema

This schema is the internal fact structure the markdown migration-readiness report is assembled
from — this skill emits a markdown report plus a runbook, not a separate YAML artifact.

```yaml
migration_risks:
  cgroup_v2:
    status: string          # applies | does-not-apply | unconfirmed
    evidence: string        # e.g. "1 workload image tagged openjdk:8u312 with a memory limit"
    # NOTE: JDK 8 <8u372 VERIFIED; JDK 11 sub-version + .NET version UNVERIFIED (verify runtime)
  imds_hop_limit:
    status: string          # applies | does-not-apply | unconfirmed
    evidence: string        # e.g. "ng-a has no launch template -> default hop limit 1"
  nodeadm_bootstrap:
    status: string          # applies | does-not-apply | unconfirmed
    evidence: string        # e.g. "ng-b launch template userData contains /etc/eks/bootstrap.sh"
  vpc_cni_version:
    status: string          # applies | does-not-apply | unconfirmed
    evidence: string        # e.g. "vpc-cni v1.15.4-eksbuild.1 (floor 1.16.2)"
    # NOTE: 1.16.2 floor VERIFIED; sub-1.16.2 failure mode UNVERIFIED
  host_agents:
    status: string          # review | does-not-apply | unconfirmed
    evidence: string        # list of flagged DaemonSets + matched signal (hostPath/privileged/hostNetwork)
```

---

## Edge Cases

### K8s API unreachable

`cgroup_v2` workload evidence and `host_agents` come from the Kubernetes API. If it is
unreachable, mark both `unconfirmed` (with reason) in Coverage — never `does-not-apply`. The
AWS-API-only risks (`imds_hop_limit`, `nodeadm_bootstrap`, `vpc_cni_version`) are still fully
assessable.

### Image tag is an imperfect JDK/.NET signal

A `:8` or `:8-jre` tag may already be 8u372+. Report the flagged image as evidence and mark the
cgroup risk `applies` **pending operator verification of the actual build** — do not assert a
definite OOM break from the tag alone.

### Self-managed VPC CNI (no EKS add-on)

`eks:DescribeAddon --addon-name vpc-cni` returns not-found for a self-managed CNI. Read the
version from the `aws-node` DaemonSet container image (Kubernetes API) instead; if the K8s API
is unreachable, mark `vpc_cni_version` `unconfirmed`, not `applies`.

### Do not assert the kube-proxy backend requirement

Per the UNVERIFIED note above, never report that AL2023 requires an nftables/iptables-nft
kube-proxy switch. It is unconfirmed by AWS docs as of 2026-07-19.
