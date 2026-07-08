# Observability for GPU / ML Workloads on Amazon ECS

GPU/ML observability on ECS adds three concerns over standard container monitoring: **accelerator utilization/memory**, **per-request/inference latency**, and **cost attribution** for expensive GPU/Neuron capacity. The primary AWS-native path is **CloudWatch Container Insights with enhanced observability**.

## GPU Metrics — Container Insights Enhanced Observability

For ECS running **NVIDIA GPU** instances, **Container Insights with enhanced observability collects GPU metrics from NVIDIA DCGM (Data Center GPU Manager) at the container, task, and instance levels** — with **no additional agent installation** required. GPU metrics are collected automatically on supported instance types once enhanced observability is enabled on the cluster ([Monitoring ECS Managed Instances — GPU monitoring](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html)).

- **GPU metrics are NOT collected with basic Container Insights** — you must **enable enhanced observability** to get GPU telemetry.
- Metrics land in CloudWatch (the `ECS/ContainerInsights` enhanced namespace); build dashboards and alarms there.
- Typical DCGM-sourced signals: GPU compute utilization, GPU memory utilization, GPU temperature, at node/task/container granularity (analogous to the EKS Container Insights GPU metric set — e.g. `*_gpu_utilization`, `*_gpu_memory_utilization`, `*_gpu_temperature`).

Enable on the cluster:

```bash
aws ecs update-cluster-settings \
  --cluster my-gpu-cluster \
  --settings name=containerInsights,value=enhanced
```

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

For Neuron workloads, use the **AWS Neuron Monitor** tooling / `neuron-monitor` (part of the Neuron SDK on the ECS Neuron-optimized AMI) to expose NeuronCore utilization, HBM usage, and EFA interface health. Publish to CloudWatch (Container Insights) or a Prometheus scrape. Key categories: per-NeuronCore compute/memory %, HBM used/free per device, EFA Tx/Rx and drops, and compilation-cache hit/miss (a miss ratio > 0 in steady state signals models aren't pre-compiled — see [neuron-on-ecs.md](neuron-on-ecs.md)).

## Standard ECS Telemetry (still applies)

- **CloudWatch metrics** — CPU, memory, network at cluster/service/task level (free, 2-week retention); Container Insights adds task/instance-level and diagnostics.
- **Logs** — `awslogs` driver to CloudWatch Logs, or **FireLens** (Fluent Bit) to route to OpenSearch/S3/third-party. Keep log routing off the GPU's critical path.
- **CloudTrail** — API audit (task launches, S3 model-bucket data events).
- **Third-party** — Datadog/Dynatrace/New Relic as agent sidecars; they can scrape DCGM/Neuron and the serving-engine `/metrics` endpoint.

## Cost Attribution

GPU/Neuron capacity is the dominant cost. Attribute it with:
- **AWS Split Cost Allocation Data (SCAD)** for per-task ECS cost allocation in Cost Explorer.
- **Cost allocation tags** on services/task definitions (team, model, environment).
- **Custom per-request accounting** from the serving engine (tokens/requests per tenant) when you need per-tenant chargeback.

## Keep Observability Off the GPU's Back

DCGM collection is agentless via Container Insights (no scheduling concern), but any **heavy log-processing or metrics sidecars** should be sized carefully — GPU-instance memory is precious. Don't co-locate memory-hungry aggregation with large model tasks; prefer routing to managed backends (CloudWatch, AMP, third-party SaaS).

## Sources

- [Monitoring Amazon ECS Managed Instances (GPU / DCGM via Container Insights enhanced)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html)
- [Amazon ECS CloudWatch Container Insights](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-container-insights.html)
- [Gain operational insights for NVIDIA GPU workloads using CloudWatch Container Insights](https://aws.amazon.com/blogs/mt/gain-operational-insights-for-nvidia-gpu-workloads-using-amazon-cloudwatch-container-insights/)
- [AWS Neuron Monitor](https://awsdocs-neuron.readthedocs-hosted.com/en/latest/tools/neuron-sys-tools/neuron-monitor-user-guide.html)
- [Send Amazon ECS logs to CloudWatch / FireLens](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_firelens.html)
- [AWS Split Cost Allocation Data](https://docs.aws.amazon.com/cur/latest/userguide/split-cost-allocation-data.html)
