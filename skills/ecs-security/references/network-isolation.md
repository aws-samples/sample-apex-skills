# Layer 5 — Network Isolation

What a task is *allowed to reach* and be reached by. The foundation is the **`awsvpc` network mode**, which gives each task its own elastic network interface (ENI) with its own private IP and security groups — enabling per-task/per-service network isolation that bridge/host mode cannot. Reference: [Network security best practices for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-network.html) · [ECS Best Practices: Security (network)](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security.html).

## `awsvpc` mode + security group per service

- **Use `awsvpc` network mode** for production. It is the **only** mode on Fargate and the recommended mode on EC2 — each task gets a dedicated ENI, so you attach VPC **security groups at task granularity**, not shared across everything on a host.
- **Least-privilege security group per service.** Give each service its own SG; allow only the ports it actually serves (ingress) and only the destinations it must reach (egress). Reference security groups by ID between tiers (e.g. app SG allows ingress only from the ALB SG) rather than by CIDR.
- **Avoid `host` network mode** for untrusted workloads — it shares the host's network namespace and undermines per-task isolation. (Security Hub flags host-mode/host-port task definitions.)

## Private subnets + no public IPs

- Run tasks in **private subnets**; do **not** auto-assign public IPs (`assignPublicIp: DISABLED`) for internal services.
- Front public-facing services with an **ALB or NLB** in public subnets, with the tasks themselves private — the load balancer is the only internet-exposed component, and its SG is the only ingress source for the task SG.
- For egress to the internet (e.g. calling a third-party API) use a **NAT gateway**; for AWS-service traffic prefer **VPC endpoints** (below) so it never leaves the AWS network.

## VPC endpoints — keep AWS-service traffic private

For tasks in fully private subnets (no NAT), or to keep sensitive traffic off the public internet for a compliance regime, create **interface/gateway VPC endpoints** for every AWS service the task and agent touch. The common set for a hardened ECS service:

| Endpoint | Type | Why |
|---|---|---|
| `com.amazonaws.region.ecr.api` | Interface | ECR API (auth, image metadata) |
| `com.amazonaws.region.ecr.dkr` | Interface | ECR image layer pulls |
| `com.amazonaws.region.s3` | **Gateway** | ECR stores image **layers in S3** — required for private image pulls |
| `com.amazonaws.region.secretsmanager` | Interface | Private secret retrieval by the execution role |
| `com.amazonaws.region.ssm` | Interface | **SSM Parameter Store secrets only** (execution-role `ssm:GetParameters`) |
| `com.amazonaws.region.ssmmessages` | Interface | **ECS Exec** session channel (Systems Manager Session Manager) — required for Exec on private networks; `ssm` alone is **not** enough |
| `com.amazonaws.region.kms` | Interface | *(optional)* only if ECS Exec sessions are **KMS-encrypted**, or for CMK `kms:Decrypt` on encrypted secrets |
| `com.amazonaws.region.logs` | Interface | `awslogs` → CloudWatch Logs |

> **`ssm` ≠ `ssmmessages`.** A common conflation: the `ssm` endpoint serves **Parameter Store** retrieval; **ECS Exec** rides Systems Manager Session Manager and needs **`ssmmessages`** (plus a task-role with `ssmmessages:*`), and **`kms`** only if you encrypt Exec sessions. Verified 2026-07-09 — [ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html).

For **ECS on EC2 in a fully private VPC**, the container instances *also* need the ECS control-plane endpoints so the agent can register and poll: `com.amazonaws.region.ecs-agent`, `com.amazonaws.region.ecs-telemetry`, and `com.amazonaws.region.ecs` (agent **1.25.1+**; restart the agent after creating them). These are not needed on Fargate. Reference: [ECS interface VPC endpoints](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/vpc-endpoints.html).

References: [ECR interface VPC endpoints (PrivateLink)](https://docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html) · [connect to Secrets Manager within a VPC](https://docs.aws.amazon.com/secretsmanager/latest/userguide/setup-create-vpc.html).

> **Two easy-to-miss endpoint gotchas:**
> - **ECR needs the S3 gateway endpoint**, not just the two ECR interface endpoints — image *layers* live in S3, so a private pull fails without it.
> - **GuardDuty ECS Runtime Monitoring on Fargate** needs the security agent to reach GuardDuty; if you use restrictive SGs/private subnets you must allow the S3 managed prefix list (for the agent image) and the GuardDuty VPC endpoint GuardDuty creates. See [runtime-security.md](runtime-security.md) and [ECS-Fargate runtime coverage](https://docs.aws.amazon.com/guardduty/latest/ug/gdu-assess-coverage-ecs.html).

## Endpoint policies + egress control

- Attach **VPC endpoint policies** to the ECR/S3 endpoints to restrict which repositories/buckets are reachable and to prevent, e.g., repository deletion through the endpoint ([ECR endpoint policy](https://docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html)).
- For high-sensitivity workloads, default-deny egress on the task SG and allowlist only required destinations (VPC endpoints + specific partner IPs), so a compromised task can't exfiltrate freely.

- **VPC Flow Logs** — enable Flow Logs on the task subnets/ENIs. The incident-response runbook and PCI Req 10 both *assume* they exist; without them there is no network-forensics trail for a compromised task. Send them to CloudWatch Logs/S3 with the same retention as the regime.

## Ingress protection for public-facing services

Front any internet-facing ALB with **AWS WAF** (managed rule groups + rate-based rules for L7 abuse) and **AWS Shield** (Standard is automatic; Shield Advanced for high-value targets) — the task SG should still accept ingress **only** from the ALB SG, so WAF/Shield harden the one exposed hop.

## Multi-tenancy isolation

For multi-tenant workloads the network tier is only part of isolation. **On EC2/Managed Instances there is no per-task kernel isolation**, so co-located tenants can reach each other's task credentials and IMDS — for cross-tenant PII/PHI/cardholder separation use **Fargate** (per-task isolation), **account-per-tenant**, or at minimum separate clusters in **separate VPCs** with no shared SGs, plus per-tenant task roles and SG-per-service. Escalate multi-tenant regulated isolation on shared EC2 instances (see [engagement-and-response.md](engagement-and-response.md)).

## Cross-account / cross-VPC service-to-service

For service-to-service across VPCs or accounts, use **Service Connect** or **VPC Lattice** (IAM/SigV4-authenticated service connectivity) rather than opening broad SG/CIDR ranges. (Design details belong to `ecs-architect`; here, the security point is to prefer authenticated, scoped connectivity over wide network openings.)

## Shared responsibility (Layer 5)

| AWS manages | Customer manages |
|---|---|
| ENI plumbing for `awsvpc`; PrivateLink endpoint infrastructure; ALB/NLB service | Network mode choice; SG-per-service least-privilege rules; private-subnet placement + no public IPs; creating the right VPC endpoints (incl. S3 gateway for ECR); endpoint policies; egress allowlisting |

## Sources
- [Network security best practices for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-network.html) · [ECS Best Practices: Security](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security.html)
- [ECR interface VPC endpoints (PrivateLink)](https://docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html) · [ECS interface VPC endpoints (ecs-agent/ecs-telemetry/ecs)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/vpc-endpoints.html) · [Connect to Secrets Manager within a VPC](https://docs.aws.amazon.com/secretsmanager/latest/userguide/setup-create-vpc.html) · [ECS-Fargate runtime coverage / endpoints](https://docs.aws.amazon.com/guardduty/latest/ug/gdu-assess-coverage-ecs.html) · [ECS Exec (ssmmessages/kms endpoints)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html)
