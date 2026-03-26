---
name: In-Place EKS Upgrade with Istio
description: Deploy an EKS 1.32 cluster with Istio service mesh, plant realistic upgrade issues, and upgrade to 1.33 using the APEX EKS upgrade workflow. Covers EnvoyFilter migration, ingress gateway availability, and sidecar injection label conflicts.
workflow: steering/workflows/upgrade.md
---

# Upgrade Your EKS Cluster In-Place with Istio and APEX EKS

A hands-on exercise that demonstrates the APEX EKS [Upgrade Workflow](../../../steering/workflows/upgrade.md) for clusters running the Istio service mesh. Deploy a cluster at EKS 1.32 with Istio, plant realistic issues, and upgrade to 1.33 -- letting APEX catch and guide you through each problem.

The upgrade workflow uses the [`eks-upgrader`](../../../skills/eks-upgrader/SKILL.md) skill for upgrade procedures and component-specific guidance (including the [Istio upgrade reference](../../../skills/eks-upgrader/references/istio.md)), combined with [`eks-best-practices`](../../../skills/eks-best-practices/SKILL.md) for general cluster knowledge.

## Overview

```
EKS 1.32 + Istio 1.25.x → EKS 1.33 + Istio 1.26.x
   │                          │
   │                          └─ Endpoints API deprecated (favor EndpointSlices)
   │                             Istio 1.25 does NOT support K8s 1.33
   │                             Must upgrade Istio to 1.26 first
   │
   └─ Starting point: deploy cluster here
       Planted issues: EnvoyFilter, single-replica gateway, label conflict
```

## Prerequisites

- AWS account with EKS permissions
- Terraform >= 1.5.7
- kubectl
- AWS CLI v2
- Helm v3
- One of:
  - [Claude Code](https://claude.ai/code)
  - [Kiro IDE](https://kiro.dev/downloads/) or [Kiro CLI](https://kiro.dev/docs/cli/installation/)

### Setup and Deploy

The deploy script handles everything: sets up APEX EKS for your chosen tool (Claude Code or Kiro), deploys the base EKS 1.32 cluster with Istio 1.25 using the [sidecar blueprint](https://github.com/aws-samples/istio-on-eks/tree/main/terraform-blueprint/sidecar) from istio-on-eks, deploys a sample workload with sidecar injection, and plants the upgrade issues.

**What it does:**

1. **APEX EKS setup** -- asks which tool you're using, then symlinks skills and commands for Claude Code (`.claude/skills/`, `.claude/commands/`) or Kiro (`.kiro/skills/`, `.kiro/steering/`)
2. **Deployment name** -- asks for a name (defaults to `cc` or `kiro`). The blueprint is copied to `istio-<name>/`, giving cluster name `ex-istio-<name>`. This enables parallel deployments -- run deploy.sh twice with different names for side-by-side testing.
3. **Deploy base cluster** -- clones istio-on-eks into `tmp/`, copies the sidecar blueprint, pins EKS to 1.32 and Istio to 1.25.x, runs `terraform init` and `terraform apply`, configures kubectl, then enables sidecar injection on the default namespace and deploys sample workloads
4. **Plant issues** -- applies manifests that simulate real-world upgrade problems:

| # | Issue | What it does | Upgrade Impact |
|---|-------|-------------|----------------|
| 1 | Istio 1.25 on K8s 1.32 | Istio version does not support K8s 1.33 | **Blocks EKS upgrade** -- Istio 1.25 supports K8s 1.29-1.32 only. Must upgrade Istio to 1.26.x (which supports 1.33) before upgrading EKS. The agent must check the [Istio support matrix](https://istio.io/latest/docs/releases/supported-releases/) to detect this. |
| 2 | `envoyfilter-metrics.yaml` | EnvoyFilter customizing Prometheus metrics | **Breaks on upgrade** -- EnvoyFilter patches are tightly coupled to xDS internals and silently break when the Envoy config structure changes. Must migrate to Telemetry API before upgrading. |
| 3 | `single-replica-gateway.yaml` | Scales istio-ingress gateway to 1 replica with no PDB | **Causes downtime** -- the single gateway pod drops all traffic for 60-90 seconds when it restarts during upgrade. Fix by scaling to >=2 replicas and adding a PDB. |
| 4 | `label-conflict.yaml` | Namespace with both `istio-injection: enabled` and `istio.io/rev` labels | **Sidecar mismatch** -- `istio-injection` takes precedence over `istio.io/rev`, so pods silently connect to the wrong control plane revision after a canary upgrade. Fix by removing the `istio-injection` label. |

Run from this directory (`examples/eks-upgrades/in-place-istio/`):

```bash
chmod +x ./scripts/deploy.sh
./scripts/deploy.sh
```

## Upgrade with APEX EKS

Now use the APEX EKS upgrade workflow. The workflow loads the [`eks-upgrader`](../../../skills/eks-upgrader/SKILL.md) skill for step-by-step upgrade procedures and the [`eks-best-practices`](../../../skills/eks-best-practices/SKILL.md) skill for cluster knowledge.

<details>
<summary><strong>Claude Code</strong></summary>

Open the repo root in Claude Code:

```bash
claude
```

Then use the slash command:

```
/apex:eks-upgrade
```

Or just say: **"Upgrade my cluster from 1.32 to 1.33"**

</details>

<details>
<summary><strong>Kiro CLI</strong></summary>

```bash
kiro-cli chat
```

```bash
/model claude-opus-4.5
```

```bash
/context add ../../../steering/eks.md
```

Then say: **"Upgrade my cluster from 1.32 to 1.33"**

</details>

## Expected Outcome

By the end of this exercise, you should have:

1. **Experienced the upgrade workflow** -- APEX walks through pre-flight -> plan -> execute -> validate
2. **Seen Istio-specific issues detected** -- Istio/K8s version incompatibility, EnvoyFilter migration, gateway availability, sidecar label conflicts
3. **Fixed issues with guidance** -- APEX provides remediation steps referencing the [Istio upgrade reference](../../../skills/eks-upgrader/references/istio.md)
4. **Successfully upgraded 1.32 -> 1.33** -- both the EKS control plane and Istio components, with validation at each step

## Test Results

Tests pending for the initial 1.32 -> 1.33 scenario.

## Cleanup

The destroy script auto-discovers active deployments under `tmp/`. If multiple exist, it asks which one to destroy (or all). It then deletes planted manifests, removes Istio Helm releases, runs `terraform destroy`, and cleans up the deployment directory.

```bash
chmod +x ./scripts/destroy.sh
./scripts/destroy.sh
```

## Further Reading

- [APEX EKS Upgrade Workflow](../../../steering/workflows/upgrade.md)
- [EKS Upgrader Skill](../../../skills/eks-upgrader/SKILL.md)
  - [In-Place Upgrade Reference](../../../skills/eks-upgrader/references/in-place-upgrade.md)
  - [Istio Upgrade Reference](../../../skills/eks-upgrader/references/istio.md)
  - [Blue-Green Upgrade Reference](../../../skills/eks-upgrader/references/blue-green-upgrade.md)
- [EKS Best Practices -- Cluster Upgrades](../../../skills/eks-best-practices/references/cluster-upgrades.md)
- [istio-on-eks (AWS Samples)](https://github.com/aws-samples/istio-on-eks)
- [Istio Upgrade Documentation](https://istio.io/latest/docs/setup/upgrade/)
- [EKS Version Release Notes -- Standard Support](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html)
