---
title: "Observability for GenAI on EKS"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/observability.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-genai/references/observability.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/observability.md). Edit the source, not this page.
:::

# Observability for GenAI on EKS

GenAI observability differs from standard Kubernetes monitoring in three fundamental ways: (1) accelerator utilization and memory pressure are first-class metrics — not afterthoughts; (2) per-token and per-request latency distributions matter more than per-pod CPU; (3) cost attribution per workload and per tenant is non-negotiable. This reference covers the full pipeline from GPU/Neuron metrics export through dashboards and alerting.

## The Standard Pipeline

```text
┌─────────────────────────────┐
│ NVIDIA DCGM Exporter        │──┐
│ (DaemonSet on GPU nodes)    │  │
└─────────────────────────────┘  │
                                 ├──▶ Prometheus ──▶ Grafana (in-cluster)
┌─────────────────────────────┐  │         │
│ AWS Neuron Monitor           │──┘         │ remote-write (SigV4)
│ (DaemonSet on Neuron nodes) │            ▼
└─────────────────────────────┘    Amazon Managed Prometheus (AMP)
                                           │
┌─────────────────────────────┐            ▼
│ vLLM / Ray metrics          │    Amazon Managed Grafana (AMG)
│ (/metrics endpoint per pod) │    (production — persistent dashboards)
└─────────────────────────────┘
```

**Dev/test:** self-hosted Prometheus + Grafana via `kube-prometheus-stack` is acceptable.
**Production:** Amazon Managed Prometheus (AMP) + Amazon Managed Grafana (AMG) — no operational burden, cross-cluster visibility, IAM-integrated access control.

## Workshop-Validated Stack (Current)

The GenAI-on-EKS workshop deploys the following validated versions:

| Component | Chart / Version | Namespace | Notes |
|-----------|----------------|-----------|-------|
| kube-prometheus-stack | Helm chart v69.7.4 | `monitoring` | Prometheus + Grafana + alerting rules |
| grafana-operator | v5.16.0 | `monitoring` | Manages GrafanaDashboard CRDs |
| NVIDIA DCGM Exporter | `gpu-helm-charts/dcgm-exporter` (repo: `https://nvidia.github.io/dcgm-exporter/helm-charts`) | `monitoring` | Port 9400, ServiceMonitor, 30s scrape |
| AMP remote-write | SigV4 authentication | — | Prometheus → AMP via `sigv4` proxy |
| Grafana AMP datasource | `grafana-amazonprometheus-datasource` plugin v2.3.2 | — | EKS Pod Identity auth to AMP |

## NVIDIA DCGM Exporter (GPU Metrics)

### What It Exposes

DCGM (Data Center GPU Manager) Exporter runs as a DaemonSet on every GPU node and exposes per-GPU metrics at `:9400/metrics`:

| Metric | What it tells you |
|--------|-------------------|
| `DCGM_FI_DEV_GPU_UTIL` | GPU compute utilization (%) — target 80–95% for inference, >90% for training |
| `DCGM_FI_DEV_FB_USED` / `DCGM_FI_DEV_FB_FREE` | Framebuffer (HBM) memory used/free — critical for KV-cache sizing |
| `DCGM_FI_DEV_POWER_USAGE` | Power draw (watts) — correlates with cost and thermal throttling |
| `DCGM_FI_DEV_SM_CLOCK` | Streaming Multiprocessor clock speed — drops indicate throttling |
| `DCGM_FI_DEV_MEM_CLOCK` | Memory clock — same throttling signal |
| `DCGM_FI_DEV_GPU_TEMP` | Temperature — alert above 85°C |

### Deployment

```yaml
# DCGM Exporter — targets only GPU nodes via nodeSelector
nodeSelector:
  karpenter.sh/nodepool: gpu

# ServiceMonitor (for kube-prometheus-stack auto-discovery)
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: dcgm-exporter
  labels:
    release: kube-prometheus-stack    # must match Prometheus label selector
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: dcgm-exporter
  endpoints:
    - port: metrics
      interval: 30s
```

Key configuration:
- **nodeSelector:** `karpenter.sh/nodepool: gpu` — ensures DCGM only schedules on GPU nodes.
- **ServiceMonitor label:** `release: kube-prometheus-stack` — required for kube-prometheus-stack's Prometheus to auto-discover the target.
- **Scrape interval:** 30 seconds is the workshop default; reduce to 15s for latency-sensitive alerting.

## AWS Neuron Monitor (Trainium / Inferentia Metrics)

### What It Exposes

The Neuron Monitor container runs as a DaemonSet on Neuron nodes and exposes NeuronCore utilization, HBM usage, and EFA interface health to Prometheus (and optionally CloudWatch Container Insights).

| Metric category | Signals |
|-----------------|---------|
| NeuronCore utilization | Per-core compute %, memory %, datapath utilization |
| HBM memory | Used / free / total per NeuronDevice |
| EFA interface | Tx/Rx bytes, packet drops (critical for multi-node training) |
| Compilation cache | Hit/miss ratio (indicates whether models are pre-compiled) |

### Two Integration Paths

1. **Prometheus → Grafana:** Same ServiceMonitor pattern as DCGM. Custom dashboards for Neuron metrics.
2. **CloudWatch Observability EKS add-on:** Auto-discovers Neuron health metrics from Trn1/Inf2 and EFA interfaces via Container Insights — zero Prometheus config needed; limited customization.

Reference: [Scale and simplify ML workload monitoring on Amazon EKS with AWS Neuron Monitor container](https://aws.amazon.com/blogs/machine-learning/scale-and-simplify-ml-workload-monitoring-on-amazon-eks-with-aws-neuron-monitor-container/).

## vLLM and Ray Dashboards

### Pre-Built Dashboards (Workshop-Validated)

The workshop ships these Grafana dashboards as GrafanaDashboard CRDs (managed by grafana-operator):

| Dashboard | Key panels | Source |
|-----------|-----------|--------|
| **NVIDIA DCGM** | GPU util, memory, power, temperature, SM clock per GPU per node | DCGM Exporter metrics |
| **vLLM** | TTFT, Time Per Output Token, Time In Queue, Request Prompt Tokens, Num Preemptions | vLLM `/metrics` endpoint |
| **vLLM-Ray** | Same vLLM metrics aggregated across Ray Serve replicas | Ray + vLLM combined |
| **Ray Default** | Cluster resources, node status, object store | Ray head metrics |
| **Ray Serve** | Request latency, throughput, replica count, queue depth | Ray Serve metrics |
| **Ray Serve Deployment** | Per-deployment replica health, autoscaling decisions | Ray Serve metrics |

### GenAI-Specific Metrics That Matter

These are the metrics that distinguish GenAI observability from standard web-service monitoring:

| Metric | Why it matters | Alert threshold (guidance) |
|--------|---------------|---------------------------|
| **TTFT (Time To First Token)** | User-perceived latency — the time from request to first streamed token | >500 ms for chat; >2 s for batch |
| **Time Per Output Token (TPOT)** | Streaming speed — directly impacts user experience for long responses | >100 ms/token for interactive |
| **Time In Queue** | Saturation signal — requests waiting for a free slot in vLLM's scheduler | >1 s sustained = scale up |
| **Num Preemptions** | KV-cache pressure — vLLM evicting in-progress requests to serve new ones | >0 sustained = increase `gpu_memory_utilization` or add replicas |
| **GPU Utilization** | Efficiency — are you paying for idle GPUs? | <50% sustained = consolidate; >95% sustained = capacity risk |
| **GPU Memory (FB Used)** | KV-cache headroom — overfull = OOM; underfull = wasted capacity | >90% with preemptions = critical |
| **GPU Power** | Cost proxy + throttling indicator | Sudden drop = throttling; correlate with clock speed |
| **SM Clock** | Throttling confirmation — clock reduction means thermal or power throttling | Below base clock = investigate cooling/power |

### vLLM Metrics Endpoint

vLLM exposes Prometheus metrics at `/metrics` on the serving port. Key metric names:

```text
vllm:time_to_first_token_seconds      # histogram
vllm:time_per_output_token_seconds    # histogram
vllm:e2e_request_latency_seconds      # histogram
vllm:request_queue_time_seconds       # histogram (Time In Queue)
vllm:num_preemptions_total            # counter
vllm:num_requests_running             # gauge
vllm:num_requests_waiting             # gauge
vllm:gpu_cache_usage_perc             # gauge (KV-cache utilization)
vllm:request_prompt_tokens            # histogram
vllm:request_generation_tokens        # histogram
```

## Amazon Managed Prometheus (AMP) + Amazon Managed Grafana (AMG)

### Why AMP for Production

- **No Prometheus operational burden** — no disk sizing, no retention management, no HA configuration.
- **Cross-cluster** — multiple EKS clusters remote-write to one AMP workspace; single-pane view across dev/staging/prod.
- **IAM-integrated** — SigV4 authentication for writes; EKS Pod Identity for Grafana reads.
- **Retention** — 150 days default; configurable.

### Remote-Write Configuration

Prometheus (from kube-prometheus-stack) remote-writes to AMP with SigV4 authentication:

```yaml
# Prometheus remote-write to AMP (in kube-prometheus-stack values)
prometheus:
  prometheusSpec:
    remoteWrite:
      - url: https://aps-workspaces.<region>.amazonaws.com/workspaces/<workspace-id>/api/v1/remote_write
        sigv4:
          region: <region>
        queueConfig:
          maxSamplesPerSend: 1000
          maxShards: 200
          capacity: 2500
```

### Grafana → AMP Datasource

In-cluster Grafana queries AMP using the `grafana-amazonprometheus-datasource` plugin (v2.3.2):

- **Authentication:** EKS Pod Identity — Grafana's ServiceAccount assumes an IAM role with `aps:QueryMetrics` permission.
- **No credentials in Grafana config** — Pod Identity handles rotation automatically.

## Cost Attribution Per Workload / Tenant

GenAI clusters are expensive. "How much does Team X's inference cost?" is a board-level question.

### Approaches

| Tool | Granularity | Effort |
|------|-------------|--------|
| **Kubecost** | Per-namespace, per-deployment, per-label | Low — Helm install + configure |
| **AWS Split Cost Allocation Data (SCAD)** | Per-pod EKS cost allocation (GA) | Low — enable in Cost Explorer |
| **LiteLLM token accounting** | Per-API-key, per-tenant token + cost | Medium — requires LiteLLM gateway |
| **Custom (Prometheus + recording rules)** | Per-label GPU-hours × instance cost | High — manual but flexible |

**Recommended pattern:** Enable **SCAD** for infrastructure cost visibility + deploy **LiteLLM** for per-request token cost attribution. Together they answer both "how much GPU time did this namespace consume?" and "how much did this tenant's API calls cost in model-tokens?"

## Critical Rule — Keep Observability Off GPU/Neuron Nodes

> **Observability pods (Prometheus, Grafana, DCGM Exporter excluded) must NOT run on GPU/Neuron nodes.**

DCGM Exporter itself must run on GPU nodes (it reads the GPU driver). But Prometheus server, Grafana, Alertmanager, grafana-operator, and any log aggregation (FluentBit) should be scheduled on **dedicated CPU nodes** or a separate CPU NodePool.

Why: GPU/Neuron node memory is precious — a single 70B model in fp16 consumes ~140 GB of HBM. Prometheus with 2-week retention can consume 10–50 GB RAM. Memory contention between observability and model loading causes OOM kills and preemptions.

Implementation:

```yaml
# Anti-affinity / node selector for Prometheus
nodeSelector:
  karpenter.sh/nodepool: system       # CPU-only NodePool
tolerations: []                        # no GPU/Neuron tolerations
```

## Alerting Rules (Starter Set)

```yaml
# PrometheusRule for GenAI alerts
groups:
  - name: genai-gpu-alerts
    rules:
      - alert: GPUMemoryPressure
        expr: DCGM_FI_DEV_FB_USED / (DCGM_FI_DEV_FB_USED + DCGM_FI_DEV_FB_FREE) > 0.92
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "GPU {{ $labels.gpu }} on {{ $labels.instance }} memory >92%"

      - alert: vLLMHighQueueTime
        expr: histogram_quantile(0.95, rate(vllm:request_queue_time_seconds_bucket[5m])) > 2
        for: 3m
        labels:
          severity: critical
        annotations:
          summary: "vLLM p95 queue time >2s — scale up replicas"

      - alert: vLLMPreemptions
        expr: rate(vllm:num_preemptions_total[5m]) > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "vLLM preemptions detected — KV-cache pressure"

      - alert: GPUThermalThrottle
        expr: DCGM_FI_DEV_GPU_TEMP > 85
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "GPU {{ $labels.gpu }} temperature >85°C — throttling likely"
```

## Neuron-Specific Observability Notes

- Neuron Monitor requires the **Neuron SDK runtime** installed on Neuron nodes (comes with EKS-optimized Neuron AMI).
- For **CloudWatch Container Insights** integration, install the **CloudWatch Observability EKS add-on** — it auto-discovers Neuron device metrics without additional Prometheus config.
- **EFA metrics** from Neuron Monitor are critical for multi-node training — packet drops or throughput degradation indicate network fabric issues before they manifest as training loss spikes.

## Sources

- [EKS AI/ML Best Practices — Observability](https://docs.aws.amazon.com/eks/latest/best-practices/aiml.html)
- [Scale and simplify ML workload monitoring on Amazon EKS with AWS Neuron Monitor container](https://aws.amazon.com/blogs/machine-learning/scale-and-simplify-ml-workload-monitoring-on-amazon-eks-with-aws-neuron-monitor-container/)
- [NVIDIA DCGM Exporter Helm Charts](https://nvidia.github.io/dcgm-exporter/helm-charts)
- [Amazon Managed Service for Prometheus](https://docs.aws.amazon.com/prometheus/latest/userguide/what-is-Amazon-Managed-Service-Prometheus.html)
- [Amazon Managed Grafana](https://docs.aws.amazon.com/grafana/latest/userguide/what-is-Amazon-Managed-Grafana.html)
- [`awslabs/ai-on-eks`](https://github.com/awslabs/ai-on-eks) — pre-built DCGM + vLLM + Ray dashboards
- [Guidance for Scalable Model Inference and Agentic AI on Amazon EKS](https://aws.amazon.com/solutions/guidance/scalable-model-inference-and-agentic-ai-on-amazon-eks/)
