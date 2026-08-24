# Workload Configuration

## Purpose
Assess workload resilience: resource requests/limits, health probes, disruption budgets, image hygiene, and storage configuration.

## Checks to Execute

### 5.1 — Resource Requests and Limits

**What to check:**
- Running pods missing resource requests or limits
- LimitRange resources in namespaces
- ResourceQuota resources in namespaces
- Recent OOMKilled events
- Admission webhooks enforcing resources (Kyverno, Gatekeeper)

**How to check:**
1. List pods (Running) across all namespaces → inspect `spec.containers[].resources.requests` and `.limits`. If 403/Forbidden when listing pods → mark the request/limit coverage signal UNKNOWN (do not treat an unreadable pod list as 0% coverage → false RED); pod is a core API so 404 is not expected. Coverage is the primary signal, so if it is UNKNOWN the check rates UNKNOWN (see UNKNOWN band) rather than RED/AMBER/GREEN.
2. Count pods with no requests vs total running pods → calculate percentage
3. List LimitRange resources across all namespaces. If 403/Forbidden → mark the LimitRange signal UNKNOWN (do not conclude absence); LimitRange is a core API so 404 is not expected — treat an empty successful list as no LimitRange.
4. List ResourceQuota resources across all namespaces. If 403/Forbidden → mark the ResourceQuota signal UNKNOWN (do not conclude absence); ResourceQuota is a core API so 404 is not expected — treat an empty successful list as no ResourceQuota.
5. Get events with reason=OOMKilling (count occurrences within the last hour, or the cluster's event-retention window if shorter — thresholds applied in the Rating block below). If 403/Forbidden when listing events → mark the OOMKill signal UNKNOWN (do not conclude zero OOMKills from an unreadable event stream). The OOMKill count feeds a defined AMBER trigger (>5/hr) and RED trigger (>20/hr), so an unverifiable OOMKill signal must not award a clean GREEN on the strength of an unconfirmed-absent storm — apply the 403 OOMKill-signal rule in the Rating block below.
6. List ValidatingWebhookConfigurations and MutatingWebhookConfigurations. If 403/Forbidden → mark the admission-enforcement signal UNKNOWN (do not conclude "no enforcement"); admissionregistration.k8s.io is core so 404 is not expected — an empty successful list means no admission webhooks.

**Rating:**
- 🟢 GREEN: >=90% of pods have requests (the 90% coverage bar is a skill-defined heuristic, not an AWS-published threshold), LimitRange/ResourceQuota in place, admission enforcement, AND the OOMKill events read SUCCEEDED and showed no OOMKill storm (an unverifiable OOMKill signal cannot award GREEN — see 403 OOMKill-signal rule)
- 🟡 AMBER: 50% to <90% of pods have requests (coverage below the GREEN bar), or most pods have requests but no enforcement mechanism, or requests broadly present but no LimitRange / ResourceQuota defined, or fewer than 50% of pods have requests but a LimitRange / ResourceQuota or admission enforcement is present (governance mitigates the low coverage, so not RED), or >5 OOMKill events in the last hour (or the cluster's event-retention window, whichever is available)
- 🔴 RED: Majority of pods missing requests AND no LimitRange AND no ResourceQuota AND no enforcement, OR >20 OOMKill events in the last hour (or the cluster's event-retention window, whichever is available)
- ⬜ UNKNOWN: The pod list returned 403/Forbidden, so request/limit coverage cannot be computed (an unreadable pod list must not be treated as 0% coverage → false RED). If instead only the enforcement signals returned 403, apply the 403 enforcement-signal rule below rather than rating UNKNOWN.
- **Evaluation order:** assess RED first; if not RED, assess AMBER; otherwise GREEN. Keeps the bands exhaustive and non-overlapping.
- **403 enforcement-signal rule:** when the enforcement signals (LimitRange/ResourceQuota/admission) are UNKNOWN because their lists returned 403/Forbidden, and those signals would otherwise be the deciding factor between RED and AMBER, do not rate RED on the strength of an unconfirmed absence. Record the enforcement uncertainty under Investigate Manually, then rate deterministically: if the other signals (request/limit coverage, OOMKill history) were read successfully and are GREEN-worthy, cap the check at AMBER with the note "resource governance signals look adequate but enforcement (LimitRange/ResourceQuota/admission) could not be verified"; if nothing else is confirmed, rate the check UNKNOWN. Do not leave the AMBER-vs-UNKNOWN choice to rater preference. A genuine RED still requires an empty *successful* list confirming no LimitRange and no enforcement.
- **403 OOMKill-signal rule:** the OOMKill event count feeds a RED trigger (>20/hr) and an AMBER trigger (>5/hr). Events RBAC is commonly narrower than pods, so the events read can be forbidden while coverage/enforcement look GREEN-worthy. When the events read returned 403/Forbidden, the OOMKill RED/AMBER trigger is UNDETERMINABLE — a clean GREEN must not be awarded on the strength of an unverifiable OOMKill storm. Cap the rating at AMBER with the note "resource governance looks adequate but OOMKill history could not be verified" and record the OOMKill uncertainty under Investigate Manually. (This never *raises* a band: a confirmed >20/hr RED or >5/hr AMBER still requires a *successful* events read; the forbidden case only caps GREEN down to AMBER, never up to RED.) GREEN remains reachable only when the events read SUCCEEDED and showed no OOMKill storm.

**Key talking point:** Without resource requests, the scheduler is flying blind. Don't set CPU limits equal to requests — causes unnecessary throttling.

---

### 5.2 — Health Probes Configured

**What to check:**
- Deployments missing readiness probes
- Deployments missing liveness probes
- Deployments missing startup probes (important for slow-starting apps: JVM/Java, Kotlin, Scala, or apps with long initialization >10s)
- Pods in CrashLoopBackOff (may indicate bad liveness probes)

**How to check:**
1. List Deployments across all namespaces → inspect containers for readinessProbe, livenessProbe, startupProbe. If 403/Forbidden when listing Deployments → mark the probe-coverage signal UNKNOWN (do not conclude probes absent); apps/v1 Deployment is a core API so 404 is not expected; an empty successful list means no Deployments.
2. Count deployments missing each probe type
3. List pods not in Running/Succeeded phase → check for CrashLoopBackOff. If 403/Forbidden when listing pods → mark the CrashLoopBackOff signal UNKNOWN (do not conclude no CrashLoopBackOff from an unreadable pod list); this signal feeds the RED trigger, so its absence must be observed via a *successful* list and never inferred from a forbidden read. Because GREEN's precondition is probe coverage only, a forbidden pod list would otherwise let a real CrashLoopBackOff pass as GREEN — apply the 403 CrashLoop-signal rule in the Rating block below.

**Rating:**
- 🟢 GREEN: >=90% of deployments have readiness probes (the 90% coverage bar is a skill-defined heuristic, not an AWS-published threshold) AND the pod list used to detect CrashLoopBackOff SUCCEEDED and showed no CrashLoopBackOff (an unverifiable CrashLoop signal cannot award GREEN — see 403 CrashLoop-signal rule)
- 🟡 AMBER: 50% to <90% of deployments have readiness probes (present on most but not all), or liveness probes missing on most deployments
- 🔴 RED: <50% of deployments have readiness probes (majority missing), or workloads stuck in CrashLoopBackOff (often a symptom of a misconfigured liveness probe)
- ⬜ UNKNOWN: Cannot determine readiness/liveness probe coverage (e.g. the Deployment list returned 403/Forbidden), so probe coverage cannot be assessed
- **Startup-probe note (non-scoring):** whether an app is JVM/slow-starting (long initialization >10s) is not observable from cluster state, so startup-probe absence is NOT a band boundary. If deployments lack startup probes, record this under Investigate Manually for the user to confirm which workloads are slow-starting; do not raise or lower the band on this basis.
- **403 CrashLoop-signal rule:** CrashLoopBackOff feeds the RED trigger, and GREEN's precondition is probe coverage only, so a Deployment-list-OK + pod-list-403 case would otherwise pass a real CrashLoopBackOff as a clean GREEN. When the pod list used to detect CrashLoopBackOff returned 403/Forbidden, the CrashLoop RED trigger is UNDETERMINABLE — a clean GREEN must not be awarded on the strength of an unverified absence. Cap the rating at AMBER with the note "probe coverage looks adequate but CrashLoopBackOff status could not be verified" and record the CrashLoop uncertainty under Investigate Manually. (This never *raises* a band: a confirmed CrashLoopBackOff RED still requires a *successful* pod list; the forbidden case only caps GREEN down to AMBER, never up to RED.) GREEN remains reachable only when the pod list SUCCEEDED and showed no CrashLoopBackOff.
- **Evaluation order:** assess RED first; if not RED, assess AMBER; otherwise GREEN. Keeps the bands exhaustive and non-overlapping.

---

### 5.3 — Pod Disruption Budgets (PDBs)

**What to check:**
- PDB resources and their settings
- Multi-replica deployments without PDBs
- PDBs with disruptionsAllowed=0 (blocks upgrades). If disruptionsAllowed=0 AND replicas=1, mark RED (single point of failure that also blocks node drains)
- Single-replica deployments (inherently not disruption-safe)

**How to check:**
1. List PodDisruptionBudgets across all namespaces → check minAvailable, maxUnavailable, disruptionsAllowed. If 403/Forbidden when listing PDBs → mark PDB coverage UNKNOWN (do not conclude "No PDBs at all" → false RED from an unreadable PDB list); policy/v1 PodDisruptionBudget is a core API so 404 is not expected — an empty successful list means no PDBs.
2. List Deployments with replicas > 1 → compare against PDB coverage. If 403/Forbidden when listing Deployments → mark Deployment coverage UNKNOWN (do not infer single-replica/coverage from an unreadable list); apps/v1 Deployment is a core API so 404 is not expected.
3. List Deployments with replicas == 1 (uses the same Deployment list as step 2; the same 403→UNKNOWN guard applies)

**Rating:**
- 🟢 GREEN: PDBs on all multi-replica production deployments with reasonable settings — where "reasonable" means each PDB leaves disruptionsAllowed >= 1 (does not set minAvailable equal to the replica count, and does not set maxUnavailable=0), so voluntary disruptions and node drains are not blocked
- 🟡 AMBER: PDBs on some but not all multi-replica deployments, or one or more PDBs block disruptions (disruptionsAllowed=0) on multi-replica (>1) deployments
- 🔴 RED: No PDBs at all, or any assumed-production workload (see Criticality assumption) running single-replica (replicas=1, inherently not disruption-safe), or a PDB with disruptionsAllowed=0 AND replicas=1 (single point of failure that also blocks node drains)
- ⬜ UNKNOWN: Cannot enumerate Deployments or PodDisruptionBudgets (e.g. RBAC forbids `list`), so coverage cannot be assessed
- **Criticality assumption:** workload criticality cannot be observed from cluster state. When criticality cannot be determined, treat workloads in application namespaces (exclude `kube-system`, `kube-public`, `kube-node-lease`, and `default`) as production for this check, apply the single-replica RED only to those assumed-production workloads, and record this assumption under Investigate Manually.
- **403 floor-and-cap rule:** a confirmed RED survives a 403 on a different read — e.g. a single-replica assumed-production Deployment (or a PDB with disruptionsAllowed=0) observed via a *successful* list stays RED even if the other list returned 403 (CONFIRMED FLOOR). GREEN requires PDBs *confirmed* present on all multi-replica deployments, so a 403 on the PDB list (PDB coverage UNKNOWN) must not award a clean GREEN on the strength of unconfirmed-present PDBs — cap at AMBER with the note "multi-replica deployments look present but PDB coverage could not be verified", or UNKNOWN, never GREEN. Whole-check UNKNOWN only when neither list yields a confirmed color AND the 403 was the sole discriminator.
- **Evaluation order:** assess RED first; if not RED, assess AMBER; otherwise GREEN. Keeps the bands exhaustive and non-overlapping.

---

### 5.4 — Image Tag Hygiene

**What to check:**
- Running pods using `:latest` tag or no tag
- ECR repositories: tag immutability and scan-on-push settings
- Image registries in use (ECR vs Docker Hub vs other)

**How to check:**
1. List running pods → inspect container images for `:latest` or missing tag. If 403/Forbidden when listing pods → mark the `:latest`/registry signals UNKNOWN (do not fabricate a tag or registry rating from an unreadable pod list); pod is a core API so 404 is not expected.
2. Use AWS API to describe ECR repositories → check `imageTagMutability` (IMMUTABLE vs MUTABLE) and `imageScanningConfiguration.scanOnPush`. If the ECR read is denied (e.g. `ecr:DescribeRepositories` returns AccessDenied/403) → mark the tag-immutability and scan-on-push signals UNKNOWN (do not assume enabled → false GREEN, and do not assume disabled → false AMBER/RED). Immutability and scan-on-push are GREEN preconditions, so an unverifiable ECR posture must not award a clean GREEN on the strength of an unconfirmed-good config — apply the 403 ECR-signal rule in the Rating block below (cap at AMBER-with-note) and record the ECR-posture uncertainty under Investigate Manually. Rate the observable `:latest`/registry dimensions RED-first (a confirmed `:latest`/non-ECR-registry RED still stands). Check 8.2 defers these image-scanning/immutability facts here, so a forbidden ECR read must surface as UNKNOWN, not a confirmed posture.
3. Aggregate image registries from pod specs (uses the same pod list as step 1; the same 403→UNKNOWN guard applies)

**Rating:**
- 🟢 GREEN: No `:latest` in production — all production workloads use pinned version or digest-pinned images — AND the ECR read SUCCEEDED and confirmed tag immutability and scan-on-push enabled (an unverifiable ECR posture cannot award GREEN — see 403 ECR-signal rule)
- 🟡 AMBER: `:latest` on <20% of production workloads (mostly versioned tags but some `:latest`), or ECR without immutability, or ECR scan-on-push disabled, or no ECR (private) usage — images run only from non-ECR registries the account controls (e.g. ECR Public, or a private / self-hosted registry), so ECR-based scan-on-push and tag-immutability posture cannot be confirmed
- 🔴 RED: `:latest` on >=20% of production workloads (widely used), or images pulled from a public registry other than ECR / ECR Public (e.g. Docker Hub, quay.io, gcr.io) — i.e. not an ECR or ECR-Public registry the account controls
- ⬜ UNKNOWN: The pod list returned 403/Forbidden, so `:latest`/registry coverage cannot be computed and no image signal is observable. If instead only the ECR describe returned 403 (the pod list SUCCEEDED), apply the 403 ECR-signal rule below rather than rating the whole check UNKNOWN — the observable `:latest`/registry dimensions still yield a color.
- **403 ECR-signal rule:** tag immutability and scan-on-push feed AMBER triggers (ECR without immutability, ECR scan-on-push disabled) and are GREEN preconditions, so a pod-list-OK + ECR-describe-403 case would otherwise pass an unconfirmed ECR posture as a clean GREEN. When the ECR describe returned 403/Forbidden, the immutability/scan-on-push signals are UNDETERMINABLE — a clean GREEN must not be awarded on the strength of an unverified-good ECR config. Cap the rating at AMBER with the note "image tags look fine but ECR immutability/scan-on-push could not be verified" and record the ECR-posture uncertainty under Investigate Manually. (This never *raises* a band: a confirmed `:latest`/non-ECR-registry RED still stands on the observable dimensions; the forbidden ECR case only caps GREEN down to AMBER, never up to RED.) GREEN remains reachable only when the ECR read SUCCEEDED and confirmed both tag immutability and scan-on-push enabled.
- **Criticality assumption:** workload criticality cannot be observed from cluster state. When criticality cannot be determined, treat all application namespaces (exclude `kube-system`, `kube-public`, `kube-node-lease`, and `default`) as production, apply the numeric thresholds to the `:latest` dimension only (GREEN none / AMBER <20% / RED >=20%); the ECR/registry AMBER clauses (immutability, scan-on-push, non-ECR registry) STILL APPLY. This assumption scopes only the criticality-of-`:latest` question, not the whole check. Record this assumption under Investigate Manually.
- **Unlisted-registry catch-all:** for a registry domain that is neither ECR/ECR-Public nor a known public registry (Docker Hub/quay.io/gcr.io/ghcr.io), the account's control over it is not observable from the image reference — treat it as AMBER (unverified external registry) and record it under Investigate Manually for the user to confirm ownership. This makes every registry domain land in exactly one band.
- **Evaluation order:** assess RED first; if not RED, assess AMBER; otherwise GREEN. Keeps the bands exhaustive and non-overlapping.
- **Scoring authority:** this check owns ECR image facts (tag immutability, scan-on-push, registry trust); check 8.2 defers here for image scanning/immutability.

---

### 5.5 — Persistent Volume & Stateful Workload Configuration

**What to check:**
- StorageClasses: provisioner, reclaimPolicy, volumeBindingMode, gp2 vs gp3
- PVCs and their status
- CSI drivers installed
- EBS CSI driver add-on status
- VolumeSnapshotClasses (backup support)
- StatefulSets
- Deprecated in-tree volume plugin usage

**How to check:**
1. List StorageClasses → for each, record provisioner (in-tree `kubernetes.io/aws-ebs` vs CSI `ebs.csi.aws.com`/`efs.csi.aws.com`), gp2 vs gp3, reclaimPolicy, volumeBindingMode. A StorageClass is only a finding when PVs are actually **bound** to it (cross-reference steps 2 and 7); the default `gp2` SC that ships on non-Auto-Mode EKS uses the in-tree `kubernetes.io/aws-ebs` provisioner but is frequently present-but-unused. If 403/Forbidden → mark the StorageClass signals (provisioner, gp2/gp3, reclaim policy, binding mode) UNKNOWN (do not conclude gp3 nor its absence from an unreadable list); storage.k8s.io StorageClass is a core API so 404 is not expected.
2. List PVCs across all namespaces, and for each bound PVC record which StorageClass/provisioner it uses (this establishes whether an in-tree or gp2 StorageClass is *actually in use* vs merely present). If 403/Forbidden → mark PVC/binding signals UNKNOWN (do not conclude "no stateful workloads" → false N/A, and do not infer an in-tree/gp2 in-use finding from an unreadable list); pod/PVC are core APIs so 404 is not expected.
3. List CSIDrivers. If 403/Forbidden → mark CSI-driver-managed signal UNKNOWN (do not conclude in-tree usage → false RED from an unreadable list).
4. Describe addon `aws-ebs-csi-driver`. If the AWS read is denied (AccessDenied/403) → mark the managed-CSI-addon signal UNKNOWN (do not assume the add-on absent → false rating).
5. List VolumeSnapshotClasses. If 404/NotFound (CRD not installed) → no snapshot support configured; report this as supporting context for check 9.4 (which owns the backup/DR signal), not scored in 5.5's bands. If 403/Forbidden → mark snapshot capability UNKNOWN.
6. List StatefulSets across all namespaces. If 403/Forbidden → mark the StatefulSet signal UNKNOWN (do not conclude "no stateful workloads" → false N/A from an unreadable list); apps/v1 StatefulSet is a core API so 404 is not expected.
7. List PersistentVolumes → check for `spec.awsElasticBlockStore` (deprecated in-tree). If 403/Forbidden → mark the deprecated-in-tree signal UNKNOWN (do not conclude no in-tree usage, and do not fabricate an in-tree RED, from an unreadable PV list); PersistentVolume is a core API so 404 is not expected.

**Rating:** (If N/A applies (no stateful workloads — successful empty StatefulSet AND PVC enumeration), N/A takes precedence over the colored bands. Otherwise evaluate RED first, then AMBER, then GREEN; the AMBER catch-all makes the bands exhaustive over every readable storage state — see decision rule below. Note: `reclaimPolicy=Delete` is the DEFAULT for every dynamically-provisioned EBS volume and is NOT by itself a RED or AMBER trigger — see Reclaim-policy note.)
- 🔴 RED: Deprecated in-tree volume plugin **actually in use** — a PV with `spec.awsElasticBlockStore`, or one or more PVs/PVCs **bound** to a StorageClass whose provisioner is an in-tree plugin such as `kubernetes.io/aws-ebs`. A merely-present-but-unused in-tree/default-gp2 StorageClass with zero bound PVs is NOT RED (see AMBER/benign-note handling).
- 🟡 AMBER (any of):
  - gp2 **in use** — one or more PVs/PVCs bound to a gp2 StorageClass (whether the CSI `ebs.csi.aws.com` gp2 or the in-tree default gp2), superseded by gp3. (If that in-use gp2 SC uses an in-tree provisioner, it is RED per the rule above, not AMBER — the in-tree-in-use RED and the gp2-in-use AMBER never both fire on one state; RED wins.), OR
  - **catch-all — storage config present but not matching the best-practice profile:** readable storage is in use (PVs/PVCs bound) but does not qualify for GREEN and triggers no RED — e.g. an `Immediate` binding mode on topology-constrained block storage, or a non-deprecated but non-preferred CSI StorageClass/driver. Flag for review under Investigate Manually.
- 🟢 GREEN: All **in-use** persistent storage (PVs/PVCs actually bound) is served by a modern, non-deprecated CSI driver (gp3, io2, EFS, or another current CSI provisioner — not gp2, not an in-tree plugin) with an appropriate binding mode (WaitForFirstConsumer for topology-constrained block storage such as gp3/io2/EBS — binding mode is not a discriminator for topology-agnostic drivers such as EFS). The reclaim policy is NOT a GREEN discriminator: a cluster on modern CSI storage stays GREEN even when volumes use the `Delete` default (including StatefulSet-attached PVCs), and a merely-present-but-unused default gp2 / in-tree StorageClass with zero bound PVs does not block GREEN (record it as a benign note, not a finding).
- N/A: No stateful workloads on EKS — requires a *successful* empty enumeration of StatefulSets and PVCs; if either list returned 403/Forbidden, rate UNKNOWN, not N/A (a forbidden read must not produce a false-favorable N/A)
- ⬜ UNKNOWN: Cannot enumerate StorageClasses, PVs/PVCs, or StatefulSets (e.g. RBAC forbids `list`), so provisioner-in-use and binding-mode signals cannot be assessed
- **Decision rule (every readable combination lands in exactly one band):** classify by, in order — (0) if there are no stateful workloads (a *successful* empty enumeration of BOTH StatefulSets and PVCs) → N/A, and N/A takes precedence over the colored bands — an orphaned PV (e.g. a lingering `spec.awsElasticBlockStore` PV) with zero bound PVCs and zero StatefulSets resolves to N/A here, exactly as check 9.4 resolves the identical state, and does NOT fire the RED arm below; (1) else any PV with `spec.awsElasticBlockStore`, or any PV/PVC **bound** to an in-tree-provisioner StorageClass → RED; (2) else any PV/PVC **bound** to a gp2 StorageClass → AMBER; (3) else, if all in-use storage is modern-CSI (gp3/io2/EFS/other current CSI) with an appropriate binding mode → GREEN (regardless of reclaim policy, and regardless of any unused default gp2/in-tree SC merely being present); (4) else (readable in-use storage that is neither clean-GREEN nor a RED/AMBER-specific trigger — e.g. an `Immediate` binding on topology-constrained CSI block storage, or another non-preferred CSI StorageClass that misses a GREEN precondition) → AMBER catch-all. This guarantees no {provisioner (in-tree/CSI) × storage type (gp2/gp3/io2/EFS) × bound-PVs?/unused-SC × reclaim (Delete/Retain) × StatefulSet-attached?} combination falls through unrated: an unused in-tree/gp2 SC with zero bound PVs is a benign note (no band), and reclaim policy never moves the band. N/A and UNKNOWN apply only when the relevant enumerations are empty-but-successful or forbidden, respectively.
- **Reclaim-policy note (Investigate Manually, not a scoring band):** `reclaimPolicy=Delete` is the normal default for dynamically-provisioned EBS volumes and is NOT inherently a defect — it must NOT by itself trigger RED or AMBER. Whether `Delete` is appropriate for a given workload's data (e.g. a database on a StatefulSet-attached PVC) is not observable from cluster state — we cannot identify "databases" or "production" from cluster state. Record a single Investigate-Manually note: "review whether the `Delete` reclaim policy is appropriate for your stateful workloads' data; back it with a tested restore path." Backup/DR coverage that would mitigate a `Delete` reclaim (Velero, snapshots) is owned by check 9.4 — 5.5 defers the backup signal there and does not turn a reclaim concern into a 5.5 RED.
- **Unused-StorageClass note:** the default `gp2` StorageClass (in-tree `kubernetes.io/aws-ebs`) ships on virtually every non-Auto-Mode EKS cluster and is commonly present with zero bound PVs. A present-but-unused in-tree/gp2 StorageClass is not a finding — record it at most as a benign note ("default gp2 StorageClass present but unused; consider setting gp3 as default"), never RED and never AMBER. Only PVs/PVCs actually **bound** to such a StorageClass promote it to a finding (in-tree bound → RED, gp2 bound → AMBER).
- **403 floor-and-cap rule:** a confirmed RED survives a 403 on a different read — e.g. deprecated in-tree volume usage (`spec.awsElasticBlockStore`) observed via a *successful* PV list, or a PV/PVC bound to an in-tree-provisioner StorageClass observed via successful PV/PVC + StorageClass lists, stays RED even if another list (CSI drivers, snapshot classes) returned 403 (CONFIRMED FLOOR). GREEN requires the modern-CSI-driver and appropriate-binding-mode preconditions all *confirmed* via successful reads, so a 403 on any read that carries one of those signals (StorageClass list, PV/PVC list, CSI-driver list) leaves that precondition UNKNOWN and must not award a clean GREEN — cap at AMBER-with-note or UNKNOWN, never GREEN. N/A stays gated on a *successful* empty enumeration of both StatefulSets and PVCs (a 403 on either → UNKNOWN, never N/A). Whole-check UNKNOWN only when nothing confirmed yields a color AND the 403 was the sole discriminator.
- **Scoring authority:** this check owns deprecated in-tree storage plugin usage and PV/StatefulSet configuration; check 10.1 defers here for the deprecated-in-tree-storage signal. Backup/DR coverage (including snapshot strategy) is owned by check 9.4 — 5.5 defers there for the backup signal and does not score it.
