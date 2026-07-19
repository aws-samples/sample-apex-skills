# Module: Guided Migration Runbook

> **Part of:** [eks-al2-to-al2023](../SKILL.md)
> **Purpose:** A template the agent fills to emit a **human-executed** AL2→AL2023 migration runbook, centered on a **canary node group** and tailored to the detected compute types. This skill assembles and instructs — it **never runs any of it**.

**This skill does not run any command in this runbook.** Every command below is an
**operator instruction**. The agent's job is to select the right migration path for each AL2
node group (from `node-inventory.md`), fill in the cluster/node-group specifics, address each
applicable risk from `migration-risks.md` in the pre-flight, and emit the assembled runbook as
the second output artifact. All commands are presented in fenced blocks prefixed
`Operator runs (this skill does not):`.

AWS recommends a **documented migration plan with workload testing and a rollback path** before
moving worker nodes to AL2023. Source:
<https://docs.aws.amazon.com/eks/latest/userguide/eks-ami-deprecation-faqs.html> (as of
2026-07-19).

## Table of Contents

- [How the agent uses this template](#how-the-agent-uses-this-template)
- [Migration paths (choose per node group)](#migration-paths-choose-per-node-group)
- [Phase 0: Pre-flight (address risks first)](#phase-0-pre-flight-address-risks-first)
- [Phase 1: Create the canary AL2023 node group](#phase-1-create-the-canary-al2023-node-group)
- [Phase 2: Schedule a representative workload subset onto the canary](#phase-2-schedule-a-representative-workload-subset-onto-the-canary)
- [Phase 3: Validate the canary](#phase-3-validate-the-canary)
- [Phase 4: Roll the fleet (per migration path)](#phase-4-roll-the-fleet-per-migration-path)
- [Phase 5: Rollback](#phase-5-rollback)
- [Runbook output template](#runbook-output-template)

---

## How the agent uses this template

For each AL2 node group in the footprint (`node-inventory.md`), the agent:

1. Selects the **migration path** below by the node group's shape (custom AMI in a launch
   template / standard LT / Karpenter).
2. Emits a **Phase 0 pre-flight** that names each risk from `migration-risks.md` with status
   `applies` and its concrete remediation for this cluster.
3. Emits the **canary** phases (1–3), then the **fleet roll** (Phase 4) for the selected path,
   then **rollback** (Phase 5).
4. Fills every `<placeholder>` with the detected cluster name, region, node-group name,
   AL2023 `amiType`, K8s version, etc.

The agent does **not** execute any of these steps — it produces the runbook as a document for
an operator (or a separate change-management pipeline) to run.

---

## Migration paths (choose per node group)

All three paths are **VERIFIED** against
<https://docs.aws.amazon.com/eks/latest/userguide/al2023.html> (as of 2026-07-19):

| # | Node group shape (from `node-inventory.md`) | Path | Mechanism |
|---|---------------------------------------------|------|-----------|
| **(a)** | Custom AMI pinned in a **launch template** (`ImageId` set) | **IN-PLACE** | Swap the launch-template `ImageId` to the AL2023 AMI, bump the LT version, update the node group to the new version → EKS rolls the nodes. |
| **(b)** | Standard MNG, or a launch template **without** an `ImageId` | **BLUE / GREEN** | Create a **new** AL2023 node group alongside the AL2 one, validate, migrate pods (cordon+drain), delete the old node group. |
| **(c)** | **Karpenter**-provisioned | **DRIFT** | Change the `EC2NodeClass` `amiFamily` to AL2023 → Karpenter **Drift** detects the change and auto-replaces nodes. |

The **canary** phases (1–3) apply to **all** paths: even for the in-place and Karpenter paths,
validate an AL2023 canary before rolling the whole node group / fleet.

---

## Phase 0: Pre-flight (address risks first)

Address **every** risk that `migration-risks.md` rated `applies` **before** creating any
AL2023 node. The agent emits only the ones that apply, with concrete values.

1. **VPC CNI floor** — if VPC CNI < 1.16.2, upgrade it first:

   Operator runs (this skill does not):
   ```bash
   aws eks update-addon --cluster-name <cluster-name> --addon-name vpc-cni \
     --addon-version <v1.16.2-or-newer-eksbuild> --resolve-conflicts PRESERVE
   ```

2. **cgroup v2 workloads** — bump JDK 8 workloads to **jdk8u372+** (or a newer JDK); verify
   .NET runtime versions for cgroup-v2 awareness. Land these workload changes **before** the
   AMI swap so the canary validates the fix.

3. **IMDS hop limit** — plan the fix: either set `HttpPutResponseHopLimit: 2` on the AL2023
   node group's launch template, **or** move IMDS-credential workloads to **EKS Pod Identity /
   IRSA**. Decide before Phase 1.

4. **nodeadm / NodeConfig** — for self-managed nodes and custom launch templates, rewrite
   `bootstrap.sh` userData to the `NodeConfig` schema (see `migration-risks.md` for the minimal
   YAML). Do **not** run `nodeadm init` — it runs via systemd on the node at boot.

5. **Host agents** — for each DaemonSet flagged `review`, confirm AL2023 support with its
   vendor and stage an AL2023-capable version to validate on the canary.

---

## Phase 1: Create the canary AL2023 node group

Create a **small** AL2023 node group **alongside** the existing AL2 node group(s) — do not
touch the AL2 nodes yet.

Operator runs (this skill does not):
```bash
# Blue/green (path b): a small AL2023 canary node group next to the AL2 one
aws eks create-nodegroup --cluster-name <cluster-name> \
  --nodegroup-name <ng-name>-al2023-canary \
  --node-role <existing-node-role-arn> \
  --subnets <subnet-ids> \
  --ami-type <AL2023-amiType-from-node-inventory> \
  --instance-types <same-as-al2-ng> \
  --scaling-config minSize=1,maxSize=2,desiredSize=1 \
  --labels migration=al2023-canary --taints key=al2023-canary,value=true,effect=NoSchedule
```

- **Path (a) in-place:** instead of a new node group, create a **new launch-template version**
  with the AL2023 `ImageId` and point a **canary** node group (or a 1-node MNG) at that LT
  version to validate before swapping the production node group.
- **Path (c) Karpenter:** create a **canary `NodePool`** referencing an AL2023 `EC2NodeClass`
  (`amiFamily: AL2023`) with a distinct taint/label, so a small number of AL2023 nodes come up
  for validation before you change the production `EC2NodeClass`.

The canary carries a **taint** (`al2023-canary=true:NoSchedule`) so only workloads you
deliberately target land on it.

---

## Phase 2: Schedule a representative workload subset onto the canary

Cordon a portion of the AL2 capacity and steer a **representative** subset of workloads onto
the canary using a `nodeSelector` + a matching toleration for the canary taint. Pick workloads
that exercise the risks: a JVM/.NET app (cgroup v2), an IMDS-credential app, and each flagged
host-agent DaemonSet.

Operator runs (this skill does not):
```bash
# Cordon a slice of AL2 nodes so the canary receives the rescheduled representative pods
kubectl cordon <one-or-two-al2-node-names>

# Example: target a test deployment onto the canary (add to the pod template)
#   spec.template.spec.nodeSelector: { migration: al2023-canary }
#   spec.template.spec.tolerations: [{ key: al2023-canary, value: "true", effect: NoSchedule }]
kubectl -n <ns> patch deployment <app> --type merge -p \
  '{"spec":{"template":{"spec":{"nodeSelector":{"migration":"al2023-canary"},"tolerations":[{"key":"al2023-canary","value":"true","effect":"NoSchedule"}]}}}}'
```

Host-agent DaemonSets that tolerate all taints (or use the canary toleration) will schedule a
pod onto the canary node automatically — that is how you validate them on AL2023.

---

## Phase 3: Validate the canary

Confirm on the AL2023 canary node **before** rolling anything fleet-wide. Validate each risk
that applied:

Operator runs (this skill does not):
```bash
# Node is up, AL2023, Ready
kubectl get nodes -l migration=al2023-canary \
  -o custom-columns=NAME:.metadata.name,OSIMAGE:.status.nodeInfo.osImage,KERNEL:.status.nodeInfo.kernelVersion,READY:.status.conditions[-1].type

# Targeted pods are Running/Ready on the canary
kubectl get pods -A -o wide | grep <canary-node-name>

# Host-agent DaemonSets have a Running pod on the canary node
kubectl get pods -A -o wide | grep <canary-node-name> | grep -Ei '<daemonset-names>'
```

Validation checklist (all must pass):
- Targeted pods reach **Ready** on the AL2023 node; app health checks pass.
- **No cgroup OOM** — JVM/.NET workloads do not OOM/restart (confirms the jdk8u372+ / runtime
  fix under cgroup v2).
- **IMDS-dependent pods still get credentials** (confirms the hop-limit fix or the Pod
  Identity/IRSA migration).
- Each flagged **host-agent DaemonSet** has a **Running** pod on the AL2023 node and is
  functioning (logs/metrics flowing) — confirms vendor AL2023 support.
- containerd runtime healthy; no kernel-module load failures for privileged agents / GPU
  drivers.

Do not proceed to Phase 4 until the checklist passes. If anything fails, fix it (or roll the
canary back — Phase 5) and re-validate.

---

## Phase 4: Roll the fleet (per migration path)

Only after Phase 3 passes. Emit the block matching the node group's path.

**Path (a) — IN-PLACE (custom AMI in a launch template).** Swap the AMI ID and update the node
group; EKS rolls the nodes with surge/drain automatically.

Operator runs (this skill does not):
```bash
# Create a new LT version with the AL2023 ImageId, then update the node group to it
aws ec2 create-launch-template-version --launch-template-id <lt-id> \
  --source-version <current-version> \
  --launch-template-data '{"ImageId":"<al2023-ami-id>"}'
aws eks update-nodegroup-version --cluster-name <cluster-name> --nodegroup-name <ng-name> \
  --launch-template id=<lt-id>,version=<new-version>
```

**Path (b) — BLUE / GREEN (standard LT or LT without an AMI ID).** Scale the AL2023 node group
to full size, then cordon + drain + delete the AL2 node group (matches the upstream
`node-readiness.md` flow).

Operator runs (this skill does not):
```bash
# Grow the AL2023 node group to the AL2 node group's capacity, then drain the AL2 fleet
aws eks update-nodegroup-config --cluster-name <cluster-name> \
  --nodegroup-name <ng-name>-al2023 --scaling-config minSize=<n>,maxSize=<n>,desiredSize=<n>

# For each AL2 node: cordon, then drain
kubectl cordon <al2-node-name>
kubectl drain <al2-node-name> --ignore-daemonsets --delete-emptydir-data

# After all pods rescheduled onto AL2023 nodes, delete the old AL2 node group
aws eks delete-nodegroup --cluster-name <cluster-name> --nodegroup-name <ng-name>
```

**Path (c) — Karpenter DRIFT.** Change the production `EC2NodeClass` `amiFamily` to AL2023;
Karpenter **Drift** detects the change and replaces nodes automatically (respecting
disruption budgets).

Operator runs (this skill does not):
```bash
# Set amiFamily: AL2023 on the production EC2NodeClass; Karpenter Drift rolls the nodes.
kubectl edit ec2nodeclass <name>    # spec.amiFamily: AL2023 (and amiSelectorTerms as needed)
```

---

## Phase 5: Rollback

Nodes are **cattle** — rollback replaces AL2023 nodes with AL2 nodes; it does not "revert" a
node.

- **Keep the AL2 node group** until fleet-wide validation passes (do not delete it in Phase 4
  until you are confident). This is your rollback target.
- **To roll back the canary or a partial roll:** cordon and drain the AL2023 nodes back onto
  the retained AL2 node group.

Operator runs (this skill does not):
```bash
# Uncordon the retained AL2 nodes, then cordon+drain the AL2023 canary/fleet back onto AL2
kubectl uncordon <al2-node-names>
kubectl cordon <al2023-node-name>
kubectl drain <al2023-node-name> --ignore-daemonsets --delete-emptydir-data
# Then scale down / delete the AL2023 (canary) node group
aws eks delete-nodegroup --cluster-name <cluster-name> --nodegroup-name <ng-name>-al2023-canary
```

- **Path (a) in-place rollback:** point the node group back at the previous launch-template
  version (the AL2 `ImageId`) and update-nodegroup-version.
- **Path (c) Karpenter rollback:** revert the `EC2NodeClass` `amiFamily` to the prior value;
  Drift rolls the nodes back.

---

## Runbook output template

The agent emits the second artifact
(`EKS-AL2023-Migration-Runbook-{cluster}-{YYYY-MM-DD}-{HHMM}.md`) using this skeleton, filled
per detected compute type. Every command block is prefixed
`Operator runs (this skill does not):`.

```markdown
# AL2 → AL2023 Migration Runbook — <cluster> (<region>)
_generated <timestamp> · K8s version: <version> · THIS RUNBOOK IS EXECUTED BY A HUMAN — this skill does not run any step_

## Scope
<the AL2 node groups from node-inventory.md and the chosen path per node group>

## Phase 0 — Pre-flight (do these first)
<only the risks rated `applies`, each with its concrete remediation + command>

## Phase 1 — Canary AL2023 node group
<create-nodegroup / new LT version / Karpenter canary NodePool, per path>

## Phase 2 — Schedule representative workloads onto the canary
<cordon a slice + nodeSelector/toleration targeting; include a JVM/.NET, IMDS, and each flagged agent>

## Phase 3 — Validate the canary
<the validation checklist; do not proceed until all pass>

## Phase 4 — Roll the fleet
<the path-specific block: in-place | blue/green | Karpenter drift>

## Phase 5 — Rollback
<keep AL2 node group until validated; cordon/drain AL2023 back to AL2>

> Reminder: this skill assessed and generated this runbook. It did not, and will not, execute any step. Review and test in a non-production cluster first.
```
