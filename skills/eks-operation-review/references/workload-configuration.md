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
1. List pods (Running) across all namespaces → inspect `spec.containers[].resources.requests` and `.limits`
2. Count pods with no requests vs total running pods → calculate percentage
3. List LimitRange resources across all namespaces
4. List ResourceQuota resources across all namespaces
5. Get events with reason=OOMKilling (count occurrences — >5 in recent events = AMBER, >20 = RED)
6. List ValidatingWebhookConfigurations and MutatingWebhookConfigurations

**Rating:**
- 🟢 GREEN: >90% of pods have requests, LimitRange/ResourceQuota in place, admission enforcement
- 🟡 AMBER: Most pods have requests but no enforcement mechanism, or frequent OOMKills
- 🔴 RED: Majority of pods missing requests, no LimitRange, no enforcement
- ⬜ UNKNOWN: Should not happen with live access

**Key talking point:** Without resource requests, the scheduler is flying blind. Don't set CPU limits equal to requests — causes unnecessary throttling.

---

### 5.2 — Health Probes Configured

**What to check:**
- Deployments missing readiness probes
- Deployments missing liveness probes
- Deployments missing startup probes (important for slow-starting apps: JVM/Java, Kotlin, Scala, or apps with long initialization >10s)
- Pods in CrashLoopBackOff (may indicate bad liveness probes)

**How to check:**
1. List Deployments across all namespaces → inspect containers for readinessProbe, livenessProbe, startupProbe
2. Count deployments missing each probe type
3. List pods not in Running/Succeeded phase → check for CrashLoopBackOff

**Rating:**
- 🟢 GREEN: >90% of deployments have readiness probes, startup probes on slow-starting apps
- 🟡 AMBER: Readiness probes on most but not all, or no startup probes for JVM apps
- 🔴 RED: Majority of deployments missing readiness probes
- ⬜ UNKNOWN: Cannot determine if apps are slow-starting without more context

---

### 5.3 — Pod Disruption Budgets (PDBs)

**What to check:**
- PDB resources and their settings
- Multi-replica deployments without PDBs
- PDBs with disruptionsAllowed=0 (blocks upgrades). If disruptionsAllowed=0 AND replicas=1, mark RED (single point of failure that also blocks node drains)
- Single-replica deployments (inherently not disruption-safe)

**How to check:**
1. List PodDisruptionBudgets across all namespaces → check minAvailable, maxUnavailable, disruptionsAllowed
2. List Deployments with replicas > 1 → compare against PDB coverage
3. List Deployments with replicas == 1

**Rating:**
- 🟢 GREEN: PDBs on all multi-replica production deployments with reasonable settings
- 🟡 AMBER: PDBs on some but not all, or some PDBs blocking disruptions
- 🔴 RED: No PDBs at all, or critical workloads running single-replica
- ⬜ UNKNOWN: Cannot determine which deployments are "production" vs "dev"

---

### 5.4 — Image Tag Hygiene

**What to check:**
- Running pods using `:latest` tag or no tag
- ECR repositories: tag immutability and scan-on-push settings
- Image registries in use (ECR vs Docker Hub vs other)

**How to check:**
1. List running pods → inspect container images for `:latest` or missing tag
2. Use AWS API to describe ECR repositories → check `imageTagMutability` and `imageScanningConfiguration`
3. Aggregate image registries from pod specs

**Rating:**
- 🟢 GREEN: No `:latest` in production, ECR with tag immutability, scan-on-push enabled
- 🟡 AMBER: Mostly versioned tags but some `:latest`, or ECR without immutability
- 🔴 RED: `:latest` widely used, or images from untrusted public registries
- ⬜ UNKNOWN: Cannot determine if tags are mutable without ECR access

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
1. List StorageClasses → check for gp3 default, Retain policy, WaitForFirstConsumer
2. List PVCs across all namespaces
3. List CSIDrivers
4. Describe addon `aws-ebs-csi-driver`
5. List VolumeSnapshotClasses. If 404/NotFound (CRD not installed) → no snapshot support configured, factor into rating. If 403/Forbidden → mark snapshot capability UNKNOWN.
6. List StatefulSets across all namespaces
7. List PersistentVolumes → check for `spec.awsElasticBlockStore` (deprecated in-tree)

**Rating:**
- 🟢 GREEN: gp3, Retain policy, WaitForFirstConsumer, CSI driver managed, snapshots configured
- 🟡 AMBER: gp2 still in use, or Delete policy on production volumes, or no snapshots
- 🔴 RED: Deprecated in-tree plugin, Delete policy on databases, or no backup strategy
- N/A: No stateful workloads on EKS
- ⬜ UNKNOWN: Cannot determine if Delete policy is intentional (dev) vs accidental (prod)
