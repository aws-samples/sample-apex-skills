---
name: eks-upgrader
description: EKS cluster upgrade companion. Add-on compatibility matrices, upgrade procedures (in-place and blue-green), and component-specific guidance for Karpenter, Istio, and other ecosystem tools. Use when planning or executing an EKS version upgrade, checking add-on compatibility, or troubleshooting upgrade issues.
---

# EKS Upgrader

Focused knowledge for upgrading EKS clusters and the ecosystem components that run on them. This skill complements `eks-best-practices` (which covers general cluster-upgrades knowledge) with deeper, component-specific upgrade guidance.

## When to Load References

### EKS Cluster Upgrade Strategies

| Reference | Load when... |
|-----------|-------------|
| [in-place-upgrade.md](references/in-place-upgrade.md) | Planning or executing a standard in-place EKS upgrade |
| [blue-green-upgrade.md](references/blue-green-upgrade.md) | Planning a blue-green cluster migration strategy |

### Custom Add-on Upgrades

| Reference | Load when... |
|-----------|-------------|
| [karpenter.md](references/karpenter.md) | Cluster uses Karpenter -- compatibility matrix, Helm upgrade, CRD management, drift-based node replacement |
| [istio.md](references/istio.md) | Cluster runs Istio -- canary/in-place upgrade, revision tags, sidecar rollout, ambient mode |

## Upgrade Principles

- EKS upgrades go one minor version at a time (control plane, then add-ons, then data plane)
- Always check add-on compatibility for the target K8s version before starting
- The control plane upgrade is irreversible -- validate everything beforehand
- Non-prod first, production second
- Custom add-ons (Karpenter, Istio, ingress controllers, etc.) need their own compatibility checks

## Strategy Decision

| Factor | In-Place | Blue-Green |
|--------|----------|------------|
| **Downtime risk** | Minutes (control plane) | Near-zero |
| **Rollback** | Not possible for control plane | DNS/LB switch back |
| **Cost** | No extra cost | 2x cluster cost during migration |
| **Complexity** | Low-Medium | High |
| **State migration** | None needed | Must migrate PVs, DNS, state |
| **Version jump** | One minor at a time | Can skip versions (new cluster) |
| **Use when** | Most upgrades | Critical workloads, major version jumps, compliance rollback requirement |

## Pre-Flight Checklist

Run these before any upgrade strategy:

```bash
CLUSTER=<cluster-name>
TARGET_VERSION=<e.g. 1.31>

# 1. Check Cluster Insights for blockers
aws eks list-insights --cluster-name ${CLUSTER} --filter 'statuses=ERROR,WARNING'

# 2. Verify subnet IP capacity (need 5+ free IPs)
aws ec2 describe-subnets --subnet-ids \
  $(aws eks describe-cluster --name ${CLUSTER} \
  --query 'cluster.resourcesVpcConfig.subnetIds' --output text) \
  --query 'Subnets[*].[SubnetId,AvailabilityZone,AvailableIpAddressCount]' \
  --output table

# 3. Verify IAM role and KMS key (both cause stuck upgrades if broken)
ROLE_ARN=$(aws eks describe-cluster --name ${CLUSTER} \
  --query 'cluster.roleArn' --output text)
aws iam get-role --role-name ${ROLE_ARN##*/} \
  --query 'Role.AssumeRolePolicyDocument'
# Should show Principal: eks.amazonaws.com, Action: sts:AssumeRole
# If secret encryption is enabled, verify KMS key access:
aws eks describe-cluster --name ${CLUSTER} \
  --query 'cluster.encryptionConfig'

# 4. Check add-on compatibility
for ADDON in vpc-cni coredns kube-proxy aws-ebs-csi-driver; do
  echo "=== ${ADDON} ==="
  aws eks describe-addon-versions \
    --addon-name ${ADDON} \
    --kubernetes-version ${TARGET_VERSION} \
    --query 'addons[0].addonVersions[0].addonVersion' \
    --output text
done

# 5. Scan for deprecated APIs (static)
# Using Pluto (install: brew install FairwindsOps/tap/pluto)
pluto detect-helm --target-versions k8s=v${TARGET_VERSION}
# Or kube-no-trouble
kubent --target-version ${TARGET_VERSION}

# 6. Check live deprecated API usage (catches what static scanning misses)
# Prometheus metric (if Prometheus is running):
kubectl get --raw /metrics | grep apiserver_requested_deprecated_apis
# CloudWatch audit log query (last 30 days):
QUERY_ID=$(aws logs start-query \
  --log-group-name /aws/eks/${CLUSTER}/cluster \
  --start-time $(date -u --date="-30 days" "+%s") \
  --end-time $(date "+%s") \
  --query-string 'fields @message | filter `annotations.k8s.io/deprecated`="true"' \
  --query queryId --output text)
sleep 5 && aws logs get-query-results --query-id $QUERY_ID

# 7. Enable control plane logging
aws eks update-cluster-config --name ${CLUSTER} \
  --logging '{"clusterLogging":[{"types":["api","audit","authenticator","controllerManager","scheduler"],"enabled":true}]}'

# 8. Back up cluster state
# Velero, GitOps export, or kubectl get -A -o yaml
```

If any Cluster Insight returns `"status": ERROR`, resolve it before proceeding.

## Version Support Lifecycle

| Phase | Duration | Cost |
|-------|----------|------|
| **Standard support** | 14 months from release | Standard pricing |
| **Extended support** | +12 months | Additional per-hour fee |
| **End of support** | N/A | Auto-upgrade to oldest supported version |

You can [disable extended support](https://docs.aws.amazon.com/eks/latest/userguide/disable-extended-support.html) so auto-upgrade happens at end of standard support instead.

Upgrade every 3-4 months to stay within standard support. Budget one upgrade cycle per quarter. Review upcoming K8s releases early to identify breaking changes before they arrive.

## Key API Removals by Version

| Version | Removed | Replacement |
|---------|---------|-------------|
| **1.29** | flowcontrol v1beta2 | flowcontrol v1 |
| **1.32** | flowcontrol v1beta3 | flowcontrol v1 |
