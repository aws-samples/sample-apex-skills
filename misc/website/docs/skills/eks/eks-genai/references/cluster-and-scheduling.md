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
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 60s
```

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

## Device Plugins — NVIDIA vs Neuron Device Plugin vs Neuron DRA

| Plugin | Exposes | Compatible with Karpenter? | Compatible with Auto Mode? | Use when |
|---|---|---|---|---|
| **NVIDIA device plugin** (DaemonSet) | `nvidia.com/gpu` | ✅ Yes | ✅ Embedded — no install needed | Any NVIDIA GPU workload |
| **AWS Neuron device plugin** (DaemonSet) | `aws.amazon.com/neuroncore`, `aws.amazon.com/neurondevice` | ✅ Yes | ✅ Yes | Neuron workloads on Karpenter or Auto Mode |
| **AWS Neuron DRA driver** (K8s 1.34+) | `ResourceClaim`-based allocation | ❌ **Not compatible** | ❌ **Not compatible** | Topology-aware NeuronCore allocation on self-managed node groups only |

**Decision rule**: Use the **Neuron device plugin** (not DRA) with Karpenter and EKS Auto Mode. The Neuron DRA driver offers topology-aware allocation and per-workload Logical NeuronCore config — but only on non-Karpenter clusters with static or Cluster-Autoscaler-managed capacity.

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

For **planned multi-day training**, Capacity Blocks guarantee p5/p5e/trn1/trn2 capacity at pricing **substantially below on-demand** ([pricing page](https://aws.amazon.com/ec2/capacityblocks/pricing/)). Book 1–14 days in advance via the EC2 console or API.

- Use Capacity Blocks for: scheduled training runs, benchmark campaigns, customer demos requiring guaranteed GPU
- Do **not** use for: inference (On-Demand with Karpenter consolidation is more flexible)
- Integration: Karpenter EC2NodeClass `capacityReservationSelectorTerms` targets the Capacity Block reservation

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
- [EC2 Capacity Blocks for ML](https://aws.amazon.com/ec2/capacityblocks/pricing/)
- [How to run AI model inference with GPUs on Amazon EKS Auto Mode](https://aws.amazon.com/blogs/containers/how-to-run-ai-model-inference-with-gpus-on-amazon-eks-auto-mode)
- [`awslabs/ai-on-eks`](https://github.com/awslabs/ai-on-eks)
