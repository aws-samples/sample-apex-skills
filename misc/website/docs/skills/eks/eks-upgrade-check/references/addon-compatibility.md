---
title: "Add-on Compatibility"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-upgrade-check/references/addon-compatibility.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-upgrade-check/references/addon-compatibility.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-upgrade-check/references/addon-compatibility.md). Edit the source, not this page.
:::


:::info[Vendored skill]
This skill is sourced from [eks-upgrade-check](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-upgrade-check), also maintained by the APEX team.
:::

# Add-on Compatibility

## Purpose
Assess all EKS managed add-ons, discovered OSS add-ons, and Karpenter for compatibility with the target Kubernetes version.

## Checks to Execute

### 4.1 — Core EKS Managed Add-ons

The 4 core add-ons that MUST be checked:
- `vpc-cni` (Amazon VPC CNI)
- `coredns`
- `kube-proxy`
- `aws-ebs-csi-driver` (if installed)

**How to check:**
1. List all EKS managed add-ons → describe each for version, status, health
2. For each core add-on:
   - Record installed version
   - Check health status and any issues
   - Note if it's self-managed (not in the managed add-on list but running in kube-system)

**MANDATORY version comparison (deterministic — do NOT eyeball or skip):**

For EVERY managed add-on, you MUST run this command and compare — never declare an
add-on "compatible" or "up to date" from judgment alone:

```bash
# Select the DEFAULT version explicitly — do NOT trust addonVersions[0].
# describe-addon-versions does NOT guarantee index 0 is the newest/default.
aws eks describe-addon-versions --addon-name <addon> --kubernetes-version <target> \
  --query 'addons[0].addonVersions[?compatibilities[0].defaultVersion==`true`].addonVersion' \
  --output text
```

If no entry is flagged `defaultVersion`, pick the **highest semver** from
`addons[0].addonVersions[].addonVersion` instead (e.g. sort with `sort -V`) —
NEVER just take the first array element (`[0]`), which is not guaranteed to be latest.
This returns the latest available build for the target Kubernetes version. Then apply
this bright-line rule for each add-on:

| Condition | Verdict | Score |
|-----------|---------|-------|
| Installed build == latest-for-target | COMPATIBLE | 0 pts |
| Installed build < latest-for-target (behind) | UPDATE_RECOMMENDED | 1 pt |
| Installed version NOT in target's compatible set (`describe-addon-versions` returns no entry for it) | INCOMPATIBLE | critical: 5 pts + hard blocker (caps ≤59) / optional: 3 pts, NO cap |
| Add-on DEGRADED / FAILED | INCOMPATIBLE (same deduction) | critical: 5 pts + hard blocker (caps ≤59) / optional: 3 pts, NO cap |
| kube-proxy skew beyond policy (>3 minors behind target) | SKEW_WARNING | 2 pts (Category 4 warning — distinct from UNKNOWN_VERIFIABLE's 2 pts) |

**Verdict precedence (most-specific-wins):** a kube-proxy build that is >3 minors behind
the target but still in the compatible set satisfies BOTH the "behind → UPDATE_RECOMMENDED"
row and the ">3 minors → SKEW_WARNING" row. Assign SKEW_WARNING (+2) — it supersedes
UPDATE_RECOMMENDED (+1). INCOMPATIBLE supersedes both. Exactly one verdict per add-on.

The critical/optional split is decisive: only a CRITICAL add-on (vpc-cni, coredns,
kube-proxy, aws-ebs-csi-driver, plus any non-AWS cluster CNI installed in place of
vpc-cni — Cilium, Calico) INCOMPATIBLE triggers hard blocker #3; an OPTIONAL
add-on INCOMPATIBLE deducts 3 pts and does NOT cap the score.

**Scope of this API-based INCOMPATIBLE rule:** this `describe-addon-versions`
compatible-set test defines INCOMPATIBLE for **EKS-managed add-ons only**.
`describe-addon-versions` does not cover OSS add-ons — those keep the upstream-source
definition of INCOMPATIBLE in §4.3 (verdict states).

"Behind" includes any add-on whose version string is for an older Kubernetes minor
(e.g., a `v1.31.x` kube-proxy build when the target is 1.32) OR a lower build number
for the same minor. If you did not run `describe-addon-versions`, you cannot assign
COMPATIBLE — the check is required, not optional.

**Key talking point:** EKS does NOT auto-update add-ons when you upgrade the control plane. This is the #1 thing customers forget. A cluster upgraded to 1.33 can still be running vpc-cni from 1.29.

**Rating per add-on:**
- Compatible + healthy → PASS
- Behind but compatible → WARN (update recommended)
- Incompatible or unhealthy → FAIL
- Self-managed (not EKS managed) → WARN (recommend converting to managed)

### 4.2 — Additional Managed Add-ons

Check any other installed managed add-ons:
- `amazon-cloudwatch-observability`
- `aws-efs-csi-driver`
- `adot` (AWS Distro for OpenTelemetry)
- `eks-pod-identity-agent`
- `aws-guardduty-agent`
- `eks-node-monitoring-agent`
- `snapshot-controller`

**How to check:**
1. List all add-ons → describe each
2. Record version, status, health for each

### 4.3 — OSS Add-on Discovery & Compatibility Verification

Scan workloads to discover non-AWS add-ons running in the cluster, then verify their
compatibility with the target Kubernetes version via web search.

**Step 1: Discover OSS add-ons**
1. List Deployments, DaemonSets, StatefulSets across all namespaces
2. For each workload, extract add-on identity from (in priority order):
   - Labels: `app.kubernetes.io/name`, `app.kubernetes.io/version`
   - Helm labels: `helm.sh/chart`, `app.kubernetes.io/managed-by`
   - Container image repo + tag (e.g., `quay.io/jetstack/cert-manager-controller:v1.15.0`)
3. Exclude AWS-managed add-ons (vpc-cni, coredns, kube-proxy, ebs-csi) and Karpenter (checked separately). A non-AWS cluster CNI (Cilium, Calico) is also excluded from this generic OSS-optional scan — it is scored on the CRITICAL add-on path above (an INCOMPATIBLE cluster CNI is a hard blocker, not a 3-pt optional finding).
4. Exclude workloads in these system namespaces (treat as user apps, not add-ons only if they
   clearly match a known add-on identifier): `kube-system` is included for add-on scan;
   `default` and application namespaces are EXCLUDED unless the workload matches a known
   add-on identifier in the registry.
5. For each workload examined, classify it into exactly one bucket:

   | Bucket | Condition | Action |
   |--------|-----------|--------|
   | **IDENTIFIED** | Matches a registry entry OR has clear labels/image identifying a known OSS project | Proceed to Step 2 |
   | **UNIDENTIFIED ADD-ON** | In `kube-system`/`karpenter`/`cert-manager`/`monitoring` etc. namespace but no matching registry entry and unclear labels | Record and flag — see "Unidentified workloads" below |
   | **USER APPLICATION** | In user namespace with no add-on indicators | Skip (covered by workload-risks scan) |

6. For each IDENTIFIED add-on, record: name, version, namespace, identification method (which label/image matched).
7. For each UNIDENTIFIED ADD-ON, record: workload kind, name, namespace, image(s), any labels present, and why it couldn't be identified.

**Common OSS add-ons to look for:**
- cert-manager
- external-dns
- metrics-server
- cluster-autoscaler
- aws-load-balancer-controller
- ingress-nginx (retired March 2026)
- istio / envoy
- prometheus / grafana
- argocd / flux

**Step 2: Verify compatibility via upstream sources (MANDATORY for each discovered OSS add-on)**

Compatibility data is NEVER read from a local file. OSS projects ship faster than any
shipped data file can keep up with, and stale data produces unsafe upgrade advice.
Always fetch compatibility information live from the upstream project.

**Lookup order (stop at the first that yields a definitive answer):**

1. **Check the local registry for the authoritative URL**
   Read `${CLAUDE_SKILL_DIR}/data/oss_addon_registry.json`. If the add-on is listed,
   use its `compatibility_url` (primary) and `releases_url` (fallback). The registry
   contains identifiers and URLs — it does NOT contain compatibility data itself.

2. **Fetch the compatibility page**
   Use `webFetch` on the registry's `compatibility_url`. Look for a supported-versions
   table or statement that covers both the installed add-on version and the target
   Kubernetes version.

3. **Fetch release notes if no compatibility page exists**
   Use `webFetch` on `releases_url` and inspect the relevant release for "Kubernetes
   compatibility" or "breaking changes" sections.

4. **Fall back to web search only if the above fail**
   Use `remote_web_search` with queries like:
   - `"<addon-name> <addon-version> supported Kubernetes versions"`
   - `"<addon-name> compatibility matrix"`
   Prefer results from the project's own domain or GitHub org.

5. **If the add-on is not in the registry**
   Search with `remote_web_search` first to identify the authoritative source
   (project docs or GitHub releases), then apply steps 2–3 against that source.

**If no authoritative source can be reached or the answer is ambiguous:**
Report the add-on as "compatibility UNKNOWN — manual verification required" with
MEDIUM severity and include the URL(s) consulted. Do NOT assume compatibility.
Do NOT fall back to LLM training data — it is likely outdated.

**Verdict states (use exactly one per add-on):**

| Verdict | Meaning | Severity | Score impact |
|---------|---------|----------|--------------|
| `COMPATIBLE` | Upstream source confirms installed version supports target K8s | — | 0 pts |
| `UPDATE_RECOMMENDED` | Current version works but a newer version is recommended | LOW | 1 pt |
| `INCOMPATIBLE` | Upstream source explicitly says installed version does not support target | HIGH | 3 pts (optional) / 5 pts + hard blocker (critical, caps ≤59) |
| `SKEW_WARNING` | kube-proxy >3 minors behind target but still in the compatible set | MEDIUM | 2 pts (Category 4 warning — distinct from UNKNOWN_VERIFIABLE) |
| `UNKNOWN_VERIFIABLE` | Add-on identified but upstream source unreachable or ambiguous | MEDIUM | 2 pts |
| `UNKNOWN_UNIDENTIFIED` | Workload looks like an add-on but could not be identified | MEDIUM | 2 pts |

Every discovered add-on MUST end with exactly one of these verdicts. "Probably fine"
is not an allowed outcome.

## Unidentified Workloads

Workloads classified as UNIDENTIFIED ADD-ON in Step 1 are a distinct concern from
UNKNOWN_VERIFIABLE add-ons. The skill found something add-on-shaped but cannot name it,
which means the user likely knows what it is and the skill does not.

**For each unidentified workload, collect:**
- Workload kind (Deployment/DaemonSet/StatefulSet) and name
- Namespace
- Container image(s) including registry, repo, and tag
- All present labels (to help the user recognize it)
- Replica count

**Report these in a dedicated "Unidentified Workloads" table in the report.** Do NOT
silently drop them. The user needs to know which of their workloads the skill could
not assess, so they can provide context or verify compatibility manually.

**Do NOT guess the identity** from image names alone if the match is ambiguous. For
example, `myregistry.internal/platform/controller:v2.1` is unidentified — not
"probably a custom controller, assumed compatible". Ambiguity is reported, not resolved.

**Registry notes field:** Some add-ons in the registry have a `notes` field flagging
special handling (e.g., ingress-nginx retirement, cluster-autoscaler K8s version
pinning). Always read and apply these notes.

**Output per OSS add-on:**
```
| Add-on | Version | Verdict | Source URL | Notes |
```
The `Verdict` column uses the exact states defined above (COMPATIBLE,
UPDATE_RECOMMENDED, INCOMPATIBLE, SKEW_WARNING, UNKNOWN_VERIFIABLE, UNKNOWN_UNIDENTIFIED).
The `Source URL` column is mandatory — it shows the user exactly where the verdict
came from (or which URL failed to load) and lets them verify it.

**Output for unidentified workloads:**
```
| Kind | Name | Namespace | Image | Labels | Why unidentified |
```

### 4.4 — Karpenter Compatibility

**How to check:**
1. List Deployments in the `karpenter` namespace, or check for NodePool CRDs (`nodepools.karpenter.sh`)
2. If installed, find the Karpenter deployment → extract version from:
   - Labels: `app.kubernetes.io/version` or `helm.sh/chart`
   - Container image tag (e.g., `public.ecr.aws/karpenter/controller:0.37.0`)
3. Check compatibility against the official matrix from https://karpenter.sh/docs/upgrading/compatibility/:

**Official Karpenter Compatibility Matrix (source: karpenter.sh):**

| Kubernetes | 1.30 | 1.31 | 1.32 | 1.33 | 1.34 | 1.35 | 1.36 |
|------------|------|------|------|------|------|------|------|
| Karpenter  | >= 0.37 | >= 1.0.5 | >= 1.2 | >= 1.5 | >= 1.6 | >= 1.9 | >= 1.13 |

**IMPORTANT:** Do NOT rely on the approximate ranges previously listed here. Always use the
matrix above. Note the jump from 0.37 (for 1.30) to 1.0.5 (for 1.31) — this is a major
version boundary that requires API migration (v1beta1 → v1).

**If the target Kubernetes version or installed Karpenter version is NOT in the matrix above:**
You MUST perform a web search to verify compatibility:
1. Search: `"Karpenter compatibility matrix Kubernetes <target-version>"` using `remote_web_search`
2. Fetch the official page: `https://karpenter.sh/docs/upgrading/compatibility/` using `webFetch`
3. Do NOT guess or assume compatibility. Report as UNKNOWN if you can't verify.

**Rating:**
- Compatible version per matrix → PASS
- Installed but version unknown/unidentifiable → WARN (manual review). Do NOT invent a
  new Category 5 deduction for this — score it as the existing `UNKNOWN_VERIFIABLE`
  verdict (2 pts), NOT a separate/new deduction.
- Incompatible version per matrix → FAIL (must upgrade Karpenter BEFORE control plane)

**Key talking point:** Karpenter must be upgraded BEFORE the control plane, not after. The order matters. The 0.x → 1.x migration requires migrating from Provisioner to NodePool v1 APIs. See https://karpenter.sh/v1.0/upgrading/v1-migration/

## Score Impact

> **Canonical scoring is defined in `references/report-generation.md` §Category 4 (Add-on Compatibility) and §Category 5 (Karpenter).**

| Finding | Deduction |
|---------|-----------|
| Critical add-on INCOMPATIBLE (vpc-cni, coredns, kube-proxy, ebs-csi, or a non-AWS cluster CNI — Cilium, Calico) | 5 pts each + hard blocker (caps ≤59) |
| Optional add-on INCOMPATIBLE | 3 pts each (no cap) |
| kube-proxy SKEW_WARNING (>3 minors behind target, still in compatible set) | 2 pts each (Cat-4 warning — distinct from UNKNOWN_VERIFIABLE) |
| Add-on UNKNOWN_VERIFIABLE (could not verify upstream) | 2 pts each |
| Workload UNKNOWN_UNIDENTIFIED (couldn't identify the add-on) | 2 pts each |
| UPDATE_RECOMMENDED (behind but compatible) | 1 pt each |
| Karpenter INCOMPATIBLE | 10 pts |
| Max category deduction | 15 pts (add-ons) + 10 pts (Karpenter) |
