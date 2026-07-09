# Observability for GPU / ML Workloads on Amazon ECS

GPU/ML observability on ECS adds three concerns over standard container monitoring: **accelerator utilization/memory**, **per-request/inference latency**, and **cost attribution** for expensive GPU/Neuron capacity. The primary AWS-native path is **CloudWatch Container Insights with enhanced observability**.

## GPU Metrics — Two Different Paths (MI vs EC2 launch type)

This is the single most-often-wrong claim about GPU observability on ECS: the **agentless DCGM path is Managed-Instances-only**, not "all ECS NVIDIA instances." Get the path right for the launch model.

### Managed Instances — agentless DCGM via Container Insights enhanced observability

For **ECS Managed Instances running NVIDIA GPU-enabled EC2 types**, Container Insights with enhanced observability collects GPU metrics from NVIDIA DCGM at the container, task, and instance levels, with **no additional agent installation** ([Monitoring ECS Managed Instances — GPU monitoring](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html)). Every one of these GPU metrics is documented as **"Available only for Amazon ECS Managed Instances running NVIDIA GPU-enabled Amazon EC2 instance types"** ([Container Insights enhanced observability metrics for ECS](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-enhanced-observability-metrics-ECS.html)).

- **GPU metrics are NOT collected with basic Container Insights** — you must **enable enhanced observability**.
- Metrics land in the `ECS/ContainerInsights` namespace. The **actual metric names** are `TaskGPUUtilization`, `TaskGPUMemoryUtilization`, `TaskGPUMemoryUsed`/`TaskGPUMemoryTotal`, `TaskGPUPowerDraw`, `TaskGPUTemperature`, `TaskGPURestartAppXidCount` (and the `ContainerGPU*` and `InstanceGPULimit`/`InstanceGPUUsageTotal` families) — **not** the EKS-style `*_gpu_utilization` names. Cite these exact names.

Enable on the cluster:

```bash
aws ecs update-cluster-settings \
  --cluster my-gpu-cluster \
  --settings name=containerInsights,value=enhanced
```

### ECS-on-EC2 launch type — no agentless DCGM path

On the **EC2 launch type there is no agentless DCGM collection**. To get GPU telemetry you deploy an agent:
- **CloudWatch agent with `nvidia_smi`** — the CloudWatch-agent collects host-level NVIDIA GPU metrics (utilization, memory, temperature, power) per **instance**. Simplest, but **host-level only — no per-task attribution**.
- **DCGM exporter (or the Neuron/DCGM exporter sidecar) → CloudWatch/AMP/Prometheus** — deploy the exporter as a container to get **per-task / per-GPU** granularity, at the cost of running and sizing the exporter yourself.

So if an inference service on the **EC2 launch type** wants GPU utilization as an autoscaling signal (see [inference-serving.md](inference-serving.md)), it must publish it via one of these agents — the agentless MI metrics won't exist.

## What to Watch (and rough thresholds)

| Signal | Why it matters | Guidance |
|---|---|---|
| **GPU utilization** | Are you paying for idle GPUs? | <50% sustained → consolidate/right-size; >90% sustained → capacity risk |
| **GPU memory utilization** | KV-cache / model headroom | >~90% → OOM risk; upsize instance or reduce batch/context |
| **GPU temperature** | Thermal throttling | Alert high temps; correlate with throughput drops |
| **Inference latency (TTFT / p99)** | User-perceived quality | Publish from the serving engine as a custom CloudWatch metric |
| **In-flight / queued requests** | Saturation signal for autoscaling | Drive ECS Service Auto Scaling ([inference-serving.md](inference-serving.md)) |
| **EFA traffic (multi-node training)** | Inter-node fabric health | Packet drops / throughput dips precede training stalls |

## Neuron (Inferentia / Trainium) Metrics

For Neuron workloads, use the **AWS Neuron Monitor** tooling / `neuron-monitor` (part of the Neuron SDK on the ECS Neuron-optimized AMI) and publish to CloudWatch (via `neuron-monitor-cloudwatch.py`) or a Prometheus scrape. Its **documented metric groups** are: `neuroncore_counters` (per-NeuronCore utilization), `memory_used`, `neuron_runtime_vcpu_usage`, `execution_stats` (error count + latency), and the system groups `vcpu_usage`, `memory_info`, and `neuron_hw_counters` — where `neuron_hw_counters` is **ECC event counters only** (corrected/uncorrected DRAM and SRAM ECC), *not* general hardware telemetry ([neuron-monitor User Guide](https://awsdocs-neuron.readthedocs-hosted.com/en/latest/tools/neuron-sys-tools/neuron-monitor-user-guide.html)).

Two corrections to a common mis-statement: **neuron-monitor has no EFA metric group** — get EFA Tx/Rx and drops from `ethtool` / `/sys/class/infiniband/*/ports/*/counters` or the CloudWatch agent, not neuron-monitor. And **neuron-monitor exposes no compilation-cache hit/miss metric** — don't monitor for it; instead enforce pre-compilation at the pipeline level (ship the compiled artifact — see [neuron-on-ecs.md](neuron-on-ecs.md)).

## Standard ECS Telemetry (still applies)

- **CloudWatch metrics** — CPU, memory, network at cluster/service/task level; Container Insights adds task/instance-level and diagnostics. **Retention:** 1-minute datapoints are kept **15 days**, but metrics persist up to **15 months** at coarser resolution (5-min to 63 days, 1-hour to 455 days) — data is aggregated, not deleted ([CloudWatch metrics retention](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_concepts.html)). Note Container Insights metrics are billed as custom metrics.
- **Logs** — `awslogs` driver to CloudWatch Logs, or **FireLens** (Fluent Bit) to route to OpenSearch/S3/third-party. Keep log routing off the GPU's critical path.
- **CloudTrail** — API audit (task launches, S3 model-bucket data events).
- **Third-party** — Datadog/Dynatrace/New Relic as agent sidecars; they can scrape DCGM/Neuron and the serving-engine `/metrics` endpoint.

## Cost Attribution

GPU/Neuron capacity is the dominant cost. Attribute it with:
- **AWS Split Cost Allocation Data (SCAD)** for per-task ECS cost allocation in Cost Explorer.
- **Cost allocation tags** on services/task definitions (team, model, environment).
- **Custom per-request accounting** from the serving engine (tokens/requests per tenant) when you need per-tenant chargeback.

## Keep Observability Off the GPU's Back

DCGM collection is agentless **only on Managed Instances** (no scheduling concern there), but on the EC2 launch type the CloudWatch-agent / DCGM-exporter and any **heavy log-processing or metrics sidecars** should be sized carefully — GPU-instance memory is precious. Don't co-locate memory-hungry aggregation with large model tasks; prefer routing to managed backends (CloudWatch, AMP, third-party SaaS).

## Sources

- [Monitoring Amazon ECS Managed Instances (GPU / DCGM via Container Insights enhanced)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html)
- [Amazon ECS Container Insights with enhanced observability metrics (GPU metric names; MI-only)](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-enhanced-observability-metrics-ECS.html)
- [Amazon ECS CloudWatch Container Insights](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-container-insights.html) · [CloudWatch metrics retention](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_concepts.html)
- [Gain operational insights for NVIDIA GPU workloads using CloudWatch Container Insights](https://aws.amazon.com/blogs/mt/gain-operational-insights-for-nvidia-gpu-workloads-using-amazon-cloudwatch-container-insights/)
- [AWS Neuron Monitor](https://awsdocs-neuron.readthedocs-hosted.com/en/latest/tools/neuron-sys-tools/neuron-monitor-user-guide.html)
- [Send Amazon ECS logs to CloudWatch / FireLens](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_firelens.html)
- [AWS Split Cost Allocation Data](https://docs.aws.amazon.com/cur/latest/userguide/split-cost-allocation-data.html)
