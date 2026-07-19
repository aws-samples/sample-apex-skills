# Module: Networking

> **Part of:** [eks-recon](../SKILL.md)
> **Purpose:** Detect network configuration - VPC identifiers, VPC CNI, subnets, ingress controllers, load balancers, service mesh, DNS, network policies, endpoint access

## Table of Contents

- [Access Model](#access-model)
- [Detection Strategy](#detection-strategy)
- [Detection Capabilities](#detection-capabilities)
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

## Access Model

This module reads facts from two sources, both read-only:

- **AWS control-plane APIs** (EKS/EC2/ELB) — the VPC/subnet/endpoint anchors and AWS-side
  network resources. Requires the read-only permissions in `references/iam-policy.json`.
  Facts sourced here: `vpc_id`, `subnet_ids`, `cluster_security_group_id`, `security_groups`,
  `ip_family`, `service_cidr`, `endpoint_access.*` (all from `eks describe-cluster`); the
  per-subnet inventory and free-IP counts (`ec2 describe-subnets`); `vpc_secondary_cidrs`
  (`ec2 describe-vpcs`); the VPC CNI addon `version`/`status` and CoreDNS addon version
  (`eks describe-addon`); and `load_balancers.aws_load_balancers` (`elasticloadbalancing
  describe-load-balancers` / `describe-target-groups`).
- **Kubernetes API** (via the Agent Space EKS access entry) — everything read from in-cluster
  objects and CRDs. Requires `authenticationMode` to include `API` and the
  `AmazonAIOpsAssistantPolicy` access entry to be present. RBAC verbs needed: `get`, `list`.
  Facts sourced here: CNI vendor (`cni.type`) and VPC CNI mode/env vars (aws-node DaemonSet);
  `kube_proxy.*`; ingress controllers and `classes`; `gateway_api.*`; `load_balancers.services`
  and `load_balancers.target_group_bindings` (TargetGroupBinding CRDs); `service_mesh.*`;
  CoreDNS deployment/replicas/Corefile and `nodelocal_dns` (`dns.*`); `network_policies.*`
  (incl. Calico/Cilium CRDs); and `external_dns.*`.

If the Kubernetes API is unreachable (access entry absent), report the AWS-API facts and mark
every K8s-dependent sub-fact (`cni.type`/`cni.vpc_cni` env facts, `kube_proxy.*`, `ingress.*`,
`gateway_api.*`, `load_balancers.services`/`target_group_bindings`, `service_mesh.*`,
`dns.coredns` deployment facts / `nodelocal_dns`, `network_policies.*`, `external_dns.*`) as
`unconfirmed` in the report's Coverage section — never as `false`/`count: 0`.

> **Reference pseudocode note.** Code blocks labeled *reference pseudocode (kubernetes client)*
> below illustrate the resource, fields, and RBAC verbs for each K8s-API read. They are **not
> executable** in the Agent Space and are not an operational path — do not emit `kubectl ... | jq`
> pipelines. The agent reads these resources through its Kubernetes-API capability.

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

## Detection Capabilities

### 1. VPC Identifiers & Endpoint Access

**Why check this:** The VPC id, subnet ids, and security groups anchor every other network
fact to concrete AWS resources. Endpoint access (public/private) describes how the API
server is reached. `ipFamily` and `serviceIpv4Cidr` describe the cluster address space.

**Via AWS API** — call EKS DescribeCluster and read `resourcesVpcConfig` and
`kubernetesNetworkConfig`:

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

**Via AWS API** — describe the subnets (ids from detection 1) and the VPC CIDR association set:

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

**Via Kubernetes API** — determine `cni.type` from installed resources, do not assume:

- **aws-vpc-cni:** `DaemonSet` `aws-node` (group/version `apps/v1`) present in `kube-system`.
- **calico:** `DaemonSet` `calico-node` in `kube-system`, and/or CRDs in the `projectcalico.org` group.
- **cilium:** `DaemonSet` `cilium` in `kube-system`, and/or CRDs in the `cilium.io` group.
- **RBAC verbs:** `get`, `list` on `daemonsets.apps` and on `customresourcedefinitions.apiextensions.k8s.io`.

- `cni.type` = `aws-vpc-cni` (aws-node present) | `calico` | `cilium` | `other`.
- **Auto Mode:** Auto Mode clusters have **no `aws-node` DaemonSet** — the CNI is managed by
  EKS. Treat the absence of `aws-node` on an Auto Mode cluster as `cni.type: auto-mode`, **not**
  as "no CNI". `aws eks describe-addon --addon-name vpc-cni` returning `ResourceNotFound` on
  Auto Mode is expected, not an error. (Detect Auto Mode via `cluster.computeConfig.enabled`.)

**Via AWS API** — VPC CNI addon status + version:

```bash
aws eks describe-addon --cluster-name <cluster-name> --region <region> --addon-name vpc-cni \
  --query 'addon.{version:addonVersion,status:status,config:configurationValues}' 2>/dev/null
```

**Via Kubernetes API** — VPC CNI mode + env vars from the aws-node DaemonSet:

- **Resource:** `DaemonSet` `aws-node`, group/version `apps/v1`, namespace `kube-system`.
- **Fields to extract:** `spec.template.spec.containers[0].env` — capture all `AWS_*`, `ENABLE_*`,
  `WARM_*`, `MINIMUM_*` entries into a name→value map. In particular:
  `ENABLE_PREFIX_DELEGATION` (prefix delegation), `ENABLE_POD_ENI` (security groups for pods),
  `AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG` (custom networking flag).
- **Custom networking CRs:** `ENIConfig`, group `crd.k8s.amazonaws.com` — count the resources.
- **RBAC verbs:** `get`, `list` on `daemonsets.apps` and on `eniconfigs.crd.k8s.amazonaws.com`.

*Reference pseudocode (kubernetes client), not executable:*
```python
apps = client.AppsV1Api()
ds = apps.read_namespaced_daemon_set("aws-node", "kube-system")
env = {e.name: e.value for e in ds.spec.template.spec.containers[0].env
       if e.name.startswith(("AWS_", "ENABLE_", "WARM_", "MINIMUM_"))}
prefix_delegation = env.get("ENABLE_PREFIX_DELEGATION")
pod_eni           = env.get("ENABLE_POD_ENI")
custom_net_flag   = env.get("AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG")

# Custom networking ENIConfig CRs (count)
custom = client.CustomObjectsApi()
eniconfigs = custom.list_cluster_custom_object("crd.k8s.amazonaws.com", "v1alpha1", "eniconfigs")
eni_config_count = len(eniconfigs["items"])
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

**Via Kubernetes API** — read the kube-proxy ConfigMap and DaemonSet:

- **Resource (mode):** `ConfigMap` `kube-proxy-config` (fall back to `kube-proxy`), group/version
  `v1` (core), namespace `kube-system`. Extract the `mode` field from `data` (or the embedded
  config YAML in `data`).
- **Resource (presence):** `DaemonSet` `kube-proxy`, group/version `apps/v1`, namespace `kube-system`.
- **RBAC verbs:** `get`, `list` on `configmaps` and on `daemonsets.apps`.

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

**Via Kubernetes API** — detect controllers (capture version from the container image tag):

- **AWS Load Balancer Controller:** `Deployment` `aws-load-balancer-controller`, group/version
  `apps/v1`, namespace `kube-system` (self-managed installs only). Extract
  `spec.template.spec.containers[0].image` → version = image tag. On EKS Auto Mode the ALB
  controller is EKS-managed and there is **NO** in-cluster `aws-load-balancer-controller`
  Deployment — that absence is a fact, not "no LB controller".
- **NGINX Ingress Controller:** `Deployment` (`apps/v1`), label selector
  `app.kubernetes.io/name=ingress-nginx`, all namespaces. Extract `{namespace, image}`.
- **Traefik:** `Deployment` (`apps/v1`), label selector `app.kubernetes.io/name=traefik`, all
  namespaces. Extract `{namespace, image}`.
- **Kong:** `Deployment` (`apps/v1`), label selector `app=kong`, all namespaces.
- **IngressClasses:** `IngressClass`, group/version `networking.k8s.io/v1`. Extract
  `metadata.name` and `spec.controller`.
- **RBAC verbs:** `get`, `list` on `deployments.apps` and on `ingressclasses.networking.k8s.io`.

- Per controller record `{name, type, namespace, version}`; `version` = the image tag.
- `type` = `aws-lb` | `nginx` | `traefik` | `kong` | `other`.
- `classes` = count+list of IngressClass names (renamed from `ingress_class`).

**Via Kubernetes API** — Gateway API:

- **CRDs:** `CustomResourceDefinition` (group `apiextensions.k8s.io`) whose names match
  `gateways`, `httproutes`, `grpcroutes` (group `gateway.networking.k8s.io`) → presence sets
  `gateway_api.detected`.
- **Gateways:** `Gateway`, group/version `gateway.networking.k8s.io/v1`, all namespaces → count.
- **RBAC verbs:** `get`, `list` on `customresourcedefinitions.apiextensions.k8s.io` and on
  `gateways.gateway.networking.k8s.io`.

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
     group — `targetgroupbindings.eks.amazonaws.com`. Read BOTH groups; whichever exists is the
     fact. Validate target-type paths on a live cluster of each kind. -->

**Via Kubernetes API** — LoadBalancer Services and TargetGroupBinding CRDs:

- **LoadBalancer Services:** `Service`, group/version `v1` (core), all namespaces, filtered to
  `spec.type == "LoadBalancer"`. Extract `{namespace, name, status.loadBalancer.ingress}`.
- **TargetGroupBindings (read BOTH groups; whichever exists is the fact):**
  - **Self-managed AWS LBC:** `TargetGroupBinding`, group/version `elbv2.k8s.aws/v1beta1`.
  - **EKS Auto Mode (EKS-managed ALB controller):** `TargetGroupBinding`, group/version
    `eks.amazonaws.com/v1`.
  - For each, extract `{namespace, name, spec.targetType (ip | instance), spec.targetGroupARN}`.
- **RBAC verbs:** `get`, `list` on `services`, `targetgroupbindings.elbv2.k8s.aws`, and
  `targetgroupbindings.eks.amazonaws.com`.

*Reference pseudocode (kubernetes client), not executable:*
```python
v1 = client.CoreV1Api()
lb_services = [
    {"namespace": s.metadata.namespace, "name": s.metadata.name,
     "external": (s.status.load_balancer.ingress or [])}
    for s in v1.list_service_for_all_namespaces().items
    if s.spec.type == "LoadBalancer"
]

custom = client.CustomObjectsApi()
tgbs = []
for group, version in (("elbv2.k8s.aws", "v1beta1"), ("eks.amazonaws.com", "v1")):
    resp = custom.list_cluster_custom_object(group, version, "targetgroupbindings")
    for i in resp["items"]:
        tgbs.append({"namespace": i["metadata"]["namespace"], "name": i["metadata"]["name"],
                     "target_type": i["spec"].get("targetType"),
                     "arn": i["spec"].get("targetGroupARN")})
```

**Via AWS API** — AWS-side load balancers and target groups:

```bash
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

**Via Kubernetes API** — detect the mesh control plane by vendor:

- **Istio:** `Deployment` `istiod`, group/version `apps/v1`, namespace `istio-system`. Version =
  `spec.template.spec.containers[0].image` tag. Ambient vs sidecar: `DaemonSet` `ztunnel` in
  `istio-system` present ⇒ `ambient`, else `sidecar`. Injection namespaces: `Namespace` (`v1`)
  objects labelled `istio-injection=enabled`.
- **AWS App Mesh:** `Deployment` `appmesh-controller`, group/version `apps/v1`, namespace
  `appmesh-system`. Virtual services: `VirtualService`, group `appmesh.k8s.aws`, all namespaces → count.
- **Linkerd:** `Deployment` `linkerd-destination`, group/version `apps/v1`, namespace `linkerd`.
- **Cilium (mesh):** `Deployment` `cilium-operator`, group/version `apps/v1`, namespace `kube-system`.
- **RBAC verbs:** `get`, `list` on `deployments.apps`, `daemonsets.apps`, `namespaces`, and
  `virtualservices.appmesh.k8s.aws`.

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

**Via AWS API** — CoreDNS addon version (when installed as an EKS managed addon):

```bash
aws eks describe-addon --cluster-name <cluster-name> --region <region> --addon-name coredns \
  --query 'addon.{version:addonVersion,status:status}' 2>/dev/null
```

**Via Kubernetes API** — CoreDNS deployment, Corefile, and NodeLocal DNSCache:

- **CoreDNS Deployment:** `Deployment` `coredns`, group/version `apps/v1`, namespace `kube-system`.
  Extract `spec.replicas` → `replicas`; `spec.template.spec.containers[0].image` tag → `version`.
- **CoreDNS ConfigMap:** `ConfigMap` `coredns`, group/version `v1` (core), namespace `kube-system`.
  Non-default Corefile entries (custom forwards/rewrites) ⇒ `custom_config: true`.
- **NodeLocal DNSCache:** `DaemonSet` `node-local-dns`, group/version `apps/v1`, namespace
  `kube-system` → presence sets `nodelocal_dns.enabled`.
- **RBAC verbs:** `get`, `list` on `deployments.apps`, `configmaps`, and `daemonsets.apps`.

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

**Via Kubernetes API** — native and vendor network policies:

- **Native policies:** `NetworkPolicy`, group/version `networking.k8s.io/v1`, all namespaces →
  total count and the set of namespaces that hold at least one policy.
- **Calico:** CRDs in the `projectcalico.org` group (presence sets `calico.detected`);
  `GlobalNetworkPolicy`, group `crd.projectcalico.org`, cluster-scoped → count.
- **Cilium:** CRDs in the `cilium.io` group (presence sets `cilium.detected`);
  `CiliumNetworkPolicy`, group `cilium.io`, all namespaces → count.
- **RBAC verbs:** `get`, `list` on `networkpolicies.networking.k8s.io`,
  `customresourcedefinitions.apiextensions.k8s.io`, `globalnetworkpolicies.crd.projectcalico.org`,
  and `ciliumnetworkpolicies.cilium.io`.

- `network_policies.count` = total native NetworkPolicy objects.
- `network_policies.namespaces_with_policies` = count+list of namespaces holding policies.
- `calico.detected` = Calico CRDs present; `calico.global_policies` = count of GlobalNetworkPolicies.
- `cilium.detected` = Cilium CRDs present.

### 9. external-dns

**Why check this:** external-dns automates DNS record creation for Services/Ingress. Its
`--domain-filter` args are the raw facts describing which zones it manages.

**Via Kubernetes API** — the external-dns Deployment:

- **Resource:** `Deployment`, group/version `apps/v1`, label selector
  `app.kubernetes.io/name=external-dns`, all namespaces.
- **Fields to extract:** `metadata.namespace`; `spec.template.spec.containers[0].args` entries
  that start with `--domain-filter`.
- **RBAC verbs:** `get`, `list` on `deployments.apps`.

- `external_dns.detected` = the deployment is present.
- `external_dns.domain_filters` = the `--domain-filter` argument values.

---

## Output Schema

This is the **single canonical schema** for the networking module — it carries every
networking fact. The `networking-recon` agent emits exactly this shape (plus the shared
`cluster:` block from `references/cluster-basics.md`). Use `null` where a fact was not
detected; never omit a key.

**Naming decision (cni vs vpc_cni):** the top-level block is `cni` and carries the vendor
`type`. The AWS VPC CNI specifics live in a nested `cni.vpc_cni` block — the full CNI detail is
kept but expressed under a single `cni` parent so there is exactly one name for it.

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
    services:                       # Kubernetes API: list Services of type LoadBalancer
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
