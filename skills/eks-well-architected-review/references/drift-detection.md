# 🎯 EKS Best Practices Baseline — Drift Detection

10 automated checks against collected cluster data. All can be answered from `$WORK` files.
Drift is reported as pass/fail in the report; it is **not** folded into pillar scores.

---

## Drift scorer — run verbatim

Requires `$WORK` (SKILL.md Step 2). Prints a ready-to-paste markdown table.

```bash
W="$WORK"
LOGS=$(jq '[.cluster.logging.clusterLogging[]?|select(.enabled==true)|.types[]]|unique|length' "$W/cluster.json")
ENC=$(jq '[.cluster.encryptionConfig[]?|select(.resources[]?=="secrets")]|length' "$W/cluster.json")
PRIV=$(jq -r '.cluster.resourcesVpcConfig.endpointPrivateAccess' "$W/cluster.json")
PUBOK=$(jq -r '.cluster.resourcesVpcConfig as $v|(($v.endpointPublicAccess==false) or (($v.publicAccessCidrs//[])|any(.=="0.0.0.0/0")|not))' "$W/cluster.json")
# Evidence must describe what was FOUND, not restate the pass condition. A ❌ row whose evidence
# column reads "not 0.0.0.0/0" tells the operator the opposite of the truth, and the evidence
# column is the whole reason the drift table is actionable.
PUBWHY=$(jq -r '.cluster.resourcesVpcConfig as $v| if $v.endpointPublicAccess==false then "public access disabled" else (($v.publicAccessCidrs//[])|if length==0 then "public enabled, no CIDR list" elif any(.=="0.0.0.0/0") then "public open to 0.0.0.0/0" else "public restricted to "+(join(","))  end) end' "$W/cluster.json")
# Workload identity. Must agree with sec-6/sec-18 or one report contradicts itself (the same defect
# that had check 6 green while sec-4 reported a High finding on the same denominator).
#   - the cluster ISSUER is present on every EKS cluster, so it proves nothing on its own;
#   - IRSA works only if a matching IAM OIDC PROVIDER is registered in the account;
#   - Pod Identity needs neither, so a Pod-Identity-only cluster must still pass.
OIDCPROV=$(jq -r -s '.[0] as $cl|.[1] as $p|(($cl.cluster.identity.oidc.issuer//"")|sub("^https://";"")) as $iss|((($iss|length)>0) and ([$p.OpenIDConnectProviderList[]?.Arn//empty]|any(endswith("oidc-provider/"+$iss))))' "$W/cluster.json" "$W/oidcproviders.json")
PIA=$(jq '[.associations[]?]|length' "$W/podidentity.json")
IRSASA=$(jq '[.items[]?|select(.metadata.annotations["eks.amazonaws.com/role-arn"])]|length' "$W/serviceaccounts.json")
if [ "$PIA" -gt 0 ] || { [ "$OIDCPROV" = true ] && [ "$IRSASA" -gt 0 ]; }; then OIDC=true; else OIDC=false; fi
WIWHY=$( { [ "$PIA" -gt 0 ] && printf '%s Pod Identity association(s)' "$PIA"; } ; \
         { [ "$PIA" -gt 0 ] && [ "$OIDCPROV" = true ] && [ "$IRSASA" -gt 0 ] && printf ' + '; } ; \
         { [ "$OIDCPROV" = true ] && [ "$IRSASA" -gt 0 ] && printf '%s IRSA SA(s) with a registered IAM OIDC provider' "$IRSASA"; } ; \
         { [ "$OIDC" = false ] && [ "$IRSASA" -gt 0 ] && [ "$OIDCPROV" != true ] && printf '%s IRSA annotation(s) but no matching IAM OIDC provider — inert' "$IRSASA"; } ; \
         { [ "$OIDC" = false ] && [ "$IRSASA" -eq 0 ] && printf 'no Pod Identity associations and no IRSA ServiceAccounts'; } )
NP=$(jq '[.items[]]|length' "$W/networkpolicies.json")
# COVERAGE on sec-4's denominator, not a bare object count. Counting policies put a green tick
# here while sec-4 reported `some — 2/3 ns covered` as a HIGH-severity finding in the same
# report: sec-4 excludes system namespaces and `^default$`, so a policy parked in `default`
# (where no workloads run) counted for this row and for nothing else.
NPCOV=$(jq -r -s '.[0] as $ns | .[1] as $np
  | [ $ns.items[]? | select((.metadata.name|test("^(kube-|amazon-)|^default$"))|not) | .metadata.name ] as $scoped
  | ($np.items|map(.metadata.namespace)|unique) as $cov
  | "\([ $scoped[] | select(. as $n|$cov|index($n)) ]|length)/\($scoped|length)"' \
  "$W/namespaces.json" "$W/networkpolicies.json")
NPOK=${NPCOV%%/*}
ESO=$(jq -r '([.items[]|select(.metadata.name|test("external-secrets"))]|length)>0' "$W/deployments.json")
AM=$(jq -r '.cluster.computeConfig.enabled==true' "$W/cluster.json")
NG=$(jq '(.nodegroups//[])|length' "$W/nodegroups.json")
# A Fargate-only cluster has NO managed node groups by design, so check 8 must not mark it as
# drifted — AWS does not offer node groups for Fargate compute at all. Detect it the way the rest
# of the skill does: every node labelled eks.amazonaws.com/compute-type=fargate (and at least one
# node, so an empty cluster does not read as Fargate). The Auto Mode guard below is the same idea;
# this closes the equivalent gap for Fargate.
FGONLY=$(jq -r '[.items[]] as $n|(($n|length)>0) and ([$n[]|select(.metadata.labels["eks.amazonaws.com/compute-type"]=="fargate")]|length)==($n|length)' "$W/nodes.json")
ADD=$(jq '(.addons//[]) as $a|["vpc-cni","coredns","kube-proxy"]|map(select(. as $x|$a|any(.==$x)))|length' "$W/addons.json")
PDB=$(jq '[.items[]]|length' "$W/pdb.json")
# COVERAGE, not cardinality — this row must agree with rel-2, which matches PDB selectors
# against each Deployment's pod-template labels. Counting PDBs made the drift table show a green
# tick on a cluster whose only PDB selects a workload that no longer exists, directly next to
# rel-2 reporting `none — 0/1 deploys covered by PDB` in the same report. A reader cannot
# reconcile those, and the green row is the one they believe.
PDBCOV=$(jq -s '.[0] as $p | .[1] as $d
  | [ $d.items[]? | select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not) | . as $dep | (($dep.spec.template.metadata.labels)//{}) as $lb
      | select([ $p.items[]? | select(.metadata.namespace==$dep.metadata.namespace)
                 | (((.spec.selector.matchLabels)//{})|to_entries) as $sel
                 | select(($sel|length)>0 and ($sel|all($lb[.key]==.value))) ]|length>0) ]|length' \
  "$W/pdb.json" "$W/deployments.json")
# Same namespace filter as rel-2 and as PDBCOV above: an operator cannot add a PDB to
# AWS's coredns/ebs-csi Deployments, and counting them made this row disagree with rel-2.
DEPTOT=$(jq '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)]|length' "$W/deployments.json")
echo "| # | Check | Status | Evidence |"
echo "|---|-------|--------|----------|"
echo "| 1 | Control plane logging | $([ "$LOGS" -ge 5 ] && echo ✅ || echo ❌) | $LOGS/5 types enabled |"
echo "| 2 | Envelope encryption | $([ "$ENC" -gt 0 ] && echo ✅ || echo ❌) | $([ "$ENC" -gt 0 ] && echo "KMS envelope on secrets" || echo "no encryptionConfig for secrets") |"
echo "| 3 | Private endpoint | $([ "$PRIV" = true ] && echo ✅ || echo ❌) | endpointPrivateAccess=$PRIV |"
echo "| 4 | Public endpoint restricted | $([ "$PUBOK" = true ] && echo ✅ || echo ❌) | $PUBWHY |"
echo "| 5 | Workload identity (Pod Identity / IRSA) | $([ "$OIDC" = true ] && echo ✅ || echo ❌) | $WIWHY |"
echo "| 6 | Network policies | $([ "${NPOK:-0}" -gt 0 ] && echo ✅ || echo ❌) | $NPCOV workload ns covered ($NP policy objects) |"
echo "| 7 | Secrets encryption | $( { [ "$ENC" -gt 0 ] || [ "$ESO" = true ]; } && echo ✅ || echo ❌) | $( [ "$ENC" -gt 0 ] && printf 'KMS envelope'; [ "$ENC" -gt 0 ] && [ "$ESO" = true ] && printf ' + '; [ "$ESO" = true ] && printf 'External Secrets Operator'; { [ "$ENC" -gt 0 ] || [ "$ESO" = true ]; } || printf 'neither KMS envelope nor ESO' ) |"
echo "| 8 | Managed node groups | $( { [ "$FGONLY" = true ] || [ "$AM" = true ] || [ "$NG" -gt 0 ]; } && echo ✅ || echo ❌) | $( [ "$FGONLY" = true ] && echo "n/a — Fargate-only cluster" || { [ "$AM" = true ] && echo "EKS Auto Mode manages compute" || echo "ng=$NG automode=$AM"; } ) |"
echo "| 9 | Managed addons | $( { [ "$AM" = true ] || [ "$ADD" -ge 3 ]; } && echo ✅ || echo ❌) | $( [ "$AM" = true ] && echo "n/a — Auto Mode delivers CNI/DNS/LB/storage as core components, not add-ons" || echo "$ADD/3 core") |"
echo "| 10 | PodDisruptionBudgets | $([ "$PDBCOV" -gt 0 ] && echo ✅ || echo ❌) | $([ "$DEPTOT" -eq 0 ] && echo "no Deployments" || echo "$PDBCOV/$DEPTOT deploys covered ($PDB PDB objects)") |"
```

Check 8 passes on Auto Mode even with an empty managed-node-group list (AWS manages nodes).

---

## Check 1: Control Plane Logging

**What:** All 5 control plane log types should be enabled (api, audit, authenticator, controllerManager, scheduler).

**Command:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.logging.clusterLogging[?enabled==\`true\`].types[]" --output json
```

**Pass:** All 5 types present in enabled entries.
**Fail:** Any of the 5 types missing.

**Remediation:** Enable all 5 control plane log types in the EKS console or via CLI:
```bash
aws eks update-cluster-config --name <CLUSTER> --region <REGION> --logging '{"clusterLogging":[{"types":["api","audit","authenticator","controllerManager","scheduler"],"enabled":true}]}'
```

---

## Check 2: Envelope Encryption

**What:** Kubernetes secrets should be encrypted at rest using a KMS key.

**Command:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.encryptionConfig[?resources[?contains(@,'secrets')]]"
```

**Pass:** encryptionConfig exists with "secrets" in resources.
**Fail:** No encryptionConfig or secrets not included.

**Remediation:** Enable envelope encryption (requires cluster recreation or `aws eks associate-encryption-config`).

---

## Check 3: Private Endpoint Enabled

**What:** The private API server endpoint should be enabled for VPC-internal communication.

**Command:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.resourcesVpcConfig.endpointPrivateAccess"
```

**Pass:** Returns `true`.
**Fail:** Returns `false`.

**Remediation:**
```bash
aws eks update-cluster-config --name <CLUSTER> --region <REGION> --resources-vpc-config endpointPrivateAccess=true
```

---

## Check 4: Public Endpoint Restricted

**What:** The public API endpoint should either be disabled or restricted to specific CIDRs (not 0.0.0.0/0).

**Command:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.resourcesVpcConfig.{public:endpointPublicAccess,cidrs:publicAccessCidrs}"
```

**Pass:** `endpointPublicAccess` is false, OR `publicAccessCidrs` does NOT contain 0.0.0.0/0.
**Fail:** Public access enabled with 0.0.0.0/0 in CIDRs.

**Remediation:**
```bash
aws eks update-cluster-config --name <CLUSTER> --region <REGION> --resources-vpc-config endpointPublicAccess=true,publicAccessCidrs="<YOUR_CIDR>/32"
```

---

## Check 5: Workload Identity Configured (Pod Identity or IRSA)

**What:** Pods that need AWS access should get it from pod-level identity, not the node instance
profile. Either mechanism satisfies this check.

**Command:**
```bash
aws eks list-pod-identity-associations --cluster-name <CLUSTER> --region <REGION> --output json
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.identity.oidc.issuer"
aws iam list-open-id-connect-providers --output json
kubectl get serviceaccounts -A -o json
```

**Pass:** at least one Pod Identity association, **or** at least one ServiceAccount annotated with
`eks.amazonaws.com/role-arn` *and* an IAM OIDC provider whose ARN matches this cluster's issuer.

**Fail:** neither — including the trap case of IRSA annotations with no registered provider, which
looks configured and grants nothing.

**Do not test the issuer alone.** It is present on every EKS cluster, so a check written that way
cannot fail. It is the input to `create-open-id-connect-provider`, not proof of one. Match it against
the provider list, and scope the match to this cluster's issuer — an account with several clusters has
several providers, and another cluster's provider does not enable IRSA here.

**Remediation:**
```bash
# preferred for new work
aws eks create-pod-identity-association --cluster-name <CLUSTER> \
  --namespace <NS> --service-account <SA> --role-arn <ROLE_ARN>
# or IRSA (also creates the provider if absent)
eksctl utils associate-iam-oidc-provider --cluster <CLUSTER> --approve
```

---

## Check 6: Network Policies Present

**What:** Every namespace that runs workloads should be covered by a NetworkPolicy.

**Measured as COVERAGE, not a count.** The scorer reports `<covered>/<scoped>` namespaces on the
same denominator as `sec-4`, which excludes `kube-*`, `amazon-*` and `default`.

**Pass:** at least one scoped namespace covered (the Evidence column carries the ratio).
**Fail:** no scoped namespace covered.

> **Do not "simplify" this back to `kubectl get networkpolicies -A | wc -l`.** A bare count put a
> green tick on this row while `sec-4` reported `some — 2/3 ns covered` as a High-severity finding
> in the same report, because a policy parked in `default` (where no workloads run) counted here and
> nowhere else. A reader cannot reconcile those two rows, and they believe the green one.

**Remediation:** Create default-deny NetworkPolicies per namespace, then allow specific traffic:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: <ns>
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
```

---

## Check 7: Secrets Encryption

**What:** Secrets should be protected via envelope encryption OR an External Secrets Operator.

**Command:**
```bash
# Check envelope encryption
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.encryptionConfig"

# Check for External Secrets Operator
kubectl get pods -A --no-headers 2>/dev/null | grep -i external-secrets
```

**Pass:** Envelope encryption includes "secrets" OR external-secrets pods exist.
**Fail:** Neither found.

**Remediation:** Deploy External Secrets Operator:
```bash
helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace
```

---

## Check 8: Managed Node Groups Used

**What:** Worker nodes should use EKS Managed Node Groups for automated lifecycle management.

**Command:**
```bash
aws eks list-nodegroups --cluster-name <CLUSTER> --region <REGION> --query "nodegroups"
```

**Pass:** At least one nodegroup returned.
**Fail:** Empty list (nodes may be self-managed or Karpenter-only).

**Remediation:**
```bash
eksctl create nodegroup --cluster <CLUSTER> --managed --name <name>
```

---

## Check 9: EKS Managed Addons

**What:** Core addons (vpc-cni, coredns, kube-proxy) should be EKS-managed for automatic updates.

**Command:**
```bash
aws eks list-addons --cluster-name <CLUSTER> --region <REGION> --query "addons"
```

**Pass:** All three present: vpc-cni, coredns, kube-proxy.
**Fail:** Any of the three missing.

**Remediation:**
```bash
aws eks create-addon --cluster-name <CLUSTER> --addon-name vpc-cni --region <REGION>
aws eks create-addon --cluster-name <CLUSTER> --addon-name coredns --region <REGION>
aws eks create-addon --cluster-name <CLUSTER> --addon-name kube-proxy --region <REGION>
```

---

## Check 10: PodDisruptionBudgets Present

**What:** Workload Deployments should be covered by a PodDisruptionBudget so node drains and
upgrades cannot take all replicas at once.

**Measured as COVERAGE, not a count.** The scorer matches each PDB's `spec.selector.matchLabels`
against each Deployment's pod-template labels in the same namespace and reports
`<covered>/<deployments>`, on the same operator-owned-namespace denominator as `rel-2`. The raw PDB
object count is still shown in parentheses as context.

**Pass:** at least one Deployment covered.
**Fail:** none covered (or no Deployments, reported as `no Deployments`).

> **Do not "simplify" this back to `kubectl get pdb -A | wc -l`.** Counting objects showed a green
> tick on a cluster whose only PDB selected a workload that no longer exists, printed directly above
> `rel-2` reporting `none — 0/1 deploys covered by PDB`. Counting also included AWS's own
> `kube-system` Deployments, which an operator cannot attach a PDB to.

**Remediation:**
```bash
kubectl create pdb <name> --selector=app=<label> --min-available=1 -n <namespace>
```

---

## Summary Table Template

After running all 10 checks, present results as:

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Control plane logging | ✅/❌ | [what was found] |
| 2 | Envelope encryption | ✅/❌ | [what was found] |
| 3 | Private endpoint | ✅/❌ | [what was found] |
| 4 | Public endpoint restricted | ✅/❌ | [what was found] |
| 5 | Workload identity (Pod Identity / IRSA) | ✅/❌ | [what was found] |
| 6 | Network policies | ✅/❌ | [count found] |
| 7 | Secrets encryption | ✅/❌ | [method found] |
| 8 | Managed node groups | ✅/❌ | [count found] |
| 9 | EKS managed addons | ✅/❌ | [which present] |
| 10 | PodDisruptionBudgets | ✅/❌ | [count found] |
