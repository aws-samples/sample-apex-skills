# Blue-Green EKS Upgrade

> **Part of:** [eks-upgrader](../SKILL.md)
> **Purpose:** Blue-green cluster migration strategy, green cluster provisioning, traffic shifting, stateful workload handling, and rollback

---

## Table of Contents

1. [When to Choose Blue-Green](#when-to-choose-blue-green)
2. [Architecture Overview](#architecture-overview)
3. [Phase 1: Prepare the Blue Cluster](#phase-1-prepare-the-blue-cluster)
4. [Phase 2: Provision the Green Cluster](#phase-2-provision-the-green-cluster)
5. [Phase 3: Deploy Workloads to Green](#phase-3-deploy-workloads-to-green)
6. [Phase 4: Validate Green Cluster](#phase-4-validate-green-cluster)
7. [Phase 5: Shift Traffic](#phase-5-shift-traffic)
8. [Phase 6: Decommission Blue Cluster](#phase-6-decommission-blue-cluster)
9. [Stateful Workload Migration](#stateful-workload-migration)
10. [OIDC, IAM, and Endpoint Migration](#oidc-iam-and-endpoint-migration)
11. [Rollback](#rollback)
12. [Downsides and Risks](#downsides-and-risks)

---

## When to Choose Blue-Green

Blue-green is higher effort but provides capabilities that in-place upgrades cannot:

| Scenario | Why blue-green |
|----------|---------------|
| **Compliance requires rollback capability** | Control plane upgrades are irreversible in-place |
| **Skipping multiple minor versions** | New cluster at target version avoids step-by-step upgrades |
| **Major architectural changes alongside upgrade** | Networking, IAM, or compute changes bundled with version bump |
| **Zero-downtime requirement for the upgrade itself** | Traffic shifts gradually with instant rollback |
| **Multi-cluster strategy already in place** | If you already run multiple clusters, blue-green is a natural fit |

For routine single-version upgrades on non-critical workloads, prefer [in-place upgrades](in-place-upgrade.md) -- they're simpler and cheaper.

---

## Architecture Overview

```
                        ┌─────────────────┐
                        │   DNS / LB      │
                        │  (Route 53,     │
                        │   ALB, GA)      │
                        └───────┬─────────┘
                           ┌────┴────┐
                           │ Weights │
                      ┌────┴───┐ ┌───┴────┐
                      │  Blue  │ │ Green  │
                      │ (old)  │ │ (new)  │
                      │ K8s N  │ │ K8s N+1│
                      └────┬───┘ └───┬────┘
                           │         │
                      ┌────┴─────────┴────┐
                      │  Shared Services  │
                      │  (RDS, DynamoDB,  │
                      │   ElastiCache,    │
                      │   EFS, S3)        │
                      └───────────────────┘
```

Both clusters share external managed services. Only Kubernetes-internal state (PVs, ConfigMaps, Secrets, CRDs) needs migration.

---

## Phase 1: Prepare the Blue Cluster

Before creating the green cluster, document everything about blue:

```bash
BLUE_CLUSTER=my-cluster-blue

# 1. Record current state
aws eks describe-cluster --name ${BLUE_CLUSTER} \
  --query 'cluster.{Version:version,Endpoint:endpoint,OidcIssuer:identity.oidc.issuer}'

# 2. Export all add-on versions
aws eks list-addons --cluster-name ${BLUE_CLUSTER} --output text | \
  xargs -I{} aws eks describe-addon --cluster-name ${BLUE_CLUSTER} \
  --addon-name {} --query 'addon.{Name:addonName,Version:addonVersion}'

# 3. List all Helm releases
helm list -A --output json

# 4. Back up cluster resources with Velero
velero backup create pre-migration-$(date +%Y%m%d) \
  --include-namespaces '*' \
  --snapshot-volumes=true

# 5. Document external integrations
# - CI/CD pipelines pointing to this cluster
# - Monitoring/alerting targets
# - IAM roles trusting this cluster's OIDC provider
# - kubectl configs distributed to developers
```

### Lower DNS TTLs

If using DNS-based traffic shifting, lower TTLs in advance so DNS changes propagate quickly during cutover:

```bash
# Lower TTL to 60 seconds (do this days before the migration)
# In Route 53, update the record set TTL for your service endpoints
```

---

## Phase 2: Provision the Green Cluster

Create the green cluster at the target K8s version using the same IaC (Terraform, CloudFormation, CDK) as blue, with version bumped.

### Key considerations

| Decision | Recommendation |
|----------|---------------|
| **Same VPC or separate?** | Same VPC simplifies shared service access. Separate VPC provides stronger isolation |
| **Same subnets?** | Separate subnets recommended -- avoids IP exhaustion from running both clusters |
| **Cluster name** | Different name (e.g., `my-cluster-green`). Avoids resource naming collisions |
| **Node groups** | Mirror blue's compute configuration at target version |

### Terraform approach

```hcl
# Duplicate the cluster module, change version and name
module "green_cluster" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "my-cluster-green"
  cluster_version = "1.31"    # target version

  # Same VPC, different subnets (or same if capacity allows)
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Mirror blue's configuration
  # ...
}
```

### Install add-ons on green

Install all EKS managed add-ons and custom add-ons at versions compatible with the target K8s version. This is where the compatibility checks matter -- use the [in-place-upgrade.md](in-place-upgrade.md) add-on tables for version selection.

```bash
GREEN_CLUSTER=my-cluster-green

# Install managed add-ons
for ADDON in vpc-cni coredns kube-proxy aws-ebs-csi-driver; do
  ADDON_VERSION=$(aws eks describe-addon-versions \
    --addon-name ${ADDON} \
    --kubernetes-version 1.31 \
    --query 'addons[0].addonVersions[0].addonVersion' --output text)

  aws eks create-addon \
    --cluster-name ${GREEN_CLUSTER} \
    --addon-name ${ADDON} \
    --addon-version ${ADDON_VERSION}
done
```

---

## Phase 3: Deploy Workloads to Green

### GitOps (recommended)

Point your GitOps tool (ArgoCD, Flux) at the green cluster and let it reconcile:

```bash
# ArgoCD: add the green cluster
argocd cluster add arn:aws:eks:us-east-1:123456789:cluster/my-cluster-green

# Update Application destinations to target green (or use ApplicationSets for multi-cluster)
```

### Velero restore

If not using GitOps, restore from the Velero backup:

```bash
# Configure Velero on the green cluster to access the same backup location
velero restore create --from-backup pre-migration-20260325 \
  --include-namespaces '*' \
  --restore-volumes=true
```

### Validate deployments

```bash
# All pods running
kubectl --context green get pods -A | grep -v Running | grep -v Completed

# Replica counts match blue
diff <(kubectl --context blue get deployments -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,REPLICAS:.spec.replicas --no-headers | sort) \
     <(kubectl --context green get deployments -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,REPLICAS:.spec.replicas --no-headers | sort)
```

---

## Phase 4: Validate Green Cluster

Run comprehensive validation before sending any real traffic:

```bash
# 1. Cluster health
kubectl --context green get nodes -o wide
# Control plane readiness (componentstatuses is deprecated and empty on modern EKS)
kubectl --context green get --raw '/readyz?verbose'

# 2. DNS resolution
kubectl --context green run dns-test --image=busybox:1.36 --rm -it --restart=Never -- \
  nslookup kubernetes.default.svc.cluster.local

# 3. Application smoke tests
# Run your application-specific health checks and integration tests against green

# 4. Load test (optional but recommended)
# Send synthetic traffic to green's ingress to verify performance under load

# 5. Verify external connectivity
# Confirm pods can reach managed services (RDS, DynamoDB, ElastiCache, S3)
```

---

## Phase 5: Shift Traffic

### Traffic shifting patterns

| Method | Granularity | Rollback Speed | Best for |
|--------|------------|----------------|----------|
| **Route 53 weighted routing** | Percentage-based | Fast (DNS TTL) | Most scenarios |
| **ALB weighted target groups** | Percentage-based | Instant | HTTP workloads behind ALB |
| **Global Accelerator** | Endpoint weights | Instant | Multi-region, TCP/UDP |
| **External DNS cutover** | All-or-nothing | DNS TTL dependent | Simple, non-critical |

### Route 53 weighted routing

```bash
# Start with 10% to green, 90% to blue
aws route53 change-resource-record-sets --hosted-zone-id Z123 \
  --change-batch '{
    "Changes": [
      {
        "Action": "UPSERT",
        "ResourceRecordSet": {
          "Name": "api.example.com",
          "Type": "A",
          "SetIdentifier": "blue",
          "Weight": 90,
          "AliasTarget": {
            "HostedZoneId": "Z456",
            "DNSName": "blue-alb.us-east-1.elb.amazonaws.com",
            "EvaluateTargetHealth": true
          }
        }
      },
      {
        "Action": "UPSERT",
        "ResourceRecordSet": {
          "Name": "api.example.com",
          "Type": "A",
          "SetIdentifier": "green",
          "Weight": 10,
          "AliasTarget": {
            "HostedZoneId": "Z789",
            "DNSName": "green-alb.us-east-1.elb.amazonaws.com",
            "EvaluateTargetHealth": true
          }
        }
      }
    ]
  }'
```

### Recommended shift schedule

| Stage | Blue Weight | Green Weight | Duration | Action |
|-------|-----------|-------------|----------|--------|
| 1 | 90% | 10% | 1-2 hours | Monitor error rates, latency |
| 2 | 50% | 50% | 2-4 hours | Validate under meaningful load |
| 3 | 10% | 90% | 1-2 hours | Final validation |
| 4 | 0% | 100% | -- | Full cutover, begin decommission window |

Monitor throughout: error rates, latency percentiles, pod restarts, and application-specific metrics. Roll back at any stage if metrics degrade.

### ALB weighted target groups

```bash
# Register green cluster's target group with the ALB
aws elbv2 modify-rule --rule-arn <rule-arn> \
  --actions '[
    {
      "Type": "forward",
      "ForwardConfig": {
        "TargetGroups": [
          {"TargetGroupArn": "<blue-tg-arn>", "Weight": 90},
          {"TargetGroupArn": "<green-tg-arn>", "Weight": 10}
        ]
      }
    }
  ]'
```

---

## Phase 6: Decommission Blue Cluster

Only after green has been running at 100% traffic with no issues for a sufficient validation period (hours to days depending on your risk tolerance):

```bash
# 1. Final backup of blue (safety net)
velero backup create final-blue-$(date +%Y%m%d) \
  --include-namespaces '*'

# 2. Remove blue from DNS/LB (if not already at weight 0)

# 3. Scale down blue workloads
kubectl --context blue scale deployment --all --replicas=0 -A

# 4. Delete the cluster (via IaC)
# terraform destroy -target=module.blue_cluster
# or
# aws eks delete-cluster --name my-cluster-blue
# (after deleting all node groups and add-ons)

# 5. Clean up orphaned resources
# - IAM roles and OIDC provider for blue
# - Security groups
# - Load balancers
# - CloudWatch log groups
```

---

## Stateful Workload Migration

### By storage type

| Storage | Migration approach |
|---------|-------------------|
| **EBS PersistentVolumes** | Snapshot -> restore in green cluster's AZs |
| **EFS** | Mount the same EFS file system from both clusters (no migration) |
| **RDS / DynamoDB / ElastiCache** | Shared managed service -- no migration needed |
| **S3** | Shared -- no migration needed |
| **In-cluster databases** (e.g., PostgreSQL on K8s) | Velero backup/restore or application-level pg_dump/restore |

### EBS volume migration

```bash
# 1. Identify PVs on blue
kubectl --context blue get pv -o custom-columns=\
NAME:.metadata.name,\
CLAIM:.spec.claimRef.name,\
NS:.spec.claimRef.namespace,\
VOLUME:.spec.awsElasticBlockStore.volumeID

# 2. Snapshot each volume
aws ec2 create-snapshot --volume-id vol-xxx --description "blue-migration"

# 3. Create volumes from snapshots in green cluster's AZs
aws ec2 create-volume \
  --snapshot-id snap-xxx \
  --availability-zone us-east-1a \
  --volume-type gp3

# 4. Create PVs in green cluster pointing to the new volumes
```

### EFS (shared access)

EFS file systems can be mounted from both clusters simultaneously. Ensure the green cluster's security groups allow NFS access (port 2049) to the EFS mount targets:

```bash
# Verify EFS mount targets are accessible from green's subnets
aws efs describe-mount-targets --file-system-id fs-xxx \
  --query 'MountTargets[*].[SubnetId,IpAddress]'
```

---

## OIDC, IAM, and Endpoint Migration

A new EKS cluster has a different API endpoint and OIDC issuer URL. Everything that trusts or connects to the old cluster needs updating.

### What changes

| Resource | Blue | Green | Action needed |
|----------|------|-------|---------------|
| **API endpoint** | `https://xxx.eks.amazonaws.com` | `https://yyy.eks.amazonaws.com` | Update kubeconfigs, CI/CD |
| **OIDC issuer** | `oidc.eks.../id/AAA` | `oidc.eks.../id/BBB` | Update IAM role trust policies |
| **Certificate authority** | Blue's CA cert | Green's CA cert | Update kubeconfigs |

### IRSA / Pod Identity trust policies

Every IAM role that uses IRSA (IAM Roles for Service Accounts) must be updated to trust the green cluster's OIDC provider:

```bash
# 1. Get green cluster's OIDC issuer
GREEN_OIDC=$(aws eks describe-cluster --name ${GREEN_CLUSTER} \
  --query 'cluster.identity.oidc.issuer' --output text | sed 's|https://||')

# 2. Create OIDC provider for green cluster (if not done by IaC)
aws iam create-open-id-connect-provider \
  --url https://${GREEN_OIDC} \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list <thumbprint>

# 3. Update each IAM role's trust policy to include green's OIDC
# (or better: manage this in Terraform alongside the cluster)
```

If using EKS Pod Identity instead of IRSA, create the pod identity associations on the green cluster:

```bash
aws eks create-pod-identity-association \
  --cluster-name ${GREEN_CLUSTER} \
  --namespace my-namespace \
  --service-account my-sa \
  --role-arn arn:aws:iam::123456789:role/my-role
```

### CI/CD pipelines

Update every pipeline that deploys to or interacts with the cluster:
- kubeconfig or EKS cluster reference
- ArgoCD/Flux cluster target
- Helm release targets
- Terraform backend references

---

## Rollback

The primary advantage of blue-green: rollback is a traffic shift, not a rebuild.

### During traffic shifting

```bash
# Shift all traffic back to blue
# Route 53: set blue weight to 100, green to 0
# ALB: set blue target group weight to 100, green to 0
```

This takes effect within seconds (ALB) or DNS TTL (Route 53 -- this is why you lowered TTLs earlier).

### After full cutover

If blue is still running (not yet decommissioned), rollback is still possible:
1. Shift traffic back to blue
2. Verify blue is still healthy (workloads may have stale state if time has passed)
3. Investigate and fix issues on green before attempting cutover again

### After blue decommission

If blue has been deleted, rollback requires rebuilding:
1. Provision new cluster at previous version
2. Restore from Velero backup
3. Shift traffic to the restored cluster

This is why the decommission phase should have a sufficient "bake" period.

---

## Downsides and Risks

| Risk | Mitigation |
|------|-----------|
| **2x cluster cost** during migration | Minimize the overlap window. Scale down blue quickly after validation |
| **API endpoint and OIDC change** | Use Terraform to manage trust policies alongside cluster. Migrate CI/CD early |
| **Load balancers can't span both clusters** | Use Route 53 or Global Accelerator in front of per-cluster LBs |
| **Dependent services must migrate together** | Map service dependencies. Migrate tightly-coupled services as a group |
| **Region EC2 capacity limits** | Running two clusters doubles EC2 demand. Check quotas and consider reserved capacity |
| **State divergence during dual-running** | Keep the overlap period short. For stateful apps, use shared managed services (RDS, EFS) |
| **Velero doesn't back up AWS resources** | IAM roles, security groups, VPC config must be recreated via IaC, not Velero |

---

**Sources:**
- [AWS EKS Best Practices Guide -- Cluster Upgrades](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
- [EKS Blue-Green Deployments](https://docs.aws.amazon.com/eks/latest/userguide/cluster-upgrades.html)
- [Velero Disaster Recovery](https://velero.io/docs/)
