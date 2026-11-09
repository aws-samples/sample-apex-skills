# EKS Runtime & Network Security

> **Part of:** [eks-best-practices](../SKILL.md)
> **Purpose:** Runtime threat detection, network policy enforcement, security groups for pods, and encryption in transit

**For core IAM, pod security, and secrets, see:** [Security](security.md)
**For supply chain, infrastructure, and compliance, see:** [Supply Chain & Compliance](security-supply-chain.md)

---

## Table of Contents

1. [Runtime Security](#runtime-security)
2. [Network Security](#network-security)
3. [Encryption in Transit](#encryption-in-transit)
4. [Detective Controls](#detective-controls)

---

## Runtime Security

### Amazon GuardDuty for EKS

**Enable Runtime Monitoring** as the first line of defense. GuardDuty's EKS protection is now delivered through the unified **Runtime Monitoring** feature (the separate "EKS Runtime Monitoring" console path has been removed (as of 2026-08-05, per the GuardDuty User Guide); AWS recommends migrating to unified Runtime Monitoring). GuardDuty combines two complementary sources of signal:

- **EKS Protection (audit-log analysis)** — analyzes K8s control-plane audit logs for threats; no agent required.
- **Runtime Monitoring (agent-based)** — the GuardDuty security agent observes container-level runtime behavior (process, file, and network activity) on your nodes.

These are distinct data sources — audit-log analysis and the runtime agent — so keep them conceptually separate rather than conflating them. GuardDuty applies ML and threat intelligence across both to detect threats without manual rule configuration.

**Key runtime finding types:**
- `CryptoCurrency:Runtime/BitcoinTool.B`
- `Impact:Runtime/CryptoMinerExecuted`
- `PrivilegeEscalation:Runtime/DockerSocketAccessed`
- `Execution:Runtime/ReverseShell`

GuardDuty produces security findings viewable in the console or via EventBridge for automated response.

### Seccomp Profiles

Seccomp (secure computing) restricts which system calls a container can make, reducing the attack surface. Containers only need a fraction of the hundreds of available syscalls.

**Use RuntimeDefault as the baseline for all workloads:**

```yaml
securityContext:
  seccompProfile:
    type: RuntimeDefault
```

As of Kubernetes 1.27 (stable), you can set `RuntimeDefault` for all pods on a node using the kubelet flag `--seccomp-default`, then only override in `securityContext` for workloads needing custom profiles.

**Custom profiles** can be generated using:
- **Inspektor Gadget** — uses eBPF to record baseline syscall usage and generate seccomp profiles
- **Security Profiles Operator** — automates deploying and managing seccomp, AppArmor, and SELinux profiles across nodes

Consider adding/dropping Linux capabilities before writing seccomp policies — capabilities are coarser but simpler. Seccomp filters all syscalls before they run, while capabilities check permissions in specific kernel functions.

### AppArmor and SELinux

Both provide mandatory access control (MAC) beyond what capabilities and seccomp offer:

| Feature | AppArmor | SELinux |
|---------|----------|---------|
| **Supported on** | Debian, Ubuntu | RHEL, CentOS, Bottlerocket, Amazon Linux 2023 |
| **K8s integration** | Via annotations (pre-1.30), security context (1.30+) | Via `seLinuxOptions` in security context |
| **Granularity** | File path, network, capabilities | Labels on files/processes/ports |

**SELinux on EKS:**
- Containers use the `container_t` label, isolating them from each other
- Configure via `securityContext.seLinuxOptions` in pod spec:

```yaml
securityContext:
  seLinuxOptions:
    level: s0:c144:c154  # Unique MCS label per container
```

Bottlerocket has SELinux enabled by default, providing an additional isolation layer.

### Falco for Runtime Threat Detection

**Chart version:** `<chart-version>` is a placeholder. Ask the user whether to pin the chart or take the newest release. To pin, look up the chart's current version live (the chart's Artifact Hub page or releases page, or `helm search repo <chart> --versions` for repo charts) and use it; for the newest, drop `--version`. If the lookup fails, say so plainly and never guess a version.

```bash
# Deploy Falco as a DaemonSet via Helm
helm repo add falcosecurity https://falcosecurity.github.io/charts
helm install falco falcosecurity/falco --version <chart-version> \
  --namespace falco --create-namespace \
  --set driver.kind=modern_ebpf \
  --set falcosidekick.enabled=true
```

**Key detection rules for EKS:**
- Container drift detection (unexpected process execution)
- Sensitive file access (/etc/shadow, /etc/kubernetes)
- Outbound connections to suspicious IPs
- Shell spawned in container

---

## Network Security

### Network Policies

**Use EKS-native VPC CNI network policies (use VPC CNI v1.22.3+, see below):**

```yaml
# Enable network policy support in VPC CNI
# NOTE: pick a current v1.22.3 or later build from
# `aws eks describe-addon-versions --addon-name vpc-cni`; do not pin a build here.
aws eks create-addon --cluster-name my-cluster \
  --addon-name vpc-cni \
  --addon-version <v1.22.3-or-later-build> \
  --configuration-values '{"enableNetworkPolicy": "true"}'
```

Network policy support is NOT enabled by default — you must enable the `ENABLE_NETWORK_POLICY` flag on the VPC CNI add-on.

Beyond the standard namespaced `NetworkPolicy` API, EKS adds two AWS-native CRDs in the `networking.k8s.aws/v1alpha1` API group (alpha, AWS's own group, not upstream `policy.networking.k8s.io`). `ClusterNetworkPolicy` is supported from VPC CNI v1.21.0 ([EKS User Guide](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy.html)). Use VPC CNI **v1.22.3+** wherever the VPC CNI enforces network policy (standard `NetworkPolicy` and `ClusterNetworkPolicy` alike): earlier releases ship a Network Policy Agent below 1.3.7, which [AWS security bulletin 2026-170](https://aws.amazon.com/security/security-bulletins/2026-170-aws/) lists as affected ("This issue has been addressed in aws-network-policy-agent versions 1.3.7 and amazon-vpc-cni-k8s version 1.22.3"). The managed add-on at v1.22.3 is offered for Kubernetes 1.30+ (`aws eks describe-addon-versions --addon-name vpc-cni`, as of 2026-11-09), so a 1.29 cluster cannot run the fixed release as a managed add-on. Read the release notes before a version change: with Network Policy on, a downgrade below v1.22.4 leaves policy unenforced on pods created before the rollback until their nodes are replaced ([v1.22.4 notes](https://github.com/aws/amazon-vpc-cni-k8s/releases/tag/v1.22.4)). SageMaker HyperPod on EKS needs v1.22.4 or later, since v1.22.0 to v1.22.3 have an Enhanced Subnet Discovery issue there ([v1.22.3 notes](https://github.com/aws/amazon-vpc-cni-k8s/releases/tag/v1.22.3)).

- **`ClusterNetworkPolicy`**: cluster-scoped, with a `tier: Admin | Baseline` field. The **Admin** tier is evaluated first and **cannot** be overridden by namespace-scoped policies; it supports explicit **Deny / Allow / Pass** actions (a Deny or Allow is terminal; Pass delegates the decision to lower tiers). The **Baseline** tier is an overridable default posture evaluated after `NetworkPolicy`, so a namespace owner's policy can override it. Available in all EKS cluster launch modes.
- **`ApplicationNetworkPolicy`**: namespaced, documented by AWS as an **EKS Auto Mode** CRD. It supports all fields of the standard Kubernetes `NetworkPolicy` and adds an **FQDN-based egress** filter (allowlist egress by domain name). Per AWS, the DNS/FQDN egress rules are **only applicable to workloads on EKS Auto Mode-launched EC2 instances**; whether an FQDN rule authored on a non-Auto-Mode node is accepted-but-ignored or rejected is not documented, so verify by testing real egress rather than assuming enforcement.

**Evaluation order:** Admin tier first (Deny > Allow > Pass; a Deny or Allow is terminal, only a Pass or no-match proceeds), then `NetworkPolicy` / `ApplicationNetworkPolicy` (which can further restrict but cannot override an Admin Deny), then the Baseline tier (overridable defaults), then default-deny if nothing matches.

Enforcement runs on the VPC CNI eBPF network-policy controller (`enable-network-policy-controller: "true"`, the network-policy-controller config key, distinct from the `ENABLE_NETWORK_POLICY` add-on flag) and applies to **EC2 Linux nodes only** (not Fargate or Windows). Egress policies must still allow TCP and UDP port 53 to CoreDNS (see Step 2 below) or DNS and FQDN filtering will break. Naming gotcha: an `ApplicationNetworkPolicy` and a `NetworkPolicy` sharing the same name in one namespace breaks `PolicyEndpoints` (both are accepted without error, so it is hard to diagnose). Check your installed VPC CNI version before relying on either CRD.

### Start with Default Deny + DNS Allow

**Step 1: Default deny all traffic per namespace:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: production
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
```

**Step 2: Allow DNS queries to CoreDNS (required after default deny):**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-access
  namespace: production
spec:
  podSelector:
    matchLabels: {}
  policyTypes:
  - Egress
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kube-system
      podSelector:
        matchLabels:
          k8s-app: kube-dns
    ports:
    - protocol: UDP
      port: 53
```

**Step 3: Incrementally allow specific traffic:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-backend
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: frontend
    ports:
    - protocol: TCP
      port: 8080
```

### Security Groups for Pods

Use when you need AWS-level network isolation (NACLs, VPC Flow Logs per pod):

```yaml
apiVersion: vpcresources.k8s.aws/v1beta1
kind: SecurityGroupPolicy
metadata:
  name: app-sgp
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: database-client
  securityGroups:
    groupIds:
    - sg-0123456789abcdef0  # Allow access to RDS
```

**Important SG for Pods requirements:**
- You **must** create SG rules allowing port 53 outbound to the cluster SG (DNS)
- You **must** update the cluster SG to accept port 53 inbound from the pod SG
- You **must** create rules for inbound traffic from the cluster SG for all health probes
- SG for pods uses ENI trunking — the number of branch ENIs varies by instance type

### Network Policy vs SG for Pods Decision

| Use Case | Network Policy | SG for Pods |
|----------|---------------|-------------|
| **Pod-to-pod traffic** (east-west) | Primary tool | Not designed for this |
| **Pod-to-AWS-service** (RDS, ElastiCache) | Cannot target AWS resources | Primary tool |
| **Reuse existing SG rules** | No | Yes — reuse EC2 SGs |
| **Isolate pod from node traffic** | No | Yes (`strict` mode) |
| **Overhead** | Low (eBPF-based) | Higher (ENI trunking) |

**Best practice: Use both as layers.** Network policies for pod-to-pod isolation, SG for Pods for AWS service-level isolation.

### AWS Network Firewall Container Rules

AWS Network Firewall can match traffic by pod. A **container association** subscribes to the cluster's pod start and stop events and keeps the matching pod IPs as a dynamic IP set; a stateful rule group references that set as an IPSet variable, so egress rules target "these pods" without fixed IPs. It collects only IP information from those events and has no part in the cluster's data path: the firewall endpoints in your VPC do the inspection. For EKS, attribute filters select pods by namespace and Kubernetes labels; one association holds up to 5 monitoring configurations, each naming one cluster in the same account and Region as the association.

| | `NetworkPolicy` | `ApplicationNetworkPolicy` | Network Firewall container rules |
|---|---|---|---|
| **Where it enforces** | VPC CNI eBPF on the node (EC2 Linux nodes) | VPC CNI eBPF on the node | Firewall endpoints in the VPC route path |
| **Pod-to-pod inside the cluster** | Yes | Yes | No: same-node traffic never leaves the node, and other traffic reaches the firewall only if your route tables send it there |
| **Egress filtering by domain name** | No | Yes, on EKS Auto Mode nodes only | Yes, with stateful domain list rules on TLS SNI or HTTP Host; a pod can fake those, so also add the `AWS_ROUTE_53_RESOLVED_DOMAIN` target type, which checks that the VPC's Route 53 Resolver returned the destination IP for that domain (in an allow list with TLS SNI or HTTP Host, both checks must pass; in a deny list either one triggers the rule). It needs [resolved IP validation](https://docs.aws.amazon.com/network-firewall/latest/developerguide/route53-resolved-ip-validation.html) on the firewall policy, with a Route 53 Resolver DNS Firewall rule group associated with the VPCs, and that setting applies its action to connections whose destination IP no associated VPC resolved for any domain (pods using fixed IPs or another resolver fail it), so start it with Action ALERT (needs firewall logging on) for about 24 hours before moving to DROP or REJECT. Before adding the target type, confirm the firewall's `DnsAzUnavailableFlows` metric is zero: in an Availability Zone without the feature, resolved-domain rules drop the traffic they inspect whatever the action |
| **Managed through** | Kubernetes API | Kubernetes API | Network Firewall API (CLI, SDK or console) |

**Use them as layers.** `NetworkPolicy` and `ClusterNetworkPolicy` for traffic inside the cluster; Network Firewall container rules for inspected egress attributed to pods, including domain filtering on nodes where `ApplicationNetworkPolicy` FQDN rules do not apply.

- **SNAT off:** the firewall must see the pod's own IP. With SNAT on, traffic arrives with the node IP and rules that reference the container association do not match, so on Linux nodes in private subnets set `AWS_VPC_K8S_CNI_EXTERNALSNAT=true` and let a NAT gateway do SNAT (disabling SNAT is not supported on Windows nodes; on IPv6 clusters egress to IPv4 is SNATed to the node IP whatever the external SNAT setting, and the Network Firewall page does not cover IPv6).
- **Routing:** only traffic your route tables send through a firewall endpoint is inspected, so route the pod subnets through the firewall endpoints. With resolved IP validation on, route each pod subnet to the endpoint in its own Availability Zone: validation is scoped to the zone, so a connection that crosses zones fails it as unresolved and gets the policy's Action, unless the firewall is transit gateway-attached, which carries the client's zone ([how resolved IP validation works](https://docs.aws.amazon.com/network-firewall/latest/developerguide/route53-resolved-ip-validation-how-it-works.html)).
- **EKS Auto Mode:** the container associations page does not mention Auto Mode; confirm support with AWS before relying on it there.

For the review checklist (IAM permissions, quotas, strict-order default actions, rule-group limits and delete protection), see the eks-security skill's `references/workload-security.md`.

References: [Container associations](https://docs.aws.amazon.com/network-firewall/latest/developerguide/container-associations.html) · [How Network Firewall works](https://docs.aws.amazon.com/network-firewall/latest/developerguide/how-it-works.html) · [Outbound access for Pods (external SNAT)](https://docs.aws.amazon.com/eks/latest/userguide/external-snat.html)

### SG Enforcing Modes

| Mode | Behavior | Use When |
|------|----------|----------|
| **`standard`** | Node SG and pod SG both apply | Using both NP and SG for Pods |
| **`strict`** | Only pod SG applies, fully isolated from node | Complete pod traffic isolation |

You **must** use `standard` mode when combining Network Policy and Security Groups for Pods.

### Third-Party Network Policy Engines

Consider third-party engines when you need advanced features:

| Engine | Key Features Beyond K8s NP |
|--------|---------------------------|
| **Calico** | Global policies, layer 7 with Istio, DNS hostname rules, service account scoping |
| **Cilium** | Layer 7 (HTTP), DNS hostname rules, eBPF-native |
| **Calico Enterprise** | Map K8s NP to AWS security groups, compliance reporting |

**Migration:** If switching from Calico/Cilium to VPC CNI network policies, the [K8s Network Policy Migrator](https://github.com/awslabs/k8s-network-policy-migrator) tool can convert CRDs to native K8s NetworkPolicy resources. Note this tool has been **dormant since 2023-08** (no updates), so validate its output against current CRD schemas and always test in a separate cluster before production.

### Ensure Network Policies Exist via OPA

Use OPA/Gatekeeper to prevent pods from being created without a corresponding network policy:

```
package kubernetes.admission
import data.kubernetes.networkpolicies

deny[msg] {
    input.request.kind.kind == "Pod"
    pod_label_value := {v["k8s-app"] | v := input.request.object.metadata.labels}
    contains_label(pod_label_value, "sample-app")
    np_label_value := {v["k8s-app"] | v := networkpolicies[_].spec.podSelector.matchLabels}
    not contains_label(np_label_value, "sample-app")
    msg := sprintf("Pod %v missing an associated Network Policy.", [input.request.object.metadata.name])
}
```

### Service Mesh vs Network Policy

| Factor | Service Mesh (Istio, Linkerd) | Network Policy |
|--------|------------------------------|---------------|
| **OSI Layer** | Layer 7 (application) | Layer 3/4 (network/transport) |
| **mTLS** | Built-in | Not available |
| **Observability** | Latency, error rates, request volume | Basic allow/deny |
| **Overhead** | Sidecar per pod | Minimal (eBPF) |
| **Use when** | Need mTLS, traffic management, observability | Simpler pod-to-pod isolation |

Network policies and service mesh can be used together — NP for baseline isolation, mesh for mTLS and observability.

---

## Encryption in Transit

### Nitro Instance Automatic Encryption

Traffic between Nitro instance types (C5n, G4, I3en, M5dn, M5n, P3dn, R5dn, R5n, etc.) is automatically encrypted by default. No configuration needed. However, traffic through intermediate hops (transit gateway, load balancer) is not encrypted by this mechanism.

### Service Mesh mTLS

For end-to-end encryption between pods:
- **Istio** — automatic mTLS between all meshed services
- **Linkerd** — automatic mTLS with minimal configuration
- **Cilium** — transparent mTLS / WireGuard-based node-to-node encryption via eBPF

> **Do not adopt AWS App Mesh.** App Mesh reaches **end of support on 2026-09-30**, after which its console and resources become inaccessible. Do not start new App Mesh mTLS deployments; migrate existing ones to Istio, Cilium mTLS, or Linkerd.

### Ingress and Load Balancer TLS

**ALB with ACM certificates:**
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  annotations:
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:region:account:certificate/cert-id
    alb.ingress.kubernetes.io/ssl-policy: ELBSecurityPolicy-TLS13-1-2-2021-06
```

**NLB with TLS termination:**
```yaml
apiVersion: v1
kind: Service
metadata:
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: external
    service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: ip
    service.beta.kubernetes.io/aws-load-balancer-ssl-cert: arn:aws:acm:region:account:certificate/cert-id
```

Where you terminate TLS depends on your security policy:
- **At the load balancer** — simplest, offloads CPU from pods
- **At the ingress controller** — more control, still centralized
- **At the pod** — end-to-end encryption, highest CPU cost

---

## Detective Controls

### Enable EKS Audit Logging

```bash
# Enable all log types
aws eks update-cluster-config \
  --name my-cluster \
  --logging '{"clusterLogging":[{"types":["api","audit","authenticator","controllerManager","scheduler"],"enabled":true}]}'
```

**Key audit log queries (CloudWatch Logs Insights):**

```
# Failed authentication attempts
fields @timestamp, @message
| filter @logStream like /kube-apiserver-audit/
| filter responseStatus.code >= 400
| sort @timestamp desc
| limit 50

# Privileged pod creation
fields @timestamp, user.username, objectRef.resource, objectRef.namespace
| filter @logStream like /kube-apiserver-audit/
| filter objectRef.resource = "pods" and verb = "create"
| filter requestObject.spec.containers.0.securityContext.privileged = true
```

### Amazon GuardDuty for EKS

Enable both:
- **EKS Audit Log Monitoring** — analyzes K8s audit logs for threats
- **EKS Runtime Monitoring** — detects container-level threats via agent

### AWS CloudTrail for EKS API Calls

All EKS API calls (`eks:*`) are logged in CloudTrail. Monitor for:
- `CreateCluster`, `DeleteCluster` events
- `UpdateClusterConfig` changes
- `CreateAccessEntry` for unauthorized access grants

### VPC Flow Logs

Enable VPC Flow Logs to capture metadata about traffic flowing through the VPC. Useful for detecting suspicious pod-to-pod communication, but pod IPs change frequently — combine with pod labels from Calico Enterprise or similar tools for better correlation.

### Monitoring Network Policy Enforcement

- Scrape Prometheus metrics from VPC CNI node agents for agent health and SDK errors
- Review audit logs for unauthorized network policy changes
- Implement automated testing to verify policies in a mirror environment
- Periodically audit policies to remove redundant rules as applications evolve

---

**Sources:**
- [AWS EKS Best Practices Guide — Runtime Security](https://docs.aws.amazon.com/eks/latest/best-practices/runtime-security.html)
- [AWS EKS Best Practices Guide — Network Security](https://docs.aws.amazon.com/eks/latest/best-practices/network-security.html)
- [AWS EKS Best Practices Guide — Detective Controls](https://docs.aws.amazon.com/eks/latest/best-practices/detective-controls.html)
