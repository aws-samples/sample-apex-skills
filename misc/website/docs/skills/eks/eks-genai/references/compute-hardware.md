---
title: "Compute & Hardware — NVIDIA GPU vs AWS Neuron"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/compute-hardware.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-genai/references/compute-hardware.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/compute-hardware.md). Edit the source, not this page.
:::

# Compute & Hardware — NVIDIA GPU vs AWS Neuron

The single most-impactful decision in any GenAI-on-EKS architecture. AWS docs explicitly state: *"When your workloads permit it, we recommend that you consider using Neuron"* ([EKS ML Get Started](https://docs.aws.amazon.com/eks/latest/userguide/ml-get-started.html)). **Do not reflexively pick NVIDIA GPU** — evaluate Neuron first for Transformer-family LLMs.

## Layer-1 Decision Rule

Right hardware = f(workload type × model family × latency × cost posture × team skill × timeline) — never one dimension alone.

- **Default to AWS Neuron** (Trn2/Trn1 training, Inf2 inference) when: model is Transformer-family (Llama, Mistral, Qwen, Falcon) + framework is PyTorch/vLLM + cost-conscious + team can absorb a 1–2 week compilation ramp.
- **Default to NVIDIA GPU** (g6/g6e inference, p5/p5e training) when: fastest time-to-first-success matters, CUDA-only dependencies exist, novel/non-Transformer architectures, or multi-modal models.

## GPU vs Neuron Decision Matrix

| Workload signal | Recommend NVIDIA GPU when… | Recommend AWS Neuron when… |
|---|---|---|
| **Training — frontier (70B+) / novel arch** | Custom CUDA kernels; H100/H200 ecosystem dependency; cutting-edge research | Model is Transformer-family — Trn2 delivers up to **50% cost-to-train savings** vs comparable GPU ([trn1 instance page](https://aws.amazon.com/ec2/instance-types/trn1/)) |
| **Training — fine-tuning (LoRA/PEFT/full)** | Fastest time-to-first-success; broadest tooling | Strong fit if base model has Neuron support (most popular FMs do) |
| **Inference — high-throughput LLM (7B–70B)** | g6 (L4) or g6e (L40S) — broad vLLM-native ecosystem | inf2 — up to **40% better price-performance** for vLLM-supported models ([inf2 instance page](https://aws.amazon.com/ec2/instance-types/inf2/)) |
| **Inference — vision / audio / multi-modal** | Required — Neuron support uneven for non-Transformer architectures | Limited — verify model-specific support before committing |
| **Inference — sub-100ms TTFT** | Best raw latency on H100/H200 | Acceptable on inf2 with TP/PP tuning + ahead-of-time compilation |
| **Customer skill** | Existing CUDA / NVIDIA tooling investment | Willing to add Neuron SDK + compilation step (`torch-neuronx`) |
| **Time-to-first-success** | Fastest path; least new tooling | +1–2 weeks ramp; ROI realized at production scale |
| **Production cost optimization** | Acceptable but more expensive per token | Recommend for steady-state production once model is stabilized |

## NVIDIA GPU Instance Quick-Reference

Network/EFA values are the per-instance maximums from the EC2 instance-type pages; EFA generation follows the Nitro version (Nitro v3 = EFA v1, no RDMA; Nitro v4+ = EFA v2/v3, with RDMA).

| Instance | Accelerator | GPU Memory | Network / EFA | Best for |
|---|---|---|---|---|
| **p5.48xlarge** | 8× NVIDIA H100 SXM5 | 640 GB HBM3 | 3200 Gbps, EFA v2 (GPUDirect RDMA) | Frontier pre-training, 100B+ models, multi-node FSDP |
| **p5e.48xlarge** | 8× NVIDIA H200 SXM5 | ~1.1 TB HBM3e | 3200 Gbps, EFA v2 (GPUDirect RDMA) | Same as p5 + larger memory for longer contexts |
| **g6e.48xlarge** | 8× NVIDIA L40S | 384 GB GDDR6 | 400 Gbps, EFA v2 | 70B inference, multi-GPU PEFT fine-tune |
| **g6e.2xlarge** | 1× NVIDIA L40S | 48 GB GDDR6 | Up to 20 Gbps (no EFA) | Single-GPU inference (7B–13B), dev/test, workshop validated |
| **g6.12xlarge** | 4× NVIDIA L4 | 96 GB GDDR6 | 40 Gbps, EFA v2 | 7B–30B inference, cost-sensitive production |
| **g6.48xlarge** | 8× NVIDIA L4 | 192 GB GDDR6 | 100 Gbps, EFA v2 | Larger multi-GPU L4 inference fleets |
| **g5.48xlarge** | 8× NVIDIA A10G | 192 GB GDDR6 | 100 Gbps, EFA v1 (no RDMA) | Multi-modal, NVIDIA NIM, dev/test, legacy workloads |

> **Workshop-validated**: The GenAI-on-EKS NVIDIA workshop runs on **g6e.2xlarge** (1× L40S, 48 GB) on EKS Auto Mode (Kubernetes 1.34) with Bottlerocket. GPU capacity reserved via On-Demand Capacity Reservation (ODCR) patched into the Karpenter EC2NodeClass via `capacityReservationSelectorTerms`.

## AWS Neuron Instance Quick-Reference

Note: Inf2 instances do **not** support EFA — their `inf2.48xlarge` chip-to-chip interconnect is **NeuronLink** (intra-instance), and their external networking is standard ENA. EFA (inter-node fabric) is a Trainium-and-GPU feature.

| Instance | Accelerator | HBM | Network / EFA | Best for |
|---|---|---|---|---|
| **trn2.48xlarge** | 16× Trainium2 | 1.5 TB HBM3 | 3.2 Tbps, EFA v3 (RDMA) | Pre-training (3× compute vs Trn1), large-scale fine-tuning |
| **trn1.32xlarge** | 16× Trainium | 512 GB HBM2e | 800 Gbps, EFA v2 | Pre-training, fine-tuning — **up to 50% cost-to-train savings** |
| **inf2.48xlarge** | 12× Inferentia2 | 384 GB HBM2e | 100 Gbps ENA (no EFA); NeuronLink chip-to-chip | High-throughput LLM inference (30B–70B) |
| **inf2.8xlarge** | 2× Inferentia2 | 64 GB HBM2e | Up to 25 Gbps ENA (no EFA) | Dev/test inference, smaller models (7B–13B) |

## When Each Accelerator Wins — Summary

| Scenario | Winner | Why |
|---|---|---|
| Cost-sensitive Transformer LLM training at scale | **Trainium (Trn2/Trn1)** | Up to 50% cost-to-train savings; EFA for multi-node |
| Cost-sensitive Transformer LLM inference at scale | **Inferentia2 (Inf2)** | Up to 40% better price-performance; vLLM+Neuron supported |
| Fastest time-to-production, any model | **NVIDIA GPU (g6e/p5)** | Broadest ecosystem; zero compilation ramp |
| Novel architecture / custom CUDA kernels | **NVIDIA GPU** | Neuron compilation may not support custom ops |
| Multi-modal (vision+language, audio) | **NVIDIA GPU** | Neuron support is model-specific; verify first |
| Shared dev cluster, multiple small models | **NVIDIA GPU (g6/g5)** | MIG/time-slicing enable multi-tenant sharing |

## GPU Optimization Techniques

### Multi-Instance GPU (MIG) — H100/A100 only

Partitions a single physical GPU into up to 7 isolated instances, each with dedicated memory, cache, and compute. Use for:

- **Multi-tenant dev clusters** — isolate teams on a single p5 node
- **Small-model inference** — run multiple 7B models on one H100 slice
- Requires NVIDIA device plugin configured with MIG strategy (`mixed` or `single`)

MIG profiles on H100 (p5.48xlarge):

| Profile | GPU Memory | Compute | Use case |
|---|---|---|---|
| 1g.10gb | 10 GB | 1/7 SM | Tiny models, embedding inference |
| 2g.20gb | 20 GB | 2/7 SM | 7B quantized inference |
| 3g.40gb | 40 GB | 3/7 SM | 7B–13B FP16 inference |
| 7g.80gb | 80 GB | Full GPU | Single-tenant training/inference |

### GPU Time-Slicing

Multiplexes multiple pods onto a single GPU via temporal sharing (no memory isolation). Use for:

- **Dev/test** environments where isolation is not critical
- **Low-utilization workloads** that don't saturate GPU compute
- Simpler than MIG; no H100/A100 requirement — works on any NVIDIA GPU
- Configure via `nvidia.com/gpu.replicas` in the device plugin ConfigMap

```yaml
# Time-slicing ConfigMap for nvidia-device-plugin
apiVersion: v1
kind: ConfigMap
metadata:
  name: nvidia-device-plugin-config
data:
  config.yaml: |
    version: v1
    sharing:
      timeSlicing:
        replicas: 4    # 4 pods share each physical GPU
```

> **Caution**: Time-slicing provides no memory isolation — one pod's OOM kills the GPU context for all co-located pods. Use only for dev/test.

### Dynamic Resource Allocation (DRA) — Kubernetes 1.31+

Fine-grained GPU partitioning managed by the Kubernetes scheduler. Use for:

- Clusters that need **scheduler-aware** GPU sharing (vs static MIG)
- **Not compatible with Karpenter or EKS Auto Mode** as of 2026 — use only on self-managed node groups with Cluster Autoscaler or static capacity

```yaml
# DRA ResourceClaim example (self-managed clusters only)
apiVersion: resource.k8s.io/v1beta1
kind: ResourceClaim
metadata:
  name: gpu-slice
spec:
  devices:
    requests:
      - name: gpu
        deviceClassName: gpu.nvidia.com
```

### Decision: MIG vs Time-Slicing vs DRA

| Technique | Isolation | Memory isolation | Karpenter compatible | Best for |
|---|---|---|---|---|
| **MIG** | Hardware-level | ✅ Yes | ✅ Yes | Production multi-tenant on H100/A100 |
| **Time-slicing** | None (temporal only) | ❌ No | ✅ Yes | Dev/test density, low-utilization workloads |
| **DRA** | Scheduler-managed | ✅ Yes | ❌ No | Fine-grained sharing on self-managed nodes |

## Neuron Compilation — The Ramp Cost

Neuron requires ahead-of-time compilation (`torch-neuronx` or `neuronx-distributed-inference`). This is the primary adoption friction vs NVIDIA GPU.

**What to expect:**

- First model compilation: 1–2 weeks (includes learning the SDK, debugging graph breaks, tuning TP/PP)
- Subsequent model versions: hours to days (incremental, reuse compilation cache)
- Ship compiled artifacts via S3 or bake into container image — never compile at pod startup

**Mitigation**: Pre-compile models offline in a CI pipeline. Store compiled `.neff` files in S3. Reference them from the serving container at startup. This removes compilation from the critical path entirely.

```yaml
# Neuron pod requesting NeuronCores (device plugin path)
resources:
  limits:
    aws.amazon.com/neuroncore: "2"     # 2 NeuronCores for this workload
  requests:
    aws.amazon.com/neuroncore: "2"
```

## Capacity Planning Guidance

| Workload | Start with | Scale signal |
|---|---|---|
| Inference (7B) | 1× g6e.2xlarge or 1× inf2.8xlarge | TTFT p99 > target → add replicas |
| Inference (30B–70B) | 4× g6e.12xlarge or 1× inf2.48xlarge | GPU memory utilization > 85% → upsize |
| Fine-tuning (7B–13B) | 1× g6e.48xlarge or 1× trn1.32xlarge | Training throughput (tokens/sec) |
| Pre-training (70B+) | 8–64× p5.48xlarge or 4–32× trn2.48xlarge | EFA all-reduce latency, loss convergence |

> **Rule**: Start small, measure, scale. Over-provisioning GPUs is the second-most-expensive mistake (after wrong hardware family).

## Cost-to-Train / Price-Performance Claims (AWS-published)

| Claim | Source |
|---|---|
| Trainium: up to **50% cost-to-train savings** vs comparable EC2 GPU instances | [aws.amazon.com/ec2/instance-types/trn1](https://aws.amazon.com/ec2/instance-types/trn1/) |
| Inferentia2: up to **40% better price-performance** vs comparable EC2 GPU instances | [aws.amazon.com/ec2/instance-types/inf2](https://aws.amazon.com/ec2/instance-types/inf2/) |
| Inferentia2: up to **50% better performance/watt** vs comparable EC2 GPU | [aws.amazon.com/ec2/instance-types/inf2](https://aws.amazon.com/ec2/instance-types/inf2/) |
| Capacity Blocks for ML: **substantially below on-demand** pricing for multi-day reservations | [aws.amazon.com/ec2/capacityblocks/pricing](https://aws.amazon.com/ec2/capacityblocks/pricing/) |

> Always provide **directional ranges with caveats** — actual savings depend on model size, traffic pattern, batch size, sequence length, and configuration. Never give point cost estimates.

## EKS Auto Mode + GPU Note

On EKS Auto Mode, the NVIDIA driver and device plugin are **embedded in the Bottlerocket AMI** — no `gpu-operator` DaemonSet or separate `nvidia-device-plugin` DaemonSet is needed. The "install nvidia-device-plugin" step you see in most guides applies to **self-managed / standard EKS** only. Auto Mode also auto-enables **SOCI parallel pull and unpack** on G/P/Trn instance families with local NVMe (always on as of Nov 19, 2025 — no configuration required), parallelizing image download/decompression for faster GPU-pod starts. Note this is SOCI *parallel pull*, distinct from SOCI lazy/index-based loading (which still needs a pre-built SOCI index in ECR).

## Sources

- [Best Practices for AI/ML Workloads on Amazon EKS](https://docs.aws.amazon.com/eks/latest/best-practices/aiml.html)
- [EKS ML Get Started](https://docs.aws.amazon.com/eks/latest/userguide/ml-get-started.html)
- [Amazon EC2 Trn1 Instances](https://aws.amazon.com/ec2/instance-types/trn1/)
- [Amazon EC2 Inf2 Instances](https://aws.amazon.com/ec2/instance-types/inf2/)
- [EC2 Capacity Blocks for ML](https://aws.amazon.com/ec2/capacityblocks/pricing/)
- [EKS Optimized Accelerated AMIs](https://docs.aws.amazon.com/eks/latest/userguide/eks-optimized-amis.html)
- [Manage Neuron devices on Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/device-management-neuron.html)
- [`awslabs/ai-on-eks`](https://github.com/awslabs/ai-on-eks)
