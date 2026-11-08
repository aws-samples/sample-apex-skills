---
title: "Read-only access per capability"
description: "Every AWS action below is a Describe, List, Get or query read."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-security/references/read-only-access.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-security/references/read-only-access.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-security/references/read-only-access.md). Edit the source, not this page.
:::

# Read-only access per capability

Every AWS action below is a Describe, List, Get or query read. Every Kubernetes permission is `get` or `list`. The C1 and C3 lists are what collect.sh and posture_collect.sh call; each collector's preflight probes its main reads. The C2 reads are the commands in security-event-response.md, which the skill runs directly; no preflight probes them.

Action names were checked against the Service Authorization Reference service pages on 2026-11-05 ([EKS](https://docs.aws.amazon.com/service-authorization/latest/reference/list_eks.html), [EC2](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html), [ECR](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ecr.html), [Inspector](https://docs.aws.amazon.com/service-authorization/latest/reference/list_inspector2.html), [GuardDuty](https://docs.aws.amazon.com/service-authorization/latest/reference/list_guardduty.html), [CloudTrail](https://docs.aws.amazon.com/service-authorization/latest/reference/list_cloudtrail.html), [IAM](https://docs.aws.amazon.com/service-authorization/latest/reference/list_iam.html), [STS](https://docs.aws.amazon.com/service-authorization/latest/reference/list_sts.html)).

Use a dedicated role for these reviews. Scope `Resource` further where your account standards require it; `"*"` is shown because most of these List and Describe actions do not support resource-level scoping.

## C1: CVE and advisory review

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EksSecurityC1ReadOnly",
      "Effect": "Allow",
      "Resource": "*",
      "Action": [
        "sts:GetCallerIdentity",
        "eks:DescribeCluster",
        "eks:ListAddons", "eks:DescribeAddon", "eks:DescribeAddonVersions",
        "eks:ListNodegroups", "eks:DescribeNodegroup",
        "eks:ListInsights",
        "ec2:DescribeInstances", "ec2:DescribeImages",
        "ecr:GetRegistryScanningConfiguration",
        "inspector2:BatchGetAccountStatus", "inspector2:ListFindings"
      ]
    }
  ]
}
```

Inspector is optional: without the two `inspector2` reads (or with `--skip-inspector`) the image leg reports `unknown` for findings, and add-on, kubelet and node-OS checks still run.

## C2: security event response

C2 adds the identity reads it needs to scope an event (which roles a workload can use, and what they allow). Add to C1's policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EksSecurityC2Identity",
      "Effect": "Allow",
      "Resource": "*",
      "Action": [
        "eks:ListPodIdentityAssociations", "eks:DescribePodIdentityAssociation", "eks:ListAccessEntries",
        "iam:GetRole", "iam:ListAttachedRolePolicies", "iam:ListRolePolicies"
      ]
    }
  ]
}
```

Plus the Kubernetes reads under `# C1` and `# C2` in the ClusterRole below (pods, nodes, deployments, service accounts, role and cluster role bindings, pod logs, events, CRDs) and the `amazon-vpc-cni` ConfigMap in `kube-system`. Checking whether an exposure was exploited is not covered yet: https://github.com/aws-samples/sample-apex-skills/issues/351

## C3: posture check

`posture_collect.sh` (adapted from eks-well-architected-review's collector, security pillar only) and `posture_extra.sh` read only what `posture_collect.sh` collected, and its preflight probes each of these actions before the run:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EksSecurityC3Posture",
      "Effect": "Allow",
      "Resource": "*",
      "Action": [
        "sts:GetCallerIdentity",
        "eks:DescribeCluster", "eks:ListAddons", "eks:DescribeAddon", "eks:ListPodIdentityAssociations",
        "eks:ListAccessEntries", "eks:ListAssociatedAccessPolicies",
        "iam:ListOpenIDConnectProviders",
        "ec2:DescribeInstances", "ec2:DescribeVolumes", "ec2:DescribeSecurityGroups",
        "ecr:DescribeRepositories", "ecr:GetRegistryScanningConfiguration",
        "guardduty:ListDetectors", "guardduty:GetDetector"
      ]
    }
  ]
}
```

GuardDuty is read for its configuration only (is EKS protection on), never for findings. The two access-entry reads list which principals hold cluster admin through an access policy (SEC-POSTURE-64); without them that check is `unknown`. On the Kubernetes side C3 uses `get` and `auth can-i`, plus two named ConfigMaps in `kube-system`: `aws-auth` and `amazon-vpc-cni`.

## Kubernetes: read-only ClusterRole

The built-in `view` ClusterRole does not cover `nodes`, cluster-scoped RBAC objects or the Auto Mode objects, and AWS documents that `AmazonEKSAdminViewPolicy` also grants read on Secrets. This role grants neither Secrets nor write. One role covers all three capabilities; trim it to the two rules under `# C1` if that is all you run.

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
  # C2: logs, events and the policy-engine check (pods/log can carry credentials a process printed)
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["get", "list"]
  - apiGroups: ["apiextensions.k8s.io"]
    resources: ["customresourcedefinitions"]
    verbs: ["get", "list"]
  # C3: storage, admission webhooks, ingresses and Gatekeeper constraints
  - apiGroups: [""]
    resources: ["persistentvolumes"]
    verbs: ["get", "list"]
  - apiGroups: ["storage.k8s.io"]
    resources: ["storageclasses"]
    verbs: ["get", "list"]
  - apiGroups: ["admissionregistration.k8s.io"]
    resources: ["validatingwebhookconfigurations", "mutatingwebhookconfigurations"]
    verbs: ["get", "list"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses"]
    verbs: ["get", "list"]
  - apiGroups: ["constraints.gatekeeper.sh"]
    resources: ["*"]
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

Rules for API groups that are not installed (Kyverno, Gatekeeper, Auto Mode objects) are harmless. The role above is the full read set. Each collector's preflight confirms its own reads; the C2 reads and the optional policy-engine and Auto Mode objects have no preflight.

## Binding it with an EKS access entry

Run once by the team, not by the skill. The cluster's authentication mode must be `API` or `API_AND_CONFIG_MAP`.

```bash
aws eks create-access-entry --cluster-name <CLUSTER> --region <REGION> \
  --principal-arn arn:aws:iam::<ACCOUNT>:role/<review-role> \
  --type STANDARD --kubernetes-groups eks-security-readers

kubectl apply -f eks-security-reader.yaml   # the ClusterRole and Role above

kubectl create clusterrolebinding eks-security-reader \
  --clusterrole=eks-security-reader --group=eks-security-readers
kubectl create rolebinding eks-security-reader-configmaps -n kube-system \
  --role=eks-security-reader-configmaps --group=eks-security-readers
```

No access policy is associated with the entry: authorization comes only from the RBAC above ([Create an access entry using Kubernetes groups](https://docs.aws.amazon.com/eks/latest/userguide/create-k8s-group-access-entry.html)). Then confirm with `collect.sh --preflight-only`.

## What it never does

- No Create, Update, Delete, Put, Tag or Untag action on any AWS service.
- No `eks:AccessKubernetesApi`: that is for the console's resources view, not `kubectl`.
- No read of Secret data (`secrets` get or list), no `pods/exec`, `pods/attach`, `pods/portforward` or `nodes/proxy`.
- No `kubectl apply`, `patch`, `delete`, `scale`, `cordon`, `drain` or `label` against the cluster. Every remediation is printed for the team to review and run.
- No call to the internet except `advisory_fetch.py`, HTTPS GET only, to the hosts in `components.json`.
- The work dir holds pod specs, which can include literal environment values: treat it as sensitive, keep it out of version control and delete it when done.
