---
title: "Incident Response & Forensics"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/incident-response-and-forensics.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-security/references/incident-response-and-forensics.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/incident-response-and-forensics.md). Edit the source, not this page.
:::

# Incident Response & Forensics

Detection (Layer 6) and audit logging (Layer 7a) produce the signals; this is how you **respond** when something fires on ECS. Have a defined, rehearsed plan *before* an incident — it materially improves posture and is itself an audit expectation.

## Prerequisites (must be in place before an incident)

- **Detective signal:** GuardDuty ECS Runtime Monitoring + Extended Threat Detection → Security Hub (Layer 6). Remember Runtime Monitoring **excludes Managed Instances** — plan alternate detection there.
- **Forensic trail:** CloudTrail (ECS API + task-role `taskArn` context), Container Insights, application logs (`awslogs`/FireLens), VPC Flow Logs, with retention meeting the regime (Layer 7a).
- **A runbook** mapping common detections (container breakout, reverse shell, crypto-mining, anomalous API call from a task role, leaked credential) to response steps and owners.

## The response loop for a compromised task

The isolation mechanics differ sharply by launch type — this is the ECS-specific crux.

1. **Identify & triage** — confirm the GuardDuty finding (e.g. `AttackSequence:ECS/CompromisedCluster`); scope the affected task(s), service, cluster, launch type, and the **task role** behind the credentials.
2. **Isolate the task (network).** Move the task/service to a **deny-all (or tightly scoped) security group** so it can't talk out while you investigate. With `awsvpc` mode each task has its own ENI/SG, so this is a per-task action — a key advantage of `awsvpc`.
3. **Preserve vs stop.**
   - **Fargate:** the task is isolated (its own kernel), so you can often stop it for capture with low blast radius; but stopping destroys ephemeral state — snapshot/export logs and any attached EBS volume first. Set the service `desiredCount` so ECS doesn't immediately reschedule onto the same compromised image.
   - **EC2 / Managed Instances:** there is **no task isolation** — a compromised container may already have reached co-located tasks' credentials, the container instance role, and IMDS. **`cordon`-equivalent:** deregister the container instance from the cluster / set it to `DRAINING`, detach it from load balancers, and treat the *whole instance* as suspect, not just the task.
4. **Revoke credentials.** The task role's temporary credentials are the blast radius. Attach an explicit **deny** or tighten the task role immediately; rotate any secret the task could read in Secrets Manager; on EC2 also review/rotate the **container instance role** (it was reachable). Use CloudTrail's `taskArn` session context to see exactly what the assumed role did.
5. **Capture forensics.** Snapshot the EBS volume (task-attached, and on EC2 the instance volume); export the relevant CloudTrail + log window; on EC2 capture instance process/network state before termination.
6. **Eradicate & recover.** Terminate the compromised task (and, on EC2, the instance — replaced from a clean AMI); redeploy from a **known-good, signed, scanned** image (Layer 4); confirm the entry vector is closed (patched CVE, removed over-broad task-role permission or `iam:PassRole`, fixed misconfig).
7. **Post-incident.** Root-cause; tighten task-definition hardening (Layer 3), SG rules (Layer 5), and role scope (Layer 2); record evidence for the auditor.

## Escalate to AWS (don't run a major incident fully self-service)

The runbook above is customer-executed, but a real breach should pull in AWS help early:

- **AWS Customer Incident Response Team (CIRT)** — a 24/7 global team that assists customers during an **active** security event on the customer side of the shared-responsibility model (triage, root-cause via service logs, recovery + hardening recommendations). Engage the CIRT **through an AWS Support case**. Reference: [Understand AWS response teams and support](https://docs.aws.amazon.com/whitepapers/latest/aws-security-incident-response-guide/understand-aws-response-teams-and-support.html).
- **AWS Support case** — open a security/urgent case (severity per your Support plan) to reach the CIRT and coordinate.
- **AWS Security Incident Response** (the managed service) — monitors your environment, triages GuardDuty/Security Hub findings, and gives you access to the Security Incident Response Engineering team across the full lifecycle (detection → triage → containment → recovery). Onboard it *before* an incident for the fastest path. Reference: [What is AWS Security Incident Response?](https://docs.aws.amazon.com/security-ir/latest/userguide/what-is.html).
- Follow the **AWS Security Incident Response Guide** for the end-to-end process (aligned to NIST 800-61).

## Design choices that make response possible

- **Fargate** shrinks blast radius (per-task isolation) and makes "stop the task" clean — the strongest IR posture on ECS.
- **`awsvpc` + SG-per-service** makes network isolation of one task a small delta, not a cluster-wide lockdown.
- **Least-privilege task role + scoped `iam:PassRole`** (Layer 2) caps what a compromised task can do.
- **Signed, scanned images + immutable tags** (Layer 4) make "redeploy from known-good" trustworthy.
- **IMDS lockdown on EC2** (Layer 1) prevents a compromised container from stealing the instance role.

## Shared responsibility (incident response)

| AWS manages | Customer manages |
|---|---|
| Control-plane integrity; GuardDuty detections; durable log/snapshot primitives; clean replacement infrastructure | The IR runbook + rehearsal; isolation/eradication actions (which differ by launch type); task-role + secret + instance-role rotation; forensic capture + evidence retention; post-incident hardening |

## Sources
- [ECS Best Practices: Security](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security.html) · [ECS task IAM role — containers are not a boundary](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html)
- [GuardDuty Runtime Monitoring](https://docs.aws.amazon.com/guardduty/latest/ug/runtime-monitoring.html) · [Roles recommendations — CloudTrail monitoring](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html#security-iam-roles-recommendations-cloudtrail-monitoring)
- [AWS Security Incident Response Guide — response teams & support (CIRT)](https://docs.aws.amazon.com/whitepapers/latest/aws-security-incident-response-guide/understand-aws-response-teams-and-support.html) · [What is AWS Security Incident Response?](https://docs.aws.amazon.com/security-ir/latest/userguide/what-is.html)
