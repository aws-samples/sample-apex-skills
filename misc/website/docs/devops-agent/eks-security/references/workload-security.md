---
title: "Layer 3: Workload Security (Pod Security + Network)"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-security/references/workload-security.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-security/references/workload-security.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-security/references/workload-security.md). Edit the source, not this page.
:::

# Layer 3: Workload Security (Pod Security + Network)

Two compounding concerns: **pod security posture** (what a pod is allowed to do) and **network policy** (what a pod is allowed to talk to).

## Pod security: three layers that compound

```text
3a: Pod Security Admission (PSA, Kubernetes-native)
     restricted profile   → MOST WORKLOADS (default for new namespaces)
     baseline profile     → workloads needing limited extra privileges
     privileged profile   → AVOID; only system / kube-system

3b: Custom policy engine (choose ONE)
     Kyverno              → Kubernetes-native, no Rego DSL; preferred for new adoption
     OPA Gatekeeper       → Rego-based; for teams with existing OPA/Rego expertise

3c: Image admission control (a sub-rule of 3b)
     Kyverno verifyImages → block unsigned / high-severity images at admission
```

- **PSA `restricted`** is the default recommendation for production namespaces. Roll out in **`audit` mode first**, confirm no workloads break, then switch to **`enforce`**.
- **Kyverno** is preferred for new adoption (Kubernetes-native YAML policies, no Rego). **OPA Gatekeeper** suits teams already invested in Rego/OPA. Both are CNCF.
- **Run the policy webhook highly available.** A webhook whose `failurePolicy` is `Fail` (the Kubernetes default, and the default for Kyverno policies) rejects every request it matches while its pods are unreachable, so one down Kyverno pod can block new pods that its policies match. Kyverno's default install runs a single replica per Deployment; for HA set `admissionController.replicas=3` (Kyverno's own example). Its Helm chart then always enables a PodDisruptionBudget (on whenever replicas > 1) and leaves `kube-system` out of its webhooks by default. The OPA Gatekeeper chart defaults its validating webhook to `Ignore`: a down Gatekeeper admits requests unchecked, so choose fail-open or fail-closed on purpose. References: [Admission webhook failure policy](https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/) · [Kyverno HA install](https://kyverno.io/docs/installation/methods/) · [Kyverno policy settings](https://kyverno.io/docs/policy-types/cluster-policy/policy-settings/) · [Kyverno chart values](https://github.com/kyverno/kyverno/blob/main/charts/kyverno/values.yaml) · [Gatekeeper chart values](https://github.com/open-policy-agent/gatekeeper/blob/master/charts/gatekeeper/values.yaml).
- **PodSecurityPolicy (PSP) was removed in Kubernetes 1.25+**: clusters on 1.25+ have no PSP. PSA + Kyverno/OPA is the canonical replacement. Do not recommend PSP.

References: [Pod Security Admission (Kubernetes)](https://kubernetes.io/docs/concepts/security/pod-security-admission/) · [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/) · [aws/aws-eks-best-practices OPA policies](https://github.com/aws/aws-eks-best-practices/tree/master/policies/opa) · [Kyverno policy library](https://kyverno.io/policies/).

## Network policy on EKS: VPC CNI is now native

- **VPC CNI native NetworkPolicy**: the AWS VPC CNI enforces standard Kubernetes `NetworkPolicy` without a third-party CNI. Default-deny on production namespaces, then allowlist required ingress/egress. Reference: [Limit pod traffic with Kubernetes network policies](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy.html).
  - **Pod Identity egress carve-out.** Pods that use EKS Pod Identity get credentials from the node's Pod Identity Agent on the link-local address `169.254.170.23` (IPv4) or `[fd00:ec2::23]` (IPv6); EKS sets `AWS_CONTAINER_CREDENTIALS_FULL_URI` to `http://169.254.170.23/v1/credentials`. A default-deny egress policy must allow `169.254.170.23/32` and `fd00:ec2::23/128` (TCP 80) so those pods can still reach their credentials. Pods behind a proxy also need both addresses in `NO_PROXY`. References: [EKS Pod Identity considerations](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html) · [How EKS Pod Identity works](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-how-it-works.html).
- **Enhanced capabilities (current versions matter).** EKS added **cluster-wide enforcement** via **ClusterNetworkPolicy** and **FQDN-based egress policies** (filter egress to cluster-external destinations by domain name). Availability specifics, framed precisely: the **VPC CNI v1.21 managed add-on with these features is offered for Kubernetes 1.29+** (a practical packaging constraint, not a hard API gate, the base NetworkPolicy [prerequisites](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy-configure.html) still list 1.26.7/1.27.4); use **VPC CNI v1.21.0+** for these features, and check the installed version against open advisories with [cve-advisory-review.md](cve-advisory-review) rather than a version pinned here; **ClusterNetworkPolicy** works in all cluster launch modes, while **DNS/FQDN-based policies are supported only on EKS Auto Mode-launched EC2 instances**. References: [Enhanced network security policies (Dec 2025)](https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-eks-enhanced-network-security-policies/) · [Enhanced network policy capabilities](https://aws.amazon.com/blogs/containers/amazon-eks-introduces-enhanced-network-policy-capabilities) · [DNS and Admin Network Policies](https://aws.amazon.com/blogs/containers/enhance-amazon-eks-network-security-posture-with-dns-and-admin-network-policies).
  - **CRD specifics.** Both CRDs live in apiGroup **`networking.k8s.aws/v1alpha1`** (alpha, AWS's own group, not upstream `policy.networking.k8s.io`) on VPC CNI v1.21.1+ (Kubernetes 1.29+ is the Auto Mode / new-cluster rollout floor, not a `ClusterNetworkPolicy` gate). **`ClusterNetworkPolicy`** is cluster-scoped with a `tier: Admin | Baseline` field (the Admin tier is evaluated first and cannot be overridden by namespace policies; Baseline is an overridable default). **`ApplicationNetworkPolicy`** is a namespaced EKS Auto Mode CRD that supports all standard `NetworkPolicy` fields and adds an FQDN-based egress filter; the FQDN egress applies only on Auto Mode nodes. Egress policies must allow TCP and UDP port 53 to the CoreDNS service IP or DNS and FQDN filtering breaks. See `security-runtime-network.md` for detail.
- **EKS Auto Mode** supports NetworkPolicy out of the box. Reference: [Network policies with EKS Auto Mode](https://docs.aws.amazon.com/eks/latest/userguide/auto-net-pol.html).
- **Cilium CNI**: **not supported on EKS Auto Mode** (Auto Mode supports no alternate CNI or network-policy plugins, [checked 2026-11-05](https://docs.aws.amazon.com/eks/latest/userguide/alternate-cni-plugins.html)); available on self-managed / managed node groups for advanced features (eBPF, Hubble, Cluster Mesh).

## Security Groups for Pods (SGP)

For compliance workloads needing **network-layer isolation between pods** (e.g., PHI-handling pods isolated from non-PHI pods in the same cluster), attach VPC Security Groups at pod granularity via the VPC CNI trunk/branch-ENI feature. Reference: [Leveraging CNI custom networking alongside Security Groups for Pods](https://aws.amazon.com/blogs/containers/leveraging-cni-custom-networking-alongside-security-groups-for-pods-in-amazon-eks).

> **SGP limitations, material for a compliance design (don't promise isolation it doesn't deliver).** Per [Security groups for Pods](https://docs.aws.amazon.com/eks/latest/userguide/security-groups-for-pods.html):
> - **Not supported on EKS Auto Mode or Windows nodes** (hard exclusion): if you need pod-SG isolation, you can't be on Auto Mode.
> - **Same-node traffic:** in `standard` mode, pod SG rules are **not applied** to traffic between pods on the *same node*; the default `strict` mode does apply them but routes all pod traffic through the VPC, which breaks NodeLocal DNSCache and `externalTrafficPolicy=Local`.
> - No `t`-family instance support; trunk/branch ENIs reduce pod density per node.
> Combine SGP with Kubernetes NetworkPolicy (default-deny) rather than treating SGP alone as the isolation boundary.

In a security event, isolate the suspect pods with a pod-scoped NetworkPolicy by label, not a namespace deny-all: see [security-event-response.md](security-event-response) step 3.

## Service-mesh mTLS (east-west encryption in transit)

For **intra-cluster pod-to-pod mTLS**, use a service mesh, **Istio** (sidecar mode), **Linkerd**, or **Cilium Service Mesh**, all run on EKS and issue/rotate workload certificates for east-west traffic.

> **Don't position VPC Lattice as an mTLS mesh, it isn't one.** VPC Lattice provides **cross-VPC / cross-cluster service connectivity with IAM-based authentication (SigV4)**, not certificate-based mTLS between pods. Use it for secure *cross-boundary* service-to-service connectivity; use a service mesh (Istio/Linkerd/Cilium) for *intra-cluster* mTLS. References: [VPC Lattice integration](https://docs.aws.amazon.com/eks/latest/userguide/integration-vpc-lattice.html) · [VPC Lattice SigV4 auth](https://docs.aws.amazon.com/vpc-lattice/latest/ug/sigv4-authenticated-requests.html).

> **Gotcha:** **AWS App Mesh reached end of support on September 30, 2026**: after that date the console and App Mesh resources are no longer accessible (checked 2026-11-05 on the notice page). Do not recommend App Mesh; migrate existing meshes and use Istio/Linkerd/Cilium mesh or VPC Lattice. Reference: [AWS App Mesh end-of-support notice](https://docs.aws.amazon.com/app-mesh/latest/userguide/what-is-app-mesh.html).

## Shared responsibility (Layer 3)

| AWS manages | Customer manages |
|---|---|
| VPC CNI + NetworkPolicy enforcement engine; PSA controller (built into the managed control plane); SGP trunk/branch ENI plumbing | PSA profile labels per namespace; Kyverno/OPA policy authoring + rollout; NetworkPolicy rules (default-deny + allowlists); SGP assignment; service-mesh deployment + mTLS config |

## Sources
- [Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/) · [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/) · [Kyverno policies](https://kyverno.io/policies/) · [aws-eks-best-practices OPA policies](https://github.com/aws/aws-eks-best-practices/tree/master/policies/opa)
- [VPC CNI NetworkPolicy](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy.html) · [Enhanced network policy capabilities](https://aws.amazon.com/blogs/containers/amazon-eks-introduces-enhanced-network-policy-capabilities) · [DNS & Admin Network Policies](https://aws.amazon.com/blogs/containers/enhance-amazon-eks-network-security-posture-with-dns-and-admin-network-policies) · [NetworkPolicy on Auto Mode](https://docs.aws.amazon.com/eks/latest/userguide/auto-net-pol.html)
- [Security Groups for Pods](https://aws.amazon.com/blogs/containers/leveraging-cni-custom-networking-alongside-security-groups-for-pods-in-amazon-eks) · [VPC Lattice integration](https://docs.aws.amazon.com/eks/latest/userguide/integration-vpc-lattice.html) · [App Mesh EOS notice](https://docs.aws.amazon.com/app-mesh/latest/userguide/what-is-app-mesh.html)
