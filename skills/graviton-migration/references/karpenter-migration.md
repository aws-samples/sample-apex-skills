# Karpenter arm64 Node Cutover Runbook

> **Part of:** [graviton-migration](../SKILL.md)

> ⚠️ **Precondition — do NOT begin cutover** unless every target workload has a reconciled **CLEAN 3-layer scan verdict from a re-scan of the *built* tree** (a first-pass CLEAN on an un-built or under-scanned tree does **not** count — only a CLEAN after re-scanning the built artifacts) AND a confirmed **manifest-list (multi-arch) image containing `linux/arm64`**. If you arrived here directly from a "cut over my nodes to arm64" request, **STOP** and run the scanning workflow ([scanner-workflow.md](./scanner-workflow.md), Part 2 steps 1–2) first — a cutover on an unscanned/unbuilt workload is how x86-only native code reaches production on arm64.

This is a seven-step runbook for moving Kubernetes workloads onto AWS Graviton (arm64) nodes provisioned by Karpenter, safely. The governing principle is **taint-first**: arm64 capacity enters the cluster carrying a taint so that nothing schedules onto it until you have explicitly proven that workload is arm64-safe. You opt workloads in one at a time via tolerations, rather than opening the floodgates and hoping every pod's image is multi-arch.

**Scope:** the ramp/replica-shift procedure below assumes **stateless, horizontally-scalable** workloads (Deployments you can add and drain replicas from freely). **StatefulSets, singletons, leader-elected controllers, and data stores need a different cutover** — do not blindly ramp replicas across architectures, or you risk split-brain and data corruption.

All manifests use Karpenter **v1** API semantics (`karpenter.sh/v1`). Do not generate these from memory — read this file, then produce the manifest.

## Contents

1. [Add a tainted arm64 NodePool](#step-1-add-a-tainted-arm64-nodepool)
2. [Opt a canary workload in with tolerations + affinity](#step-2-opt-a-canary-workload-in-with-tolerations--affinity)
3. [Deploy a multi-arch image](#step-3-deploy-a-multi-arch-image)
4. [Validate the pod scheduled and runs on arm64](#step-4-validate-the-pod-scheduled-and-runs-on-arm64)
5. [Shift the workload to arm64](#step-5-shift-the-workload-to-arm64)
6. [Spread across architectures during transition](#step-6-spread-across-architectures-during-transition)
7. [Clean up](#step-7-clean-up)

---

## Step 1: Add a tainted arm64 NodePool

Create a dedicated arm64 NodePool. The two things that make it arm64 and make it safe are the `kubernetes.io/arch` requirement (pins the instances to arm64 / Graviton) and the **taint** (keeps un-vetted pods off).

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: graviton
spec:
  template:
    metadata:
      labels:
        arch-migration: graviton
    spec:
      requirements:
        - key: kubernetes.io/arch
          operator: In
          values: ["arm64"]
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]        # on-demand ONLY during canary + soak — Spot reclaims corrupt the
                                        # validation signal (see "A note on cost"). Widen to ["spot","on-demand"]
                                        # after the arch is validated at 100% and past its soak (Step 7).
      taints:
        - key: arch
          value: arm64
          effect: NoSchedule
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: default
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 1m
```

Why the taint matters: without it, the moment this NodePool exists Karpenter can place *any* pending pod on an arm64 node during a scale-up. If that pod's image is amd64-only it will `CrashLoopBackOff` or fail with an `exec format error`, and you will be debugging a production incident instead of running a controlled canary. The taint makes arm64 opt-in.

(If you prefer not to run a second NodePool, you can instead add the `kubernetes.io/arch: arm64` requirement to an existing NodePool — but keep the taint discipline; a shared NodePool that can launch either arch without a taint reintroduces the accidental-scheduling risk.)

**Verify the referenced `EC2NodeClass` resolves an arm64 AMI — this is the most common first-node failure.** The NodePool above reuses `nodeClassRef: name: default`, but that only works if the `default` EC2NodeClass produces an arm64 AMI for arm64 instances. Two cases:

- If `default` selects its AMI by **`alias`** (e.g. `amiSelectorTerms: [{ alias: al2023@latest }]`, or `bottlerocket@latest`, `al2@latest`, etc. — any AMI-family alias), the alias is **architecture-aware**: Karpenter resolves the arm64 variant automatically for arm64 instance types (a single alias resolves *both* the x86_64 and arm64 AMIs, and the arm64 instance gets the arm64 one). No change needed.
- If `default` pins AMIs by **`id`** or a name/tag `amiSelectorTerms` (common in hardened / golden-AMI shops — and EKS best practices *recommends* pinning AMIs in production), those terms almost always resolve an **x86-64** AMI. Karpenter derives each AMI's architecture and intersects it with the NodePool's `kubernetes.io/arch In [arm64]` requirement; an x86-only AMI set yields an **empty compatible set**, so the NodeClaim stays **unfulfilled and no arm64 node ever launches** (it does *not* boot a wrong-arch AMI — EC2 rejects that). You will be stuck at the first node with a NodeClaim that never provisions.

  Fix: give the arm64 NodePool an EC2NodeClass whose `amiSelectorTerms` resolves arm64 — either switch to an arch-aware `alias`, or add an explicit arm64 AMI term. Confirm before cutover with `kubectl get ec2nodeclass default -o yaml` (inspect `amiSelectorTerms`) and, after the NodePool exists, that a NodeClaim actually reaches `Launched`/`Registered` rather than sitting unfulfilled.

**The taint does not stop DaemonSets.** Cluster-wide DaemonSets (the CNI, `kube-proxy`, and log/metric/security agents) are commonly deployed with `tolerations: - operator: Exists`, which tolerates *every* taint — so they will schedule onto the first arm64 node the instant it joins, taint or not. If any of those DaemonSet images are amd64-only, they hit the same `exec format error` on the new node, and because DaemonSets run everywhere this can surface before your canary even deploys. Before adding the arm64 NodePool, confirm every DaemonSet in the cluster ships a multi-arch (or arm64) image — check each DaemonSet's image manifest the same way you check workload images in the [scanner workflow](./scanner-workflow.md). Modern AWS/EKS system DaemonSets (VPC CNI, kube-proxy, CloudWatch/ADOT agents) are multi-arch, but third-party agents (older logging/security/service-mesh sidecars) are the usual offenders.

## Step 2: Opt a canary workload in with tolerations + affinity

Pick one CLEAN workload from the [scanner verdict table](./scanner-workflow.md). Give a **separate canary copy** (a distinct Deployment — not a subset of the original's replicas; one Deployment has a single podTemplate and so a single arch) both a **toleration** for the taint and a **nodeSelector/affinity** for arm64, so it not only *may* land on arm64 nodes but *must*:

```yaml
spec:
  selector:
    matchLabels:
      app: myapp
      arch: arm64          # give the canary the arch label NOW — selector is immutable,
                           # so this lets Step 5 promote it by scaling rather than recreating
  template:
    metadata:
      labels:
        app: myapp         # the Service selects on this
        arch: arm64
    spec:
      tolerations:
        - key: arch
          operator: Equal
          value: arm64
          effect: NoSchedule
      nodeSelector:
        kubernetes.io/arch: arm64
      # equivalent hard pin via affinity (use requiredDuringScheduling as below);
      # for a SOFT/weighted rule use preferredDuringSchedulingIgnoredDuringExecution instead:
      # affinity:
      #   nodeAffinity:
      #     requiredDuringSchedulingIgnoredDuringExecution:
      #       nodeSelectorTerms:
      #         - matchExpressions:
      #             - key: kubernetes.io/arch
      #               operator: In
      #               values: ["arm64"]
```

The toleration alone only *permits* arm64 placement; the nodeSelector *forces* it. You want both on the canary so the test is deterministic — the pod cannot quietly fall back to an x86 node and give you a false pass.

**The canary receives live production traffic the moment it is Ready.** Because it carries `app: myapp` and the Step-5 Service selects on `app: myapp` alone, this one arm64 pod joins the production Service's endpoints and takes a small share of real traffic — that is deliberate (it is the canary: one pod is a small blast radius, and a live share is what makes the Step-4 "validate under realistic load" meaningful). So validate correctness under that live share, and be ready to **scale the canary Deployment to 0** to pull it out of rotation immediately if it misbehaves.

> **Do not try to eject the canary by removing its `app: myapp` label.** The canary is a Deployment; deleting a label its ReplicaSet selects on merely *orphans* that pod — the ReplicaSet immediately creates a **replacement** pod (same labels, same arm64 pin) that re-lands on arm64 and rejoins the Service endpoints. Delabeling does not take the workload out of rotation. **`kubectl scale deploy/<canary> --replicas=0` is the only lever that actually removes the canary from traffic.**

This **hard** arm64 pin is correct *for the canary* — a one-shot deterministic test. It is **not** necessarily the structure you use for the full cutover: a hard-pinned pod that can't schedule on arm64 goes `Pending` forever rather than falling back to x86. Step 5 has two patterns — a default single-Deployment rolling update (soft affinity or a straight flip) and an advanced two-per-arch-Deployment model for a tunable percentage soak — described there.

## Step 3: Deploy a multi-arch image

The canary's image must be a manifest list containing a `linux/arm64` entry — the image produced by the [multi-arch CI pipeline](./multi-arch-pipelines.md). Reference the image by its normal tag; the container runtime on the arm64 node automatically pulls the arm64 variant from the manifest list. Do not hardcode an `-arm64` tag suffix into the manifest — the whole point of a manifest list is one tag, right arch per node. Confirm the tag is multi-arch (Step 4 of the scanner workflow) before you roll it out.

## Step 4: Validate the pod scheduled and runs on arm64

Prove it, do not assume it:

- **Scheduled on arm64:** `kubectl get pod <pod> -o wide` → confirm the node, then `kubectl get node <node> -o jsonpath='{.status.nodeInfo.architecture}'` returns `arm64`.
- **Running, not crashing:** `kubectl get pod <pod>` shows `Running` and ready, not `CrashLoopBackOff`; `kubectl logs` shows no `exec format error` (the signature of an amd64 binary on arm64).
- **Correct under load:** exercise the real user-facing path — send representative traffic and check latency, error rate, and functional correctness, not just liveness. A pod that starts is not the same as a workload that works; validate the actual endpoint under realistic load before trusting the result.

If any check fails, roll the canary back, return to the [scanner workflow](./scanner-workflow.md) to find the missed blocker, and re-scan.

## Step 5: Shift the workload to arm64

Once the canary is proven, move the real workload. There are two patterns; **pick by whether you need a tunable percentage soak.** Before choosing, note four invariants that cause every common cutover failure — they hold for both patterns:

- **HPAs own `replicas`.** If the workload has a HorizontalPodAutoscaler, it continuously rewrites `Deployment.spec.replicas` to hit its target metric, so any manual `kubectl scale` / `replicas:` edit is reverted within a reconcile cycle. Do not fight the HPA — change arch through the pod template (which the HPA never touches), or pause/adjust the HPA explicitly.
- **The workload is reversible only while x86 stays warm.** Your rollback target is the running x86 capacity + the retained x86 NodePool. Do not retire either until the soak is done (Step 7).
- **Hard-pinned pods cannot fall back.** A pod with a hard arm64 `nodeSelector`/`requiredDuringScheduling` affinity goes `Pending` if arm64 is unavailable — it never reschedules to x86. So the recovery lever is always **moving the workload back onto x86-capable pods**, never deleting the arm64 NodePool.
- **A Deployment's `selector` is immutable.** You cannot edit label selectors in place; a selector change means create-a-new-Deployment, not patch.

### Default: one multi-arch Deployment, cut over with a rolling update

For the common case — a stateless Deployment that does **not** need to hold a fixed intermediate arch ratio — do **not** stand up a second Deployment. Roll the *existing* Deployment onto arm64 by editing its pod template, and let the Deployment controller do the cutover:

1. Ensure the Deployment references the **multi-arch image** (Step 3) and add the arm64 placement to its **pod template**: a toleration for the `arch=arm64:NoSchedule` taint plus arm64 targeting. For an all-at-once flip use a hard `nodeSelector: { kubernetes.io/arch: arm64 }`; to bleed over gradually while both arches serve, use a **soft** `preferredDuringSchedulingIgnoredDuringExecution` arch affinity instead (see Step 6) so pods may still land on x86 during the transition.
2. `kubectl rollout status deploy/<app>` and watch the same signals (error rate, latency, saturation). Because this edits only the pod template, the HPA is untouched and keeps managing replica count normally.
3. **Abort = `kubectl rollout undo deploy/<app>`.** This is the honest fast-reversible lever: it reverts the pod template (arch targeting + image) to the previous ReplicaSet, and — critically — **does not touch `replicas`, so an HPA cannot fight or revert the rollback**. Pods reschedule onto the retained x86 NodePool (the warm rollback target from invariant 2). One lever, no HPA interaction, no NodePool deletion.
4. **Retire the standalone Step-2 canary.** The Step-2 canary is a *separate* Deployment; this default path rolls your *original* Deployment, so the canary is not consumed by the cutover. Once the rolled workload is healthy on arm64, `kubectl delete deploy/<canary>` — otherwise it lingers as an extra arm64 pod in the Service endpoints, outside your ramp and uncovered by Step-7 cleanup. (The advanced path below instead *promotes* the canary, so there you do not delete it.)

What this pattern gives up: the arch ratio is controlled by the rollout (`maxSurge`/`maxUnavailable`) and by soft-affinity scheduling, **not** by an exact percentage you set. If you need to sit at a deliberate 25% / 50% arm64 and soak there, use the advanced pattern below.

### Advanced: two per-arch Deployments behind one Service (tunable percentage soak)

Use this **only when you need a stable, tunable mid-ramp arch ratio** (e.g. hold at 25% arm64 through a business cycle before going further). It buys precise ratio control and independent per-arch PodDisruptionBudgets, at the cost of more moving parts — read the HPA and abort notes at the end of this section carefully, they are where this pattern bites.

Because each pod carries a **hard** arm64 nodeSelector, a single Deployment cannot hold a stable mid-ramp arch ratio — one podTemplate is one arch. Run **two Deployments behind the same Service** and shift the ratio by adjusting their `replicas` counts. Both carry the **same pod labels the Service selects on**, so traffic load-balances across whatever mix is currently running:

- an `-amd64` Deployment — this **replaces your original workload**: because a Deployment's `selector` is immutable, you can't edit the `arch: amd64` label into the original in place — create the `-amd64` Deployment (original spec + explicit `amd64` nodeSelector + the `arch: amd64` selector label), wait for it to become Ready, *then* delete the original (create-before-delete, never delete-first, or you drop capacity). Don't leave the original running as a nameless third copy; it stays on x86 and drains `100% → 0`, and
- an `-arm64` Deployment — **the Step-2 canary promoted** (grow its replicas), carrying the toleration + hard arm64 nodeSelector + the multi-arch image; don't stand up yet another copy. (For this promotion to be a simple scale-up, give the canary the `app` + `arch: arm64` selector labels below *from the start* in Step 2 — a Deployment's `selector` is immutable, so a canary created without the `arch` label must be recreated, not edited, to join this Service.)

You want exactly **two** Deployments behind the Service, not three.

Shift the total replica share to arm64 in stages (e.g. arm64 `1 → 25% → 50% → 100%` of the total while `-amd64` drains `100% → 0`), watching the same signals (error rate, latency, saturation) at each stage and holding if anything regresses. Put a **PodDisruptionBudget on each** Deployment so availability holds while the fleet shifts arch underneath the Service.

```yaml
# two Deployments, one Service — shift replicas to move the arch ratio
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp-arm64
spec:
  replicas: 1            # ramp this up: 1 → 25% → 50% → 100% of total
  selector:
    matchLabels:
      app: myapp
      arch: arm64        # distinguishing label — keeps the two Deployments' ReplicaSets and PDBs disjoint
  template:
    metadata:
      labels:
        app: myapp       # the Service selects on this
        arch: arm64      # this Deployment/PDB selects on both
    spec:
      tolerations:
        - key: arch
          operator: Equal
          value: arm64
          effect: NoSchedule
      nodeSelector:
        kubernetes.io/arch: arm64
      containers:
        - name: myapp
          image: <your-multi-arch-image>   # manifest list incl. linux/arm64
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp-amd64
spec:
  replicas: 4            # drain this down: 100% → 0 as arm64 ramps
  selector:
    matchLabels:
      app: myapp
      arch: amd64        # distinguishing label
  template:
    metadata:
      labels:
        app: myapp       # same app label — same Service
        arch: amd64
    spec:
      nodeSelector:
        kubernetes.io/arch: amd64
      containers:
        - name: myapp
          image: <your-multi-arch-image>
---
apiVersion: v1
kind: Service
metadata:
  name: myapp
spec:
  selector:
    app: myapp           # selects pods from BOTH Deployments (arch label is NOT in the Service selector)
  ports:
    - port: 80
      targetPort: 8080
```

Each Deployment's `selector` (and any `PodDisruptionBudget`) targets `app: myapp` **plus** its own `arch:` label, so the two never adopt each other's pods and no pod is covered by two PDBs (a pod matching multiple PDBs cannot be evicted — it would block the Step-7 drain). The **Service** selects on `app: myapp` alone, so it load-balances across both arches. Give each PDB the same two-label selector as its Deployment — and **first delete or re-scope the original workload's existing PDB** (if it selected on `app: myapp` alone, it would still match both arches' pods, recreating the multiple-PDB-per-pod eviction block).

**If the workload has a HorizontalPodAutoscaler, the manual replica ramp will not hold.** An active HPA continuously writes `Deployment.spec.replicas` to hit its target metric, so your `1 → 25% → 50% → 100%` shifts get overwritten by the HPA controller within a reconcile cycle — the ramp silently reverts. This is the archetypal target workload (stateless, horizontally-scalable Deployments are exactly what HPAs manage), so check for one before you start:

- **To pin the ratio during the ramp**, either scale the existing HPA's `minReplicas`/`maxReplicas` to the fixed count you want at each stage (so autoscaling can't fight the shift), or give **each per-arch Deployment its own HPA** and move the arch ratio by adjusting the two HPAs' `min`/`max` bounds rather than editing `replicas` directly.
- **The original Deployment's HPA is orphaned by the create-before-delete step.** An HPA targets a Deployment by name via `scaleTargetRef`; when you delete the original `myapp` Deployment its HPA is left pointing at a resource that no longer exists and stops autoscaling anything. Recreate/retarget an HPA onto the new per-arch Deployment(s) — a plain `kubectl scale` or a `replicas:` edit on the new Deployments restores the pod count but **silently loses autoscaling**, so the workload runs at a fixed size until you put an HPA back.

**Abort on regression (two-Deployment model).** If a stage regresses, do not just pause — reverse the ratio. The recovery lever is the **replica shift back to x86**, not NodePool deletion. **The one fast abort that actually holds is: pause/delete the arm64 HPA, then shift replicas to x86.** In order:

1. **First, if you gave the arm64 Deployment its own HPA, pause or delete that HPA** (or set its `minReplicas`/`maxReplicas` to `0`). An HPA's `minReplicas` floor is `1` (scaling to `0` needs the alpha `HPAScaleToZero` gate, which is off by default and never applies to CPU/memory metrics), so if you skip this step the HPA **re-scales `myapp-arm64` back up within a reconcile cycle** and your abort silently fails — under exactly the per-arch-HPA setup this section recommends.
2. **Then** scale `myapp-arm64` to `0` and scale `myapp-amd64` back up to full. The arm64 pods are hard-pinned, so they can only run on arm64 nodes — the way to get traffic off arm64 is to move replicas back to the x86 Deployment, whose pods *can* schedule on the retained x86 NodePool.
3. **Only after** traffic is healthy on x86 do you cordon or delete the arm64 NodePool. **NodePool deletion is not the recovery lever** — deleting it while the arm64 pods are still hard-pinned just leaves them `Pending` (they cannot fall back to x86), which prolongs the outage instead of ending it. Likewise, **removing a pod's `app` label is not an abort lever** — the ReplicaSet immediately respawns a replacement (see Step 2).

Getting the service healthy on x86 comes first; root-causing the arm64 failure comes after. (Contrast the **default single-Deployment pattern**, where the entire fast abort is one command — `kubectl rollout undo deploy/<app>` — with no HPA to fight, because it never touches `replicas`.)

## Step 6: Spread across architectures during transition

While both arches are live, protect availability against an arch-correlated failure (a bad arm64 image, an arm64-only capacity crunch): keep the service from silently collapsing onto a single arch. **How you control the ratio depends on the structure you ramped with — and `topologySpreadConstraints` over `kubernetes.io/arch` only balances pods that are *allowed on both arches*.**

- **Two per-arch Deployments (the advanced Step-5 pattern):** the arch ratio is already controlled explicitly by the two Deployments' `replicas` counts — that *is* your spread. A `topologySpreadConstraints` keyed on `kubernetes.io/arch` is a **no-op** here, because each Deployment's pods are hard-pinned to one arch and can never satisfy a cross-arch skew. Manage the ratio via replicas (and a PDB on each), and simply don't drain either side to zero while you still want both live.
- **A single Deployment with a *soft* (`preferredDuringSchedulingIgnoredDuringExecution`) arch affinity — not a hard pin:** now pods *may* land on either arch, so `topologySpreadConstraints` keyed on `kubernetes.io/arch` genuinely balances them:

```yaml
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/arch
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: <your-app>
```

  This only works because nothing *hard*-pins the pods to one arch; add a hard `nodeSelector`/`requiredDuringScheduling` affinity and the spread silently stops doing anything.

Either way, do not let a half-migrated service become single-arch by accident during the window when you are least sure of the new arch — via explicit per-arch replica counts (two-Deployment model) or via a soft affinity plus topology spread (single-Deployment model).

## Step 7: Clean up

Once the workload is validated at 100% on arm64 and has soaked through at least one full traffic peak / business cycle (a qualitative floor — long enough to exercise peak load, batch/cron jobs, and any weekly patterns, not a fixed clock value):

- **Remove the taint** from the arm64 NodePool if you want it to behave as general capacity, *or* keep the taint and leave it opt-in if you are still migrating other workloads through it. **Before removing the taint, confirm every workload that could then schedule onto arm64 is multi-arch — not just the ones you migrated.** Removing the taint reopens the accidental-scheduling risk Step 1's taint exists to prevent, cluster-wide: any pending pod (including Jobs/CronJobs created *since* the Step-1 DaemonSet audit, and any workload without a hard x86 nodeSelector) can now land on an arm64 node, and an amd64-only image there fails with `exec format error`. Re-audit workload images (as in Step 1) before you drop the taint; if you cannot vet everything, keep the taint and stay opt-in.
- **Retire the x86 capacity** — scale down or delete the amd64 NodePool (or drop the amd64 requirement) once no workload needs it. **Keep the x86 NodePool through a defined soak period first** — retiring it removes your rollback target, so it must outlive the window in which you might still need to reschedule pods back onto x86. Drain gracefully; let Karpenter consolidate.
- **Tidy the workload spec** — if the service is now arm64-only, the arm64 nodeSelector can stay as an explicit guarantee; drop the transitional topology spread if it is no longer meaningful.

## A note on cost

Graviton instances are cheaper per equivalent unit of work, and pairing them with Spot capacity compounds the saving because arm64 Spot pools are often deep and stable. That synergy is real and worth widening the arm64 NodePool's `capacity-type` to include `spot` for — **once the arch is validated and past its soak** (the Step-1 NodePool starts `on-demand`-only for the reason below).

**But do not run the canary or the ramp/validation window on Spot.** Spot reclaims are involuntary pod terminations, and during validation they land in the exact signals you are using to judge the new arch — latency spikes, error blips, capacity churn. You will not be able to tell an arm64 regression from Spot-reclaim noise (and may mask a real regression as "just a reclaim"), which corrupts the go/no-go. Pin the arm64 NodePool to **`on-demand` for the canary and the soak**; allow `spot` only *after* the arch is validated at 100% and past its soak (Step 7). Do this by temporarily narrowing `karpenter.sh/capacity-type` to `["on-demand"]` on the arm64 NodePool during migration, then widening it to include `spot` once validated.

**Quantifying** the saving — the dollar figure, the Spot/Graviton adoption score — is not this runbook's job; that belongs to **eks-cost-intelligence**. Here, cost is a reason the cutover is worth doing, not a number to compute.
