---
title: "Cluster & Scheduling — Karpenter, Device Plugins, EFA, Capacity"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/cluster-and-scheduling.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-genai/references/cluster-and-scheduling.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/cluster-and-scheduling.md). Edit the source, not this page.
:::

# Cluster & Scheduling — Karpenter, Device Plugins, EFA, Capacity

Karpenter is the **only recommended autoscaler** for GPU/Neuron workloads on EKS. Cluster Autoscaler cannot handle instance heterogeneity, Spot diversification, or consolidation at GenAI scale. Provision **two NodePools** (GPU + Neuron) from day one — future hardware migration becomes a cost experiment, not a re-architecture.

## Karpenter GPU NodePool

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: gpu
spec:
  template:
    metadata:
      labels:
        karpenter.sh/nodepool: gpu
    spec:
      taints:
        - key: nvidia.com/gpu
          value: "true"
          effect: NoSchedule
      requirements:
        - key: karpenter.k8s.aws/instance-accelerator-manufacturer
          operator: In
          values: ["nvidia"]
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["g6e.2xlarge", "g6e.12xlarge", "g6e.48xlarge", "g6.12xlarge", "p5.48xlarge"]
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand", "reserved"]   # reserved = ODCR via capacityReservationSelectorTerms
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
  limits:
    nvidia.com/gpu: "16"        # hard cap on GPU scale-out: guardrail against cost runaway
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 60s
```

> **Cap runaway GPU spend:** always set NodePool `spec.limits` (e.g. `nvidia.com/gpu`, or `cpu`/`memory`) plus a per-namespace `ResourceQuota`. Together they bound how many accelerators a NodePool and a tenant can ever provision, so a runaway Deployment or bad HPA can't scale GPUs without bound.

> **Workshop-validated**: The NVIDIA workshop uses `capacity-type: reserved + on-demand`, taint `nvidia.com/gpu=true:NoSchedule`, and label `karpenter.sh/nodepool: gpu`. GPU capacity is reserved via ODCR patched into the EC2NodeClass with `capacityReservationSelectorTerms`.

## Karpenter Neuron NodePool

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: neuron
spec:
  template:
    metadata:
      labels:
        karpenter.sh/nodepool: neuron
    spec:
      taints:
        - key: aws.amazon.com/neuron
          value: "true"
          effect: NoSchedule
      requirements:
        - key: karpenter.k8s.aws/instance-accelerator-manufacturer
          operator: In
          values: ["aws"]
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["inf2.8xlarge", "inf2.48xlarge", "trn1.32xlarge", "trn2.48xlarge"]
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 60s
```

Key difference: `instance-accelerator-manufacturer: aws` selects Trainium/Inferentia families. Use `aws.amazon.com/neuron` taint for workload isolation.

### Consolidation: inference pools vs training pools

The `consolidationPolicy: WhenEmptyOrUnderutilized` + `consolidateAfter: 60s` shown above is correct for **inference** pools. It packs replicas tightly and reclaims idle GPUs quickly. It is **wrong for multi-node / EFA training** pools: underutilized-consolidation can evict and reschedule nodes mid-run, tearing down a distributed job and losing progress since the last checkpoint.

Per the [AI/ML networking best practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-networking.html), a **training** NodePool should:

- use `consolidationPolicy: WhenEmpty` (only reclaim nodes with zero workloads, never "underutilized" ones),
- set `expireAfter` longer than the longest training job (or `Never` to disable node expiry), so a run is never interrupted by node age, and
- back it with `karpenter.sh/do-not-disrupt: "true"` (annotation on the training pods) and PDBs. These guard *voluntary* disruption only: on a Capacity Block they do **not** survive end-of-block reclamation (involuntary), so checkpoint/resume stays mandatory (see the Capacity Blocks section).

```yaml
# TRAINING NodePool overrides (multi-node / EFA jobs); replaces the inference defaults above
spec:
  template:
    spec:
      expireAfter: Never              # v1: expireAfter lives under template.spec, NOT disruption; or set longer than the longest job (e.g. 168h)
  disruption:
    consolidationPolicy: WhenEmpty    # never disrupt "underutilized" nodes mid-run
    consolidateAfter: 300s
```

Leave inference pools on `WhenEmptyOrUnderutilized`. Do not blanket-apply the training settings to them, or you forfeit inference bin-packing and cost savings.

## Device Plugins — NVIDIA vs Neuron Device Plugin vs Neuron DRA

| Plugin | Exposes | Compatible with Karpenter? | Compatible with Auto Mode? | Use when |
|---|---|---|---|---|
| **NVIDIA device plugin** (DaemonSet) | `nvidia.com/gpu` | ✅ Yes | ✅ Embedded — no install needed | Any NVIDIA GPU workload |
| **AWS Neuron device plugin** (DaemonSet) | `aws.amazon.com/neuroncore`, `aws.amazon.com/neurondevice` | ✅ Yes | ✅ Yes | Neuron workloads on Karpenter or Auto Mode |
| **AWS Neuron DRA driver** (K8s 1.34+) | `ResourceClaim`-based allocation | ⚠️ **Static NodePools only** (no dynamic provisioning) | ❌ **Not supported** | Topology-aware NeuronCore allocation on Karpenter static-capacity NodePools, EKS managed node groups, or self-managed nodes |

**Decision rule**: On **EKS Auto Mode**, use the **Neuron device plugin**. The DRA driver is **not supported** there. The Neuron DRA driver (K8s 1.34+) adds topology-aware allocation and per-workload Logical NeuronCore config, and is **supported on Karpenter static-capacity NodePools, EKS managed node groups, and self-managed nodes**. It does **not** drive dynamic Karpenter provisioning: nodes must already exist (static NodePool capacity or a managed/self-managed node group), so pair it with pre-provisioned capacity rather than expecting Karpenter to scale up against a `ResourceClaim`.

Reference: [Manage Neuron devices on Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/device-management-neuron.html)

## EKS Auto Mode + GPU

On EKS Auto Mode (Kubernetes 1.34+), the NVIDIA driver and device plugin are **embedded in the Bottlerocket AMI**. You do **not** install:

- `gpu-operator`
- `nvidia-device-plugin` DaemonSet
- Any CUDA driver management

The "install nvidia-device-plugin DaemonSet" step in most guides applies to **self-managed / standard EKS only**. Auto Mode also auto-enables **SOCI snapshotter** on G/P/Trn instance families — container images pull in parallel from local NVMe, slashing cold-start time for multi-GB model images.

## EKS-Optimized Accelerated AMIs

Always use EKS-optimized accelerated AMIs — never manage drivers yourself.

| AMI | Ships with | Recommended for |
|---|---|---|
| **Bottlerocket (GPU)** | NVIDIA driver + device plugin + containerd | Auto Mode default; security-hardened; immutable root |
| **AL2023 (GPU)** | NVIDIA driver + CUDA toolkit | Self-managed nodes needing custom packages |
| **Bottlerocket (Neuron)** | Neuron driver + Neuron runtime | Neuron workloads on Auto Mode |
| **AL2023 (Neuron)** | Neuron driver + Neuron SDK | Self-managed Neuron nodes |

Reference: [EKS Optimized AMIs](https://docs.aws.amazon.com/eks/latest/userguide/eks-optimized-amis.html)

## EFA Networking + NUMA Pinning

Required for multi-node distributed training (NCCL/MPI collectives). Without correct configuration, **EFA bandwidth halves or worse**.

### Setup Requirements

1. **EFA device plugin** — install `aws-efa-k8s-device-plugin` DaemonSet (exposes `vpc.amazonaws.com/efa`)
2. **NUMA pinning** — kubelet `topologyManagerPolicy: single-numa-node` ensures GPU + EFA NIC + memory are on the same NUMA domain
3. **Static CPU manager** — kubelet `cpuManagerPolicy: static` prevents OS from migrating training threads across NUMA boundaries
4. **NCCL + MPI in container image** — EFA hardware is unused without these libraries; use AWS Deep Learning Containers or build with `aws-ofi-nccl`

```yaml
# kubelet configuration for EFA nodes (self-managed or NodeConfig)
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
topologyManagerPolicy: single-numa-node
cpuManagerPolicy: static
reservedSystemCPUs: "0-3"
```

### Pod spec for EFA workload

```yaml
resources:
  limits:
    nvidia.com/gpu: "8"
    vpc.amazonaws.com/efa: "32"    # p5.48xlarge has 32 EFA interfaces
  requests:
    cpu: "180"
    memory: "1800Gi"
```

Reference: [EFA with EKS](https://docs.aws.amazon.com/eks/latest/userguide/node-efa.html) · [EKS AI/ML Networking Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-networking.html)

## VPC CNI Tuning at GPU Scale

Large GPU instances (p5 = 192 vCPUs, g6e.48xlarge = 192 vCPUs) trigger excessive ENI allocation at default VPC CNI settings — each ENI consumes subnet IPs. Real pod density on GPU nodes is 1–4 pods (not 100+). Subnet IP exhaustion is a **top-3 production issue** 12–18 months after GenAI cluster launch.

```yaml
# aws-node DaemonSet environment (VPC CNI)
env:
  - name: WARM_IP_TARGET
    value: "2"              # keep 2 warm IPs per node (not default 1-per-ENI)
  - name: MINIMUM_IP_TARGET
    value: "4"              # minimum IPs pre-allocated
  - name: WARM_ENI_TARGET
    value: "0"              # don't pre-attach extra ENIs
  - name: ENABLE_PREFIX_DELEGATION
    value: "true"           # /28 prefixes for IP density where needed
```

## EC2 Capacity Blocks for ML

For **planned multi-day training**, Capacity Blocks guarantee accelerated capacity (p4d/p4de, p5/p5e/p5en, p6-b200/p6-b300, trn1/trn2, and other supported families — see the [pricing page](https://aws.amazon.com/ec2/capacityblocks/pricing/) for the current list) with upfront, market-based pricing (guaranteed capacity access, not a guaranteed discount vs on-demand).

- Use Capacity Blocks for: scheduled training runs, benchmark campaigns, customer demos requiring guaranteed GPU
- Do **not** use for: inference (On-Demand with Karpenter consolidation is more flexible)
- Integration: Karpenter EC2NodeClass `capacityReservationSelectorTerms` targets the Capacity Block reservation
- **Single-AZ:** a CB is scoped to one Availability Zone. The consuming NodePool/EC2NodeClass must be constrained to that AZ (and, for multi-node training, the CB is placed in a single cluster/UltraCluster for low-latency EFA) — nodes can't span the reservation across zones.
- **UltraServers:** GB200 NVL72-class multi-node training is reserved via UltraServer Capacity Blocks, a distinct CB type from instance-level blocks (see the pricing page).

### Karpenter consumes reservations — it never purchases them

**The #1 SA misconception:** Karpenter does **not** create, buy, or extend a Capacity Block (or ODCR). It only *consumes* a reservation that already exists in the account. Karpenter launches nodes via the EC2 Fleet `CreateFleet` API, which *launches instances into capacity* — it does **not** *acquire* capacity. Purchasing a CB is a separate commercial transaction Karpenter never performs. If the `EC2NodeClass` doesn't explicitly target a reservation, launched instances consume regular On-Demand and leave the CB idle (still billing).

The workflow is **manual-first, Karpenter-second**:

**1. Customer purchases the CB** (console or CLI) — `describe-capacity-block-offerings` to find an offering, then `purchase-capacity-block`. `describe-capacity-block-offerings` returns an offering ID (`cb-…`); you pass that offering ID to `purchase-capacity-block`, which returns the reservation ID (`cr-…`). Payment is upfront, and the reservation is **not usable until it becomes `active`** (it sits in `payment-pending` → `scheduled` first — a `scheduled` CB has **zero available capacity**). A CB **can't be cancelled** once reserved — but **extensions ARE possible** (request before expiry; not guaranteed, capacity-dependent). See [Find and purchase Capacity Blocks](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-purchase.html) and [Extend Capacity Blocks](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-extend.html) for current duration/instance-count limits, payment states, and timing.

> **IAM — spending authority:** `ec2:PurchaseCapacityBlock` (and `ec2:PurchaseCapacityBlockExtension`, for extensions) commits real money upfront. Scope it to FinOps/platform-admin roles, not to cluster operators or CI. Karpenter's node role never needs it — Karpenter only *consumes* the reservation, so its permissions cover launching/terminating instances, not purchasing capacity.

```bash
aws ec2 describe-capacity-block-offerings \
  --instance-type p5.48xlarge --instance-count <COUNT> \
  --start-date-range <START> --end-date-range <END> \
  --capacity-duration-hours <HOURS>
aws ec2 purchase-capacity-block \
  --capacity-block-offering-id cb-0123456789abcdef0 --instance-platform Linux/UNIX
```

**2. Point Karpenter at it** — add the `cr-…` ID (or tags) to `capacityReservationSelectorTerms` on the `EC2NodeClass`, and allow `reserved` in the NodePool (already shown in the GPU NodePool above):

```yaml
# EC2NodeClass
spec:
  capacityReservationSelectorTerms:
    - id: cr-0123456789abcdef0        # the CB's underlying reservation
    # or: - tags: { team: ml-training }
```

> **Two consume-failure footguns:** (1) the NodePool's instance-type requirements must permit the CB's exact instance type. If they exclude it, Karpenter launches on-demand instead and the CB sits idle (still billing). (2) A `tags` selector matches any reservation carrying that tag, including other teams' reservations, so prefer the reservation `id` or a unique per-CB tag.

**3. Karpenter fills and prioritizes it** — once the block is **`active`** and pods are pending, Karpenter launches nodes into the CB, models the pre-paid capacity as **$0** so it prefers `reserved` over on-demand/spot (including during consolidation), then falls back once the reservation is exhausted. Karpenter cannot launch into a CB that is still `scheduled` — only after the reservation window opens and it goes `active`.

> **Version, limit, and timing values live in AWS docs — not here.** Karpenter version gates for ODCR / Capacity-Block / interruptible support, feature-gate names, instance-count and duration limits, and CB reclamation/drain timing all change over time. Consult the [Karpenter ODCR docs](https://karpenter.sh/docs/tasks/odcrs/) and the [EC2 Capacity Blocks pricing & billing docs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-pricing-billing.html) for current values. Operationally: CBs are time-bound, EC2 reclaims the instances at the block end, and Karpenter preemptively drains affected nodes ahead of that, so set an appropriate `terminationGracePeriodSeconds` for a graceful drain. Note that PDBs and the `karpenter.sh/do-not-disrupt` annotation do **not** stop the forced reclamation at block end (it is involuntary disruption). The real safeguard is checkpoint/resume before the block ends, plus sizing the block to the job duration.

**EKS Auto Mode nuance:** Auto Mode auto-uses *open* ODCRs via open-matching (nodes labeled `on-demand`, not prioritized). **Capacity Blocks always require explicit `capacityReservationSelectorTerms`.** Once you set `capacityReservationSelectorTerms` on any NodeClass, Auto Mode stops auto-using open ODCRs for *all* NodeClasses — so **add explicit ODCR selector terms to every other NodeClass that should continue using reservations**, or their open-ODCR consumption silently breaks.

> **P5 reality:** a plain On-Demand request for scarce GPUs (p5/p5e) often fails with `InsufficientInstanceCapacity` precisely because that capacity is held in reservations. For short P5 runs the CB is effectively mandatory — the customer procures it; Karpenter only launches into what they already own.

> **Prerequisite (accelerated-instance vCPU quota):** before any of this, check the **EC2 Service Quota** for the relevant accelerated-instance vCPUs. New accounts start at **0** for accelerated (P / G / Trn) instance vCPU quotas, so the very first launch fails not with `InsufficientInstanceCapacity` but with a quota/`VcpuLimitExceeded`-style error. This is the most common first-launch blocker. The P/G/Trn On-Demand and Spot quotas are separate limits (e.g. "Running On-Demand P instances", "Running On-Demand G and VT instances", each an `L-…` code), and a quota increase can take hours to days to be approved. Verify and, if needed, request the increase in **Service Quotas** well ahead of the build.

## Spot vs On-Demand Decision Rule

| Workload | Capacity type | Condition |
|---|---|---|
| **Training** | Spot | ✅ Only with checkpoint/resume wired (FSx → S3 DRA every 15–30 min) |
| **Training** | On-Demand / Capacity Blocks | When job cannot tolerate interruption or checkpoint/resume is not implemented |
| **Inference (production)** | On-Demand | Always — Spot interruptions break per-request SLAs |
| **Development / experimentation** | Spot | ✅ Default — tolerable interruption profile |

**Spot without checkpoint/resume is guaranteed cost-burn.** Every interruption restarts training from epoch 0. Karpenter will provision replacement Spot capacity — but the training run loses all progress since last checkpoint.

### Training pod annotation to prevent Karpenter disruption

```yaml
metadata:
  annotations:
    karpenter.sh/do-not-disrupt: "true"    # prevents consolidation from evicting active training
```

## EKS Auto Mode — What Changes for GenAI

| Concern | Auto Mode behavior | Standard EKS (self-managed) |
|---|---|---|
| NVIDIA driver | Embedded in Bottlerocket AMI | Install via gpu-operator or AMI bake |
| NVIDIA device plugin | Embedded — no DaemonSet | Deploy nvidia-device-plugin DaemonSet |
| Neuron device plugin | Supported | Deploy neuron-device-plugin DaemonSet |
| SOCI snapshotter | Auto-enabled on G/P/Trn families | Manual configuration |
| Custom kubelet config | ❌ Not supported | ✅ Full control |
| CIS-hardened AMI | ❌ Not supported (Bottlerocket only) | ✅ Custom AMI |
| Karpenter | Built-in (managed) | Self-installed |

**Rule**: Use Auto Mode for inference clusters and standard GenAI workloads. Use self-managed node groups when you need custom kubelet (e.g., `topologyManagerPolicy` for EFA training) or CIS-hardened AMIs for regulated environments.

## Sources

- [EKS Karpenter Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/karpenter.html)
- [EKS AI/ML Networking Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-networking.html)
- [EFA with EKS](https://docs.aws.amazon.com/eks/latest/userguide/node-efa.html)
- [Manage Neuron devices on Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/device-management-neuron.html)
- [EKS Optimized AMIs](https://docs.aws.amazon.com/eks/latest/userguide/eks-optimized-amis.html)
- [EC2 Capacity Blocks for ML — pricing](https://aws.amazon.com/ec2/capacityblocks/pricing/)
- [EC2 — Find and purchase Capacity Blocks](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-purchase.html)
- [EC2 — Capacity Blocks pricing and billing](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-pricing-billing.html)
- [Karpenter — Utilizing ODCRs and Capacity Blocks](https://karpenter.sh/docs/tasks/odcrs/)
- [EKS — Manage compute for AI/ML workloads with Auto Mode and Karpenter](https://docs.aws.amazon.com/eks/latest/userguide/ml-node-pools.html)
- [EKS — Control deployment of workloads into Capacity Reservations with Auto Mode](https://docs.aws.amazon.com/eks/latest/userguide/auto-odcr.html)
- [How to run AI model inference with GPUs on Amazon EKS Auto Mode](https://aws.amazon.com/blogs/containers/how-to-run-ai-model-inference-with-gpus-on-amazon-eks-auto-mode)
- [`awslabs/ai-on-eks`](https://github.com/awslabs/ai-on-eks)
