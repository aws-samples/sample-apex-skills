# Istio Upgrade Guide

> **Part of:** [eks-upgrader](../SKILL.md)
> **Purpose:** Istio <-> K8s version compatibility, upgrade strategies (canary and in-place), revision-based rollout, ambient mode, and common issues

---

## Table of Contents

1. [Version Compatibility](#version-compatibility)
2. [Pre-Upgrade Validation](#pre-upgrade-validation)
3. [EnvoyFilter Migration](#envoyfilter-migration)
4. [Upgrade Strategy Decision](#upgrade-strategy-decision)
5. [Upgrade Checklist](#upgrade-checklist)
6. [Canary Upgrade (Recommended)](#canary-upgrade-recommended)
7. [In-Place Upgrade](#in-place-upgrade)
8. [Revision Tags for Production](#revision-tags-for-production)
9. [Data Plane Rollout](#data-plane-rollout)
10. [Gateway Upgrades](#gateway-upgrades)
11. [Ambient Mode Upgrades](#ambient-mode-upgrades)
12. [Rollback](#rollback)
13. [Common Issues](#common-issues)

---

## Version Compatibility

### Version Skew Rules

| Rule | Detail |
|------|--------|
| **Istio minor version jump** | Canary (revision-based): can skip one minor (e.g., 1.22 -> 1.24). In-place: one minor at a time only |
| **Istio <-> K8s support** | Each Istio minor release supports ~4 K8s minor versions. Check the [Istio support matrix](https://istio.io/latest/docs/releases/supported-releases/) for exact ranges |
| **Control plane <-> data plane** | Sidecar proxies must be within +/- 1 minor version of istiod |
| **istioctl version** | Use the istioctl binary matching the *target* Istio version for upgrades, and the *old* version for downgrades |

### Compatibility Check

Always verify your target Istio version supports your current (or target) K8s version *before* upgrading either component. When upgrading both EKS and Istio:

1. Upgrade Istio first if the current Istio version doesn't support the target K8s version
2. Upgrade EKS first if the current Istio version already supports the target K8s version
3. Check both the current and target Istio release notes for K8s version support

**How to look up the matrix:** Fetch the supported releases page at `https://istio.io/latest/docs/releases/supported-releases/` and find the "Support status of Istio releases" table. It lists each Istio minor version and the K8s versions it supports. Cross-reference the cluster's current Istio version and the target K8s version to determine whether Istio must be upgraded first.

For self-managed (Helm) installations, you can also check what the installed chart declares:

```bash
# Current Istio version
istioctl version

# Check the Helm chart's appVersion for the target Istio release
helm search repo istio/istiod --versions | head -20
```

### EKS-Managed Istio Add-on

If Istio is installed as an [EKS add-on](https://docs.aws.amazon.com/eks/latest/userguide/istio.html), the add-on lifecycle is managed through the EKS API:

```bash
# Check current Istio add-on version
aws eks describe-addon --cluster-name my-cluster --addon-name adot

# List compatible Istio versions for target K8s version
aws eks describe-addon-versions \
  --addon-name amazon-eks-istio \
  --kubernetes-version 1.31 \
  --query 'addons[0].addonVersions[*].addonVersion'
```

For EKS-managed Istio, the upgrade is handled via `aws eks update-addon` and the rest of this guide's manual procedures don't apply. The sections below cover self-managed Istio installations using Helm or istioctl.

---

## Pre-Upgrade Validation

Run precheck before every upgrade -- it catches incompatible configurations, deprecated APIs, and version conflicts:

```bash
# Download the target Istio version
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.29.1 sh -
cd istio-1.29.1

# Run precheck with the NEW version's istioctl
bin/istioctl x precheck
```

Additional pre-upgrade checks:

```bash
# Verify current Istio version and component health
istioctl version
istioctl proxy-status

# Check for proxies out of sync with control plane
istioctl proxy-status | grep -v "SYNCED"

# Review any analyzer warnings
istioctl analyze --all-namespaces
```

---

## EnvoyFilter Migration

EnvoyFilter is an alpha API tightly coupled to Istio's xDS internals. It frequently breaks across upgrades because the Envoy config structure it patches can change between versions. Before upgrading, audit your EnvoyFilters and migrate to first-class APIs where replacements exist.

### Telemetry API replaces metrics customization

IstioOperator-based Prometheus metric customization relies on a template EnvoyFilter under the hood. Replace it with the Telemetry API -- the two approaches are incompatible and cannot be mixed.

**Before (IstioOperator + EnvoyFilter):**

```yaml
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
spec:
  values:
    telemetry:
      v2:
        prometheus:
          configOverride:
            inboundSidecar:
              metrics:
                - name: requests_total
                  dimensions:
                    destination_port: string(destination.port)
```

**After (Telemetry API):**

```yaml
apiVersion: telemetry.istio.io/v1
kind: Telemetry
metadata:
  name: namespace-metrics
spec:
  metrics:
  - providers:
    - name: prometheus
    overrides:
    - match:
        metric: REQUEST_COUNT
      mode: SERVER
      tagOverrides:
        destination_port:
          value: "string(destination.port)"
```

### WasmPlugin API replaces Wasm filter injection

EnvoyFilter-based Wasm filter injection is replaced by the WasmPlugin API, which supports dynamic loading from artifact registries, URLs, or local files. The "Null" plugin runtime is no longer recommended.

### Gateway topology replaces connection manager EnvoyFilters

Two common EnvoyFilter patterns for ingress gateways now have first-class replacements via `gatewayTopology` in ProxyConfig:

**Trusted hops** -- instead of patching `xff_num_trusted_hops` via EnvoyFilter:

```yaml
metadata:
  annotations:
    "proxy.istio.io/config": '{"gatewayTopology" : { "numTrustedProxies": 1 }}'
```

**PROXY protocol** -- instead of inserting a `proxy_protocol` listener filter via EnvoyFilter:

```yaml
metadata:
  annotations:
    "proxy.istio.io/config": '{"gatewayTopology" : { "proxyProtocol": {} }}'
```

### Proxy annotation replaces histogram bucket EnvoyFilter

Custom histogram bucket sizes previously required an EnvoyFilter patching the bootstrap config. Use the pod annotation instead:

```yaml
metadata:
  annotations:
    "sidecar.istio.io/statsHistogramBuckets": '{"istiocustom":[1,5,50,500,5000,10000]}'
```

### Migration checklist

Before upgrading, run through this list:

1. `kubectl get envoyfilters --all-namespaces` -- inventory all EnvoyFilters
2. For each, check if a first-class API replacement exists (Telemetry, WasmPlugin, gatewayTopology, proxy annotations)
3. Deploy the replacement alongside the EnvoyFilter and validate behavior
4. Remove the EnvoyFilter before upgrading -- stale EnvoyFilters silently break when the underlying xDS structure changes

---

## Upgrade Strategy Decision

| Factor | Canary (Revision-Based) | In-Place |
|--------|------------------------|----------|
| **Safety** | High -- old control plane stays running | Lower -- replaces control plane directly |
| **Rollback** | Uninstall canary revision | Requires running istioctl with old version binary |
| **Version jump** | Can skip one minor version | One minor at a time only |
| **Complexity** | Higher -- two control planes coexist | Lower -- single upgrade command |
| **Namespace migration** | Gradual, per-namespace | All at once after control plane upgrade |
| **Production recommendation** | Yes | Only for non-critical environments |
| **Tool support** | istioctl install --revision, Helm | istioctl upgrade, Helm upgrade |

**Use canary** for production clusters. It lets you validate the new control plane with a subset of workloads before committing. **Use in-place** only for dev/test environments where speed matters more than safety.

---

## Upgrade Checklist

Before generating an upgrade plan, confirm all applicable items are included:

- [ ] EnvoyFilter audit and migration (BEFORE upgrading -- stale EnvoyFilters silently break when xDS structure changes between versions). See [EnvoyFilter Migration](#envoyfilter-migration)
- [ ] CRD ownership fix if upgrading a Helm install from pre-1.23 (see [Common Issues](#crd-ownership-errors-with-helm))
- [ ] Gateway replica count >= 2 with PDB -- a single-replica gateway drops all traffic during pod restart (60-90s outage)
- [ ] Control plane upgrade step (canary or in-place)
- [ ] Data plane rollout -- sidecars still run the old version until pods restart. Include namespace-by-namespace restart plan
- [ ] If using revision tags: tag promotion step (retarget tag, then restart workloads)
- [ ] If using ambient mode: ztunnel and CNI agent upgrade sequencing (ztunnel upgrade briefly disrupts all ambient traffic on the node)
- [ ] Post-upgrade validation: `istioctl proxy-status` (all proxies SYNCED) + `istioctl analyze` (no warnings)

Do not proceed with plan generation until all applicable items are addressed.

---

## Canary Upgrade (Recommended)

A canary upgrade installs the new istiod alongside the old one. Workloads are migrated namespace-by-namespace by changing labels, then restarting pods. The old control plane is removed only after full validation.

### With istioctl

**Step 1: Install the new revision**

Use a revision name that encodes the version (replace `.` with `-`):

```bash
istioctl install --set revision=1-29-1 --set profile=minimal --skip-confirmation
```

**Step 2: Verify both control planes are running**

```bash
kubectl get pods -n istio-system -l app=istiod
# Should show both old and new istiod pods

kubectl get svc -n istio-system -l app=istiod
# Should show services for both revisions

kubectl get mutatingwebhookconfigurations | grep istio
# Should show sidecar injectors for both revisions
```

**Step 3: Migrate namespaces to the new revision**

For each namespace, swap the injection label to point to the new revision. The `istio-injection` label must be removed because it takes precedence over `istio.io/rev`:

```bash
# Switch a namespace to the new revision
kubectl label namespace my-app istio-injection- istio.io/rev=1-29-1 --overwrite

# Restart pods to pick up the new sidecar
kubectl rollout restart deployment -n my-app

# Verify pods are connected to the new control plane
istioctl proxy-status | grep "\.my-app "
```

Start with a low-risk namespace. Validate traffic, metrics, and mTLS before migrating critical namespaces.

**Step 4: Uninstall the old revision**

After all namespaces are migrated and validated:

```bash
istioctl uninstall --revision 1-28-1 -y

# Confirm only the new control plane remains
kubectl get pods -n istio-system -l app=istiod
```

### With Helm

**Step 1: Upgrade base chart (CRDs)**

```bash
helm repo update istio

# If upgrading from Istio 1.23 or older, fix CRD ownership first:
for crd in $(kubectl get crds -l chart=istio -o name && \
             kubectl get crds -l app.kubernetes.io/part-of=istio -o name); do
    kubectl label "$crd" "app.kubernetes.io/managed-by=Helm"
    kubectl annotate "$crd" "meta.helm.sh/release-name=istio-base"
    kubectl annotate "$crd" "meta.helm.sh/release-namespace=istio-system"
done

helm upgrade istio-base istio/base -n istio-system
```

**Step 2: Install canary istiod**

```bash
helm install istiod-canary istio/istiod \
    --set revision=canary \
    -n istio-system

# Verify both versions running
kubectl get pods -l app=istiod -L istio.io/rev -n istio-system
```

**Step 3: Migrate namespaces** (same label swap as istioctl method above)

**Step 4: Uninstall old istiod and promote canary**

```bash
helm delete istiod -n istio-system

# Make canary the default revision
helm upgrade istio-base istio/base --set defaultRevision=canary -n istio-system
```

---

## In-Place Upgrade

Simpler but riskier -- the control plane is replaced directly. Only supported for one-minor-version jumps (e.g., 1.28 -> 1.29, not 1.28 -> 1.30).

### With istioctl

```bash
# Use the NEW version's istioctl binary
istioctl upgrade

# If you installed with custom config, pass the same file:
istioctl upgrade -f my-istio-config.yaml
```

Ensure at least 2 istiod replicas and a PodDisruptionBudget before upgrading to minimize API disruption.

### With Helm

```bash
helm upgrade istio-base istio/base -n istio-system
helm upgrade istiod istio/istiod -n istio-system
# Optional: upgrade gateways
helm upgrade istio-ingress istio/gateway -n istio-ingress
```

After the control plane upgrade, restart workloads to pick up new sidecars (see [Data Plane Rollout](#data-plane-rollout)).

---

## Revision Tags for Production

Revision tags are stable identifiers that point to a revision. They decouple namespace labels from specific versions, so you can move many namespaces to a new revision without relabeling each one.

### Setup

```bash
# Install two revisions
istioctl install --revision=1-28-1 --set profile=minimal --skip-confirmation
istioctl install --revision=1-29-1 --set profile=minimal --skip-confirmation

# Create tags pointing to revisions
istioctl tag set prod-stable --revision 1-28-1
istioctl tag set prod-canary --revision 1-29-1

# Label namespaces with tags (not revision numbers)
kubectl label ns app-ns-1 istio.io/rev=prod-stable
kubectl label ns app-ns-2 istio.io/rev=prod-stable
kubectl label ns app-ns-3 istio.io/rev=prod-canary
```

### Promote canary to stable

When the canary revision is validated, retarget the `prod-stable` tag:

```bash
# One command moves all prod-stable namespaces to the new revision
istioctl tag set prod-stable --revision 1-29-1 --overwrite

# Restart workloads to pick up the new sidecar
kubectl rollout restart deployment -n app-ns-1
kubectl rollout restart deployment -n app-ns-2
```

With Helm, revision tags are set via:

```bash
helm template istiod istio/istiod \
    -s templates/revision-tags-mwc.yaml \
    --set revisionTags="{prod-stable}" \
    --set revision=1-29-1 \
    -n istio-system | kubectl apply -f -
```

### The default tag

The revision pointed to by the `default` tag has special behavior:
- Injects sidecars for `istio-injection=enabled`, `sidecar.istio.io/inject=true`, and `istio.io/rev=default` selectors
- Validates Istio resources
- Takes the leader lock for singleton mesh responsibilities (status updates)

```bash
istioctl tag set default --revision 1-29-1
```

When setting a `default` tag alongside an existing non-revisioned installation, remove the old `MutatingWebhookConfiguration` (typically `istio-sidecar-injector`) to prevent both control planes from attempting injection.

### Cleanup

```bash
istioctl tag remove prod-stable
istioctl tag remove prod-canary
```

---

## Data Plane Rollout

After upgrading the control plane (canary or in-place), sidecar proxies still run the old version until pods are restarted. This is by design -- it gives you control over the rollout.

### Rollout Strategy

| Approach | Risk | Speed |
|----------|------|-------|
| **Namespace-by-namespace** | Low -- validate each namespace | Slow |
| **All at once** | Higher -- less time to catch issues | Fast |
| **Deployment-by-deployment** | Lowest -- surgical control | Slowest |

### Namespace-by-namespace rollout (recommended)

```bash
# List namespaces with Istio injection
kubectl get ns -l istio.io/rev --show-labels

# Restart deployments in one namespace
kubectl rollout restart deployment -n <namespace>

# Verify all proxies synced to new control plane
istioctl proxy-status | grep "<namespace>"
```

### Verify sidecar versions

```bash
# Check proxy versions across the mesh
istioctl proxy-status

# Look for version mismatches (old proxies still on previous version)
istioctl proxy-status | awk '{print $8, $9}' | sort | uniq -c
```

All proxies should report `SYNCED` and show the new istiod pod name. Version mismatches are expected during rollout but should resolve as pods restart.

---

## Gateway Upgrades

### Ingress gateway availability

Before upgrading, ensure ingress gateways have at least 2 replicas and a PodDisruptionBudget. A single gateway pod means incoming traffic drops entirely when that pod restarts during the upgrade -- this commonly causes 60-90 seconds of downtime that's easily avoided:

```bash
# Check current replica count
kubectl get deploy -n istio-ingress -l istio=ingress

# Scale up if needed (or set in Helm values permanently)
kubectl scale deploy istio-ingressgateway -n istio-ingress --replicas=2

# Verify a PDB exists
kubectl get pdb -n istio-ingress
```

### Istio Ingress Gateway

Gateway behavior during upgrade depends on the strategy:

**Canary upgrade:** Gateways are in-place upgraded to use the new control plane by default (when using the default profile). To run revision-specific gateways:

```bash
# Install a canary gateway alongside the existing one
helm install istio-ingress-canary istio/gateway \
    --set revision=canary \
    -n istio-ingress
```

**In-place upgrade:** Gateways are upgraded with the control plane.

### Gateway API vs Istio Gateway

If you're using the Kubernetes Gateway API (recommended for new deployments):
- Gateway API resources (`Gateway`, `HTTPRoute`) are K8s-native and version-independent of Istio
- Ensure the Gateway API CRDs installed in your cluster are compatible with both the old and new Istio versions
- Istio's Gateway API support has evolved rapidly -- check release notes for behavior changes

If you're using Istio's classic `Gateway`/`VirtualService` model:
- These resources are Istio CRDs and are upgraded with `istio-base`
- No special migration needed during a minor version upgrade
- Consider migrating to Gateway API when convenient -- it's the future direction

---

## Ambient Mode Upgrades

If your mesh uses Istio ambient mode (ztunnel + waypoint proxies instead of sidecars), the upgrade process differs.

### Upgrade sequence

```
1. Control plane (istiod)        -- same as sidecar mode
2. Istio CNI node agent           -- must be within 1 minor version of istiod
3. ztunnel DaemonSet              -- per-node proxy, briefly disrupts ambient traffic
4. Waypoint proxies / gateways    -- per-gateway upgrade
```

### Key differences from sidecar mode

| Component | Sidecar Mode | Ambient Mode |
|-----------|-------------|--------------|
| **Data plane unit** | Per-pod sidecar | Per-node ztunnel DaemonSet |
| **Disruption scope** | Single pod restart | Entire node during ztunnel upgrade |
| **CNI agent** | Not applicable | Must upgrade (DaemonSet, system-node-critical) |
| **Waypoint proxies** | Not applicable | Upgraded like gateways (revision-aware) |

### ztunnel upgrade

Upgrading ztunnel in-place briefly disrupts all ambient mesh traffic on the node. For production:

- **Recommended:** Cordon and drain nodes before upgrading ztunnel, or use blue/green node pools
- **Acceptable for non-prod:** In-place upgrade with brief disruption

```bash
# In-place ztunnel upgrade
helm upgrade ztunnel istio/ztunnel -n istio-system --wait

# CNI agent upgrade (after istiod, before or with ztunnel)
helm upgrade istio-cni istio/cni -n istio-system
```

The CNI agent prevents new pods from starting on a node during its upgrade, to avoid unsecured traffic leakage. Existing ambient pods continue operating normally.

---

## Rollback

### Canary rollback (safest)

If the canary revision has issues, uninstall it and leave the old control plane running:

```bash
# Revert any namespaces already migrated
kubectl label namespace my-app istio.io/rev=1-28-1 --overwrite
kubectl rollout restart deployment -n my-app

# Remove the canary revision
istioctl uninstall --revision=canary -y
```

If gateways were in-place upgraded to the canary, you must manually reinstall them for the old revision *before* uninstalling the canary. Use the old version's istioctl for this.

### In-place rollback

Use the **old** version's istioctl binary to downgrade:

```bash
# Download the OLD Istio version
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.28.1 sh -

# Downgrade (same as upgrade, just with old binary)
istio-1.28.1/bin/istioctl upgrade

# Restart pods to revert sidecars
kubectl rollout restart deployment --all-namespaces -l istio-inject=true
```

In-place downgrade only works within one minor version (1.29 -> 1.28, not 1.29 -> 1.27).

### Revision tag rollback

If using revision tags, just retarget the tag:

```bash
istioctl tag set prod-stable --revision 1-28-1 --overwrite
# Restart workloads in affected namespaces
```

---

## Common Issues

### Sidecar version mismatch

**Symptom:** `istioctl proxy-status` shows proxies connected to the old control plane after migration.

**Cause:** Pods weren't restarted after the namespace label change, or the `istio-injection` label still exists (it takes precedence over `istio.io/rev`).

```bash
# Check for conflicting labels
kubectl get ns <namespace> --show-labels | grep istio

# Fix: remove istio-injection label, ensure istio.io/rev is set
kubectl label namespace <namespace> istio-injection-
kubectl label namespace <namespace> istio.io/rev=<target-revision> --overwrite

# Restart pods
kubectl rollout restart deployment -n <namespace>
```

### Webhook failures during upgrade

**Symptom:** Pod creation fails with webhook errors like `failed calling webhook "sidecar-injector.istio.io"`.

**Cause:** The sidecar injector webhook is pointing to an istiod that's not ready or has been removed.

```bash
# Check webhook configurations
kubectl get mutatingwebhookconfigurations | grep istio

# Verify the referenced service exists and has endpoints
kubectl get endpoints -n istio-system | grep istiod

# If a stale webhook exists for a removed revision, delete it
kubectl delete mutatingwebhookconfiguration istio-sidecar-injector-<old-revision>
```

### CRD ownership errors with Helm

**Symptom:** `Error: rendered manifests contain a resource that already exists. Unable to continue with update: CustomResourceDefinition ... invalid ownership metadata`

**Cause:** CRDs were created by a previous Istio installation (pre-1.23) without Helm ownership labels.

```bash
# One-time fix: add Helm ownership metadata to existing CRDs
for crd in $(kubectl get crds -l chart=istio -o name && \
             kubectl get crds -l app.kubernetes.io/part-of=istio -o name); do
    kubectl label "$crd" "app.kubernetes.io/managed-by=Helm"
    kubectl annotate "$crd" "meta.helm.sh/release-name=istio-base"
    kubectl annotate "$crd" "meta.helm.sh/release-namespace=istio-system"
done
```

### Control plane not ready after upgrade

**Symptom:** New istiod pod is running but proxies show `NOT SENT` or `STALE` in proxy-status.

**Cause:** The new istiod may be waiting for leader election, or there's a configuration validation issue.

```bash
# Check istiod logs for errors
kubectl logs -n istio-system -l app=istiod,istio.io/rev=<new-revision> --tail=100

# Check if leader election succeeded
kubectl logs -n istio-system -l app=istiod,istio.io/rev=<new-revision> | grep "leader"
```

### Coordinating Istio and EKS upgrades

When upgrading both the K8s cluster and Istio in the same maintenance window:

1. **Check compatibility overlap** -- the Istio version you're running must support both current and target K8s versions during the transition
2. **Upgrade order** -- if your current Istio supports the target K8s version, upgrade EKS first, then Istio. If not, upgrade Istio first to a version that supports both
3. **Avoid simultaneous upgrades** -- always complete one upgrade fully before starting the other
4. **Re-validate after each step** -- run `istioctl proxy-status` and `istioctl analyze` after each upgrade

---

**Sources:**
- [Istio Canary Upgrades](https://istio.io/latest/docs/setup/upgrade/canary/)
- [Istio In-Place Upgrades](https://istio.io/latest/docs/setup/upgrade/in-place/)
- [Istio Helm Upgrade](https://istio.io/latest/docs/setup/upgrade/helm/)
- [Istio Ambient Upgrade](https://istio.io/latest/docs/ambient/upgrade/helm/)
- [Istio Supported Releases](https://istio.io/latest/docs/releases/supported-releases/)
