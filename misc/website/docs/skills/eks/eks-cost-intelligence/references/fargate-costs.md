---
title: "Fargate Cost Checks"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-cost-intelligence/references/fargate-costs.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-cost-intelligence/references/fargate-costs.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-cost-intelligence/references/fargate-costs.md). Edit the source, not this page.
:::

# Fargate Cost Checks

> **Part of:** [eks-cost-intelligence](../)
> **Purpose:** Fargate profile detection for Step 0, plus Fargate-specific cost checks — pod request right-sizing against Fargate's vCPU/memory combinations, and capacity strategy for interruption-tolerant Fargate workloads
>
> Facts verified 2026-07-17 against https://docs.aws.amazon.com/eks/latest/userguide/fargate-pod-configuration.html, https://docs.aws.amazon.com/eks/latest/userguide/fargate.html, and https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-services.html

---

## Why Fargate Needs Its Own Checks

EKS Fargate has a fundamentally different cost model from EC2 nodes:

- **Billing is per pod, based on provisioned vCPU/memory** — not on node capacity. Fargate rounds each pod's resource requests **up** to the nearest valid vCPU/memory combination and bills for that provisioned capacity (visible in the pod's `CapacityProvisioned` annotation), regardless of actual utilization.
- **One pod per Fargate node.** There is no bin-packing, no idle-node concept, and no consolidation. Node-based checks (idle nodes, Karpenter consolidation, node-based cost estimation) do NOT apply to Fargate-scheduled pods — exclude them from those checks.
- **Requests equal limits.** All Fargate pods run with Guaranteed QoS, so over-stated requests translate directly into over-billed capacity.
- **No Spot tier.** As of 2026-07-17, Amazon EKS does not support Fargate Spot (Fargate Spot exists for ECS only). Savings levers for Fargate on EKS are request right-sizing, Compute Savings Plans (Fargate is eligible), or migrating interruption-tolerant workloads to EC2 Spot capacity.

---

## Detection (runs in Step 0 pre-flight)

**Via AWS CLI:**

```bash
# List Fargate profiles for the cluster
aws eks list-fargate-profiles --cluster-name <cluster>

# For each profile, capture its selectors (namespace + optional labels)
aws eks describe-fargate-profile \
  --cluster-name <cluster> \
  --fargate-profile-name <profile> \
  --query '{name: fargateProfile.fargateProfileName, status: fargateProfile.status, selectors: fargateProfile.selectors, subnets: fargateProfile.subnets}'
```

**Via kubectl (identify running Fargate pods and their provisioned capacity):**

```bash
# Fargate nodes carry the compute-type label
kubectl get nodes -l eks.amazonaws.com/compute-type=fargate -o wide

# Fallback: Fargate node names start with "fargate-"
kubectl get nodes | grep ^fargate-

# The CapacityProvisioned annotation on a Fargate pod shows the billed combination
kubectl get pods --all-namespaces -o json | \
  jq -r '.items[] |
    select(.metadata.annotations["CapacityProvisioned"] != null) |
    "\(.metadata.namespace)/\(.metadata.name): requested cpu=\([.spec.containers[].resources.requests.cpu // "0"] | join("+")) mem=\([.spec.containers[].resources.requests.memory // "0"] | join("+")) → billed \(.metadata.annotations["CapacityProvisioned"])"'
```

**Detection outcome:**

- If no Fargate profiles exist → skip this reference entirely; note "Fargate Profiles: none" in the report.
- If profiles exist → record which namespaces (and label selectors) are Fargate-scheduled, exclude Fargate pods from node-based checks (idle nodes, consolidation, node-based estimation), and run checks F1 and F2 below. List the Fargate-scheduled namespaces in the report metadata.

A profile selector always contains a namespace and may include labels (up to 5 selectors per profile; `*` and `?` wildcards are allowed in selector criteria).

---

## Check F1: Right-Size Pod Requests to Fargate Combinations

### What it detects

Fargate pods whose requests round up into a larger billed combination than the workload needs. You pay for the rounded-up combination, not the raw request — so a request sitting just above a combination boundary wastes the entire gap to the next tier.

### Fargate vCPU/memory combinations

Fargate provisions the smallest combination that fits the pod's aggregate request **plus 256 MB** of memory overhead reserved for Kubernetes components (kubelet, kube-proxy, containerd). If no requests are specified, the smallest combination (.25 vCPU / 0.5 GB) is used.

> Facts verified 2026-07-17 against https://docs.aws.amazon.com/eks/latest/userguide/fargate-pod-configuration.html

| vCPU value | Memory values |
|-----------|---------------|
| .25 vCPU | 0.5 GB, 1 GB, 2 GB |
| .5 vCPU | 1 GB, 2 GB, 3 GB, 4 GB |
| 1 vCPU | 2–8 GB in 1-GB increments |
| 2 vCPU | 4–16 GB in 1-GB increments |
| 4 vCPU | 8–30 GB in 1-GB increments |
| 8 vCPU | 16–60 GB in 4-GB increments |
| 16 vCPU | 32–120 GB in 8-GB increments |

The 256 MB overhead can bump a pod into a larger tier: per the AWS docs example, a request of 1 vCPU / 8 GB becomes 8 GB + 256 MB, which doesn't fit any 1-vCPU combination — Fargate provisions **2 vCPU / 9 GB**.

### Analysis logic

```
For each Fargate-scheduled pod:
  billed = parse CapacityProvisioned annotation (e.g., "0.5vCPU 2GB")
  requested = sum of container requests (+ init-container max rule)

  # Boundary waste: request lands just above a combination boundary
  If (requested + 256MB) marginally exceeds a smaller combination:
    → Finding: trimming requests slightly would drop the pod a full tier
    monthly_waste = (billed_tier_cost - smaller_tier_cost) × 730h × replica_count

  # Utilization waste: billed capacity far above P95 usage (when metrics available)
  If P95 usage < 50% of billed capacity:
    → Finding: right-size requests toward P95 + headroom, re-check tier fit
```

Use Fargate per-vCPU-hour and per-GB-hour rates from the AWS Price List API (`pricing:GetProducts`) or https://aws.amazon.com/fargate/pricing/ — do not hardcode rates.

### Severity classification

Severity follows the standard monthly-waste thresholds (see `findings-format.md`): >$500 CRITICAL, $200–$500 HIGH, $50–$200 MEDIUM, <$50 LOW.

### Remediation

```yaml
# Right-size requests so (requests + 256MB) fits the intended combination
# Example: fit into the 0.5 vCPU / 1 GB tier
spec:
  template:
    spec:
      containers:
      - name: app
        resources:
          requests:
            cpu: "500m"
            memory: "768Mi"   # 768Mi + 256MB overhead ≈ 1 GB tier
          limits:
            cpu: "500m"       # Fargate enforces requests == limits (Guaranteed QoS)
            memory: "768Mi"
```

---

## Check F2: Interruption-Tolerant Workloads on Fargate

### What it detects

Workloads that meet the Spot-eligibility criteria (stateless Deployment, replicas ≥ 2, PDB present — see Check 5 in `spot-graviton-adoption.md`) but run on Fargate. As of 2026-07-17, **Amazon EKS does not support Fargate Spot**, so these workloads cannot get a Spot discount while staying on Fargate.

### Analysis logic

```
For each Spot-eligible workload scheduled on Fargate:
  → Finding: interruption-tolerant workload on Fargate (no Spot tier available on EKS)
  Options, in savings order:
    1. Migrate to EC2 Spot capacity (Karpenter NodePool or Spot node group)
       — up to 90% discount vs On-Demand; use ~60% for conservative estimates
    2. Cover steady Fargate usage with a Compute Savings Plan
       — Fargate is eligible for Compute Savings Plans
  monthly_savings (option 1) ≈ fargate_monthly_cost × 0.60 (conservative)
```

Also surface Compute Savings Plans coverage for clusters with significant steady Fargate spend even when workloads are not Spot-eligible (informational, consistent with the SP/RI out-of-scope rule — coverage notes only, not scored).

### Severity classification

| Condition | Severity |
|-----------|----------|
| Spot-eligible Fargate workloads with monthly savings > $500 | CRITICAL |
| Spot-eligible Fargate workloads with monthly savings $200–$500 | HIGH |
| Spot-eligible Fargate workloads with monthly savings $50–$200 | MEDIUM |
| Below $50/month or migration blocked (e.g., isolation requirement drove the Fargate choice) | LOW |

### Remediation

```yaml
# Karpenter NodePool for migrating interruption-tolerant Fargate workloads to EC2 Spot
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: spot-migration
spec:
  template:
    spec:
      requirements:
      - key: karpenter.sh/capacity-type
        operator: In
        values: ["spot", "on-demand"]
      - key: karpenter.k8s.aws/instance-category
        operator: In
        values: ["m", "c", "r"]
```

Then remove (or narrow) the Fargate profile selector matching the workload's namespace/labels so pods schedule onto EC2 nodes. Note: Fargate profiles are immutable — create a replacement profile without the selector, then delete the old one.

---

## Scoring Contribution

Fargate findings feed **existing dimensions** — no new dimension is added:

- Check F1 findings → **Compute Efficiency** (dimension `compute`)
- Check F2 findings → **Spot/Graviton Adoption** (dimension `spot_graviton`)

Severity-weighted deductions and caps follow the standard rules in `report-generation.md`.

---

## Sources

- [Fargate Pod vCPU and memory configuration](https://docs.aws.amazon.com/eks/latest/userguide/fargate-pod-configuration.html) — combination table, 256 MB overhead, rounding behavior, `CapacityProvisioned` annotation
- [AWS Fargate considerations for Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/fargate.html) — one pod per compute boundary, "Amazon EKS doesn't support Fargate Spot", DaemonSet/EBS limitations
- [Define which Pods use AWS Fargate when launched](https://docs.aws.amazon.com/eks/latest/userguide/fargate-profile.html) — profile selectors (namespace + labels, up to 5, wildcards), profile immutability
- [Services eligible for Savings Plans benefits](https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-services.html) — Fargate is eligible for Compute Savings Plans
- [AWS Fargate Pricing](https://aws.amazon.com/fargate/pricing/) — per-vCPU-hour and per-GB-hour rates

---

*This reference file is part of the eks-cost-intelligence skill, provided as sample code
for educational and demonstration purposes only. See the project's README and LICENSE
for full terms.*
