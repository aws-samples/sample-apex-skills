# ECS Observability — Launch-Type Support Matrix

> **Part of:** [ecs-observability](../SKILL.md)
> **Purpose:** The single per-capability support matrix across the four ECS launch types — EC2, Fargate, Managed Instances (MI), and ECS Anywhere (EXTERNAL). Scope-bleed between launch types is the #1 error class in ECS observability advice; check this table before making any capability claim.

**For per-capability depth, see:** [log-delivery.md](log-delivery.md), [metrics-stacks.md](metrics-stacks.md), [tracing-and-signals.md](tracing-and-signals.md), [native-visibility-and-exec.md](native-visibility-and-exec.md)

---

## How to read this table

- **Yes** = explicitly documented by AWS for that launch type.
- **No** = explicitly documented as unsupported or structurally impossible.
- **Undocumented — verify** = AWS docs neither confirm nor deny; do not assert support in customer advice without checking the linked page live.

> ⚠️ **Facts verified 2026-07-09** against the source URL on each row. Launch-type support changes; re-verify rows older than a few months before load-bearing recommendations.

## The matrix

| Capability | EC2 | Fargate | Managed Instances | EXTERNAL (ECS Anywhere) | Source |
|---|---|---|---|---|---|
| awslogs log driver | Yes | Yes | Yes | Yes (execution role delivers to CloudWatch Logs) | https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html |
| Extra Docker log drivers (fluentd/gelf/json-file/journald/syslog) | Yes | No | Undocumented — verify | Undocumented — verify | https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html |
| FireLens (awsfirelens) | Yes (Linux only) | Yes (Linux only) | Undocumented — verify | Undocumented — verify | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_firelens.html |
| Container Insights — standard | Yes (agent ≥ 1.29) | Yes | Yes | Not documented — don't claim | https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/deploy-container-insights-ECS-cluster.html |
| Container Insights — enhanced | Yes | Yes | Yes | Not listed — don't claim | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-container-insights.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html |
| Agentless GPU/DCGM metrics (container/task/instance level) | **No** — GPU *reservation* metric only | No (no GPU tasks) | **Yes — MI-only**, NVIDIA GPU instance types, enhanced CI required | No | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-metrics.html |
| Instance-level CI metrics | Yes — requires CloudWatch agent as daemon service | N/A (no host) | Auto-published (OS + data volume) with CI enabled — agentless | Not documented | https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/deploy-container-insights-ECS-instancelevel.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html |
| ADOT sidecar → AMP / CloudWatch / X-Ray | Yes | Yes | Undocumented — verify (docs enumerate FG + EC2 only) | **No** — "External instances aren't supported currently" | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/application-metrics-prometheus.html |
| Application Signals — sidecar strategy | Yes | Yes | Not documented | Not documented (awsvpc requirement also blocks it structurally) | https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-ECS-Sidecar.html |
| Application Signals — daemon strategy | Yes | **No** | Not documented | Not documented | https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-ECS-Daemon.html |
| X-Ray daemon sidecar (legacy — maintenance mode since 2026-02-25) | Yes | Yes (sidecar only) | Undocumented — verify | Needs outbound reachability to X-Ray endpoints | https://docs.aws.amazon.com/xray/latest/devguide/xray-daemon-ecs.html |
| ECS Exec | Yes (Linux any ECS-optimized AMI; Windows on listed AMIs, agent ≥ 1.56) | Yes (Linux + Windows) | **Yes — the ONLY shell path (no SSH on MI)** | **Yes** — explicitly supported | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html |
| Free vended CloudWatch metrics | Yes (CPU/mem/GPU reservation + utilization) | Yes (CPU/mem utilization, automatic) | Yes (+ EC2/EBS instance metrics) | Yes — via `ecs-t-*` endpoints (must be network-reachable) | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-metrics.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html |
| Service events / EventBridge / container health checks | Yes | Yes | Yes | Yes (health checks need agent ≥ 1.17.0) | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_cwe_events.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/healthcheck.html |

## Launch-type-specific constraints that shape observability advice

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html

**Managed Instances (MI):**
- The AMI is AWS-owned — you cannot bake agents into it. Instances have a 14-day maximum lifetime (auto-drain and replace), so host-installed state is disposable by design.
- No SSH; ECS Exec is the sole interactive path. Management is via ECS APIs only.
- GPU auto-repair exists for impaired GPU instances (https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-gpu-auto-repair.html).

**ECS Anywhere (EXTERNAL):**
- `awsvpc` network mode is unsupported (bridge/host/none only) — this structurally excludes every pattern that requires `awsvpc` (e.g., the Application Signals sidecar).
- Network prerequisites for observability data to flow: outbound + DNS to `ecs-a-*`, `ecs-t-*` (task/container metrics), `ecs`, `ssm`, `ec2messages`, `ssmmessages` regional endpoints, plus whatever the telemetry destination needs (CloudWatch Logs, ECR, ...).
- Windows support for ECS Anywhere is deprecated.

**Fargate:**
- No host access — every collector, router, or agent must be an in-task sidecar. Instance-level metrics do not exist.

**EC2:**
- The most flexible: sidecars, daemon-scheduled collectors, extra Docker log drivers, custom host agents. The cost is that everything host-level (CloudWatch agent daemon, DCGM exporters) is customer-managed.
