# Section 02 — Networking

## Purpose
Assess task network mode, security-group segmentation, subnet IP capacity for `awsvpc` ENIs, private connectivity to AWS services, and service-to-service networking. Grounded in the ECS Best Practices Guide networking pillar and [network security best practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security-network.html).

## Checks to Execute

### 2.1 — Task Network Mode (awsvpc preferred)

**What to check:**
- `networkMode` in each task definition (`awsvpc`, `bridge`, `host`, `none`).
- Fargate tasks must use `awsvpc` (enforced).

**How to check:**
1. `aws ecs list-task-definitions` → `aws ecs describe-task-definition --task-definition <arn>` → read `networkMode`.

**Rating:**
- 🟢 GREEN: `awsvpc` mode — each task gets its own ENI and can be assigned dedicated security groups.
- 🟡 AMBER: `bridge` mode on EC2 where per-task SG isolation would be valuable.
- 🔴 RED: `host` mode for internet-facing or multi-tenant workloads (shared host network namespace, no per-task SG, port conflicts).
- ⬜ UNKNOWN: Cannot describe task definitions.

**Key talking point:** `awsvpc` is the preferred mode and the only mode that lets you assign security groups per task; it is mandatory for Fargate. See [network security best practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security-network.html).

---

### 2.2 — Security Groups per Task / Least-Privilege Ingress

**What to check:**
- Security groups attached via the service's `networkConfiguration.awsvpcConfiguration.securityGroups`.
- Overly-permissive ingress (`0.0.0.0/0` on non-LB ports), or one shared broad SG across all tasks.

**How to check:**
1. `aws ecs describe-services --cluster <c> --services <s>` → `networkConfiguration.awsvpcConfiguration.securityGroups`.
2. `aws ec2 describe-security-groups --group-ids <sg>` → inspect ingress rules.

**Rating:**
- 🟢 GREEN: Task SGs scoped to required ports/sources; ingress from the load balancer SG or specific CIDRs only.
- 🟡 AMBER: One shared SG across dissimilar workloads, or broader ingress than needed.
- 🔴 RED: `0.0.0.0/0` ingress on application ports directly to tasks (bypassing the LB), or wide-open SGs.
- ⬜ UNKNOWN: Cannot read SG rules.

Deep network-isolation hardening → **`ecs-security`**.

---

### 2.3 — Subnet IP Capacity for awsvpc ENIs

**What to check:**
- Subnets used by services and available IP addresses.
- Whether the subnets have enough free IPv4 to scale to the desired/max task count (each `awsvpc` task consumes at least one ENI IP).

**How to check:**
1. From `awsvpcConfiguration.subnets`, run `aws ec2 describe-subnets --subnet-ids <ids>` → `AvailableIpAddressCount`.
2. Compare against current running task count and autoscaling max.

**Rating:**
- 🟢 GREEN: >30% IP headroom across task subnets relative to max scale.
- 🟡 AMBER: Adequate now but tight relative to autoscaling max.
- 🔴 RED: <15% free IPs, or prior task-launch failures due to subnet IP exhaustion.
- ⬜ UNKNOWN: Cannot determine autoscaling max or subnet sharing with other workloads.

**Key talking point:** Insufficient private IPv4 in task subnets is a common hard stop on scaling `awsvpc`/Fargate tasks — size subnets (e.g., /20s) for peak task count. See [scale to 15,000+ tasks](https://aws.amazon.com/blogs/containers/scale-to-15000-tasks-in-a-single-amazon-elastic-container-service-ecs-cluster/).

---

### 2.4 — Private Connectivity to AWS Services (VPC Endpoints / NAT)

**What to check:**
- Whether tasks in private subnets reach ECR, CloudWatch Logs, Secrets Manager, SSM, etc. via VPC (PrivateLink) endpoints vs a NAT gateway or public egress.
- Presence of interface endpoints: `ecr.api`, `ecr.dkr`, `logs`, `secretsmanager`, `ssm`, and an S3 gateway endpoint (ECR layers).

**How to check:**
1. `aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=<vpc>` → enumerate service names.
2. Cross-check against the VPC/subnets the tasks run in.

**Rating:**
- 🟢 GREEN: Interface endpoints for the AWS services tasks use, plus S3 gateway endpoint; private subnets need no internet path for control-plane traffic.
- 🟡 AMBER: Some endpoints present but relying on NAT for others.
- 🔴 RED: Sensitive/regulated workloads egressing to AWS APIs over the public internet with no endpoint policy.
- ⬜ UNKNOWN: Cannot map task subnets to endpoints.

**Key talking point:** AWS PrivateLink endpoints keep ECS/ECR/Logs/Secrets traffic on the AWS network and let you attach least-privilege endpoint policies. See [security considerations blog](https://aws.amazon.com/blogs/security/security-considerations-for-running-containers-on-amazon-ecs/).

---

### 2.5 — Service-to-Service Networking (Service Connect / VPC Lattice / Service Discovery)

**What to check:**
- Whether inter-service traffic uses **Service Connect** (managed service mesh + discovery + metrics), **VPC Lattice** (cross-VPC/cross-account app networking with IAM-based auth), Service Discovery (Cloud Map), or hardcoded endpoints/internal ALBs.
- For Service Connect: whether **automatic connection draining** is in play so clients switch to new endpoints during deploys without traffic errors.

**How to check:**
1. `aws ecs describe-services --cluster <c> --services <s>` → `serviceConnectConfiguration` (enabled?), `vpcLatticeConfigurations` (VPC Lattice target-group registration), and `serviceRegistries` (Cloud Map).

**Rating:**
- 🟢 GREEN: Service Connect enabled for intra-cluster east-west calls (short names, built-in metrics/logs, resilient client-side LB, automatic connection draining), or VPC Lattice where cross-cluster / cross-account / cross-compute connectivity is the requirement.
- 🟡 AMBER: Legacy Service Discovery (Cloud Map) only, or internal ALB hops where Service Connect / VPC Lattice would simplify.
- 🔴 RED: Hardcoded IPs/DNS or cross-service coupling with no discovery mechanism.
- ⬜ UNKNOWN: Single-service estate (N/A), or cannot read service config.

**Key talking point:** Service Connect provides discovery + a service mesh with standardized metrics/logs, doesn't depend on VPC DNS, and supports automatic connection draining for near-zero-error rolling/blue-green deploys — best for intra-cluster east-west traffic. **VPC Lattice** natively integrates with ECS (ECS auto-registers/deregisters task IPs as Lattice IP targets via the ECS infrastructure IAM role) and is the right choice for cross-VPC, cross-account, cross-compute connectivity without intermediate load balancers. Choose per requirement, not by default. See [Service Connect](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect.html) and [native ECS support in VPC Lattice](https://aws.amazon.com/blogs/aws/streamline-container-application-networking-with-native-amazon-ecs-support-in-amazon-vpc-lattice/).
