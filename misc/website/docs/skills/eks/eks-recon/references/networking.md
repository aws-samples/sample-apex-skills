---
title: "Module: Networking"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/networking.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-recon/references/networking.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/networking.md). Edit the source, not this page.
:::

# Module: Networking

> **Part of:** [eks-recon](../)
> **Purpose:** Detect network configuration - VPC identifiers, VPC CNI, subnets, ingress controllers, load balancers, service mesh, DNS, network policies, endpoint access

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [1. VPC Identifiers & Endpoint Access](#1-vpc-identifiers--endpoint-access)
  - [2. Subnets & IP Address Availability](#2-subnets--ip-address-availability)
  - [3. CNI Vendor & VPC CNI Configuration](#3-cni-vendor--vpc-cni-configuration)
  - [3a. kube-proxy Mode](#3a-kube-proxy-mode)
  - [4. Ingress Controllers & Gateway API](#4-ingress-controllers--gateway-api)
  - [5. Load Balancers](#5-load-balancers)
  - [6. Service Mesh Detection](#6-service-mesh-detection)
  - [7. DNS Configuration](#7-dns-configuration)
  - [8. Network Policies](#8-network-policies)
  - [9. external-dns](#9-external-dns)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Prerequisites

- **Cluster name required:** Yes
- **MCP tools used:** `describe_eks_resource`, `get_eks_vpc_config`, `list_k8s_resources`
- **CLI fallback:** `aws eks`, `aws ec2`, `aws elbv2`, `kubectl`

---

## Detection Strategy

Network configuration spans multiple layers:

```
1. VPC identifiers & endpoint access -> Which VPC, subnets, SGs; how the API server is reached
2. Subnets & IP availability          -> Per-subnet free IPs, secondary CIDRs
3. CNI vendor & VPC CNI config         -> Pod networking vendor, mode, env vars
4. Ingress & Gateway API               -> How external traffic enters the cluster
5. Load balancers                      -> Provisioned ELBs and target group bindings
6. Service mesh                        -> Service-to-service communication
7. DNS                                 -> CoreDNS + NodeLocal DNSCache
8. Network policies                    -> Pod-to-pod traffic control
9. external-dns                        -> DNS record automation
```

---

## Detection Commands

### 1. VPC Identifiers & Endpoint Access

**Why check this:** The VPC id, subnet ids, and security groups anchor every other network
fact to concrete AWS resources. Endpoint access (public/private) describes how the API
server is reached. `ipFamily` and `serviceIpv4Cidr` describe the cluster address space.

**MCP:**
```
describe_eks_resource(
  resource_type="cluster",
  cluster_name="<cluster-name>"
)
-> Read cluster.resourcesVpcConfig and cluster.kubernetesNetworkConfig
```

```
get_eks_vpc_config(
  cluster_name="<cluster-name>"
)
```

**CLI:**
```bash
# VPC id, subnet ids, security groups, endpoint access (all from resourcesVpcConfig)
aws eks describe-cluster --name <cluster-name> --region <region> \
  --query 'cluster.resourcesVpcConfig.{
    vpcId:vpcId,
    subnetIds:subnetIds,
    clusterSecurityGroupId:clusterSecurityGroupId,
    securityGroupIds:securityGroupIds,
    endpointPublicAccess:endpointPublicAccess,
    endpointPrivateAccess:endpointPrivateAccess,
    publicAccessCidrs:publicAccessCidrs
  }'

# IP family (ipv4 | ipv6) and service CIDR
aws eks describe-cluster --name <cluster-name> --region <region> \
  --query 'cluster.kubernetesNetworkConfig.{
    ipFamily:ipFamily,
    serviceIpv4Cidr:serviceIpv4Cidr
  }'
```

- `vpc_id` = `cluster.resourcesVpcConfig.vpcId`.
- `subnet_ids` = `cluster.resourcesVpcConfig.subnetIds` (also the input for the per-subnet detection below).
- `cluster_security_group_id` = `clusterSecurityGroupId` (the EKS-managed primary SG).
- `security_groups` = `securityGroupIds` (additional SGs attached to the control plane ENIs; count+list).
- `endpoint_access.public` / `endpoint_access.private` = the two `endpoint*Access` booleans.
- `endpoint_access.public_cidrs` = `publicAccessCidrs` (`0.0.0.0/0` when open to all).
- `ip_family` = `cluster.kubernetesNetworkConfig.ipFamily` (`ipv4` | `ipv6`).
- `service_cidr` = `cluster.kubernetesNetworkConfig.serviceIpv4Cidr`.

**Example output:**
```json
{
  "vpcId": "vpc-0abc123",
  "subnetIds": ["subnet-0aaa111", "subnet-0bbb222"],
  "clusterSecurityGroupId": "sg-0cluster99",
  "securityGroupIds": ["sg-0extra11"],
  "endpointPublicAccess": true,
  "endpointPrivateAccess": true,
  "publicAccessCidrs": ["0.0.0.0/0"]
}
```

### 2. Subnets & IP Address Availability

**Why check this:** Per-subnet free-IP counts are the raw facts behind pod IP capacity.
Secondary VPC CIDRs indicate an expanded address space (often used with custom networking).

**CLI:**
```bash
# Per-subnet id, AZ, CIDR, and free IP count — subnet ids come from
# cluster.resourcesVpcConfig.subnetIds (detection 1)
aws ec2 describe-subnets --subnet-ids <ids> --region <region> \
  --query 'Subnets[].{id:SubnetId,az:AvailabilityZone,cidr:CidrBlock,free:AvailableIpAddressCount}'

# Secondary (additional) VPC CIDR blocks. NOTE: CidrBlockAssociationSet INCLUDES the primary
# CIDR — filter it out. The primary is Vpcs[0].CidrBlock. This query returns only association-set
# CIDRs that are not equal to the primary; empty result => no secondary CIDR.
aws ec2 describe-vpcs --vpc-ids <vpc-id> --region <region> \
  --query 'Vpcs[0].CidrBlockAssociationSet[?CidrBlock!=`'"$(aws ec2 describe-vpcs --vpc-ids <vpc-id> --region <region> --query 'Vpcs[0].CidrBlock' --output text)"'`].CidrBlock'
```

- `subnets` = count+list of `{id, az, cidr, free}`; `free` = `AvailableIpAddressCount`.
- `vpc_secondary_cidrs` = the CIDR association set **minus the primary** (`Vpcs[0].CidrBlock`).
  The raw `CidrBlockAssociationSet` includes the primary, so a VPC with no secondary CIDR would
  otherwise falsely report its primary; exclude the primary so an empty list means no secondary.

**Example output:**
```json
[
  {"id": "subnet-0aaa111", "az": "us-west-2a", "cidr": "10.0.1.0/24", "free": 210},
  {"id": "subnet-0bbb222", "az": "us-west-2b", "cidr": "10.0.2.0/24", "free": 187}
]
```

### 3. CNI Vendor & VPC CNI Configuration

**Why check this:** The primary CNI vendor determines pod networking behavior. VPC CNI mode
directly impacts pod IP capacity — prefix delegation can increase pods-per-node from ~29 to
~110 on m5.large. Custom networking is used when pod subnets differ from node subnets. The
IP-target env vars govern warm-pool sizing.

**Primary CNI vendor detection:** Determine `cni.type` from installed resources, do not assume:
```bash
# aws-vpc-cni: the aws-node DaemonSet is present
kubectl get daemonset aws-node -n kube-system 2>/dev/null

# calico: calico-node DaemonSet / CRDs
kubectl get daemonset -n kube-system calico-node 2>/dev/null
kubectl get crd 2>/dev/null | grep -i projectcalico.org

# cilium: cilium DaemonSet / CRDs
kubectl get daemonset -n kube-system cilium 2>/dev/null
kubectl get crd 2>/dev/null | grep -i cilium.io
```

- `cni.type` = `aws-vpc-cni` (aws-node present) | `calico` | `cilium` | `other`.
- **Auto Mode:** Auto Mode clusters have **no `aws-node` DaemonSet** — the CNI is managed by
  EKS. Treat the absence of `aws-node` on an Auto Mode cluster as `cni.type: auto-mode`, **not**
  as "no CNI". `aws eks describe-addon --addon-name vpc-cni` returning `ResourceNotFound` on
  Auto Mode is expected, not an error. (Detect Auto Mode via `cluster.computeConfig.enabled`.)

**MCP (VPC CNI addon):**
```
describe_eks_resource(
  resource_type="addon",
  cluster_name="<cluster-name>",
  resource_name="vpc-cni"
)
```

**CLI (VPC CNI addon status + version):**
```bash
aws eks describe-addon --cluster-name <cluster-name> --region <region> --addon-name vpc-cni \
  --query 'addon.{version:addonVersion,status:status,config:configurationValues}' 2>/dev/null
```

**VPC CNI mode + env vars (from the aws-node DaemonSet):**
```bash
# All AWS_/ENABLE_/WARM_/MINIMUM_ env vars in one map
kubectl get daemonset aws-node -n kube-system -o json 2>/dev/null | jq -r '
  .spec.template.spec.containers[0].env |
  map(select(.name | startswith("AWS_") or startswith("ENABLE_")
             or startswith("WARM_") or startswith("MINIMUM_"))) |
  from_entries'

# Prefix delegation
kubectl get daemonset aws-node -n kube-system -o json 2>/dev/null | \
  jq -r '.spec.template.spec.containers[0].env[] | select(.name=="ENABLE_PREFIX_DELEGATION") | .value'

# Security groups for pods
kubectl get daemonset aws-node -n kube-system -o json 2>/dev/null | \
  jq -r '.spec.template.spec.containers[0].env[] | select(.name=="ENABLE_POD_ENI") | .value'

# Custom networking config flag
kubectl get daemonset aws-node -n kube-system -o json 2>/dev/null | \
  jq -r '.spec.template.spec.containers[0].env[] | select(.name=="AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG") | .value'

# Custom networking ENIConfig CRs
kubectl get eniconfigs.crd.k8s.amazonaws.com --no-headers 2>/dev/null | wc -l
```

**Mode determination (`cni.vpc_cni.mode`):**
- **secondary-ip** (default): `ENABLE_PREFIX_DELEGATION` unset or `false`, no ENIConfigs.
- **prefix-delegation**: `ENABLE_PREFIX_DELEGATION=true`.
- **custom-networking**: ENIConfig CRs exist (`AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG=true`).

**IP-target env vars — record verbatim as facts (no interpretation):**
- `WARM_IP_TARGET`, `MINIMUM_IP_TARGET`, `WARM_ENI_TARGET`, `WARM_PREFIX_TARGET`,
  `AWS_VPC_K8S_CNI_EXTERNALSNAT`.

**Example output (env map):**
```json
{
  "ENABLE_PREFIX_DELEGATION": "true",
  "WARM_PREFIX_TARGET": "1",
  "WARM_IP_TARGET": "5",
  "MINIMUM_IP_TARGET": "10",
  "ENABLE_POD_ENI": "false",
  "AWS_VPC_K8S_CNI_EXTERNALSNAT": "false",
  "AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG": "false"
}
```

### 3a. kube-proxy Mode

**Why check this:** kube-proxy programs Service (ClusterIP/NodePort) routing on each node. Its
`mode` is a concrete, discoverable networking fact read from the kube-proxy ConfigMap. On EKS
Auto Mode, kube-proxy may be absent entirely (EKS manages Service networking differently) —
treat absence as a fact, not an error.

**CLI:**
```bash
# kube-proxy mode from the kube-proxy ConfigMap (data map)
kubectl -n kube-system get configmap kube-proxy-config -o jsonpath='{.data}' 2>/dev/null

# Fallback ConfigMap name / full YAML — extract the mode: field
kubectl -n kube-system get cm kube-proxy -o yaml 2>/dev/null | grep -E '^\s*mode:'

# Presence — kube-proxy DaemonSet (absent on some Auto Mode clusters)
kubectl get daemonset kube-proxy -n kube-system 2>/dev/null
```

- `kube_proxy.present` = the kube-proxy DaemonSet / ConfigMap exists.
- `kube_proxy.mode` = the `mode` field from the ConfigMap. Values: `""` or `iptables`
  (both the default), `ipvs`, `nftables`. An empty string means the default (iptables) —
  record it verbatim.
- **kube-proxy absent (e.g. Auto Mode):** record `kube_proxy.present: false` and
  `kube_proxy.mode: null`. This is a fact, **not** an error.

### 4. Ingress Controllers & Gateway API

**Why check this:** Ingress controllers determine how external traffic reaches cluster
services. Multiple controllers may coexist (e.g., AWS LBC for ALB/NLB, nginx for internal
routing). Gateway API is the successor resource model and may be present alongside Ingress.

**MCP:**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="Deployment",
  api_version="apps/v1",
  namespace="kube-system"
)
```

**CLI (controllers — capture version from the container image tag):**
```bash
# AWS Load Balancer Controller (self-managed installs only). On EKS Auto Mode the ALB
# controller is EKS-managed and there is NO in-cluster aws-load-balancer-controller
# Deployment — that absence is a fact, not "no LB controller".
kubectl get deploy -n kube-system aws-load-balancer-controller -o json 2>/dev/null | \
  jq -r '.spec.template.spec.containers[0].image'

# NGINX Ingress Controller
kubectl get deploy -A -l "app.kubernetes.io/name=ingress-nginx" -o json 2>/dev/null | \
  jq -r '.items[] | {ns: .metadata.namespace, image: .spec.template.spec.containers[0].image}'

# Traefik
kubectl get deploy -A -l "app.kubernetes.io/name=traefik" -o json 2>/dev/null | \
  jq -r '.items[] | {ns: .metadata.namespace, image: .spec.template.spec.containers[0].image}'

# Kong
kubectl get deploy -A -l "app=kong" 2>/dev/null

# IngressClasses (name + controller)
kubectl get ingressclasses -o json 2>/dev/null | \
  jq -r '.items[] | {name: .metadata.name, controller: .spec.controller}'
```

- Per controller record `{name, type, namespace, version}`; `version` = the image tag.
- `type` = `aws-lb` | `nginx` | `traefik` | `kong` | `other`.
- `classes` = count+list of IngressClass names (renamed from `ingress_class`).

**CLI (Gateway API):**
```bash
# Gateway API CRDs
kubectl get crd 2>/dev/null | grep -E "gateways|httproutes|grpcroutes"

# Gateway resources
kubectl get gateways.gateway.networking.k8s.io -A --no-headers 2>/dev/null | wc -l
```

- `gateway_api.detected` = Gateway API CRDs present.
- `gateway_api.gateways` = count of Gateway resources.

**Example output (IngressClasses):**
```json
{"name": "alb", "controller": "ingress.k8s.aws/alb"}
{"name": "nginx", "controller": "k8s.io/ingress-nginx"}
```

### 5. Load Balancers

**Why check this:** LoadBalancer Services and TargetGroupBindings map cluster traffic to AWS
ELBs. Target type (`ip` vs `instance`) explains routing and IP consumption.

<!-- UNVALIDATED LIVE (broadened): field paths per API/CRD schema. On self-managed AWS Load
     Balancer Controller, TGBs are under `targetgroupbindings.elbv2.k8s.aws` and an
     aws-load-balancer-controller Deployment exists in-cluster. On EKS Auto Mode the ALB
     controller is EKS-managed: there is NO in-cluster aws-load-balancer-controller Deployment
     (that absence is a fact, not "no LB controller"), and TGBs register under a DIFFERENT API
     group — `targetgroupbindings.eks.amazonaws.com`. Query BOTH groups; whichever exists is the
     fact. Validate target-type paths on a live cluster of each kind. -->
```bash
# Service-type LoadBalancer objects
kubectl get svc -A -o json 2>/dev/null | jq -r '
  .items[] | select(.spec.type=="LoadBalancer") |
  {ns: .metadata.namespace, name: .metadata.name,
   external: (.status.loadBalancer.ingress // [])}'

# TargetGroupBindings — target type ip | instance. Query BOTH API groups; whichever exists
# is the fact (guarded with 2>/dev/null). Self-managed AWS LBC uses elbv2.k8s.aws; EKS Auto
# Mode's EKS-managed ALB controller uses eks.amazonaws.com.
kubectl get targetgroupbindings.elbv2.k8s.aws -A -o json 2>/dev/null | jq -r '
  .items[] | {ns: .metadata.namespace, name: .metadata.name,
              target_type: .spec.targetType, arn: .spec.targetGroupARN}'
kubectl get targetgroupbindings.eks.amazonaws.com -A -o json 2>/dev/null | jq -r '
  .items[] | {ns: .metadata.namespace, name: .metadata.name,
              target_type: .spec.targetType, arn: .spec.targetGroupARN}'

# AWS-side load balancers and target groups
aws elbv2 describe-load-balancers --region <region> \
  --query 'LoadBalancers[].{name:LoadBalancerName,type:Type,scheme:Scheme,dns:DNSName}'
aws elbv2 describe-target-groups --region <region> \
  --query 'TargetGroups[].{name:TargetGroupName,targetType:TargetType,protocol:Protocol,port:Port}'
```

- `load_balancers.services` = count+list of LoadBalancer Services `{namespace, name, external}`.
- `load_balancers.target_group_bindings` = count+list of `{namespace, name, target_type, arn}`;
  `target_type` = `ip` | `instance`.
- `load_balancers.aws_load_balancers` = count+list from `describe-load-balancers`.

### 6. Service Mesh Detection

**Why check this:** Service meshes add mTLS, observability, and traffic management at the
application layer. Detecting mesh presence explains sidecar containers, elevated resource
usage, and additional CRDs.

**Istio:**
```bash
# Control plane
kubectl get deploy -n istio-system istiod 2>/dev/null

# Version (image tag)
kubectl get deploy -n istio-system istiod -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null

# Sidecar injection namespaces
kubectl get ns -l istio-injection=enabled -o name 2>/dev/null

# Ambient mode (ztunnel DaemonSet present => ambient, else sidecar)
kubectl get daemonset -n istio-system ztunnel 2>/dev/null
```

**AWS App Mesh:**
```bash
# Controller
kubectl get deploy -n appmesh-system appmesh-controller 2>/dev/null

# Virtual services
kubectl get virtualservices.appmesh.k8s.aws -A --no-headers 2>/dev/null | wc -l
```

**Linkerd:**
```bash
kubectl get deploy -n linkerd linkerd-destination 2>/dev/null
```

**Cilium (mesh):**
```bash
kubectl get deploy -n kube-system cilium-operator 2>/dev/null
```

- `service_mesh.type` = string enum `istio` | `appmesh` | `linkerd` | `cilium` | `none`.
- `istio.mode` = `sidecar` | `ambient` (ambient when the `ztunnel` DaemonSet exists).
- `istio.injection_namespaces` = namespaces labelled `istio-injection=enabled`.
- `appmesh.virtual_services` = count of `virtualservices.appmesh.k8s.aws`.

**Example output (Istio detected):**
```
NAME     READY   UP-TO-DATE   AVAILABLE   AGE
istiod   2/2     2            2           45d
```

### 7. DNS Configuration

**Why check this:** CoreDNS is critical for service discovery. NodeLocal DNSCache improves DNS
performance and reduces CoreDNS load. Custom Corefile entries indicate special routing.

**MCP:**
```
describe_eks_resource(
  resource_type="addon",
  cluster_name="<cluster-name>",
  resource_name="coredns"
)
```

**CLI:**
```bash
# CoreDNS deployment (replicas + version from image tag)
kubectl get deploy -n kube-system coredns -o json 2>/dev/null | jq '{
  replicas: .spec.replicas,
  image: .spec.template.spec.containers[0].image
}'

# CoreDNS ConfigMap — presence of non-default Corefile entries => custom_config: true
kubectl get configmap -n kube-system coredns -o yaml 2>/dev/null

# NodeLocal DNSCache
kubectl get daemonset -n kube-system node-local-dns 2>/dev/null
```

- `coredns.version` = image tag; `coredns.replicas` = `.spec.replicas`.
- `coredns.custom_config` = the Corefile contains non-default entries (e.g. custom forwards/rewrites).
- `nodelocal_dns.enabled` = the `node-local-dns` DaemonSet is present.
- **CoreDNS absent (e.g. Auto Mode):** On EKS Auto Mode there is no CoreDNS Deployment in
  kube-system and no `kube-dns` Service — DNS is EKS-managed and not discoverable in-cluster.
  Record `dns.coredns.version: null`, `dns.coredns.replicas: null`, and
  `dns.coredns.custom_config: null`. Null here is the fact (managed and undetectable), **not** an
  error or "broken DNS". (Confirm Auto Mode via `cluster.computeConfig.enabled`.)

**Example output:**
```json
{
  "replicas": 2,
  "image": "602401143452.dkr.ecr.us-west-2.amazonaws.com/eks/coredns:v1.10.1-eksbuild.6"
}
```

### 8. Network Policies

**Why check this:** Network policies enforce pod-to-pod traffic rules. Their absence means all
pods can communicate. Calico and Cilium extend native Kubernetes policies with cluster-wide
and L7 rules.

```bash
# Native NetworkPolicy objects (use -o name | wc -l to avoid the header off-by-one)
kubectl get networkpolicies -A -o name 2>/dev/null | wc -l

# Namespaces that hold at least one policy
kubectl get networkpolicies -A -o json 2>/dev/null | \
  jq -r '[.items[].metadata.namespace] | unique'

# Calico
kubectl get crd 2>/dev/null | grep -i projectcalico.org
kubectl get globalnetworkpolicies.crd.projectcalico.org --no-headers 2>/dev/null | wc -l

# Cilium
kubectl get crd 2>/dev/null | grep -i cilium.io
kubectl get ciliumnetworkpolicies -A --no-headers 2>/dev/null | wc -l
```

- `network_policies.count` = total native NetworkPolicy objects.
- `network_policies.namespaces_with_policies` = count+list of namespaces holding policies.
- `calico.detected` = Calico CRDs present; `calico.global_policies` = count of GlobalNetworkPolicies.
- `cilium.detected` = Cilium CRDs present.

### 9. external-dns

**Why check this:** external-dns automates DNS record creation for Services/Ingress. Its
`--domain-filter` args are the raw facts describing which zones it manages.

```bash
kubectl get deploy -A -l app.kubernetes.io/name=external-dns -o json 2>/dev/null | jq -r '
  .items[] | {
    ns: .metadata.namespace,
    domain_filters: [.spec.template.spec.containers[0].args[]
                     | select(startswith("--domain-filter"))]
  }'
```

- `external_dns.detected` = the deployment is present.
- `external_dns.domain_filters` = the `--domain-filter` argument values.

---

## Output Schema

This is the **single canonical schema** for the networking module — it carries every
networking fact. The `networking-recon` agent emits exactly this shape (plus the shared
`cluster:` block from `references/cluster-basics.md`). Use `null` where a fact was not
detected; never omit a key.

**Naming decision (cni vs vpc_cni):** the top-level block is `cni` and carries the vendor
`type`. The AWS VPC CNI specifics live in a nested `cni.vpc_cni` block. The BUILD-SPEC rename
table does not rename this key, so the richer reference structure is kept but expressed under
a single `cni` parent so there is exactly one name for it across reference and agent.

```yaml
networking:
  # --- VPC identifiers (cluster.resourcesVpcConfig) ---
  vpc_id: string                    # resourcesVpcConfig.vpcId
  subnet_ids: list                  # resourcesVpcConfig.subnetIds
  cluster_security_group_id: string # resourcesVpcConfig.clusterSecurityGroupId (EKS-managed primary SG)
  security_groups:                  # additional SGs (resourcesVpcConfig.securityGroupIds)
    count: int
    list: list

  ip_family: string                 # kubernetesNetworkConfig.ipFamily (ipv4 | ipv6)
  service_cidr: string              # kubernetesNetworkConfig.serviceIpv4Cidr

  endpoint_access:                  # resourcesVpcConfig
    public: bool                    # endpointPublicAccess
    private: bool                   # endpointPrivateAccess
    public_cidrs: list              # publicAccessCidrs

  # --- Subnets & IP availability ---
  subnets:                          # aws ec2 describe-subnets (ids from subnet_ids)
    count: int
    list:
      - id: string                  # SubnetId
        az: string                  # AvailabilityZone
        cidr: string                # CidrBlock
        free: int                   # AvailableIpAddressCount
  vpc_secondary_cidrs: list         # aws ec2 describe-vpcs CidrBlockAssociationSet (beyond primary)

  # --- CNI ---
  cni:
    type: string                    # aws-vpc-cni | calico | cilium | auto-mode | other (detected, not assumed)
    vpc_cni:                        # AWS VPC CNI specifics (null when cni.type != aws-vpc-cni)
      detected: bool                # aws-node DaemonSet present
      version: string               # describe-addon addonVersion
      status: string                # describe-addon status (ResourceNotFound on Auto Mode is expected)
      mode: string                  # secondary-ip | prefix-delegation | custom-networking
      custom_networking:
        enabled: bool               # ENIConfig CRs exist / CUSTOM_NETWORK_CFG=true
        eni_configs: int            # count of ENIConfig resources
      security_groups_for_pods:
        enabled: bool               # ENABLE_POD_ENI=true
      ip_env:                       # IP-target env vars, verbatim facts (null when unset)
        warm_ip_target: string      # WARM_IP_TARGET
        minimum_ip_target: string   # MINIMUM_IP_TARGET
        warm_eni_target: string     # WARM_ENI_TARGET
        warm_prefix_target: string  # WARM_PREFIX_TARGET
        external_snat: string       # AWS_VPC_K8S_CNI_EXTERNALSNAT

  # --- kube-proxy ---
  kube_proxy:
    present: bool                   # kube-proxy DaemonSet/ConfigMap exists (false on some Auto Mode clusters)
    mode: string                    # ConfigMap mode field: "" | iptables (default) | ipvs | nftables (null when absent)

  # --- Ingress & Gateway API ---
  ingress:
    controllers:
      - name: string
        type: string                # aws-lb | nginx | traefik | kong | other
        namespace: string
        version: string             # from container image tag
    classes:                        # IngressClass names (renamed from ingress_class)
      count: int
      list: list
    gateway_api:
      detected: bool                # Gateway API CRDs present
      gateways: int                 # count of Gateway resources

  # --- Load balancers (UNVALIDATED — see detection 5) ---
  load_balancers:
    services:                       # kubectl get svc type=LoadBalancer
      count: int
      list:
        - namespace: string
          name: string
          external: list            # status.loadBalancer.ingress
    target_group_bindings:          # targetgroupbindings.elbv2.k8s.aws
      count: int
      list:
        - namespace: string
          name: string
          target_type: string       # ip | instance
          arn: string                # spec.targetGroupARN
    aws_load_balancers:             # aws elbv2 describe-load-balancers
      count: int
      list:
        - name: string
          type: string               # application | network
          scheme: string             # internet-facing | internal
          dns: string

  # --- Service mesh ---
  service_mesh:
    type: string                    # istio | appmesh | linkerd | cilium | none (string enum)
    istio:
      detected: bool
      version: string               # istiod image tag
      mode: string                  # sidecar | ambient
      injection_namespaces: list    # namespaces labelled istio-injection=enabled
    appmesh:
      detected: bool
      virtual_services: int         # count of virtualservices.appmesh.k8s.aws
    linkerd:
      detected: bool

  # --- DNS ---
  dns:
    coredns:
      version: string               # image tag
      replicas: int
      custom_config: bool           # non-default Corefile entries present
    nodelocal_dns:
      enabled: bool                 # node-local-dns DaemonSet present

  # --- Network policies ---
  network_policies:
    count: int                      # total native NetworkPolicy objects
    namespaces_with_policies:
      count: int
      list: list
    calico:
      detected: bool
      global_policies: int          # count of GlobalNetworkPolicies
    cilium:
      detected: bool

  # --- external-dns ---
  external_dns:
    detected: bool
    domain_filters: list            # --domain-filter arg values
```

---

## Edge Cases

### Auto Mode CNI (no aws-node DaemonSet)

On EKS Auto Mode clusters there is **no `aws-node` DaemonSet** and `describe-addon
--addon-name vpc-cni` returns `ResourceNotFound`. This is the managed Auto Mode CNI, **not**
an absent CNI. Record `cni.type: auto-mode` and set `cni.vpc_cni.detected: false`; do not
report "no CNI". Confirm Auto Mode via `cluster.computeConfig.enabled`.

### Multiple Ingress Controllers

Common to have both AWS LBC and nginx (AWS LBC for external ALB/NLB, nginx for internal
routing). Record every controller in `ingress.controllers[]` and every IngressClass in
`ingress.classes`.

### VPC CNI Custom Configuration

Non-default settings surface through the aws-node env vars (Security Groups for Pods via
`ENABLE_POD_ENI`, External SNAT via `AWS_VPC_K8S_CNI_EXTERNALSNAT`, custom networking via
`AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG` + ENIConfig CRs). These are captured in
`cni.vpc_cni.ip_env`, `cni.vpc_cni.security_groups_for_pods`, and `cni.vpc_cni.custom_networking`.

### Subnet IP Address Availability

Per-subnet free-IP counts are recorded as facts in `subnets.list[].free` (from
`AvailableIpAddressCount`). Secondary VPC CIDRs appear in `vpc_secondary_cidrs`. Report the
numbers; draw no conclusion.
