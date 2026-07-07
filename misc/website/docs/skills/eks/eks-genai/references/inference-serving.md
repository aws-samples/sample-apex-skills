---
title: "Inference Serving Frameworks on EKS"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/inference-serving.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-genai/references/inference-serving.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/inference-serving.md). Edit the source, not this page.
:::

# Inference Serving Frameworks on EKS

Opinionated guidance for choosing and configuring the LLM inference engine on Amazon EKS. Default → **vLLM**; deviate only when a specific flag below fires.

## Framework Decision Table

| Framework | Default for… | When to recommend | When NOT to recommend |
|-----------|-------------|-------------------|----------------------|
| **vLLM** | All LLM inference | Transformer-family models (Llama, Mistral, Qwen, Falcon); need OpenAI-compatible API; GPU or Neuron (via `neuronx-distributed-inference`); PagedAttention memory efficiency; continuous batching | Vision/audio/multi-modal; TensorRT-optimized pipelines; non-Transformer architectures |
| **Ray Serve + KubeRay** | Multi-replica autoscaling | Heterogeneous GPU/Neuron fleets; dynamic replica scaling; Spot integration; multi-model on one cluster; compose vLLM as a Ray Serve deployment | Single-replica deployments (over-engineered); team has no Ray experience and simple workload |
| **NVIDIA Triton** | Multi-framework serving | Multiple model formats on one server (ONNX + TensorRT + PyTorch); ensemble pipelines; model versioning with A/B traffic split | Single-model LLM serving (vLLM is simpler + higher throughput for LLMs) |
| **NVIDIA Dynamo** | Disaggregated prefill/decode | Frontier-scale (70B+) multi-node inference; separate prefill workers from decode workers; KV-cache transfer across nodes | Newer than vLLM (announced at NVIDIA GTC, March 2025); vLLM is more battle-tested for most deployments today |
| **KServe** | Scale-to-zero inference | Moderate-traffic models needing scale-to-zero; GPU cost savings during idle; Knative-based serverless model serving | High-throughput LLM serving (cold-start latency is unacceptable for chat); max QPS lower than vLLM+Ray |

**Rule of thumb:** vLLM alone for single-model ≤ 2 replicas; vLLM + Ray Serve for multi-replica autoscaling or multi-model; Triton when TensorRT or multi-framework is the hard requirement; KServe when scale-to-zero matters more than p99 latency.

## vLLM — The Default LLM Engine

vLLM is deployed via an [AWS Deep Learning Container](https://aws.amazon.com/ai/machine-learning/containers/) on EKS. It provides PagedAttention (near-zero KV-cache waste), continuous batching, an OpenAI-compatible `/v1/completions` and `/v1/chat/completions` API, and supports both NVIDIA GPU and AWS Neuron (via `neuronx-distributed-inference`).

### Key vLLM Serving Arguments

```bash
# Core performance tuning
--gpu-memory-utilization 0.90          # fraction of GPU VRAM for KV-cache; 0.85-0.95 typical
--max-model-len 8192                   # max sequence length; OOM if too high for available VRAM
--tensor-parallel-size 1               # number of GPUs per model replica (TP); match to model size

# Model loading — Run:ai Streamer (no PV/PVC needed)
--load-format runai_streamer
--model-loader-extra-config '{"concurrency": 16}'

# Tool calling (Mistral family — required for vLLM 0.9.0+)
--enable-auto-tool-choice
--tool-call-parser mistral
--config-format mistral

# KV-cache tiering (when LMCache is wired — see kv-cache-and-cost.md)
--kv-transfer-config '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'
--enforce-eager                        # required with FLASHINFER backend + LMCache
```

Environment variables commonly set alongside:

```bash
VLLM_ATTENTION_BACKEND=FLASHINFER      # required for LMCache integration
PYTHONHASHSEED=0                       # cross-pod cache-key stability
```

### Workshop-Validated Configuration

The current NVIDIA workshop serves **Ministral-3-8B-Instruct-2512** on **g6e.2xlarge (L40S)** with the Run:ai Streamer pulling weights directly from S3 — no PersistentVolume required for standalone vLLM. This is the fastest cold-start path for models ≤ 48 GB.

Reference: [Generative AI on EKS using NVIDIA GPU Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/029d6c4e-4775-41c9-85ff-9f5360f32a15); [`awslabs/ai-on-eks` inference blueprints](https://github.com/awslabs/ai-on-eks).

## Model-Loading Patterns

| Pattern | How it works | When to use | Trade-off |
|---------|-------------|-------------|-----------|
| **Run:ai Streamer (S3 direct)** | `--load-format=runai_streamer --model-loader-extra-config='{"concurrency":16}'` streams weights from S3 at pod start | Standalone vLLM; models ≤ ~48 GB; want zero PV/PVC management | Cold-start time proportional to model size ÷ S3 bandwidth; no local cache across restarts |
| **Mountpoint for S3 CSI** | PV/PVC with `ReadOnlyMany`; kernel-level FUSE mount; per-pod 5-10 GB local cache | Ray Serve multi-replica (shared model mount); models > 48 GB; want OS-level caching | Requires PV/PVC manifests; FUSE overhead (negligible for sequential reads) |
| **Bake into container image** | Model weights in the Docker layer | Tiny models (< 5 GB); air-gapped / disconnected environments | Couples model release to image release; bloated images; slow pull |
| **FSx for Lustre pre-cache** | Model weights pre-staged on FSx; pods mount via FSx CSI | Training clusters that also serve eval checkpoints; ultra-low latency model swap | Requires FSx provisioning + same-AZ constraint; overkill for inference-only |

**Decision rule:** Default → Run:ai Streamer for standalone vLLM (simplest, no PVC). Switch to Mountpoint S3 CSI when using Ray Serve (the KubeRay RayService CRD mounts the PV across head + workers). Use FSx only when the same cluster does training + inference and checkpoint-to-serve latency matters.

## Ray Serve + KubeRay — Multi-Replica Autoscaling

When you need >1 replica, autoscaling, or multi-model routing at the framework level, wrap vLLM inside a Ray Serve deployment managed by the KubeRay operator.

### KubeRay Setup

```bash
# Install KubeRay operator (Helm)
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm install kuberay-operator kuberay/kuberay-operator --version 1.1.0
```

Deploy a **RayService** CRD — the operator manages the Ray cluster lifecycle and rolling updates:

```yaml
apiVersion: ray.io/v1
kind: RayService
metadata:
  name: vllm-serve
spec:
  serveConfigV2: |
    applications:
      - name: llm
        import_path: serve_vllm:deployment
        deployments:
          - name: VLLMDeployment
            num_replicas: 2
            ray_actor_options:
              num_gpus: 1
  rayClusterConfig:
    headGroupSpec:
      rayStartParams:
        dashboard-host: "0.0.0.0"
      template:
        spec:
          nodeSelector:
            node.kubernetes.io/instance-type: m5.xlarge   # Head on CPU — NOT GPU
    workerGroupSpecs:
      - groupName: gpu-workers
        replicas: 2
        rayStartParams: {}
        template:
          spec:
            nodeSelector:
              node.kubernetes.io/instance-type: g6e.2xlarge
            containers:
              - name: ray-worker
                resources:
                  limits:
                    nvidia.com/gpu: "1"
```

**Critical rule:** Ray Head should NOT be co-located on GPU nodes in production. The workshop co-locates head + workers on GPU for time efficiency only — production deployments place the head on a CPU instance (m5.xlarge or similar) to avoid wasting GPU memory on scheduler/GCS processes.

### Model Mount via Mountpoint for S3 CSI

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: mistral-model-pv
spec:
  capacity:
    storage: 100Gi
  accessModes:
    - ReadOnlyMany
  csi:
    driver: s3.csi.aws.com
    volumeHandle: s3-model-bucket
    volumeAttributes:
      bucketName: my-model-bucket
      mountOptions: "--prefix models/mistral/"
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: mistral-model-pvc
spec:
  accessModes:
    - ReadOnlyMany
  resources:
    requests:
      storage: 100Gi
  volumeName: mistral-model-pv
```

Workers mount this PVC at `/models/mistral` and vLLM reads weights from the local path — the S3 CSI driver handles lazy-load + caching transparently.

## NVIDIA Triton Inference Server

Use Triton when you need:

- **Multi-framework** on one server — ONNX, TensorRT, PyTorch, TensorFlow, Python backend
- **Model ensembles** — chain pre-processing → model → post-processing in a single request
- **TensorRT optimization** — max throughput for latency-critical non-LLM models (vision, embedding)

Triton on EKS is shipped in [`awslabs/ai-on-eks` `blueprints/inference/nvidia-triton`](https://github.com/awslabs/ai-on-eks). Deploy via the NVIDIA Triton Helm chart with model repository on S3.

**When NOT to use Triton for LLMs:** vLLM's PagedAttention + continuous batching outperforms Triton's default LLM backend for autoregressive generation. Use Triton only when TensorRT-LLM is compiled and the team maintains the TRT-LLM build pipeline.

## NVIDIA Dynamo — Disaggregated Inference

Dynamo (announced at NVIDIA GTC in March 2025) separates prefill and decode into independent worker pools — prefill workers handle prompt processing while decode workers generate tokens. This enables:

- Independent scaling of prefill vs decode based on workload mix
- KV-cache transfer between nodes (prefill produces KV, decode consumes it)
- Higher overall GPU utilization for frontier-scale (70B+) models

Reference: [Accelerate generative AI inference with NVIDIA Dynamo and Amazon EKS](https://aws.amazon.com/blogs/machine-learning/accelerate-generative-ai-inference-with-nvidia-dynamo-and-amazon-eks/).

**Recommendation:** Evaluate Dynamo for p5/p6 multi-node deployments serving 70B+ models where prefill latency is the bottleneck. For ≤ 30B single-node deployments, vLLM with standard batching is simpler and sufficient.

## KServe — Scale-to-Zero

KServe (built on Knative) enables serverless model inference — pods scale to zero when idle, saving GPU cost during off-hours. Trade-off: cold-start latency (model reload) on first request after scale-down.

**When to use:** Dev/test endpoints; internal tools with sporadic traffic; models where 30-60s cold-start is acceptable. **When NOT:** Production chat/interactive endpoints; latency SLA < 5s p99.

## Neuron Backend (vLLM on Inferentia2 / Trainium)

vLLM supports AWS Neuron via `neuronx-distributed-inference`. Same OpenAI-compatible API, same serving args — the backend compiles the model for NeuronCores instead of CUDA. Deploy on `inf2` instances for up to ~40% better price-performance on supported Transformer architectures.

Key difference: Neuron requires a one-time model compilation step (`neuron_compile`) before serving. Pre-compile offline and ship the compiled artifact via S3/FSx — do not compile at pod startup in production.

Reference: [`awslabs/ai-on-eks` `blueprints/inference/neuron-vllm`](https://github.com/awslabs/ai-on-eks); [Generative AI on EKS using AWS Neuron Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/e21aadbd-23cb-4207-bd09-625e6de08a6c).

## Sources

- [EKS AI/ML Best Practices — Performance](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-performance.html)
- [Quickstart: High-throughput LLM inference with vLLM on Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/ml-realtime-inference-llm-inference-vllm.html)
- [Deploy LLMs on Amazon EKS using vLLM Deep Learning Containers](https://aws.amazon.com/blogs/architecture/deploy-llms-on-amazon-eks-using-vllm-deep-learning-containers/)
- [`awslabs/ai-on-eks`](https://github.com/awslabs/ai-on-eks) — inference blueprints
- [Generative AI on EKS using NVIDIA GPU Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/029d6c4e-4775-41c9-85ff-9f5360f32a15)
- [Accelerate generative AI inference with NVIDIA Dynamo and Amazon EKS](https://aws.amazon.com/blogs/machine-learning/accelerate-generative-ai-inference-with-nvidia-dynamo-and-amazon-eks/)
