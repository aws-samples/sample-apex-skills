# Read-only access per capability

Every AWS action below is a Describe, List, Get or query read. Every Kubernetes permission is `get` or `list`. The lists follow the reads the C1, C2 and C3 procedures make. A read the Agent Space is refused is reported by name, and the matching parts of the review read `unknown`, never clean.

Action names mirror the Claude Code skill's `references/read-only-access.md`, which checked them against the Service Authorization Reference on 2026-11-05 ([EKS](https://docs.aws.amazon.com/service-authorization/latest/reference/list_eks.html), [EC2](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html), [ECR](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ecr.html), [Inspector](https://docs.aws.amazon.com/service-authorization/latest/reference/list_inspector2.html), [GuardDuty](https://docs.aws.amazon.com/service-authorization/latest/reference/list_guardduty.html), [IAM](https://docs.aws.amazon.com/service-authorization/latest/reference/list_iam.html)).

## AWS: the Agent Space role

[`iam-policy.json`](iam-policy.json) is the whole policy to attach to the Agent Space execution role. It holds the hardening-guidance reads plus the reads below. `"*"` is shown because most of these List and Describe actions do not support resource-level scoping; scope further where your account standards require it.

| Capability | Actions it uses |
|---|---|
| C1 CVE and advisory review | `eks:ListClusters`, `eks:DescribeCluster`, `eks:ListAddons`, `eks:DescribeAddon`, `eks:DescribeAddonVersions`, `eks:ListNodegroups`, `eks:DescribeNodegroup`, `eks:ListInsights`, `eks:DescribeInsight`; `ec2:DescribeInstances`, `ec2:DescribeImages`, `ec2:DescribeLaunchTemplateVersions`; `ecr:DescribeRepositories`, `ecr:DescribeImages`, `ecr:GetRegistryScanningConfiguration`, `ecr:DescribeImageScanFindings`; `inspector2:BatchGetAccountStatus`, `inspector2:ListCoverage`, `inspector2:ListFindings` |
| C2 security event response (adds) | `eks:ListPodIdentityAssociations`, `eks:DescribePodIdentityAssociation`, `eks:ListAccessEntries`; `iam:GetRole`, `iam:ListAttachedRolePolicies`, `iam:ListRolePolicies` |
| C3 posture check (containment checks) | `eks:DescribeCluster`, `eks:ListAddons`, `eks:DescribeAddon`, `eks:ListPodIdentityAssociations`, `eks:ListAccessEntries`, `eks:ListAssociatedAccessPolicies`; `ec2:DescribeInstances`, `ec2:DescribeSecurityGroups`; `ecr:DescribeRepositories`, `ecr:GetRegistryScanningConfiguration`; `guardduty:ListDetectors`, `guardduty:GetDetector` (configuration only, never findings); `iam:ListOpenIDConnectProviders`; plus, for the node-role check, `eks:DescribeNodegroup` (C1) and `iam:ListAttachedRolePolicies`, `iam:ListRolePolicies` (C2) |

The two access-entry reads list which principals hold cluster admin through an access policy (SEC-POSTURE-64); without them that check reads `unknown`. Inspector is optional: without the three `inspector2` reads the image leg reports `unknown` for findings, and add-on, kubelet and node-OS checks still run. Checking whether an exposure was exploited is not covered yet: https://github.com/aws-samples/sample-apex-skills/issues/351

## Kubernetes: the access entry and a supplementary ClusterRole

The Agent Space reaches the Kubernetes API through an EKS access entry for its role, which `devops-agent/setup.sh` associates with the AWS-managed `AmazonAIOpsAssistantPolicy`. That policy authorizes reads on built-in API groups, enough for C1's nodes, pods, DaemonSets and Deployments, but not on custom resource groups. C2 and C3 also read RBAC objects, service accounts, NetworkPolicies, Auto Mode NodeClasses, Karpenter NodePools and policy engine objects. Bind this read-only ClusterRole for them; it grants no Secrets and no write. Rules for API groups that are not installed are harmless.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: eks-security-reader
rules:
  # C1
  - apiGroups: [""]
    resources: ["nodes", "namespaces", "pods"]
    verbs: ["get", "list"]
  - apiGroups: ["apps"]
    resources: ["daemonsets", "deployments", "statefulsets"]
    verbs: ["get", "list"]
  # C2 and C3
  - apiGroups: [""]
    resources: ["serviceaccounts"]
    verbs: ["get", "list"]
  - apiGroups: ["rbac.authorization.k8s.io"]
    resources: ["roles", "rolebindings", "clusterroles", "clusterrolebindings"]
    verbs: ["get", "list"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["networkpolicies"]
    verbs: ["get", "list"]
  # C3: Auto Mode node settings and admission policy engines, where installed
  - apiGroups: ["eks.amazonaws.com"]
    resources: ["nodeclasses"]
    verbs: ["get", "list"]
  - apiGroups: ["karpenter.sh"]
    resources: ["nodepools", "nodeclaims"]
    verbs: ["get", "list"]
  - apiGroups: ["kyverno.io"]
    resources: ["clusterpolicies", "policies"]
    verbs: ["get", "list"]
  - apiGroups: ["templates.gatekeeper.sh"]
    resources: ["constrainttemplates"]
    verbs: ["get", "list"]
---
# C3: the aws-auth mapping and the VPC CNI settings (the Auto Mode network policy switch) live in two ConfigMaps.
# Scoped by name so no other ConfigMap is readable.
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: eks-security-reader-configmaps
  namespace: kube-system
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["aws-auth", "amazon-vpc-cni"]
    verbs: ["get"]
```

Binding, run once by the team (the agent never runs it). The cluster's authentication mode must be `API` or `API_AND_CONFIG_MAP`. `update-access-entry --kubernetes-groups` sets the entry's group list, so include any groups it already has ([Update access entries](https://docs.aws.amazon.com/eks/latest/userguide/updating-access-entries.html)):

```bash
kubectl apply -f eks-security-reader.yaml   # the ClusterRole and Role above

kubectl create clusterrolebinding eks-security-reader \
  --clusterrole=eks-security-reader --group=eks-security-readers
kubectl create rolebinding eks-security-reader-configmaps -n kube-system \
  --role=eks-security-reader-configmaps --group=eks-security-readers

aws eks update-access-entry --cluster-name <CLUSTER> --region <REGION> \
  --principal-arn arn:aws:iam::<ACCOUNT>:role/<agent-space-role> \
  --kubernetes-groups eks-security-readers
```

Without this binding, every check that needs one of these reads is `unknown` with reason `denied`.

## What it never does

- No Create, Update, Delete, Put, Tag or Untag action on any AWS service.
- No `eks:AccessKubernetesApi`: Kubernetes access comes from the access entry, not an IAM action.
- No read of Secret data (`secrets` get or list), no `pods/exec`, `pods/attach`, `pods/portforward` or `nodes/proxy`.
- No apply, patch, delete, scale, cordon, drain or label against the cluster. Every remediation is printed for the team to review and run.
- No `podsecuritypolicies` read: the PodSecurityPolicy API was removed in Kubernetes 1.25; Pod Security Admission labels on namespaces are read instead.
