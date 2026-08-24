# Infrastructure as Code & GitOps

## Purpose
Assess whether cluster infrastructure and workload deployments are reproducible, auditable, and version-controlled.

## Automation Note
This section is only partially automatable. The skill can detect tool presence (ArgoCD, Flux, CloudFormation stacks, cluster tags) but cannot assess process maturity (PR reviews, pipeline enforcement). Process-dependent items are marked UNKNOWN.

## Checks to Execute

### 2.1 — Cluster Provisioned via IaC

**What to check:**
- Cluster tags for IaC provenance (terraform, eksctl, cdk, aws:cloudformation:stack-name)
- CloudFormation provenance via the `aws:cloudformation:stack-name` tag (tag-only — stack-listing APIs are not available and must not be called)

**How to check:**
1. Describe cluster → inspect `tags` for IaC indicators (tags were already retrieved in Step 0 pre-flight — reuse that data)
2. Look for tags: `terraform`, `managed-by`, `aws:cloudformation:stack-name`, `eksctl.cluster.k8s.io/*`, `aws:cdk:*`

**Rating:**
- 🟢 GREEN: A clear declarative-IaC provenance tag is present — Terraform (`terraform` / `managed-by=terraform`), CloudFormation (`aws:cloudformation:stack-name`), or CDK (`aws:cdk:*`)
- 🟡 AMBER: Only eksctl-provenance tags present (`eksctl.cluster.k8s.io/*` — imperative-ish, less declarative; rated AMBER even if an `aws:cloudformation:stack-name` tag is also present, since eksctl provisions via CloudFormation under the hood), OR provenance tags are ambiguous/conflicting (multiple different IaC tools' tags suggesting partial/mixed management)
- 🔴 RED: No IaC-provenance tags at all — cluster appears console/CLI-created
- ⬜ UNKNOWN: The Step 0 cluster describe / tag read was forbidden (403), so provenance tags could not be read and no band can be assigned. (Whether IaC is pipeline-driven vs manually applied is not observable from tags at all — that is not a band boundary; it lives under Investigate Manually.)
- **Evaluation order:** assess RED first; if not RED, assess AMBER; otherwise GREEN. If the tag read was forbidden, rate UNKNOWN. Keeps the bands exhaustive and non-overlapping.
- **Scoring authority:** this check owns the IaC-provenance signal (terraform / CloudFormation / eksctl / CDK tags); check 1.5 gathers the same tags as evidence and defers their scoring here.

**Investigate manually:** Is IaC applied via CI/CD pipeline or manually? Could you recreate this cluster from code? Whether the IaC state is actually current — i.e. whether the tagged stack still exists or the live cluster has drifted from code — is NOT observable from tags alone (a provenance tag persists after its stack is deleted or drifts), so it is not a band boundary here; verify against the IaC source of truth.

---

### 2.2 — Workload Deployment via GitOps or CI/CD

**What to check:**
- ArgoCD namespace and Application resources
- Flux namespace and Kustomization resources
- Other CD tools (Spinnaker, Tekton namespaces)

**How to check:**
1. List namespaces → check for `argocd`, `flux-system`, `spinnaker`, `tekton-pipelines`
2. If argocd namespace exists → list `applications.argoproj.io` resources, check sync status. If the CRD list returns 404/NotFound → tool not installed → UNKNOWN (external CI/CD undetectable from cluster state); if 403/Forbidden → mark ONLY the ArgoCD signal UNKNOWN (insufficient CRD access), do not assume absence and do not mark the whole check UNKNOWN — a confirmed sync state read from the other GitOps tool still stands (see the 403 floor-and-scope rule below)
3. If flux-system exists → list `kustomizations.kustomize.toolkit.fluxcd.io` resources. If the CRD list returns 404/NotFound → tool not installed → UNKNOWN (external CI/CD undetectable from cluster state); if 403/Forbidden → mark ONLY the Flux signal UNKNOWN (insufficient CRD access), do not assume absence and do not mark the whole check UNKNOWN — a confirmed sync state read from the other GitOps tool still stands (see the 403 floor-and-scope rule below)

**Rating:**
- 🟢 GREEN: GitOps tool active with apps in-sync
- 🟡 AMBER: GitOps tool installed but apps out-of-sync, or CI/CD present but no GitOps
- 🔴 RED: GitOps/CD tooling is present in-cluster but non-functional — an observable broken state (e.g. controller pods crash-looping, or the tool is installed yet manages zero workloads)
- ⬜ UNKNOWN: No GitOps or CD tooling detected in-cluster. External CI/CD cannot be confirmed or denied from cluster state — investigate manually: how do teams deploy workloads?
- **Evaluation order:** assess RED first; if not RED, assess AMBER; then GREEN. If nothing is detected in-cluster, rate UNKNOWN (not RED) — external CI/CD is undetectable from cluster state. Exactly one band applies; the bands are non-overlapping.
- **403 floor-and-scope rule:** a 403/Forbidden on one GitOps tool's CRD list marks ONLY that tool's signal UNKNOWN — it does not force the whole check UNKNOWN. A confirmed out-of-sync (AMBER) or observably-broken/non-functional (RED) state read successfully from the OTHER GitOps tool SURVIVES that 403 (CONFIRMED FLOOR) and is never downgraded to UNKNOWN by it. Whole-check UNKNOWN applies only when NO GitOps tool could be read (every attempted CRD list was 403/Forbidden or none is present) AND that forbidden read is the sole discriminator — i.e. no successfully-read tool already yields a color.

---

### 2.3 — Configuration Drift Detection & Remediation

**What to check:**
- ArgoCD auto-sync and self-heal settings
- Flux reconciliation status

**How to check:**
1. If ArgoCD present → read Application resources, check `spec.syncPolicy.automated` for `selfHeal: true`. If the CRD list returns 404/NotFound → tool not installed → UNKNOWN (external drift detection undetectable from cluster state); if 403/Forbidden → mark ONLY the ArgoCD signal UNKNOWN (insufficient CRD access), do not assume absence and do not mark the whole check UNKNOWN — a confirmed drift/self-heal state read from the other GitOps tool still stands (see the 403 floor-and-scope rule below)
2. If Flux present → check kustomization ready status. If the CRD list returns 404/NotFound → tool not installed → UNKNOWN (external drift detection undetectable from cluster state); if 403/Forbidden → mark ONLY the Flux signal UNKNOWN (insufficient CRD access), do not assume absence and do not mark the whole check UNKNOWN — a confirmed drift/reconciliation state read from the other GitOps tool still stands (see the 403 floor-and-scope rule below)

**Rating:**
- 🟢 GREEN: GitOps with self-heal enabled, all apps in-sync
- 🟡 AMBER: GitOps present but no self-heal, or some apps out-of-sync
- 🔴 RED: GitOps is present but its drift-detection is observably broken (e.g. reconciliation is failing/errored, or sync is disabled on managed apps)
- ⬜ UNKNOWN: No GitOps tools detected in-cluster. Drift detection often lives in external CI/CD, which is undetectable from cluster state — investigate manually.
- **Evaluation order:** assess RED first; if not RED, assess AMBER; then GREEN. If no GitOps/drift-detection tooling is detected in-cluster, rate UNKNOWN (not RED) — external drift detection is undetectable from cluster state. Exactly one band applies; the bands are non-overlapping.
- **403 floor-and-scope rule:** a 403/Forbidden on one GitOps tool's CRD list marks ONLY that tool's signal UNKNOWN — it does not force the whole check UNKNOWN. A confirmed drift/out-of-sync (AMBER) or observably-broken-reconciliation (RED) state read successfully from the OTHER GitOps tool SURVIVES that 403 (CONFIRMED FLOOR) and is never downgraded to UNKNOWN by it. Whole-check UNKNOWN applies only when NO GitOps tool could be read (every attempted CRD list was 403/Forbidden or none is present) AND that forbidden read is the sole discriminator — i.e. no successfully-read tool already yields a color.

---

### 2.4 — Access Control & RBAC Defined in Code

**What to check:**
- Authentication mode (API, CONFIG_MAP, API_AND_CONFIG_MAP)
- EKS Access Entries
- ClusterRoleBindings to cluster-admin
- Whether RBAC resources have GitOps labels

**How to check:**
1. Describe cluster → `accessConfig.authenticationMode`
2. List access entries. **403 guard:** if `eks:ListAccessEntries` returns 403/Forbidden → mark the access-entries signal UNKNOWN (do NOT read a forbidden list as "no access entries"). A forbidden `ListAccessEntries` alone never forces the whole check UNKNOWN — a confirmed CONFIG_MAP-only RED (step-4 no-evidence read succeeded) survives it (confirmed floor; see the combo map).
3. List ClusterRoleBindings → filter for `roleRef.name == "cluster-admin"`
4. Check ClusterRoles/ClusterRoleBindings for labels indicating Helm/ArgoCD management. If 403/Forbidden when listing ClusterRoles/ClusterRoleBindings or reading their labels → mark the IaC/GitOps-management signal UNKNOWN (do not infer "no evidence of management" from a forbidden list); rbac.authorization.k8s.io is core so 404 is not expected. When auth mode is CONFIG_MAP-only but the management-evidence read was forbidden, rate UNKNOWN rather than RED.

**Rating:**
- 🟢 GREEN: API mode with Access Entries CONFIRMED present (step-2 `ListAccessEntries` read SUCCEEDED) AND the step-4 management-evidence read SUCCEEDED and confirmed RBAC managed by IaC/GitOps (cluster-admin scope is rated under 3.2). GREEN requires BOTH the access-entries signal AND the management-evidence signal CONFIRMED via successful reads — if step 2 (`ListAccessEntries`) returned 403/Forbidden OR step 4 returned 403/Forbidden, GREEN is not awardable even when auth-mode is GREEN-worthy (see the AMBER-with-note caps and the combo map)
- 🟡 AMBER: API_AND_CONFIG_MAP (transitional), or RBAC partially in code, or **API mode with a SUCCESSFUL step-4 management-evidence read that found NO IaC/GitOps management of access resources** (confirmed access-as-code-not-practiced — a decidable AMBER finding, never UNKNOWN; cluster-admin breadth is rated under 3.2), or CONFIG_MAP-only auth mode but aws-auth/RBAC managed by IaC/GitOps (legacy auth mode, but access-as-code), OR **AMBER-with-note (management-evidence 403)**: auth mode is GREEN-worthy (API mode, Access Entries confirmed) but the step-4 management-evidence read returned 403/Forbidden so IaC/GitOps management of RBAC could not be confirmed — cap at AMBER with the note "access config good but IaC/GitOps management of RBAC could not be verified" (GREEN's management-evidence precondition is unconfirmed) and record the uncertainty under Investigate Manually, OR **AMBER-with-note (access-entries 403)**: auth mode is API (confirmed) and the step-4 management-evidence read SUCCEEDED (RBAC IaC/GitOps-managed), but the step-2 `ListAccessEntries` read returned 403/Forbidden so Access-Entries presence could not be confirmed — cap at AMBER with the note "auth mode API and RBAC IaC/GitOps-managed, but Access Entries presence could not be verified" (GREEN's access-entries precondition is unconfirmed) and record the uncertainty under Investigate Manually. These AMBER-with-note caps never *raise* a band — a confirmed CONFIG_MAP-only-with-successful-read RED still stands; they only cap an otherwise-GREEN down to AMBER
- 🔴 RED: An observable access-as-code failure — CONFIG_MAP-only auth mode with no evidence of IaC/GitOps management of aws-auth **where the management-evidence read (step 4) actually succeeded** (the auth mode is observable via `accessConfig.authenticationMode`, and the absence of GitOps CRDs / IaC-provenance tags on the access resources is observable only when those resources could be listed — a 403/Forbidden on the step-4 read is UNKNOWN, not "no evidence"), **OR** observed drift between code-declared RBAC and live cluster state. RED requires one of these observable-bad signals to be present; mere absence of evidence, or a forbidden management-evidence read, is UNKNOWN, not RED (cluster-admin breadth is rated under 3.2)
- ⬜ UNKNOWN: **forbidden/failed-read triggers only — a SUCCESSFUL read that finds no management is confirmed-absent, never UNKNOWN.** (a) Indeterminate provenance from a forbidden management-evidence read: auth mode is not CONFIG_MAP-only, the step-4 management-evidence read returned 403/Forbidden (so IaC/GitOps management can neither be confirmed nor ruled out), no observable bad state (no observed drift), AND no other confirmed signal already yields a color — RBAC/access entries may be applied by an external pipeline undetectable from cluster state → UNKNOWN, not RED (mirrors checks 2.2/2.3). (b) The CONFIG_MAP-only-plus-step-4-403 case: auth mode is CONFIG_MAP-only but the step-4 management-evidence read was forbidden (403), so "no evidence" cannot be inferred → UNKNOWN, not RED. In both cases the discriminating read must have FAILED (403); a step-4 read that SUCCEEDED and found no management is a confirmed access-as-code-not-practiced finding → AMBER (API mode) or RED (CONFIG_MAP-only), not UNKNOWN. Whether RBAC changes go through PR review is NOT observable from cluster state and never drives this band — see Investigate Manually.
- **Evaluation order:** assess RED first; if not RED, assess AMBER; then GREEN. UNKNOWN is not part of this RED→AMBER→GREEN ladder — it fires only when the discriminating read FAILED (step-4 management-evidence 403, per the UNKNOWN triggers) and no confirmed signal already yields a color. A SUCCESSFUL management-evidence read that finds no IaC/GitOps management is confirmed-absent → AMBER (API mode) or RED (CONFIG_MAP-only), never UNKNOWN. Exactly one band applies; the bands are non-overlapping.
- **Signal-combination map ({auth-mode × step-2 access-entries-read-outcome × step-4 management-evidence-read-outcome} → exactly one band; every combination maps):**
  - **API mode**, access-entries read SUCCEEDED (entries **present**), management-evidence read SUCCEEDED, RBAC managed by IaC/GitOps confirmed → **GREEN** (all three preconditions confirmed)
  - **API mode**, management-evidence read SUCCEEDED, **no IaC/GitOps management found** (any access-entries outcome — present, empty, or 403) → **AMBER** (confirmed access-as-code-not-practiced: a successful read that observed the *absence* of management is a decidable finding, never UNKNOWN; RBAC partially/not in code)
  - **API mode**, access-entries read SUCCEEDED (entries **empty** — no access entries present), management-evidence read SUCCEEDED, RBAC managed by IaC/GitOps confirmed → **AMBER** (RBAC in code but Access Entries confirmed absent, so GREEN's access-entries precondition is unmet)
  - **API mode**, access-entries read SUCCEEDED (entries **present**), management-evidence read **403/Forbidden** → **AMBER-with-note (management-evidence 403)** ("access config good but IaC/GitOps management of RBAC could not be verified"; GREEN's management-evidence precondition unconfirmed)
  - **API mode**, access-entries read **403/Forbidden**, management-evidence read SUCCEEDED, RBAC managed by IaC/GitOps → **AMBER-with-note (access-entries 403)** ("auth mode API and RBAC IaC/GitOps-managed, but Access Entries presence could not be verified"; GREEN's access-entries precondition unconfirmed)
  - **API mode**, access-entries read SUCCEEDED (entries **empty**) OR **403/Forbidden**, management-evidence read **403/Forbidden**, no observed drift → **UNKNOWN** (the discriminating management-evidence read FAILED and no confirmed signal yields a color; mirrors 2.2/2.3). *(Contrast: entries-present + management-evidence 403 is AMBER-with-note above, because an otherwise-GREEN state exists to cap.)*
  - **API_AND_CONFIG_MAP** (any access-entries and any management-evidence outcome) → **AMBER** (transitional)
  - **CONFIG_MAP-only**, management-evidence read SUCCEEDED, aws-auth/RBAC managed by IaC/GitOps (any access-entries outcome) → **AMBER** (legacy auth mode, but access-as-code)
  - **CONFIG_MAP-only**, management-evidence read SUCCEEDED, **no IaC/GitOps management found** (any access-entries outcome, incl. step-2 403) → **RED** (observable access-as-code failure; the confirmed no-evidence read is a confirmed floor that survives a step-2 `ListAccessEntries` 403)
  - **CONFIG_MAP-only**, management-evidence read **403/Forbidden** (any access-entries outcome) → **UNKNOWN** (the forbidden management-evidence read is the sole discriminator; do not infer "no evidence" from a 403)
- **Scoring authority:** cluster-admin scope / least-privilege RBAC is rated under check 3.2; this check assesses whether access control is defined in code (auth mode, GitOps management).

**Investigate manually:** Do RBAC/access-entry changes go through PR review before they are applied? This is a process question that is not observable from cluster state, so it never drives the UNKNOWN band (mirrors 3.2/8.1/9.4) — a confirmed GREEN or RED from the combo map stands regardless; verify the review process with the user.
