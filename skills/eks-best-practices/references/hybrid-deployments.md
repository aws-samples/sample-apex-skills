# Hybrid & On-Premises EKS Deployments — Hybrid Nodes, EKS Anywhere, and Outposts

> **Part of:** [eks-best-practices](../SKILL.md)
> **Purpose:** Choose among and operate the three on-premises/hybrid EKS deployment models — EKS Hybrid Nodes, EKS Anywhere, and EKS on Outposts. This guide is decision-first: which model fits a site, then the per-model networking, disconnection behavior, compute/autoscaling, identity, and lifecycle you have to get right. It does **not** cover in-Region cluster design (that is the rest of [../SKILL.md](../SKILL.md)), region-extension edge such as Local Zones or Wavelength, or the Terraform to *enable a hybrid-nodes cluster* — control-plane config, remote networks, IAM/access entry, CNI (see [terraform-examples.md](terraform-examples.md)).

---

## Table of Contents

1. [Choosing a Model](#choosing-a-model)
2. [EKS Hybrid Nodes](#eks-hybrid-nodes)
3. [EKS Anywhere](#eks-anywhere)
4. [EKS on Outposts](#eks-on-outposts)
5. [Cross-Model Support Matrix](#cross-model-support-matrix)
6. [Sources](#sources)

---

## Choosing a Model

Three models run EKS outside a standard in-Region cluster. Positioning first, in one line each:

- **EKS Hybrid Nodes** — the simplest hybrid when you have a *reliable* Region link and want an AWS-managed control plane driving your *own* on-prem or edge hardware.
- **EKS Anywhere** — air-gapped, isolated, or disconnected sites where you own the *full* stack (control plane, etcd, and nodes) on your infrastructure.
- **EKS on Outposts** — data residency, sovereignty, or low-latency needs met with *AWS-owned, AWS-managed* hardware installed in your data center.

The single most important question is who owns the control plane and whether the site stays connected to an AWS Region.

| Model | Control plane (who / where) | Nodes / hardware | Reliable Region link required? | Disconnect-tolerant? | Choose when |
|-------|-----------------------------|------------------|-------------------------------|----------------------|-------------|
| **EKS Hybrid Nodes** | AWS-managed, hosted in an AWS Region | Your own on-prem/edge bare-metal or VMs (x86 or Arm) | **Yes** — explicitly not for DDIL | No — running pods survive a blip, but no mutating ops until reconnect | Reliable link; you want AWS to run the control plane over your hardware |
| **EKS Anywhere** | **You** run it on your infrastructure (EKS Distro + CAPI) | Your infrastructure (vSphere, bare metal, Nutanix, Snow, CloudStack) | No | **Yes** — fully air-gapped operation supported | Isolated, air-gapped, or disconnected sites; you own the whole stack |
| **EKS on Outposts (extended)** | AWS-managed, in the parent Region | Nodes on the Outpost | **Yes** — control plane is in-Region | No — control-plane disconnects "might lead to application downtime" | AWS-owned hardware, but you want to conserve Outpost capacity and have a reliable link |
| **EKS on Outposts (local)** | AWS-managed, running **on the Outpost** | Control plane + nodes on the Outpost — **racks only** | No | **Yes** — continues Kubernetes ops through Region disconnects (degraded — IAM/IRSA/KMS/EBS-PV/Route 53 unavailable offline) | AWS-owned hardware with data-residency mandates or disconnect tolerance |

**Critical rule.** Split the decision by *why* the site is disconnected. **Permanently air-gapped or isolated → EKS Anywhere** — the only model that fully operates air-gapped. **A connected site that must keep operating *through* Region outages on AWS-owned hardware (data-residency / sovereignty) → Outposts local clusters** (Outposts racks only) — these are disconnect-*tolerant*, **not** air-gapped: during a disconnect IAM/IRSA/Pod Identity/KMS/EBS-PV/Route 53 all go unavailable and mutating operations fail. **EKS Hybrid Nodes and Outposts extended clusters both depend on a reliable connection to an AWS Region** and are the wrong tool for a site that must keep operating through Region isolation. Hybrid Nodes is explicitly *not* a fit for DDIL (disconnected, disrupted, intermittent, limited) environments.

A second axis is **how much of the stack you want to own**. Hybrid Nodes gives you the least to operate — AWS runs the control plane, you bring the hosts — and bills pay-as-you-go per reported vCPU-hour with no upfront commitment. ("Least to operate" here means control-plane *ownership* only; the on-prem networking, CNI, host lifecycle, and the absence of a node autoscaler are still yours to run.) Outposts gives you AWS-owned, AWS-managed hardware but constrains you to self-managed node groups and Outpost-bounded capacity, and carries its own cost shape: an up-front Outpost capacity commitment (multi-year term) plus, for extended clusters, the in-Region control-plane hourly charge. EKS Anywhere gives you everything (control plane, etcd, node lifecycle, and an Enterprise Subscription priced per cluster) in exchange for being the only fully air-gapped option.

The models are also not mutually exclusive at the edge. A single Hybrid Nodes cluster can run VPC CNI cloud nodes alongside Cilium/Calico on-prem nodes (mixed mode) so cloud-hosted workloads and burst capacity live in the Region while latency- or residency-sensitive workloads run on your hardware. Match the model to the *connectivity* requirement first, then to the ownership/cost posture you can support day-2.

See also the model summary in [../SKILL.md](../SKILL.md#eks-deployment-models).

---

## EKS Hybrid Nodes

EKS Hybrid Nodes attach your own on-prem or edge hosts (bare metal or VMs) as nodes to an AWS-hosted EKS control plane — a "stretched" cluster where AWS runs the control plane and you run the nodes. It is GA and billed per hybrid-node vCPU-hour while a node is attached. Available in all Regions **except** AWS GovCloud (US) and China (as of 2026-08-18).

### When to Choose

Pick Hybrid Nodes when you have a reliable network path to an AWS Region and want AWS to operate the control plane while your workloads run on hardware you already own on-prem or at the edge. It supports x86 and Arm, physical or virtual. A few boundaries define the fit:

- Do **not** pick it for disconnected/air-gapped sites — that is EKS Anywhere.
- Running hybrid nodes on cloud infrastructure (Regions, Local Zones, Outposts, or other clouds) is **not supported**, and you are still billed if you try — that separation is the boundary against Outposts.
- Available in all Regions **except** AWS GovCloud (US) and China — and in **GovCloud (US)**, **EKS Anywhere is likewise unavailable**, so there is no first-party Hybrid Nodes or EKS Anywhere path in that partition (for China, EKS Anywhere availability is not documented — do not assume it).

### Networking

Networking is where hybrid-node deployments most often stall, so plan the connectivity, CIDR, CNI, endpoint-mode, and pod-routing decisions before you create the cluster.

**Connectivity.** Establish a private link over AWS Site-to-Site VPN, Direct Connect, or your own VPN. Control-plane <-> node traffic routes through the VPC/subnets you pass at cluster creation. The published guidance (not a hard requirement) is:

- >= 100 Mbps of bandwidth.
- <= 200 ms round-trip time.
- Redundant DX/VPN paths, since a broken link makes the cluster unmanageable even though running pods survive.

**Remote CIDRs.** Pass your on-prem node and pod CIDRs via `RemoteNodeNetwork` and `RemotePodNetwork`:

- They must be RFC-1918 or CGNAT (100.64.0.0/10).
- They must not overlap each other, the VPC CIDR, or the service CIDR.
- Limit: up to **15 remote-node + 15 remote-pod CIDRs** per cluster.
- Explicitly set the service IPv4 CIDR at cluster creation to avoid auto-reassignment.

**CNI.** The Amazon VPC CNI is **not compatible** with hybrid nodes — it carries anti-affinity on `eks.amazonaws.com/compute-type: hybrid`. Use one of:

- **Cilium** — the AWS-supported CNI. AWS supports only its own Cilium builds: IPv4 only, VXLAN overlay, Cilium Cluster-Scope IPAM, BGP control plane, kube-proxy replacement. Cilium v1.17.x/v1.18.x; v1.18.3 needs kernel >= 5.10 (so not Ubuntu 20.04 / RHEL 8).
- **Calico** — also supported.

**Endpoint mode gotcha.** Use **public OR private** access. The **"Public and Private"** mode always resolves to public IPs for hybrid nodes and can **block them from joining**. For all-private traffic, use private access or resolve the endpoint to control-plane ENI private IPs on-prem.

**Pod-CIDR routing — the baseline.** On a non-gateway cluster, the **pod CIDR must be routable on-prem** for a whole class of features to work, and the documented baseline is to advertise it via **Cilium/Calico BGP**. This is required for:

- Admission webhooks running on hybrid nodes (otherwise run webhooks on cloud nodes).
- Metrics Server and AMP scrape reaching hybrid pods.
- Cloud <-> hybrid pod east-west traffic.

Two related traps: the node IP (reported in `Node.status.addresses`; there is no CCM for hybrid nodes) must be routable from the VPC or `kubectl logs/exec/port-forward` fail, and a broken kube-proxy on a freshly-registered node crashes the CNI. ALB/NLB IP targets must also be routable from AWS.

**The AWS-managed alternative (April 2026).** The **EKS Hybrid Nodes gateway** "eliminates the need for making on-premises pod networks routable or coordinating network infrastructure changes." It is Helm-deployed, automates control-plane -> webhook and pod <-> pod (cloud <-> on-prem) traffic, and auto-programs VPC route tables. There is **no additional charge for the gateway itself, but you pay for the EC2 / EKS Auto Mode compute that runs it** (2 pods; >= 2 nodes recommended for HA). **It requires the EKS Cilium CNI with VTEP (VXLAN) enabled** — the VPC CNI is incompatible, and **Calico clusters cannot use the gateway** and must keep routable / BGP-advertised pod CIDRs. On an eligible EKS-Cilium cluster, treat routable/BGP-advertised pod CIDR as the baseline for non-gateway setups and the gateway as the AWS-managed way to remove that requirement (as of 2026-08-18).

**Mixed mode.** When you run VPC CNI on cloud nodes and Cilium/Calico on hybrid nodes, keep >= 1 CoreDNS replica on each side and use Service Traffic Distribution (Kubernetes >= 1.31) to keep traffic zone-local.

### Disconnection Behavior

Hybrid Nodes rely on the Region and are explicitly **not** for DDIL, but they do degrade gracefully during a *transient* disconnect — the design goal is static stability, not indefinite standalone operation. Understand the timings and the eviction-cancellation logic before you rely on a lossy link.

- **Static stability.** Running pods keep running; you cannot perform mutating operations until reconnect. The control plane cannot reach kubelet, so it marks nodes `NotReady` (Lease not renewed).
- **Timings** (Kubernetes defaults, **not configurable** in EKS): `node-monitor-grace-period` 40s, `default-unreachable-toleration-seconds` 300s.
- **Eviction cancellation.** Full-cluster, full-zone, and majority-zone (>= 55% via `unhealthy-zone-threshold`) disruptions **cancel** pod evictions (`large-cluster-size-threshold` is set to 100,000 in EKS). *Partial* disruptions still evict/reschedule pods on unreachable nodes. This cancellation applies only to clusters **larger than three nodes**; in clusters of **three nodes or fewer**, pods on unreachable nodes are still scheduled for eviction (relevant for small edge clusters).
- **Best practice.** Redundant DX/VPN; run **>= 4 nodes** for eviction safety where feasible (only clusters larger than three nodes get the majority/zone eviction-cancellation) — on a fixed <= 3-node edge cluster, a pod can raise its own `tolerationSeconds` on the `node.kubernetes.io/unreachable` toleration to *delay* (not cancel) eviction and buy reconnect time; set `topology.kubernetes.io/zone` per node via `nodeadm` (no CCM to auto-label); alarm on `NodeNotReady`; keep local troubleshooting via `crictl`.

### Compute & Autoscaling

There is **no AWS-native autoscaler for the hybrid data plane** — you provision the hosts yourself.

- **Karpenter and EKS Auto Mode** provision EC2 instances only and **cannot** scale on-prem hybrid nodes (as of 2026-08-18). In mixed-mode clusters they scale only the cloud portion (burst-to-cloud).
- **Cluster Autoscaler** likewise scales EC2 node groups, not on-prem hosts.
- The `eks-hybrid-nodes` Terraform example provisions the **cloud/cluster side** — `remote_network_config`, the `HYBRID_LINUX` access entry, the hybrid-node IAM role, SSM activation, and a Packer node image. What has **no supported IaC** is the **on-prem physical hosts themselves** — no autoscaler and no supported provisioning path for the bare-metal/VM worker lifecycle (as of 2026-08-18); the field pattern is to bake `nodeadm` into a golden OVA/ISO for boot-time join.

**GPU / accelerated inference.** For **GenAI/ML** GPU workloads on Hybrid Nodes or EKS Anywhere (NVIDIA device plugin / GPU Operator, DCGM metrics), see the [`eks-genai`](../../eks-genai/SKILL.md) skill — this guide does not cover accelerator serving. Plain non-ML GPU use (CUDA batch, media transcode) is general EKS and not covered by `eks-genai`.

### Security & Identity

Hybrid nodes need a way to prove their identity to the control plane without the IMDS-based credential path that EC2 nodes use. There are exactly two options, and you pick one — not both.

- **SSM hybrid activations** — choose this if you have no existing PKI. Credentials are valid 1h and the node name is auto-assigned (`mi-...`). SSM's advanced-instances tier and its 1,000-node free limit were **removed effective June 30, 2026** — you can register any number of hybrid nodes with no per-node fee; from **2026-09-30**, Session Manager and Run Command on non-EC2 (hybrid) nodes move to pay-as-you-go pricing (the EKS `hybrid-nodes-creds` page still describes the older 1,000-free / advanced-tier model). On disconnect the SSM agent backs off up to 30 min (agent >= 3.3.808.0).
- **IAM Roles Anywhere** — choose this if you already run a CA. Credentials default to 1h (max 12h via `durationSeconds`) and reconnect within seconds. It also **avoids the SSM Session Manager/Run Command pay-as-you-go usage cost** that begins 2026-09-30 for non-EC2 nodes — a factor when choosing between the two.

Either way you need a **Hybrid Nodes IAM role** granting `eks:DescribeCluster`, `eks:ListAccessEntries`, ECR pull-only, plus the SSM or Roles Anywhere permissions, mapped to the cluster via **access entries / aws-auth**. For workload credentials, **both IRSA and EKS Pod Identity work** on hybrid nodes: IRSA via the cluster OIDC provider + projected service-account token calling the **regional STS endpoint** (`sts.<region>.amazonaws.com`) — it is *not* IMDS-based — and **Pod Identity** via the Pod Identity Agent add-on (>= v1.3.3-eksbuild.1; on **Bottlerocket** hybrid nodes, >= v1.3.7-eksbuild.2 **and** Bottlerocket OS >= 1.39.0) with the hybrid credentials DaemonSet enabled (required because hybrid nodes have no IMDS). Use `nodeadm` >= 1.0.19 (SSM signing key).

### Observability

Most of the EKS observability stack works on hybrid nodes, but with one notable hole.

- **Works:** the CloudWatch Observability agent (needs `RUN_WITH_IRSA=True`), ADOT, the AMP managed collector (needs a private endpoint + routable pod CIDR), cluster/workload/pod/container metrics, and the Node monitoring agent.
- **Gap:** node-level CloudWatch Container Insights metrics are **not available** on hybrid nodes because there is no IMDS. Prepare secondary local logging/metrics backends so you retain visibility during disconnects.

### Upgrades & Lifecycle

You own OS and host provisioning, so lifecycle is more hands-on than an in-Region cluster.

- **Validated OSes:** AL2023 (on-prem virtualized only, and not covered by Support Plans outside EC2), Bottlerocket (VMware vSphere x86_64 only, v1.37.0+, Kubernetes >= 1.28, no `nodeadm`), Ubuntu 20.04/22.04/24.04, RHEL 8/9. Note the CNI-kernel interaction: Cilium v1.18.3 needs kernel >= 5.10, which the stock Ubuntu 20.04 / RHEL 8 kernels do not meet — pair those older OSes with a Cilium build that supports their kernel, or move to a newer OS.
- **Version skew:** nodes run the same EKS Kubernetes version and may be at most 3 minors behind the control plane — never ahead. Hybrid Nodes tracks the EKS-supported Kubernetes version range (standard + extended support); there is no separate minimum.
- **Upgrade path:** prefer **cutover/blue-green**; **in-place `nodeadm` upgrade** works but incurs node downtime. Bump the CNI first if needed.

**Managed add-on allow-list.** Only an explicit set of managed add-ons schedules on hybrid nodes; everything else carries hybrid anti-affinity and will not schedule. Supported:

- AWS-vended: kube-proxy, CoreDNS, ADOT, CloudWatch agent, EKS Pod Identity agent, Node monitoring agent, CSI snapshot controller, Private CA connector, FSx CSI, Secrets Store CSI provider.
- Community: Metrics Server, cert-manager, Node Exporter, kube-state-metrics, External DNS.
- Plus the AMP managed collector and the AWS Load Balancer Controller.

**Storage caveat.** Persistent storage on hybrid nodes is narrow: the **EFS CSI driver is explicitly not compatible** with hybrid nodes, and the **EBS CSI driver is not among the hybrid-compatible add-ons** (don't assume standard EBS PVs work on-prem). The **FSx for Lustre CSI driver is compatible** (minimum `v1.7.0-eksbuild.1`); otherwise use local/node storage — but local/node storage is **not resilient to node loss**, so use the FSx CSI or replicate at the application layer for stateful workloads.

### Air-Gapped / Proxied Install

`nodeadm` installs containerd, ca-certificates, iptables, and ssm-agent via the **OS package manager** (yum/apt/snap). The required-access table includes an **"Operating System package manager endpoints"** row (HTTPS 443) that is OS-specific and varies by Region (not enumerated in the docs). Plan for OS-package-repo reachability — or a mirror, or a **prebuilt Packer image** (the documented disconnected path; `nodeadm --containerd-source` defaults to `distro`) — *in addition to* the EKS/nodeadm/SSM endpoints. Air-gapped installs commonly stall on OS-package fetches (as of 2026-08-18).

### Billing Note

Hybrid nodes are billed **per vCPU per hour based on the resources of the nodes as reported to Kubernetes** (tiered). A couple of specifics matter for sizing:

- On bare metal, each physical CPU core reports two vCPUs, and billing is on total reported vCPUs.
- The docs are **silent** on whether limiting kubelet allocatable CPU reduces the bill — **do not claim allocatable-based savings.**

The safe framing: the bill scales with attached/reported vCPU capacity, so **size hosts to the workload** rather than over-provisioning idle cores.

Separately, from **2026-09-30** AWS Systems Manager **Session Manager and Run Command on non-EC2 (hybrid) nodes move to pay-as-you-go** usage pricing — budget for it if you use SSM for node credentials or operations (IAM Roles Anywhere avoids this usage cost).

### Getting Started

For a concrete Arm/edge example, see [aws-samples/sample-eks-hybrid-nodes-raspberry-pi](https://github.com/aws-samples/sample-eks-hybrid-nodes-raspberry-pi). Note the eksworkshop lab runs hybrid nodes **on EC2 for demonstration only** — that is not a supported production pattern.

✅ DO:
- **Prefer private**; use public or private endpoint access (never **"Public and Private"**).
- Make pod CIDRs routable on-prem via Cilium/Calico BGP if you need webhooks, Metrics Server, AMP scrape, or cloud<->hybrid pod east-west — or, **on an EKS Cilium (VTEP/VXLAN) cluster**, adopt the EKS Hybrid Nodes gateway to skip that requirement (April 2026). **Calico clusters cannot use the gateway** and must keep routable/BGP-advertised pod CIDRs.
- Set per-node zone labels and multi-DC topology spread for eviction safety.
- Bake `nodeadm` into a golden image for boot-time join — no supported IaC for the on-prem *host* lifecycle (the `eks-hybrid-nodes` example covers the cloud/cluster side).
- Size hosts to the workload — the bill scales with reported vCPUs.

❌ DON'T:
- Use the **"Public and Private"** endpoint mode (it blocks joins).
- Run the VPC CNI on hybrid nodes, or expect Karpenter/Auto Mode/Cluster Autoscaler to scale on-prem hosts (as of 2026-08-18).
- Use Hybrid Nodes for DDIL (use EKS Anywhere), or run hybrid nodes on EC2/cloud (unsupported and still billed).
- Claim savings from capping kubelet allocatable CPU — undocumented.

**Caveats (as of 2026-08-18):** unavailable in GovCloud/China; node-level Container Insights unavailable (no IMDS); AL2023 unsupported by Support Plans off-EC2; Bottlerocket limited to vSphere x86_64; `nodeadm` >= 1.0.19 required for SSM.

---

## EKS Anywhere

EKS Anywhere is "container management software built by AWS that makes it easier to run and manage Kubernetes clusters on-premises and at the edge," built on **EKS Distro**. It is customer-managed: "you are responsible for cluster lifecycle operations and maintenance." **Both the control plane and the data plane run on your infrastructure.**

### When to Choose

Choose EKS Anywhere for **isolated or air-gapped** on-premises environments where clusters must run entirely on your infrastructure and you own the control plane and etcd. Two framing points:

- It is the **only** model that fully operates air-gapped — do **not** pick Hybrid Nodes or Outposts-extended for disconnected sites, since both need Region connectivity.
- Conversely, if you *are* reliably connected, Hybrid Nodes is usually cheaper and simpler (pay-as-you-go, no upfront subscription), so do not reach for EKS Anywhere just to avoid a Region link you already have.

### Supported Providers

You pick exactly one infrastructure provider per cluster — there are **no mixed-provider node pools**. The supported providers (as of 2026-08-18):

- **VMware vSphere 7 or 8** — no vSphere 9 / VCF 9.
- **Bare metal** via Tinkerbell.
- **Nutanix**.
- **AWS Snow** — limited to **Snowball Edge Compute Optimized** devices; not yet available on other Snow Family devices.
- **Apache CloudStack** — GA since Oct 2022, still listed in the FAQ and deployment-options docs but de-emphasized in the getting-started chooser; verify currency against live release notes before committing.
- **Docker** — development-only, never production.

### Air-Gapped Operation

Fully disconnected operation is supported, and internet access is needed **only** temporarily to bootstrap: "Once these dependencies are downloaded and imported in a local registry, you no longer need internet access." The workflow:

1. Run `eksctl anywhere download artifacts` to produce `eks-anywhere-downloads.tar.gz`.
2. Push the images — EKS Distro, Cluster API providers, EKS Anywhere controllers, Cilium CNI, kube-vip, cert-manager — to a **local registry mirror**.
3. Copy the **curated-package** images from Amazon ECR into that same mirror in a single step.

The admin machine needs **>= 80 GB** scratch space. Bare metal additionally requires `osImageURL` and `hookImagesURLPath` in the cluster spec. Stand up the local registry mirror before you attempt air-gapped cluster creation (and external etcd too, but only if you opt for unstacked etcd — stacked is the default).

### Lifecycle

Built on **Cluster API (CAPI)**. Cluster topology:

- **Management** clusters — long-lived; create and manage a fleet of workload clusters.
- **Workload** clusters — run cluster components + your apps.
- **Standalone** clusters — single-cluster, management + workload combined, managed via `eksctl`.

**Create flow:**

1. From the admin machine, stand up a bootstrap **kind** cluster.
2. Install CAPI + EKS-A core into the bootstrap cluster.
3. Provision the target cluster.
4. **MOVE** the CAPI/EKS-A components from the bootstrap cluster onto the target.
5. Shut down the bootstrap cluster.

Clusters are managed declaratively via `eksctl` or the Kubernetes API / GitOps (Flux).

**OS images.** How you obtain the node OS depends on the OS:

- **Bottlerocket** (vSphere, bare metal) is AWS-distributed via `tuftool`.
- **Ubuntu/RHEL** — AWS **no longer ships OVAs**, so you build them with `image-builder` (Ubuntu/RHEL for vSphere/Nutanix/bare metal). **RHEL 8 and 9 are both supported** — it is not "RHEL 8 only" (as of 2026-08-18).
- `image-builder` installs the **latest** OS/kernel at build time with **no documented kernel-pin option** — rebuild the image to change the kernel.

**Upgrades** cover **both** the Kubernetes version and the EKS Anywhere version, and **management-components upgrades are a separate step**.

### Reliability

Because you own the control plane, etcd, and data plane, HA is your responsibility to configure — nothing is managed for you.

**Day-2 backup/DR.** For the customer-owned-etcd models — EKS Anywhere and **EBS-backed** Outposts local clusters — etcd backup and restore is your responsibility (there is no managed backup); a lost or corrupted etcd with no backup is **unrecoverable**. Schedule etcd snapshots and rehearse restore.

- `controlPlaneConfiguration.count` is required.
- **External (unstacked) etcd** is optional (`externalEtcdConfiguration.count` / `machineGroupRef`).
- The control-plane endpoint is a **floating VIP via kube-vip** — a unique IP **outside the DHCP range**.

Prefer a **management cluster** (not standalone) for multi-cluster fleets, and **>= 3 control-plane nodes + external etcd** for HA. The docs do not explicitly mandate odd/3-node counts, so treat this as standard etcd-quorum HA judgment, not a doc-quoted requirement.

### Security & Identity

A few identity and visibility facts shape what you can rely on:

- The **EKS Connector** gives read-only visibility of the cluster in the EKS console, but it **requires outbound connectivity to AWS**, so it does **not** work in a true air-gap.
- **Bottlerocket** is a supported node OS.
- **Curated Packages** are AWS-vended and gated behind the subscription.

Do **not** assert root/cluster-CA rotation on existing clusters — the docs cover only leaf/component (etcd + control-plane) certificate renewal, so CA rotation is unconfirmed (as of 2026-08-18).

### Support & Cost

The base software is free, but support and several features are gated behind a paid subscription — buy it before you need any of them.

- The **EKS Anywhere Enterprise Subscription** is priced **per cluster**, 1-year or 3-year.
- It is required to receive **AWS support** ("You can only receive support for... clusters licensed under an active... Subscription"), for **Curated Packages**, and for **extended Kubernetes version support**.
- The license uses an **ID + token** (token added in v0.22.0) and **cannot be shared via AWS RAM**.
- The core software — EKS Distro, Cilium, Flux, kube-vip — is open source and free.

Exact per-cluster dollar pricing was not found in the docs, so treat pricing specifics as judgment, not doc-quoted (as of 2026-08-18).

### Observability

The observability stack ships as **curated packages** and runs **entirely in-cluster** with no mandatory AWS *runtime* dependency — this is the on-prem/air-gapped observability answer, and it is the reason a disconnected EKS Anywhere cluster can still be monitored without a Region. Note the curated packages are gated behind the Enterprise Subscription (see [Support & Cost](#support--cost)), so "no runtime dependency" does not mean "free/ungated":

- Prometheus and Grafana for metrics and dashboards.
- metrics-server for the Kubernetes metrics API.
- ADOT for collection/export.

✅ DO:
- Choose EKS Anywhere for air-gapped/isolated sites; buy the Enterprise Subscription **before** you need support or curated packages (both are license-gated).
- Stand up the local registry mirror before air-gapped cluster creation (plus external etcd only if you choose unstacked etcd — stacked is the default).
- Prefer a management cluster for fleets and >= 3 control-plane nodes + external etcd for HA (etcd-quorum judgment).
- Rebuild `image-builder` images to change the kernel — there is no pin.

❌ DON'T:
- Use EKS Anywhere just to avoid Region connectivity if you are connected — Hybrid Nodes is cheaper/simpler.
- Expect EKS Connector console visibility in a true air-gap (needs AWS egress).
- Mix infrastructure providers in one cluster.

**Caveat (as of 2026-08-18):** verify current provider status on the getting-started chooser and version-support policy pages before committing — provider lists and Snow device support have shifted between releases, and Docker remains dev-only.

---

## EKS on Outposts

EKS on Outposts runs Kubernetes on **AWS-owned, AWS-managed hardware** installed in your data center, using the same EKS APIs/console/tools as in-Region. Choose it when you need AWS-operated infrastructure on-prem for **low latency** to local systems or **data-residency** mandates — the only model where AWS owns the on-prem hardware.

### When to Choose

Pick Outposts when the hardware itself must be AWS-owned and AWS-managed — for low latency to local systems or data-residency mandates — and you still want the same EKS APIs, console, and tools as in-Region. Within Outposts, the connectivity requirement decides the sub-model:

- Choose **local** clusters when you need "continued Kubernetes operations through network disconnects, or if required by data residency mandates."
- Choose **extended** clusters to conserve Outpost capacity when you have a reliable Region link.

### Extended vs Local Clusters

The first Outposts decision is where the control plane lives, which is what determines disconnect tolerance.

- **Extended cluster:** control plane in the AWS Region, nodes on the Outpost. This conserves Outpost capacity but requires a reliable Region link — Kubernetes handling of control-plane <-> node disconnects "might lead to application downtime," so design for static stability.
- **Local cluster:** control plane **and** nodes on the Outpost, which is what lets it survive Region disconnects. Local clusters are GA on **Outposts racks only**.

Local clusters come in two distinct implementations (generations), and the differences are large enough to drive the decision:

| Aspect | Local, **EBS-backed** (original) | Local, **EC2-instance-store-backed** (newer, announced June 2026) |
|--------|----------------------------------|-------------------------------------------------------------------|
| Control plane | In **your** account, 3 EC2 instances, stacked etcd | In an **AWS-managed** account, 6 instances (3 etcd + 3 API server) |
| Add-ons | **Self-managed only** — no EKS add-ons | **EKS add-ons** (validated list) or self-managed |
| IRSA / Pod Identity | **Not supported** | **IRSA + Pod Identity** (plus OIDC) |
| Access entries / aws-auth | No — **IAM + x.509 only** | Access entries, aws-auth, OIDC, x.509 |
| Node OS | AL2023 (EKS-optimized standard/nvidia/neuron), self-managed | Bottlerocket + AL2023 |
| Version lifecycle | **Outposts-specific** lifecycle | **Standard** EKS version/platform lifecycle |
| Region availability | 14 named Regions | All Outposts-racks Regions |

Prefer the **instance-store local** implementation for cloud parity unless a constraint forces EBS-backed (as of 2026-08-18). It is newer (announced 2026), so validate it for your workload; EBS-backed remains the choice for constraint cases.

### Networking

This section covers **local-cluster** networking; **extended**-cluster networking differs (nodes sit in an Outpost subnet reached over the Region service link, with the control plane in-Region). The local-cluster VPC must be associated with the **Outpost local gateway (LGW) route table**, and subnets must route to the LGW to reach the API server over the local network — otherwise access is only from within the VPC. Requirements:

- **>= 1 private subnet**, all on the same logical Outpost.
- **>= 3 free IPs** for the control-plane instances.
- **IP-address-based naming** — resource-based naming is unsupported.
- **No IPv6** and **no IP prefixes**.
- Private subnets reach Regional AWS services via NAT gateway or interface VPC endpoints.

**Load balancing: the AWS Load Balancer Controller provisions ALB only — NO NLB**, across all three options. The default CNI is the **Amazon VPC CNI** in secondary-IP mode with `WARM_ENI_TARGET=1`.

### Reliability & Disconnection

This is the whole reason to pick a local cluster: it keeps apps running *and* allows cluster operations during a Region disconnect, where an extended cluster cannot. Control-plane HA uses **placement groups** to spread the control-plane instances. For **EBS-backed local clusters**:

- **1-2 racks** -> host-level spread.
- **>= 3 racks** -> rack-level spread.
- Either way you need **>= 3 hosts** of the chosen instance type.

For **instance-store local clusters**, spread is set via `spreadLevel` on `controlPlanePlacement` / `etcdPlacement`: `host` requires **>= 3 hosts** of the chosen instance type, `rack` requires **>= 3 racks** (EKS auto-creates the Spread placement group; `groupName` is not used).

During a disconnect a specific set of operations degrades or fails:

- IAM is unavailable -> authenticate with **x.509 client certs**; use static control-plane IPs / local DNS (Route 53 unavailable).
- **EBS-backed PVs** cannot be created/updated/scaled (needs the Region EBS API); **EBS snapshots blocked**.
- **IRSA/Pod Identity cannot mint new credentials** (STS is in-Region); **KMS** mutations fail.
- ALB TLS termination continues, but mutations (new ingress/cert/scale) fail; control-plane logs cache locally and ship to CloudWatch on reconnect.
- Monitor via the Outposts **`ConnectedStatus`** metric.

There is **no documented maximum disconnected duration** for local clusters — do not invent a cap; the real constraints are that IRSA/Pod Identity credentials eventually expire and Region-dependent/mutating operations fail while disconnected. **Extended clusters are fully Region-dependent** for the control plane.

### Compute & Autoscaling

Compute on Outposts is deliberately narrow — plan around self-managed nodes and finite, fixed capacity.

- **Self-managed node groups only** across all three options — **no Managed Node Groups, no Fargate, no EKS Auto Mode** ("Node types: Self-managed only").
- **EC2 On-Demand only.** AMIs are limited to EKS-optimized **AL2023** (standard/nvidia/neuron), plus **Bottlerocket only on instance-store** Outposts.
- **Karpenter is not documented as supported on Outposts** (as of 2026-08-18) — consistent with the self-managed-only compute model and fixed Outpost capacity; treat this as high-confidence inference, not verbatim doc wording.
- **Cluster Autoscaler** can drive self-managed ASGs but is **bounded by finite Outpost capacity** — provision spare capacity while connected so a scale-up during a disconnect has somewhere to land.
- **Control-plane instance sizing — EBS-backed local clusters only.** For the EBS-backed variant (self-managed control plane, 3 stacked-etcd EC2 instances in *your* account), sizing scales with node count, from `large` (1-20 nodes) up to `4xlarge` (251-500 nodes), and needs **246 GB EBS for etcd**. The **instance-store local** cluster (the recommended variant) has an **AWS-managed** control plane on local NVMe — sized via `controlPlaneInstanceType` + `etcdInstanceType`, with **no 246 GB EBS** requirement — and **extended** clusters run the control plane in-Region with no customer-side sizing.

### Security/Identity, Storage, Add-ons

Identity, storage, and add-on support all vary by variant, so confirm the variant before you design any of them:

- **Identity:** extended = IAM/OIDC/access entries; EBS local = IAM + x.509 only; instance-store local = IAM/OIDC/access entries/aws-auth/x.509.
- **Node storage:** EBS gp2 + local NVMe SSD, except instance-store local clusters, which are **local NVMe SSD only**.
- **Secrets envelope encryption (KMS):** **not supported on either local cluster**; extended clusters support it.
- **Add-ons:** extended and instance-store = EKS add-ons or self-managed; EBS local = self-managed only.

### Upgrades & Lifecycle

Which lifecycle you follow depends on the variant:

- **EBS local clusters** follow an **Outposts-specific** version/platform lifecycle.
- **Instance-store local and extended clusters** follow the **standard EKS version lifecycle**, including extended-support pricing.

Two operational cautions apply regardless of variant:

- **Control-plane updates roll instances one-by-one** and need free slotted capacity — otherwise the update stalls in `Creating`/updating.
- **Self-managed nodes are not auto-upgraded** — patch them manually, and remember that **kubelet client certs expire at 1 year** (rotate AMIs or enable cert rotation).

✅ DO:
- Pick **local** clusters for disconnect-tolerance/data residency; **extended** to conserve Outpost capacity with a reliable link.
- Prefer the **EC2-instance-store** local-cluster implementation for cloud parity (EKS add-ons, IRSA, Bottlerocket, standard lifecycle) — it is newer (2026), so validate it for your workload; EBS-backed remains for constraint cases.
- Pre-provision spare capacity + a local image cache/registry, and use placement groups (host/rack spread) before disconnects.

❌ DON'T:
- Expect NLB, Managed Node Groups, Fargate, or Auto Mode — self-managed nodes only. Karpenter is *not documented as supported* either (inference — see the compute section above); treat it as unsupported.
- Rely on IRSA/Pod Identity, EBS PV create/scale, KMS secrets encryption, or IAM auth while disconnected — pre-stage x.509 certs and local DNS.

**Caveats (as of 2026-08-18):** local clusters are **Outposts racks only** — Outposts *servers* are not a supported EKS local-cluster target; EBS-backed local clusters lack IRSA/EKS add-ons and use an Outposts-specific version lifecycle.

---

## Cross-Model Support Matrix

One place to compare the five deployment variants across the capabilities that most often drive a model choice. Read it alongside the per-model sections above — the qualifiers here are deliberately terse.

Legend: ✅ supported, ❌ not available, ⚠️ supported with a caveat, and **"not documented"** meaning the facts backing this guide did not state the cell — verify against current AWS docs rather than assuming either way.

| Capability | Hybrid Nodes | EKS Anywhere | Outposts (extended) | Outposts (local, EBS) | Outposts (local, instance-store) |
|------------|--------------|--------------|---------------------|-----------------------|----------------------------------|
| **Managed Node Groups** | ❌ self-provisioned on-prem hosts | ❌ CAPI-managed machines, not EKS MNG | ❌ self-managed only | ❌ self-managed only | ❌ self-managed only |
| **Fargate** | ❌ in-Region compute only | ❌ not an EKS Anywhere concept | ❌ | ❌ | ❌ |
| **EKS Auto Mode** | ❌ EC2-only; can't scale on-prem hosts | ❌ not an EKS Anywhere concept | ❌ | ❌ | ❌ |
| **Karpenter** | ❌ EC2-only; scales cloud portion only | not documented | not documented as supported | not documented as supported | not documented as supported |
| **NLB (via LBC)** | ⚠️ IP targets must be routable from AWS | not documented | ❌ LBC provisions ALB only | ❌ ALB only | ❌ ALB only |
| **IRSA** | ✅ general pods via cluster OIDC + regional STS endpoint (not IMDS-based) | not documented | ✅ OIDC/IRSA | ❌ IAM + x.509 only | ✅ |
| **EKS Pod Identity** | ✅ supported | not documented | not documented | ❌ not supported | ✅ |
| **Access entries** | ✅ role mapped via access entries/aws-auth | not documented | ✅ | ❌ IAM + x.509 only | ✅ |
| **KMS envelope encryption** | not documented | not documented | ✅ supported | ❌ not on local clusters | ❌ not on local clusters |
| **Amazon VPC CNI** | ❌ incompatible — use Cilium/Calico | ❌ ships Cilium | ✅ secondary-IP, `WARM_ENI_TARGET=1` | ✅ | ✅ |
| **EKS managed add-ons** | ⚠️ explicit allow-list only | ❌ Curated Packages model instead | ✅ EKS add-ons or self-managed | ❌ self-managed only | ✅ validated list |
| **Air-gapped / fully-disconnected operation** | ❌ needs reliable Region link (not DDIL) | ✅ fully supported | ❌ Region-dependent control plane | ⚠️ survives temporary Region disconnects; mutating ops degrade — not air-gapped | ⚠️ survives temporary Region disconnects; mutating ops degrade — not air-gapped |

*Support facts are as of 2026-08-18; verify against current AWS documentation before committing.*

---

## Sources

- [Amazon EKS User Guide — Deployment options](https://docs.aws.amazon.com/eks/latest/userguide/eks-deployment-options.html)
- [AWS GovCloud (US) — Amazon EKS differences](https://docs.aws.amazon.com/govcloud-us/latest/UserGuide/govcloud-eks.html)
- [Amazon EKS User Guide — Hybrid Nodes overview](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-overview.html)
- [Amazon EKS User Guide — Hybrid Nodes networking](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-networking.html)
- [Amazon EKS User Guide — Hybrid Nodes nodeadm](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-nodeadm.html)
- [Amazon EKS User Guide — Hybrid Nodes Kubernetes concepts](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-concepts-kubernetes.html)
- [Amazon EKS User Guide — Hybrid Nodes traffic flows](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-concepts-traffic-flows.html)
- [Amazon EKS Best Practices Guide — Hybrid Nodes network disconnections](https://docs.aws.amazon.com/eks/latest/best-practices/hybrid-nodes-network-disconnections.html)
- [Amazon EKS Best Practices Guide — Kubernetes pod failover through network disconnections](https://docs.aws.amazon.com/eks/latest/best-practices/hybrid-nodes-kubernetes-pod-failover.html)
- [Amazon EKS Hybrid Nodes gateway (What's New, April 2026)](https://aws.amazon.com/about-aws/whats-new/2026/04/amazon-eks-hybrid-nodes-gateway/)
- [Amazon EKS User Guide — Hybrid Nodes gateway overview](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-gateway-overview.html)
- [Amazon EKS User Guide — Hybrid Nodes gateway CNI requirements](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-gateway-cni.html)
- [Amazon EKS User Guide — Hybrid Nodes CNI](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-cni.html)
- [Amazon EKS User Guide — Hybrid Nodes add-ons](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-add-ons.html)
- [Amazon EKS User Guide — Hybrid Nodes prerequisites](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-prereqs.html)
- [Amazon EKS User Guide — Hybrid Nodes webhooks](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-webhooks.html)
- [Amazon EKS User Guide — Prepare operating system for hybrid nodes](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-os.html)
- [Amazon EKS Best Practices Guide — Hybrid Nodes host credentials](https://docs.aws.amazon.com/eks/latest/best-practices/hybrid-nodes-host-creds.html)
- [AWS Systems Manager — support for multicloud and on-premises VMs (What's New, 2026)](https://aws.amazon.com/about-aws/whats-new/2026/06/aws-systems-manager-multicloud-vm/)
- [AWS Systems Manager — Hybrid Activations](https://docs.aws.amazon.com/systems-manager/latest/userguide/activations.html)
- [Amazon EKS User Guide — Hybrid Nodes credentials](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-creds.html)
- [Amazon EKS User Guide — Configure the AWS STS endpoint for hybrid nodes](https://docs.aws.amazon.com/eks/latest/userguide/configure-sts-endpoint.html)
- [Amazon EKS User Guide — Amazon EBS CSI driver](https://docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html)
- [Amazon EKS User Guide — Amazon EFS CSI driver](https://docs.aws.amazon.com/eks/latest/userguide/efs-csi.html)
- [Amazon EKS pricing](https://aws.amazon.com/eks/pricing/)
- [EKS Workshop — EKS Hybrid Nodes](https://www.eksworkshop.com/docs/networking/eks-hybrid-nodes/)
- [aws-samples/eks-hybrid-examples — network disconnections](https://github.com/aws-samples/eks-hybrid-examples/tree/main/network-disconnections)
- [aws-samples/sample-eks-hybrid-nodes-raspberry-pi](https://github.com/aws-samples/sample-eks-hybrid-nodes-raspberry-pi)
- [EKS Anywhere — Getting started overview](https://anywhere.eks.amazonaws.com/docs/getting-started/overview/)
- [EKS Anywhere — Air-gapped installation](https://anywhere.eks.amazonaws.com/docs/getting-started/airgapped/)
- [EKS Anywhere — OS management artifacts](https://anywhere.eks.amazonaws.com/docs/osmgmt/artifacts/)
- [EKS Anywhere — vSphere prerequisites](https://anywhere.eks.amazonaws.com/docs/getting-started/vsphere/vsphere-prereq/)
- [EKS Anywhere — Support scope](https://anywhere.eks.amazonaws.com/docs/concepts/support-scope/)
- [EKS Anywhere — Architecture](https://anywhere.eks.amazonaws.com/docs/concepts/architecture/)
- [EKS Anywhere — Curated packages overview](https://anywhere.eks.amazonaws.com/docs/packages/overview/)
- [EKS Anywhere — FAQs](https://aws.amazon.com/eks/eks-anywhere/faqs/)
- [Amazon EKS User Guide — EKS on Outposts](https://docs.aws.amazon.com/eks/latest/userguide/eks-outposts.html)
- [Amazon EKS User Guide — Outposts VPC and subnet requirements](https://docs.aws.amazon.com/eks/latest/userguide/eks-outposts-vpc-subnet-requirements.html)
- [Amazon EKS User Guide — Outposts network disconnects](https://docs.aws.amazon.com/eks/latest/userguide/eks-outposts-network-disconnects.html)
- [Amazon EKS User Guide — Outposts capacity considerations](https://docs.aws.amazon.com/eks/latest/userguide/eks-outposts-capacity-considerations.html)
- [Amazon EKS User Guide — Outposts instance-store capacity considerations](https://docs.aws.amazon.com/eks/latest/userguide/eks-outposts-instance-store-capacity-considerations.html)
- [Amazon EKS User Guide — Outposts self-managed nodes](https://docs.aws.amazon.com/eks/latest/userguide/eks-outposts-self-managed-nodes.html)
- [Amazon EKS on Outposts with EC2 instance-store (What's New, June 2026)](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-eks-aws-outposts-ec2-instance-store/)
- [Amazon EKS User Guide — Outposts instance-store local cluster overview](https://docs.aws.amazon.com/eks/latest/userguide/eks-outposts-instance-store-local-cluster-overview.html)
