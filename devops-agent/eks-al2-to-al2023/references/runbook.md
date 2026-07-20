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
- [Phase 4 (cont.): Decommission the canary on success](#phase-4-cont-decommission-the-canary-on-success)
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

1. **Back up before you touch nodes.** Node migration replaces nodes and reschedules pods; confirm the cluster's backup posture is sound first. Run the `eks-backup` skill (or otherwise verify AWS Backup for EKS / Velero coverage of any StatefulSet/PV data) before creating any AL2023 node. This skill does not perform backups.

2. **VPC CNI floor** — if VPC CNI < 1.16.2, upgrade it first:

   Operator runs (this skill does not):
   ```bash
   aws eks update-addon --cluster-name <cluster-name> --addon-name vpc-cni \
     --addon-version <v1.16.2-or-newer-eksbuild> --resolve-conflicts PRESERVE
   ```

3. **cgroup v2 workloads (Java)** — detection (`node-inventory.md` section 6 + `migration-risks.md`
   Risk 1) produces an **at-risk / not-at-risk-newer-jdk / unconfirmed** Java list; the exact JDK
   build is not readable from the control plane. **First resolve the build** (also resolves the
   `unconfirmed` bucket):

   Operator runs (this skill does not):
   ```bash
   # See the real image, confirm the JDK build, and see the JVM's resolved heap under the cgroup limit
   kubectl get pod <pod> -n <ns> -o jsonpath='{.spec.containers[*].image}'
   kubectl exec <pod> -n <ns> -c <container> -- java -version
   kubectl exec <pod> -n <ns> -c <container> -- java -XshowSettings:vm -version   # check MaxHeapSize
   ```

   For each **at-risk** workload, apply these levers (operator action — this skill does not modify
   workloads):

   1. **Bump the JDK to `8u372`+ (or a newer LTS JDK)** — `8u372` is the JDK 8 build that detects
      the container memory limit under cgroup v2; older builds size the heap from node memory and
      OOM. This is the primary fix. **Note the 8u191-8u371 trap:** those builds have
      `UseContainerSupport` on by default yet do **not** read cgroup **v2** limits, so "flag on,
      newer than 8u191" is **not** safe — only the version bump to 8u372+ fixes them.
   2. **Confirm `-XX:+UseContainerSupport` is not explicitly disabled** — it is ON by default on
      `8u191+`/`10+`, so confirm nothing set `-XX:-UseContainerSupport` in `JAVA_TOOL_OPTIONS` /
      `JDK_JAVA_OPTIONS` / args; do not blindly add the flag on a modern JDK where it is the
      default. Flag-on is necessary but **not sufficient** (see the 8u191-8u371 trap above).
   3. **Size the heap with `-XX:MaxRAMPercentage` — after removing any surviving `-Xmx`.** A
      leftover `-Xmx` **overrides** `-XX:MaxRAMPercentage` (the percentage is silently ignored; this
      holds on both HotSpot and OpenJ9), so first find and remove any `-Xmx`/`-Xms` in
      `JAVA_TOOL_OPTIONS` / `JDK_JAVA_OPTIONS` / args **or baked into the image `ENTRYPOINT`** (an
      ENTRYPOINT-baked `-Xmx` is invisible to this skill — confirm with
      `java -XshowSettings:vm -version` above). But first **confirm the `-Xmx` is not an intentional
      cap** — some workloads set it deliberately to leave headroom for off-heap/native/metaspace;
      removing a deliberate cap and applying 75% can enlarge the heap and OOM a pod that was
      previously safe. Then set the percentage against
      the pod's cgroup-v2 memory limit: `-XX:MaxRAMPercentage=75.0` suits a **dedicated, larger**
      pod; use **50-60%** for **small pods (< 1-2 GB)** where metaspace/threads/direct buffers are
      proportionally large. Always pair it with an explicit pod `resources.limits.memory`.

   **ClickOps / no-IaC path (clusters managed by console/CLI with no manifest in git).** When there is no IaC
   to edit, inject the flags directly:

   Operator runs (this skill does not):
   ```bash
   # Inject/adjust JVM flags via env (edits the live Deployment)
   kubectl set env deployment/<app> -n <ns> JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75.0"
   # or edit the full spec (image tag bump, resources.limits.memory, remove -Xmx, etc.)
   kubectl edit deployment/<app> -n <ns>
   ```
   > **Env injection alone can fail.** An `-Xmx` **baked into the image `ENTRYPOINT`** overrides a
   > `JAVA_TOOL_OPTIONS` you inject, so `kubectl set env` will not take effect for heap sizing —
   > you must rebuild the image (or otherwise remove the baked `-Xmx`). This ties to the §6
   > detection blind spot: the baked flag is not visible from the control plane.

   **Triage — is it really this bug?** Confirm the OOM is the cgroup-v2 heap mis-sizing, not an
   app leak: this bug shows as a **kernel OOMKill** — `kubectl describe pod <p>` shows
   `reason: OOMKilled` and **exit code 137**, with **no JVM stack**. A `java.lang.OutOfMemoryError`
   **with a JVM stack** in the logs is an application leak, which these levers won't fix. Use the
   same check to confirm the fix landed.

   Also verify **.NET** runtime versions for cgroup-v2 awareness **by hand** — .NET is a **manual
   review flag, NOT detected** by section 6 (UNVERIFIED version — treat as "verify your runtime").
   Land these workload changes **before** the AMI swap so the canary validates the fix.

4. **IMDS hop limit** — plan the fix. Setting `HttpPutResponseHopLimit: 2` on the AL2023 node
   group's launch template is the complete fix (it restores IMDS access for **both** credential
   and metadata calls). Moving workloads to **EKS Pod Identity / IRSA** only removes the
   *credential* dependency — pods that still call IMDS for **metadata** (region, AZ, instance-id)
   remain broken at hop limit 1, so Pod Identity/IRSA alone is not sufficient unless no pod calls
   IMDS for metadata. Decide before Phase 1.

5. **nodeadm / NodeConfig** — for self-managed nodes and custom launch templates, rewrite
   `bootstrap.sh` userData to the `NodeConfig` schema (see `migration-risks.md` for the minimal
   YAML). Do **not** run `nodeadm init` — it runs via systemd on the node at boot.

6. **Host agents** — for each DaemonSet flagged `review`, confirm AL2023 support with its
   vendor and stage an AL2023-capable version to validate on the canary.

---

## Phase 1: Create the canary AL2023 node group

Create a **small** AL2023 node group **alongside** the existing AL2 node group(s) — do not
touch the AL2 nodes yet.

> **Apply the Phase 0 fixes to the canary itself — or the canary validates nothing.** If IMDS
> hop limit was flagged `applies`, the canary must come up with the **fixed** hop limit, not the
> default. A managed node group created **without** a launch template defaults to hop limit **1**
> (per `migration-risks.md` Risk 2) — so the canary would reproduce the *unfixed* state and
> Phase 3's hop-limit check would be meaningless (false alarm, or false confidence). Give the
> canary a launch template that sets `HttpPutResponseHopLimit: 2` (below), and likewise carry any
> other Phase 0 remediation into the canary's cluster/config — VPC CNI floor, workload cgroup
> fixes, **and (for path (a) in-place / self-managed nodes) the `bootstrap.sh` → `NodeConfig`
> userData rewrite (Risk 3)**. A custom launch template that swaps only the AL2023 `ImageId`
> while keeping AL2 `bootstrap.sh` userData will **fail to boot** on AL2023 — the canary node
> never joins and validates nothing.

Operator runs (this skill does not):
```bash
# Blue/green (path b): a small AL2023 canary node group next to the AL2 one.
# Create a launch template first so the canary inherits the Phase 0 IMDS hop-limit fix
# (skip the LT only if the IMDS risk did NOT apply — otherwise the canary comes up at hop limit 1).
aws ec2 create-launch-template --launch-template-name <ng-name>-al2023-canary-lt \
  --launch-template-data '{"MetadataOptions":{"HttpPutResponseHopLimit":2,"HttpTokens":"required","HttpEndpoint":"enabled"}}'

aws eks create-nodegroup --cluster-name <cluster-name> \
  --nodegroup-name <ng-name>-al2023-canary \
  --node-role <existing-node-role-arn> \
  --subnets <subnet-ids> \
  --ami-type <AL2023-amiType-from-node-inventory> \
  --instance-types <same-as-al2-ng> \
  --launch-template name=<ng-name>-al2023-canary-lt \
  --scaling-config minSize=1,maxSize=2,desiredSize=1 \
  --labels migration=al2023-canary --taints key=al2023-canary,value=true,effect=NoSchedule
```

- **Path (a) in-place:** instead of a new node group, create a **new launch-template version**
  with the AL2023 `ImageId`, the **rewritten `NodeConfig` userData** (Risk 3 — keeping the AL2
  `bootstrap.sh` userData fails to boot on AL2023), **and** `MetadataOptions.HttpPutResponseHopLimit: 2`
  (if the IMDS risk applied), and point a **canary** node group (or a 1-node MNG) at that LT
  version to validate before swapping the production node group. Give the canary group the
  **same `migration=al2023-canary` label + `NoSchedule` taint** as the path-(b) canary so the
  Phase 2/3 selectors (`-l migration=al2023-canary`) target it.
- **Path (c) Karpenter:** create a **canary `NodePool`** referencing an AL2023 `EC2NodeClass`
  (`amiFamily: AL2023`) — give the `NodePool` the **`migration=al2023-canary` label + a
  matching `NoSchedule` taint** (so the Phase 2/3 selectors and workload tolerations line up
  with paths a/b), and set the `EC2NodeClass`
  `metadataOptions.httpPutResponseHopLimit: 2` (if the IMDS risk applied) so the canary nodes
  come up with the fix — so a small number of AL2023 nodes come up for validation before you
  change the production `EC2NodeClass`.

The canary carries a **taint** (`al2023-canary=true:NoSchedule`) so only workloads you
deliberately target land on it.

---

## Phase 2: Schedule a representative workload subset onto the canary

Cordon a portion of the AL2 capacity and steer a **representative** subset of workloads onto
the canary using a `nodeSelector` + a matching toleration for the canary taint. Pick workloads
that exercise the risks: a JVM/.NET app (cgroup v2), a pod that calls IMDS (for credentials
**or** metadata — both break at hop limit 1), and each flagged host-agent DaemonSet.

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
- **IMDS-dependent pods still reach IMDS for credentials AND metadata** (confirms the hop-limit
  fix; the Pod Identity/IRSA migration only covers the credential path — verify metadata calls
  too if any pod makes them).
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

> **Roll the fleet to the *validated canary* configuration — do not rebuild from the AL2
> source.** The new production LT version must carry **all** the fixes the canary proved, not
> just the AMI ID: the **rewritten `NodeConfig` userData** (Risk 3 — an LT that keeps the AL2
> `bootstrap.sh` userData fails to boot on AL2023) **and** `HttpPutResponseHopLimit: 2` (Risk 2,
> if it applied). Deriving `--source-version` from the current **AL2** LT and overriding only
> `ImageId` silently reintroduces both defects on the whole fleet. Reuse the canary's launch
> template (or copy its full `--launch-template-data`) so the rolled fleet == the validated
> canary.

Operator runs (this skill does not):
```bash
# Create a new LT version carrying the FULL validated canary config (not just the AMI ID):
# AL2023 ImageId + rewritten NodeConfig userData (Risk 3) + hop-limit 2 (Risk 2, if it applied).
aws ec2 create-launch-template-version --launch-template-id <lt-id> \
  --source-version <canary-lt-version> \
  --launch-template-data '{"ImageId":"<al2023-ami-id>","UserData":"<base64 NodeConfig>","MetadataOptions":{"HttpPutResponseHopLimit":2}}'
aws eks update-nodegroup-version --cluster-name <cluster-name> --nodegroup-name <ng-name> \
  --launch-template id=<lt-id>,version=<new-version>
```

**Path (b) — BLUE / GREEN (standard LT or LT without an AMI ID).** Scale the AL2023 node group
to full size, then cordon + drain + delete the AL2 node group (matches the upstream
`node-readiness.md` flow).

> **The full-size AL2023 group must be the *validated canary* configuration — not a fresh bare
> group.** Scale up the same launch template you validated in Phase 1 (the one carrying
> `HttpPutResponseHopLimit: 2` and, for self-managed/custom-LT nodes, the rewritten `NodeConfig`
> userData). A bare managed node group created **without** that launch template comes up at hop
> limit **1** (Risk 2) — reintroducing the defect fleet-wide. Before scaling, **remove the
> Phase 1 canary `NoSchedule` taint** (`key=al2023-canary`) so production pods can schedule onto
> the group; the taint existed only to keep the canary isolated during validation.

> **Note:** pods pinned to the old node group via `nodeSelector`/`nodeAffinity` on `eks.amazonaws.com/nodegroup: <old-name>` will not schedule onto the new, separately-named AL2023 group — update or remove those pins before draining, or the drained pods will stay Pending.

> **Before draining:** `--delete-emptydir-data` discards emptyDir contents, and draining detaches EBS volumes (and unmounts EFS/NFS mounts) as pods reschedule — confirm StatefulSet/PV data is backed up (Phase 0 step 1) and can survive node replacement. A restrictive PodDisruptionBudget can stall or block a drain; check PDBs for the workloads on each node first and plan for it (raise `maxUnavailable`, or accept a slower rolling drain). Never force-delete PDB-protected pods without understanding the availability impact.

Operator runs (this skill does not):
```bash
# Grow the VALIDATED CANARY group (created in Phase 1, taint removed above) to the AL2 node
# group's capacity, then drain the AL2 fleet. Scaling this group — not a fresh bare one —
# is what keeps the fleet on the validated hop-limit-2 launch template.
aws eks update-nodegroup-config --cluster-name <cluster-name> \
  --nodegroup-name <ng-name>-al2023-canary --scaling-config minSize=<n>,maxSize=<n>,desiredSize=<n>

# For each AL2 node: cordon, then drain
kubectl cordon <al2-node-name>
kubectl drain <al2-node-name> --ignore-daemonsets --delete-emptydir-data

# After all pods rescheduled onto AL2023 nodes, delete the old AL2 node group
aws eks delete-nodegroup --cluster-name <cluster-name> --nodegroup-name <ng-name>
```

**Path (c) — Karpenter DRIFT.** Change the production `EC2NodeClass` to AL2023;
Karpenter **Drift** detects the change and replaces nodes automatically (respecting
disruption budgets).

> **Carry the validated canary settings onto the *production* `EC2NodeClass` — not just
> `amiFamily`.** The Phase 1 canary's hop-limit fix lived on a *separate* AL2023 `EC2NodeClass`;
> editing only `spec.amiFamily` on the production class leaves its `metadataOptions` at the
> default, so the drifted Karpenter fleet comes up at hop limit **1** (Risk 2). Set
> `spec.metadataOptions.httpPutResponseHopLimit: 2` (if the IMDS risk applied) on the production
> `EC2NodeClass` in the same edit. AL2023 `NodeConfig` userData is generated by Karpenter, so the
> Risk 3 `bootstrap.sh` rewrite does not apply to this path.

Operator runs (this skill does not):
```bash
# Set the production EC2NodeClass to AL2023 AND carry the hop-limit fix; Karpenter Drift rolls the nodes.
kubectl edit ec2nodeclass <name>
# spec.amiFamily: AL2023 (and amiSelectorTerms as needed)
# spec.metadataOptions.httpPutResponseHopLimit: 2   (if the IMDS risk applied)
```

---

## Phase 4 (cont.): Decommission the canary on success

Once the fleet is fully on AL2023 and validated, clean up the canary scaffolding — otherwise
paths (a) and (c) leave an orphaned canary node group / `NodePool` running (idle cost), and the
Phase 2 pin leaves workloads stuck to the canary.

- **Revert the Phase 2 validation pin.** Remove the `nodeSelector: migration=al2023-canary` +
  `al2023-canary` toleration you patched onto the canary workloads (Phase 2) so they schedule
  freely across the AL2023 fleet — otherwise they stay pinned and go `Pending` when the canary
  is removed.
- **Path (b):** the canary group *became* the fleet (scaled up in Phase 4), so there is no
  separate canary to delete — just confirm the old AL2 group was deleted.
- **Paths (a) / (c):** the production node group / `EC2NodeClass` was rolled in place, so the
  **separate** canary node group (a) or canary `NodePool` + its AL2023 `EC2NodeClass` (c) is now
  redundant — delete it (and remove the `al2023-canary` taint/label references) once validation
  has passed.

## Phase 5: Rollback

Nodes are **cattle** — rollback replaces AL2023 nodes with AL2 nodes; it does not "revert" a
node.

- **Keep the AL2 node group** until fleet-wide validation passes (do not delete it in Phase 4
  until you are confident). This is your rollback target.
- **To roll back the canary or a partial roll:** cordon and drain the AL2023 nodes back onto
  the retained AL2 node group.

> **Before draining (same caveat as Phase 4):** `--delete-emptydir-data` discards emptyDir
> contents, and draining detaches EBS volumes (and unmounts EFS/NFS mounts) as pods reschedule
> — confirm StatefulSet/PV data can survive the move back to AL2 nodes. A restrictive PodDisruptionBudget can stall or
> block the drain; check PDBs first and plan for it (raise `maxUnavailable`, or accept a slower
> rolling drain). Never force-delete PDB-protected pods without understanding the impact.

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
