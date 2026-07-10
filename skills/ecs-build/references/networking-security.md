# Networking and Security

> **Part of:** [ecs-build](../SKILL.md)

awsvpc networking, the full VPC endpoint set for private/air-gapped projects, IAM trust scoping, and launch-type-scoped security capabilities.

> Facts verified 2026-07-10 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/vpc-endpoints.html, https://docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html, https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html, and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html

## awsvpc mode

- All generated task definitions use `network_mode = "awsvpc"` (mandatory on Fargate; each task gets its own ENI).
- Services specify `network_configuration { subnets, security_groups, assign_public_ip }`. Default: private subnets, `assign_public_ip = false`.
- Public-subnet tasks pulling images need `assign_public_ip = true` (or a NAT route); private-subnet tasks need NAT or the VPC endpoint set below.
- Security groups: one per service; endpoint security groups must allow TCP 443 from the task subnets.

## VPC endpoint set for private / air-gapped (Critical Rule 8)

All interface endpoints unless noted. Scope by launch type -- do not generate the EC2-only trio for Fargate-only projects.

| Endpoint | Type | Needed when | Launch-type scope |
|---|---|---|---|
| `com.amazonaws.<region>.ecr.api` | Interface | Any private ECR pull | All |
| `com.amazonaws.<region>.ecr.dkr` | Interface (private DNS required) | Any private ECR pull | All |
| `com.amazonaws.<region>.s3` | **Gateway** | Always with ECR -- image layers live in S3 (`arn:aws:s3:::prod-<region>-starport-layer-bucket/*`). The most-missed endpoint; pulls hang without it | EC2-hosted tasks and Fargate PV >= 1.4.0 |
| `com.amazonaws.<region>.logs` | Interface | awslogs driver without internet path | All |
| `com.amazonaws.<region>.ecs` | Interface | Container-instance agent control plane | **EC2 launch type only** (agent >= 1.25.1); not required for Fargate tasks |
| `com.amazonaws.<region>.ecs-agent` | Interface | Agent + Service Connect Envoy management | **EC2 launch type only** |
| `com.amazonaws.<region>.ecs-telemetry` | Interface | Agent telemetry | **EC2 launch type only** |
| `com.amazonaws.<region>.ssmmessages` | Interface | **ECS Exec** in private networks (Fargate and EC2/awsvpc without NAT) -- note it is `ssmmessages`, NOT `ssm` | All where Exec is enabled |
| `com.amazonaws.<region>.secretsmanager` | Interface | Secrets Manager secrets pulled privately | All |
| `com.amazonaws.<region>.ssm` | Interface | SSM Parameter Store secrets pulled privately | All |
| `com.amazonaws.<region>.kms` | Interface | ECS Exec with a KMS session key; secrets with CMKs | All |

- In Regions launched after 2023-12-23, all three region-specific ECS endpoints (`ecs`, `ecs-agent`, `ecs-telemetry`) are mandatory for EC2 container instances or traffic silently goes public.
- FIPS variants exist for ECR (`ecr-fips.api` / `ecr-fips.dkr`).
- ECR pull-through-cache caveat: the FIRST pull through a PTC rule via PrivateLink still requires an internet route (NAT/public path); subsequent pulls do not (https://docs.aws.amazon.com/AmazonECR/latest/userguide/pull-through-cache.html, verified 2026-07-10).

> **Managed Instances endpoint caveat (verified 2026-07-10):** MI VPC-endpoint requirements are **NOT documented** -- managed-instance-networking.html and vpc-endpoints.html are silent on MANAGED_INSTANCES. The only documented connectivity guidance is NAT gateway / public IP (https://docs.aws.amazon.com/AmazonECS/latest/developerguide/getting-started-managed-instances-cli.html). The EC2-launch-type endpoint trio MAY apply de facto (inference only -- the ECS agent runs on Bottlerocket in your subnets), but this is unconfirmed. **Research live before generating an air-gapped MI project.**
- Hardening: pin ECR pulls in the execution-role policy with `aws:SourceVpc`/`aws:SourceVpce` condition keys; restrict the S3 gateway endpoint policy to the starport layer bucket.

## Task/execution role trust scoping (Critical Rule 5)

Recommended trust policy for both task and execution roles:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": ["ecs-tasks.amazonaws.com"] },
    "Action": "sts:AssumeRole",
    "Condition": {
      "ArnLike":      { "aws:SourceArn": "arn:aws:ecs:<region>:<account-id>:*" },
      "StringEquals": { "aws:SourceAccount": "<account-id>" }
    }
  }]
}
```

- **The `aws:SourceArn` MUST be the account-wide wildcard.** Per the ECS task IAM role docs: "Using the `aws:SourceArn` condition key to specify a specific cluster is not currently supported, you should use the wildcard to specify all clusters." A cluster-scoped ARN is documented-unsupported and breaks role assumption, as of 2026-07-10 (https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html). The validator flags cluster-scoped SourceArn.
- Containers are not a security boundary: on EC2, Managed Instances, and ECS Anywhere there is **no task isolation** -- co-located containers can potentially reach other tasks' credentials and IMDS. Fargate gives per-task isolation. For strict isolation requirements, use Fargate; on EC2 block task access to IMDS per the ECS roles recommendations. Deep hardening strategy -> `ecs-security`.

## ECS Exec plumbing

When `enable_execute_command = true`:

- Task role needs `ssmmessages:CreateControlChannel`, `CreateDataChannel`, `OpenControlChannel`, `OpenDataChannel` (task role, not execution role).
- Private subnets need the `ssmmessages` endpoint; add `kms` if a KMS key encrypts sessions.
- Conflicts with `readonlyRootFilesystem = true` -- the SSM agent needs a writable filesystem (Critical Rule 12).
- On Managed Instances, ECS Exec is the ONLY interactive access path (no SSH).

## Launch-type-scoped security capabilities

State these with their scope -- they are the classic "halo" errors:

- **GuardDuty Runtime Monitoring: NOT supported for workloads on ECS Managed Instances** as of 2026-07-10 (https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-guard-duty-integration.html). It covers Fargate (ECS) via the managed sidecar agent and EC2 instances via the agent. Do not generate MI projects that assume GuardDuty runtime coverage; note the gap in the README. Customers requiring runtime monitoring should use EC2 or Fargate capacity, or compensate on MI with Bottlerocket's immutable-root + SELinux posture plus CloudTrail/Config monitoring.
- **SOCI lazy loading: Fargate Linux platform version 1.4.0 only** -- not EC2, not MI ([task-definition-guide.md](task-definition-guide.md)).
- **Fargate capabilities:** only `CAP_SYS_PTRACE` addable; `privileged` invalid. MI optionally allows CAP_NET_ADMIN/CAP_SYS_ADMIN/CAP_BPF/CAP_PERFMON; EC2 allows the full set you configure.
- **MI security posture** (do not attribute to EC2): no SSH, immutable root filesystem, SELinux mandatory access controls, automatic patching via the 14-21-day drain-and-replace lifecycle.
- Compliance program claims: cite ONLY https://aws.amazon.com/compliance/services-in-scope/ -- never assert scope from memory.

## Sources

- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/vpc-endpoints.html · https://docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-ssm-paramstore.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-guard-duty-integration.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-security.html
