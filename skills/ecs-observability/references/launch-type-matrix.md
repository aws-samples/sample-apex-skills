# ECS Observability — Launch-Type Support Matrix

> **Part of:** [ecs-observability](../SKILL.md)
> **Purpose:** The single per-capability support matrix across the four ECS launch types — EC2, Fargate, Managed Instances (MI), and ECS Anywhere (EXTERNAL). Scope-bleed between launch types is the #1 error class in ECS observability advice; check this table before making any capability claim.

**For per-capability depth, see:** [log-delivery.md](log-delivery.md), [metrics-stacks.md](metrics-stacks.md), [tracing-and-signals.md](tracing-and-signals.md), [native-visibility-and-exec.md](native-visibility-and-exec.md)

---

## How to read this table

- **Yes** = explicitly documented by AWS for that launch type.
- **No** = explicitly documented as unsupported or structurally impossible.
- **Undocumented — verify** = AWS docs neither confirm nor deny; do not assert support in customer advice without checking the linked page live.

> ⚠️ **Facts verified 2026-07-09** against the source URL on each row; the extra-Docker-driver, `splunk`-driver, FireLens, ADOT-sidecar, Application Signals (both strategies), and X-Ray-daemon rows were **re-verified 2026-07-10**. Launch-type support changes; re-verify rows older than a few months before load-bearing recommendations. This matrix is the **single source of truth** for launch-type support inside this skill — other files point here rather than restating quotes.

## The matrix

| Capability | EC2 | Fargate | Managed Instances | EXTERNAL (ECS Anywhere) | Source |
|---|---|---|---|---|---|
| awslogs log driver | Yes | Yes | Yes (per the MI getting-started task definition: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/getting-started-managed-instances.html) | Yes (execution role delivers to CloudWatch Logs) | https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html |
| `splunk` log driver | Yes | Yes | Undocumented — verify | Undocumented — verify | https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html |
| Extra Docker log drivers (fluentd/gelf/json-file/journald/syslog) | Yes | No | Undocumented — verify | Undocumented — verify | https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html |
| FireLens (awsfirelens) | Yes (Linux only) | Yes (Linux only) | Undocumented — verify | Undocumented — verify | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_firelens.html |
| Container Insights — standard | Yes (agent ≥ 1.29) | Yes | Yes | Undocumented — verify | https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/deploy-container-insights-ECS-cluster.html |
| Container Insights — enhanced | Yes (agent ≥ 1.29) | Yes | Yes | Undocumented — verify | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-container-insights.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html |
| Agentless GPU/DCGM metrics (container/task/instance level) | **No** — GPU *reservation* metric only | No (no GPU tasks) | **Yes — MI-only**, NVIDIA GPU instance types, enhanced CI required | No | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-metrics.html |
| Instance-level CI metrics | Yes (requires CloudWatch agent as daemon service) | No (no host — structurally impossible) | Yes (filesystem utilization only — OS + data volumes — auto-published with CI, agentless; other `instance_*` metrics not documented) | Undocumented — verify | https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/deploy-container-insights-ECS-instancelevel.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html |
| ADOT sidecar → AMP / CloudWatch / X-Ray | Yes | Yes | Undocumented — verify (docs enumerate FG + EC2 only) | **No** — "External instances aren't supported currently" | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/application-metrics-prometheus.html |
| Application Signals — sidecar strategy | Yes | Yes | Undocumented — verify | No (requires `awsvpc`, which EXTERNAL does not support) | https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-ECS-Sidecar.html |
| Application Signals — daemon strategy | Yes | **No** | Undocumented — verify | Undocumented — verify | https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-ECS-Daemon.html |
| X-Ray daemon sidecar (legacy — maintenance mode since 2026-02-25) | Yes | Undocumented — verify (the daemon-on-ECS page does not mention Fargate as of 2026-07-10; the sidecar pattern is operationally common but not explicitly documented there) | Undocumented — verify | Undocumented — verify (daemon additionally needs outbound reach to X-Ray endpoints from on-prem) | https://docs.aws.amazon.com/xray/latest/devguide/xray-daemon-ecs.html |
| ECS Exec | Yes (Linux any ECS-optimized AMI; Windows on listed AMIs, agent ≥ 1.56) | Yes (Linux + Windows) | **Yes — the ONLY shell path (no SSH on MI)** | **Yes** — explicitly supported | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html |
| Free vended CloudWatch metrics | Yes — CPU/mem reservation + utilization; **GPU reservation ONLY, no GPU utilization** (see agentless GPU row) | Yes (CPU/mem utilization, automatic) | Yes (+ EC2/EBS instance metrics) | Yes — via `ecs-t-*` endpoints (must be network-reachable) | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-metrics.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html |
| Service events / EventBridge / container health checks | Yes | Yes | Yes | Yes | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_cwe_events.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/healthcheck.html (container health checks require agent ≥ 1.17.0 on any agent-based launch type) |

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
