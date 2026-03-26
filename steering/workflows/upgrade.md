---
name: upgrade
description: Day 2 upgrade workflow. Pre-flight validation, upgrade planning, guided execution with checkpoints, and post-upgrade validation.
---

# Upgrade Workflow

> **Part of:** [APEX EKS Hub](../eks.md)
> **Lifecycle:** Day 2 -- Operate
> **Skill:** `eks-upgrader` — [SKILL.md](../../skills/eks-upgrader/SKILL.md) | [in-place-upgrade.md](../../skills/eks-upgrader/references/in-place-upgrade.md) | [blue-green-upgrade.md](../../skills/eks-upgrader/references/blue-green-upgrade.md)

---

## Access Model

This workflow operates in **read-only + advisory mode**:

- **CAN** run read-only commands to discover cluster state and monitor progress
- **CAN** generate upgrade plans with exact commands the user should run
- **CANNOT** execute mutating commands (upgrades, applies, deletes, annotations)

All cluster mutations are executed by the user. The agent gathers intelligence, plans, guides, and validates.

Why: Cluster upgrades are high-impact, often irreversible operations. The agent adds value through analysis and guidance, not by running commands on the user's behalf. This keeps the user in control and avoids accidental state changes.

---

## How to Route Requests

| User Request | Mode | Phases |
|-------------|------|--------|
| "Upgrade my cluster" / "Plan an upgrade" | **Full workflow** | 1 -> 2 -> 3 -> 4 -> 5 |
| "What happens if I upgrade?" / "Upgrade readiness" | **Assessment** | 1 -> 2 only -- present findings, stop |
| "Help me upgrade add-ons" | **Scoped** | Gather add-on context -> plan add-on upgrades only |
| "Rollback plan" / "What if upgrade fails?" | **Rollback advisory** | Present rollback matrix from [in-place-upgrade.md -- Emergency Rollback](../../skills/eks-upgrader/references/in-place-upgrade.md#emergency-rollback) or [blue-green -- Rollback](../../skills/eks-upgrader/references/blue-green-upgrade.md#rollback) |
| "I'm mid-upgrade and something's wrong" | **Companion only** | Jump to Phase 4 -- diagnose and advise |

---

## Upgrade Sequence Overview

```
Phase 1: Gather Context        -> Read cluster state, detect IaC, understand environment
Phase 2: Pre-flight Validation -> Run read-only checks, present pass/fail report
Phase 3: Generate Upgrade Plan -> Output markdown runbook for user to review/approve
Phase 4: Upgrade Companion     -> Guide user through execution, monitor progress (read-only)
Phase 5: Post-Upgrade Valid.   -> Run health checks, present final report
```

For multi-hop upgrades (e.g., 1.29 -> 1.32), repeat the full sequence for each hop.

---

## Phase 1: Gather Context

Collect ALL of the following before proceeding. If shared context exists from a previous conversation or the Design Workflow, use it -- don't re-ask.

### Required Context

```
MUST gather ALL before proceeding to Phase 2:

[ ] 1. Cluster name and AWS region
[ ] 2. Current EKS version
       -> aws eks describe-cluster --name <name> --query 'cluster.version'
[ ] 3. Target EKS version (or "latest in standard support")
[ ] 4. Compute strategy: Karpenter / MNG / Auto Mode / Fargate / Mixed
[ ] 5. IaC detection (see below)
[ ] 6. Upgrade strategy: in-place (default) or blue-green
[ ] 7. Environment: production / staging / development
[ ] 8. Non-prod upgraded first? If no -> recommend it
[ ] 9. Version validation (see below)
```

### IaC Detection (Item 5)

Search the workspace for infrastructure-as-code files:

```bash
find . -name "*.tf" -path "*eks*" 2>/dev/null | head -20
```

**If Terraform files found:**
1. Read the `.tf` files -- understand `cluster_version`, `cluster_addons`, node group config
2. Confirm with the user: *"I see Terraform managing this cluster. The upgrade plan will target Terraform changes -- direct CLI upgrades would cause state drift."*

**If no IaC files found:** Ask how the cluster was provisioned. Only plan for CLI path if confirmed manual/CLI-managed.

### Version Validation (Item 9)

- Confirm the target version exists and is in standard support
- EKS requires one minor version per hop
- If multiple versions behind, calculate the hop count and inform the user:
  *"You're on `<current>` targeting `<target>` -- that's `<N>` sequential upgrades. I'll plan each hop separately."*

---

## Phase 2: Pre-flight Validation

Run ALL checks below using read-only commands. Present results as a pass/fail report.

Do not proceed to Phase 3 until all checks pass or user explicitly accepts risks.

For full context on each check, read the [eks-upgrader Pre-Flight Checklist](../../skills/eks-upgrader/SKILL.md#pre-flight-checklist).

### Check 1: EKS Cluster Insights

```bash
aws eks list-insights --cluster-name <cluster> --filter 'statuses=ERROR,WARNING'
```

If issues found, get details with `aws eks describe-insight --cluster-name <cluster> --id <insight-id>`.

STOP on ERROR findings -- present them and ask user to resolve before continuing.

### Check 2: Infrastructure Requirements

```bash
# Verify subnet IP availability (need 5+ free per subnet)
aws ec2 describe-subnets --subnet-ids \
  $(aws eks describe-cluster --name <cluster> \
  --query 'cluster.resourcesVpcConfig.subnetIds' --output text) \
  --query 'Subnets[*].[SubnetId,AvailabilityZone,AvailableIpAddressCount]' \
  --output table

# Verify IAM role and encryption config
aws eks describe-cluster --name <cluster> \
  --query 'cluster.{Role:roleArn,Encryption:encryptionConfig}'
```

### Check 3: Deprecated API Scan

Check for scanning tools:
```bash
which pluto 2>/dev/null && which kubent 2>/dev/null
```

If available, run them targeting the next version. If not, ask user if they'd like to install them -- note reduced coverage if declined.

See the [eks-upgrader SKILL.md -- Key API Removals](../../skills/eks-upgrader/SKILL.md#key-api-removals-by-version) for removals by version. The pre-flight script includes both static scanning (Pluto/kubent) and live detection (Prometheus metric, CloudWatch audit logs).

**Important:** `kubectl get` auto-converts resources to the latest served API version. To detect the true stored version, check the `kubectl.kubernetes.io/last-applied-configuration` annotation.

### Check 4: Add-on Compatibility

```bash
for addon in vpc-cni coredns kube-proxy aws-ebs-csi-driver eks-pod-identity-agent; do
  echo "=== $addon ==="
  aws eks describe-addon-versions \
    --addon-name $addon \
    --kubernetes-version <target> \
    --query 'addons[0].addonVersions[0:3].{Version:addonVersion,Default:compatibilities[0].defaultVersion}' \
    --output table 2>/dev/null || echo "Not available"
done
```

Build a current -> target version matrix. STOP if any core add-on has no compatible version.

### Check 5: PDB Audit

```bash
kubectl get pdb -A -o json | jq -r '
  .items[] |
  "\(.metadata.namespace)/\(.metadata.name): minAvailable=\(.spec.minAvailable // "N/A"), maxUnavailable=\(.spec.maxUnavailable // "N/A"), disruptionsAllowed=\(.status.disruptionsAllowed)"'
```

Flag blocking PDBs (disruptionsAllowed = 0). STOP and provide fix options -- scale up replicas or switch to `maxUnavailable`.

### Check 6: Compute Compatibility

**Karpenter** -- check installed version supports target K8s version:
```bash
kubectl get deploy -A -o json | jq -r '
  .items[] |
  select(.spec.template.spec.containers[].image | contains("karpenter")) |
  "\(.metadata.namespace)/\(.metadata.name): \(.spec.template.spec.containers[0].image)"'
```

Cross-reference against [Karpenter release notes](https://karpenter.sh/docs/upgrading/) for target version support. Actually verify -- don't just note "check compatibility."

**MNG:**
```bash
aws eks describe-nodegroup --cluster-name <cluster> --nodegroup-name <name> \
  --query 'nodegroup.{AMI:amiType,Version:version,ReleaseVersion:releaseVersion}'
```

### Check 7: Custom Add-ons

```bash
helm list -A
```

Check each against the target K8s version compatibility matrix. Flag any that need upgrading before or after the control plane.

The `eks-upgrader` skill maintains dedicated upgrade references for specific add-ons under `references/`. Read the [SKILL.md Custom Add-on Upgrades table](../../skills/eks-upgrader/SKILL.md) to see which add-ons have dedicated guides. For each one, verify whether it is present in the cluster -- it may not appear in `helm list` if installed via a different mechanism (e.g., operator, manifest, EKS add-on). If a match is found, load that reference for compatibility checks, version-specific breaking changes, and upgrade sequencing.

### Check 8: Backup Status

Ask the user:
- *"Do you have cluster backups (Velero, GitOps, or similar)?"*
- *"When was the last backup taken?"*

STOP if no backup strategy -- the control plane upgrade is irreversible. Recommend establishing backups first.

### Pre-flight Report

Present results:

```
+------------------------------+--------+-----------------------------+
| Check                        | Status | Details                     |
+------------------------------+--------+-----------------------------+
| 1. Cluster Insights          |  P/F   |                             |
| 2. Infrastructure (IPs/IAM)  |  P/F   |                             |
| 3. Deprecated APIs           |  P/F   |                             |
| 4. Add-on compatibility      |  P/F   |                             |
| 5. PDB configuration         |  P/F   |                             |
| 6. Compute compatibility     |  P/F   |                             |
| 7. Custom add-ons            |  P/F   |                             |
| 8. Backup verified           |  P/F   |                             |
+------------------------------+--------+-----------------------------+
| OVERALL                      |  P/F   | Ready / Blockers found      |
+------------------------------+--------+-----------------------------+
```

**If blockers found:** Present remediation steps. Ask: *"Resolve these first, or proceed accepting the risks?"*

**If all pass:** Proceed to Phase 3.

---

## Phase 3: Generate Upgrade Plan

Generate a customized markdown upgrade plan based on context from Phase 1 and findings from Phase 2. Output it as a fenced code block or write to a file the user can review, share with their team, or attach to a change ticket.

### What Goes in the Plan

Pull exact commands and procedures from the `eks-upgrader` skill -- the plan is a curated, cluster-specific subset of the references below. **Load the full upgrade procedure from each reference, not just version numbers.** If the reference has a checklist, include every applicable item.
- In-place (CLI): [in-place-upgrade.md](../../skills/eks-upgrader/references/in-place-upgrade.md)
- In-place (Terraform): [in-place-upgrade.md](../../skills/eks-upgrader/references/in-place-upgrade.md) + [terraform-examples.md](../../skills/eks-best-practices/references/terraform-examples.md)
- Blue-green: [blue-green-upgrade.md](../../skills/eks-upgrader/references/blue-green-upgrade.md)
- Karpenter upgrade: [karpenter.md](../../skills/eks-upgrader/references/karpenter.md)
- Istio upgrade: [istio.md](../../skills/eks-upgrader/references/istio.md)

### Plan Structure

```markdown
# EKS Upgrade Plan: <cluster-name>
# <current-version> -> <target-version>

> This plan was generated before the upgrade began. During the Upgrade
> Companion phase, steps may be adjusted based on actual cluster behavior
> and any issues encountered.

## Cluster Context
- **Cluster:** <name>
- **Current version:** <version>
- **Target version:** <version>
- **Compute:** <strategy>
- **IaC:** Terraform / CLI
- **Environment:** <env>
- **Hops required:** <N>

## Pre-flight Summary
<key findings from Phase 2 -- blockers resolved, risks accepted>

## Upgrade Steps

### Step 1: Enable Control Plane Logging (if not already enabled)
<command>
Validation: <how to verify>

### Step 2: Upgrade Control Plane
WARNING: This is irreversible. Cannot roll back the control plane version.
<command -- terraform plan/apply or aws eks update-cluster-version>
Expected duration: ~15-30 minutes
Monitoring: <read-only command to check status>
Validation: <command to confirm version>

### Step 3: Upgrade EKS Add-ons
<ordered list with current -> target versions>
Validation: All add-ons in ACTIVE status
Rollback: Revert to previous version via API/Terraform

### Step 4: Upgrade Data Plane
<path-specific: Karpenter drift / MNG update / Auto Mode / Fargate restart>
Validation: All nodes at target version
Rollback: <path-specific>

### Step 5: Upgrade Custom Add-ons
<list from pre-flight Check 7>
Validation: All add-ons running
Rollback: helm rollback or GitOps revert

### Step 6: Post-Upgrade Validation
<pointer to Phase 5 checks>

## Rollback Reference
<rollback matrix customized to this cluster's components>
```

Customize the template based on what applies to this cluster. Skip steps that don't apply (e.g., no custom add-ons, no Fargate). For Terraform-managed clusters, all mutating steps should be `terraform plan` / `terraform apply` with the specific values to change.

### STOP Gate

Present the plan and wait for explicit approval before proceeding:
*"Here's the upgrade plan. Review it -- when you're ready to start, I'll guide you through each step."*

---

## Phase 4: Upgrade Companion

The user executes the plan. Your role is to guide, monitor, and adapt.

### For Each Step

1. **Remind** the user what to do next (from the plan)
2. **Warn** before irreversible actions -- especially before the control plane upgrade:
   *"Once the control plane is upgraded, you cannot roll it back. The only recovery path is rebuilding the cluster from backup. Are you sure?"*
3. **User executes** the command
4. **Monitor** with read-only commands:
   ```bash
   # Control plane upgrade progress
   aws eks describe-update --name <cluster> --update-id <id>

   # Node status during data plane upgrade
   kubectl get nodes -o wide

   # Pod health
   kubectl get pods -A --field-selector 'status.phase!=Running,status.phase!=Succeeded'

   # Recent events
   kubectl get events -A --sort-by='.lastTimestamp' | tail -20
   ```
5. **Checkpoint** after each step completes:
   ```
   Step N complete.
   Validated:
   - <what was checked>
   - <result>

   Rollback option: <what can/cannot be undone at this point>

   Ready for Step N+1?
   ```

### Reacting to Problems

If something unexpected happens:

1. Run read-only diagnostics to understand the situation
2. Distinguish between expected behavior and actual problems:
   - **Expected:** brief API errors during CP upgrade, pod restarts during node replacement, temporary NotReady nodes
   - **Problems:** nodes stuck NotReady >10 min, pods in CrashLoopBackOff, add-ons stuck DEGRADED, update status ERROR
3. Reference [in-place-upgrade.md -- Emergency Rollback](../../skills/eks-upgrader/references/in-place-upgrade.md#emergency-rollback) for rollback options
4. Adjust remaining plan steps if needed and explain what changed and why

### Common Issues

| Symptom | Likely Cause | Diagnosis (read-only) | Guidance |
|---------|-------------|----------------------|----------|
| Nodes stuck NotReady | Drain blocked by PDB | `kubectl get pdb -A`, `kubectl describe node <node>` | Suggest PDB adjustment |
| Pods CrashLoopBackOff after CP upgrade | Deprecated API usage | `kubectl describe pod`, `kubectl logs` | Check API deprecation findings from Phase 2 |
| Add-on stuck DEGRADED | Version incompatibility | `aws eks describe-addon --cluster-name <cluster> --addon-name <name>` | Suggest compatible version from Check 4 |
| CP update >45 min | Possible infrastructure issue | `aws eks describe-update --name <cluster> --update-id <id>` | Check for ERROR status, review CloudWatch logs |

---

## Phase 5: Post-Upgrade Validation

Run ALL these read-only checks and present the results:

```bash
# 1. Cluster version
aws eks describe-cluster --name <cluster> --query 'cluster.version'

# 2. Node versions
kubectl get nodes -o wide

# 3. System pods health
kubectl get pods -n kube-system

# 4. Add-on status
for addon in vpc-cni coredns kube-proxy aws-ebs-csi-driver eks-pod-identity-agent; do
  aws eks describe-addon --cluster-name <cluster> --addon-name $addon \
    --query 'addon.{Status:status,Version:addonVersion}' 2>/dev/null || echo "$addon: Not installed"
done

# 5. Unhealthy pods
kubectl get pods -A --field-selector 'status.phase!=Running,status.phase!=Succeeded'

# 6. Recent error events
kubectl get events -A --sort-by='.lastTimestamp' | grep -i "restart\|backoff\|failed" | tail -20
```

### Post-Upgrade Report

```
+------------------------------+--------+-----------------------------+
| Validation                   | Status | Details                     |
+------------------------------+--------+-----------------------------+
| Cluster version              |  P/F   |                             |
| All nodes at target version  |  P/F   |                             |
| System pods healthy          |  P/F   |                             |
| EKS add-ons active           |  P/F   |                             |
| No unhealthy pods            |  P/F   |                             |
| No error events              |  P/F   |                             |
+------------------------------+--------+-----------------------------+
| UPGRADE STATUS               |  P/F   | Complete / Issues found     |
+------------------------------+--------+-----------------------------+
```

If issues found, diagnose using read-only commands and advise on remediation.

For multi-hop upgrades, after successful validation loop back to Phase 1 for the next hop.

---

## Multi-Hop Upgrades

When upgrading across multiple minor versions (e.g., 1.29 -> 1.32):

1. **Plan all hops upfront** -- show the full path: `1.29 -> 1.30 -> 1.31 -> 1.32`
2. **Execute one hop at a time** -- full cycle per version (Phases 1-5)
3. **Pre-flight each hop** -- API deprecations and add-on compatibility differ between versions
4. **Non-prod first** -- upgrade through all hops in staging before production

---

## Version Support Awareness

| Phase | Duration | Cost Impact |
|-------|----------|-------------|
| Standard support | 14 months | Standard pricing |
| Extended support | +12 months | Additional per-hour fee |
| End of support | Auto-upgrade by AWS | N/A |

If on extended support, flag the extra cost. If near end of support, warn about auto-upgrade.

For full details, see [eks-upgrader SKILL.md -- Version Support Lifecycle](../../skills/eks-upgrader/SKILL.md#version-support-lifecycle). You can [disable extended support](https://docs.aws.amazon.com/eks/latest/userguide/disable-extended-support.html) so auto-upgrade happens at end of standard support.
