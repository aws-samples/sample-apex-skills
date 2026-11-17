# SREGym on Amazon EKS: feasibility note

Research only, written 2026-11-16; nothing was run against a cluster. Source ids in brackets, for example [S1], point to the Sources table at the end. Anything marked "opinion" or "estimate" is the note's own, not a source's.

SREGym/SREGym [S1], MIT, read at main 148dded7ca2737ded1085e7dc7bbf2a8fcfe7861 (committed 2026-11-16 02:27 UTC); paper arXiv 2605.07161 [S2].

## What SREGym is

- A live benchmark for AI SRE agents: it deploys real apps on Kubernetes, injects a fault, lets an agent diagnose and then mitigate, and grades the result. README.md:16, :21 [S1]: 90 problems, a superset of AIOpsLab and ITBench, with OS-level, metastable and concurrent failures. The paper says the same, 90 problems [S2]. Problem List.md has 129 table rows (an awk count over its rows; it lists variants per app), by fault level: Cluster Management 54, App 38, Container 17, Hardware 12, OS 5, OS/App 1, Hardware/App 1, one malformed row [S3].
- **SREGym-Lite**: 17 problems "easy and reliable to run", on kind with 8 vCPU and 16 GB minimum, 16 vCPU and 32 GB recommended (`c7a.2xlarge` / `c7a.4xlarge`), 1 control-plane plus 3 worker kind nodes (docs/SREGym-Lite.md:3, :13-16, :39) [S4]; the list is sregym/conductor/problem_sets.py:3 [S5].
- **Problems** subclass `Problem` with `inject_fault()`, `recover_fault()`, a structured `root_cause` string and optional `diagnosis_oracle` and `mitigation_oracle` (sregym/conductor/problems/base.py:6-50) [S6].
- **Fault injection** layers (sregym/generators/fault/) [S7]: `inject_virtual.py` (Kubernetes API edits, used by most problems), `inject_app.py`, `inject_kafka.py`, `inject_otel.py` (astronomy-shop feature flags), `inject_operator.py`, `inject_tt.py` (TrainTicket feature-flag faults), `inject_remote_os.py` (SSH via paramiko to Ansible-inventory hosts, or `docker exec` on kind nodes, :1, :95-122, :192-213), and `inject_os.py` (`sudo` a local BPF `err_inject` binary, :39-45). Some problems run privileged `hostNetwork`/`hostPID` pods with `nsenter` instead (node_clock_drift.py:346-404; oracles/conntrack_mitigation.py:54-69) [S8]. Noise uses Chaos Mesh, installed by Helm (generators/noise/manager.py:358-390) [S9].
- **Oracles**: diagnosis is an LLM judge comparing the agent's answer with the root cause against a checklist (oracles/llm_as_a_judge/llm_as_a_judge_oracle.py:8-12; judge.py:56 `DEFAULT_JUDGE_MAX_TOKENS = 16384`, :506 `MAX_PARSE_ATTEMPTS = 3`); mitigation oracles read cluster state, for example `MitigationOracle` checks the baseline Deployments, Services, PVCs and StatefulSets (oracles/mitigation.py:21-60) [S10].
- **Harness**: `main.py` runs stages `diagnosis` then `mitigation` (README.md:139-158), agents in hardened Docker containers (README.md:169-201), agent timeout 1800 s for the whole agent phase (main.py:1366-1369), filtered egress by default (README.md:179-184). The agent reaches the cluster through a filtering API proxy that hides the `chaos-mesh` and `khaos` namespaces (sregym/service/k8s_proxy.py:1-15) [S11]. Agents include `claudecode`, `codex`, `stratus`, `autosubmit` and others (agents.yaml:1-80) [S12].
- **Cluster it assumes**: a self-managed cluster with SSH and root on every node. README.md:66-69 [S1]: "A managed Kubernetes service won't work out of the box, since SREGym's setup needs SSH and root access to the nodes for OS-level cluster configuration." The same note is in scripts/ansible/README.md:5-6. The Ansible path installs Ubuntu's generic 6.8 kernel and cri-dockerd (scripts/ansible/setup_cluster.yml:44, :197-253) [S13]. The kind path uses Calico v3.29.3 as CNI, because filtered runs need Calico policy tiers (kind/setup_kind_cluster.sh:3, :21-22, :76-88) [S14]. OpenEBS `openebs-hostpath` is the storage class (service/apps/deathstarbench/application.py:396, :446; service/cluster_state.py:24-36) [S15].
- No EKS support today: a repo-wide grep for `eks`, `gke` and `aks` finds no EKS code path (2026-11-16, at S1's sha); `gh search issues --repo SREGym/SREGym "EKS"` returns one unrelated problem RFC (number 930, closed).

## 1. Is an EKS adaptation feasible?

**Yes with conditions.** SREGym-Lite's 17 problems can run on an EKS managed node group cluster with Amazon VPC CNI, Calico in policy-only mode on a Calico version that still has the `adminnetworkpolicy` tier (section 2), OpenEBS hostpath and Chaos Mesh, after three harness fixes (the proxy's 15-minute token, Claude Code on Bedrock, our skills in the agent container), scored on the diagnosis stage only, with VPC CNI's own network policy left off (Tigera eks.mdx:46 [W1]). Most of the full set's node-level and Calico-networking problems do not carry over as written.

Reasons:
- **Lite is API-level.** A grep over the 17 Lite problem files for node or CNI hooks (`privileged`, `hostPID`, `hostNetwork`, `nsenter`, `RemoteOS`, `docker exec`, `paramiko`, `calico`, `IPPool`, `openebs`, `hostPath`, Chaos Mesh kinds, `kube-system`) finds one hit, in service_dns_resolution_failure.py:33, which edits CoreDNS in `kube-system`. CoreDNS runs as an EKS add-on whose Corefile the add-on manages; direct edits can be overwritten (BPG networking/vpc-cni.adoc:136 [B6]), so the problem carries only with CoreDNS self-managed or the add-on removed before the run.
- **SSH is the README's blocker, and it is replaceable.** SREGym already runs privileged `hostNetwork` pods with `nsenter` for node faults (conntrack_mitigation.py:54-69, node_clock_drift.py:346-404) [S8]. That pattern works on EC2 managed nodes, so the SSH injectors (`inject_remote_os.py`) can be rewritten onto it (opinion). It does not work on EKS Auto Mode: no SSH (BPG security/automode.adoc:425-426), immutable nodes with a read-only root filesystem on a Bottlerocket variant (automode.adoc:110-122) [B1]. So the target is managed node groups on AL2023, not Auto Mode.
- **The control plane is AWS's.** BPG security/index.adoc:40-49 [B2]: AWS manages the control plane nodes and etcd. Problems that need control-plane hosts cannot run; the SREGym node injectors already target workers only (the kind path skips control-plane nodes via `_is_control_plane_node`, inject_remote_os.py:47-49; the SSH path reads only `worker_nodes` from the inventory, :69), so this removes nothing from Lite (opinion).
- **Calico networking does not fit EKS as it does kind.** Calico CNI replacing VPC CNI cannot reach pods from the EKS control plane, so admission webhooks need `hostNetwork` (the BPG is silent on webhook reachability; W1 eks.mdx:138-141); Lite has a mutating-webhook problem. So the CNI stays VPC CNI, and Calico runs for policy only (the BPG says Calico "works well with EKS", security/network.adoc:442-444 [B3]). That loses the two problems built on Calico IPAM and BGP: pod_cidr_exhaustion_hotel_reservation.py:28 "Requires Calico CNI", and calico_route_reflector_label_drift.
- **The proxy reads the EKS token once.** k8s_proxy.py:519 sets _bearer_token from the kubeconfig once at start, and no refresh code is found (a case-insensitive grep for refresh|expir in k8s_proxy.py finds no match; the token is assigned only at :480 and :519). An EKS token lives 15 minutes (BPG security/iam.adoc:125 [B4]); one run is longer than that (agent phase up to 1800 s alone). The fix is small: the proxy already has an in-cluster ServiceAccount-token path (k8s_proxy.py:476-486), or it can use a ServiceAccount-token kubeconfig like ours (misc/evals/setup/readonly-rbac.yaml:1-6, but with write verbs for SREGym's conductor) (opinion).

## 2. Component by component

The EKS Best Practices Guide (B-rows) is silent on the kubelet config path, the containerd socket, Chaos Mesh settings, Calico tiers and AdminNetworkPolicy, Claude Code's config directory, and webhook reachability from the control plane under the Calico CNI: a grep under latest/bpg/ at its sha finds none of them (Calico appears only as install links, windows/networking.adoc:107; no line pairs webhook with calico or hostNetwork). Those rows cite the projects' own docs and source.

| Component | Carries over as is | New work for EKS | Source |
|---|---|---|---|
| Conductor, problem registry, stages, results | Yes | None expected | S6, S1 README.md:139-167 |
| Apps (hotel-reservation, social-network, astronomy-shop, Kafka, Valkey) | Yes, as Helm or manifests | Image pulls need egress (NAT) from private subnets | S15 |
| API-level injectors (`inject_virtual`, `inject_app`, `inject_kafka`, `inject_otel`, `inject_operator`) | Yes | None expected; CoreDNS edits can be overwritten by the CoreDNS add-on (BPG networking/vpc-cni.adoc:136 [B6]) | S7 |
| SSH and `docker exec` injectors (`inject_remote_os`: kubelet crash, eviction threshold, disk pressure) | No | Rewrite onto privileged `nsenter` pods, and edit the AL2023 kubelet config path: SREGym edits `/var/lib/kubelet/config.yaml` (inject_remote_os.py:270, :302), while nodeadm on the EKS-optimized AL2023 AMI writes `/etc/kubernetes/kubelet/config.json` (`kubeletConfigRoot = "/etc/kubernetes/kubelet"`, `kubeletConfigFile = "config.json"`, config.go:32-33, joined at :365 [W2]). Kubelet crash on every worker may be fought by node auto repair (BPG reliability/dataplane.adoc:179-187 [B5]): node auto repair is opt-in on managed node groups; leave it disabled (the default) (node-repair.html, read 2026-11-16 [W13]) | S7, W2, B5, W13 |
| Local `sudo` BPF injector (`inject_os`: disk wear-out) | No | It runs on the SREGym host, not a node (inject_os.py:39-45); needs a privileged DaemonSet with kernel headers on AL2023, or drop it | S7 |
| Privileged `nsenter` pods (clock drift, conntrack) | Yes on managed nodes | Not on Auto Mode (B1) | S8 |
| Calico-dependent problems (pod CIDR exhaustion, route reflector) | No | Drop, or write EKS-native twins (VPC subnet IP exhaustion is the real EKS analogue: BPG networking/ip-optimization-strategies.adoc:12-14, :24 [B7]) | S16, B7 |
| Filtered egress (Calico `adminnetworkpolicy` tier, setup_check.py:379-393; cluster_egress.py:111-123) | Only on Calico 3.31 or earlier | Calico 3.31 creates the tier itself: "The `Tier` with name `adminnetworkpolicy` is where all Kubernetes admin network policies reside. It is automatically created during installation" [W6]. Its code does so whatever the CNI: `EnsureInitialized` calls `ensureTierExists` for the `adminnetworkpolicy` tier with no CNI condition (libcalico-go/lib/clientv3/client.go:279 at v3.31.7 [W12]), and calico-node and calico-kube-controllers call it at start (node/pkg/lifecycle/startup/startup.go:1252, kube-controllers/cmd/kube-controllers/main.go:127 [W12]), so policy-only mode beside VPC CNI creates it too (read from source, not run on a cluster). Calico 3.32 dropped it: "3.32 removed support for both in favor of `ClusterNetworkPolicy`" [W7]. So pin Calico at 3.31 or earlier (the kind path pins v3.29.3, S14), or change SREGym's tier check. Fallback: `--internet-access open` (README.md:184), or remove Calico and write a new egress module on VPC CNI ClusterNetworkPolicy (Admin tier, VPC CNI 1.21.0 or later [W3]); the two engines cannot run together (W1 eks.mdx:46) | S14, W1, W3, W6, W7, W12 |
| NetworkPolicy problem (`network_policy_block`) | Yes with an engine | Calico policy-only, or, with Calico removed, VPC CNI with ENABLE_NETWORK_POLICY=true (BPG security/network.adoc:62-65 [B3]) | B3 |
| Storage (`openebs-hostpath`; WiredTiger damage reads `pv.spec.local` or `host_path`, mongo_storage_faults.py:53) | Yes once OpenEBS is installed | Install OpenEBS localpv on the nodes; EBS CSI volumes would break the storage faults (no local path) | S15 |
| Chaos Mesh noise | Yes | New work: none; SREGym's installer reads the node runtime and passes both settings when nodes run containerd (manager.py:369-389), AL2023's socket (containerd/config.go:20 [W2]) | S9, W2 |
| API filtering proxy | Partly | Token refresh or ServiceAccount token (section 1) | S11, B4 |
| `claudecode` agent client | Partly | It needs `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` (clients/claudecode/claudecode_agent.py:281-290) and maps any `bedrock` model to "sonnet" (:258-264); we run Claude Code on Bedrock, so it needs a Bedrock path. It sets `CLAUDE_CONFIG_DIR` to a session dir (:273). Claude Code reads personal skills from `~/.claude/skills/<skill-name>/SKILL.md` [W10], and "If you set `CLAUDE_CONFIG_DIR`, every `~/.claude` path on this page lives under that directory instead" [W11], so our skills go in `<session dir>/skills/<skill-name>/` | S12, W10, W11 |
| LLM judge | Yes | `--judge-model` takes LiteLLM Bedrock strings (README.md:254-269) | S10, S1 |
| Cluster build | No (kind or Ansible) | Terraform for an EKS cluster with one managed node group on AL2023, node auto repair off | S13, S14 |

Build size of each new-work row:
- Apps: no code; the NAT gateway is part of the cluster build.
- SSH and `docker exec` injectors: 1 file (inject_remote_os.py), 3 faults moved onto privileged `nsenter` pods, plus the kubelet config path.
- Local `sudo` BPF injector: 1 file (inject_os.py) rewritten as a privileged DaemonSet, or 1 problem dropped.
- Calico-dependent problems: 2 problems dropped, or 2 new problem files for the EKS twins.
- Filtered egress: 1 install setting (the Calico version pin), or 1 new egress module.
- NetworkPolicy problem: 1 install setting (Calico policy-only, or the VPC CNI flag).
- Storage: 1 Helm install (OpenEBS localpv).
- API filtering proxy: 1 file (k8s_proxy.py).
- `claudecode` agent client: 1 file (claudecode_agent.py) for the Bedrock path, plus 1 staging step for our skills.
- Cluster build: 1 Terraform project (VPC with NAT, the cluster, one managed node group).

## 3. What it would cost to run

All figures are **estimates**; nothing was run. Prices are AWS list prices from the AWS Price List, US West (Oregon), read 2026-11-16 [W5].

**Cluster.** Lite on kind needs one host of 8 vCPU / 16 GB (minimum) to 16 vCPU / 32 GB (recommended) for 1 control plane and 3 workers [S4]. On EKS the control plane is AWS's, so 3 workers carry the apps, Calico, OpenEBS, Chaos Mesh and the observability stack. Pick: 3 x m7i.2xlarge (8 vCPU, 32 GiB each; 24 vCPU / 96 GiB in all), "$0.4032 per On Demand Linux m7i.2xlarge Instance Hour", above the kind recommendation to cover DaemonSet overhead (opinion).
- Workers: 3 x $0.4032 = $1.2096 per hour.
- EKS control plane: $0.10 per cluster per hour on standard support [W4].
- NAT gateway: "$0.045 per NAT Gateway Hour", one gateway.
- EBS root volumes: 3 x 100 GB gp3 (Lite's host minimum, SREGym-Lite.md:15 [S4]) at "$0.08 per GB-month of General Purpose (gp3) provisioned storage", 300 x $0.08 / 730 h = $0.0329 per hour.
- **Per hour: $1.3875.**
- Data, one-off per cluster: image pulls through NAT, about 20 GB (estimate) at "$0.045 per GB Data Processed by NAT Gateways" = $0.90; traffic between Availability Zones, up to 50 GB (estimate) at "$0.010 per GB - regional data transfer - in/out/between EC2 AZs" = $0.50. Nothing is sent out to the internet beyond replies (out to the internet would be "$0.090 per GB - first 10 TB / month").

**Wall time per attempt.** Not measured. Each attempt deploys the app, runs baseline traffic, injects, runs the agent (capped at 1800 s, main.py:1366-1369), grades and recovers. Assume 15 to 45 minutes per attempt (estimate).

**Runs.** The trial's shape is three runs per case, with and without the skill.
- Lite, diagnosis only: 17 problems x 3 runs x 2 arms (with and without our skill) = **102 attempts**.
- Serial wall time: 102 x 0.25 h = 25.5 h, to 102 x 0.75 h = 76.5 h.
- Cluster cost: 25.5 h x $1.3875 = $35.38, to 76.5 h x $1.3875 = $106.14, plus about 2 h of build and teardown (2 x $1.3875 = $2.78) and the $1.40 of data above: **$39.56 to $110.32**. This is not part of the runner trial or its budget ($205 for all candidates together, unless the maintainers set another limit with the spend decision, cost-estimate.md).
- The full-flow sanity check before that (one run per Lite problem, one arm): 17 attempts, 4.25 to 12.75 h, $5.90 to $17.69.

**Fault injection.** No separate cost: the injectors are in-cluster API calls and pods. Chaos Mesh runs on the same nodes.

**Model calls per problem.** One Claude Code session per attempt (clients/claudecode/driver.py:297-328 waits for a submission-ready stage, then calls `agent.run(instruction)` once, with one instruction that covers both stages, :178-186; the session is one `claude -p`, claudecode_agent.py:311-320), plus 1 judge call with up to 3 parse attempts (judge.py:506). Model requests inside a session are not bounded by the harness except by the 1800 s timeout. Assuming 20 to 60 model turns per session (estimate, opinion), that is 21 to 63 requests per attempt, or 2,142 to 6,426 for the 102 attempts. Estimate: $0.16 to $1.81 per attempt, the span of the trial's measured runs (cost-estimate.md), so $16.32 to $184.62 for the 102 attempts. A 20 to 60 turn session is longer than any measured run, so this span is a lower bound (estimate); re-measured on an EKS run. The `autosubmit` agent (agents.yaml:8-13) can smoke-test the harness on EKS with no agent model calls, only the judge's.

## 4. What it would measure that our evals do not

Our suites (misc/evals/<suite>/evals.json at 7efa0776) are mostly offline: of 89 cases across 16 suites, 6 are `live_only` (eks-recon 2, eks-operation-review 2, update-docs 2; a count over each file's `live_only` field). The live ones run on a cluster in whatever state it is, with read-only RBAC (misc/evals/setup/readonly-rbac.yaml:57, verbs `get`, `list`, `watch`), and grade the report's shape and content against expectations, with no fault planted.

What SREGym adds (opinion, from S6 to S10):
- **Ground truth on a live cluster**: a known fault with a structured root cause (base.py:34-42), so a skill's finding is right or wrong, not only well formed.
- **Noise and changing state**: Chaos Mesh noise and live traffic make the cluster move while the skill reads it.
- **Repeatable seeded clusters**: the same broken state for the old and new skill, which the old-against-new comparison needs.

The fit is partial, and that is the main condition. SREGym asks an agent to diagnose and fix an incident. None of our EKS skills claims that job: eks-recon says "Troubleshooting specific issues (use `eks-best-practices`)" and "this is read-only" (skills/eks-recon/SKILL.md:28-29); eks-operation-review is not for "AWS troubleshooting" (skills/eks-operation-review/SKILL.md:14). So SREGym's own prompt and judge would mostly measure the agent, not our skill. The use that fits (opinion): take SREGym's apps, injectors and ground truth as **seeded-fault fixtures**, run our own skill prompts on them through our runner, and score whether the report names the planted fault.

| Skill | Gains? | Why (opinion) |
|---|---|---|
| eks-recon | Yes | Does the fact report show the planted state: taint without toleration, wrong selector, missing ConfigMap, probe settings, PVC binding, NetworkPolicy present |
| eks-operation-review | Yes | Does the workload, networking or access section rate RED or AMBER on the planted misconfig (probes, HPA without CPU requests, RBAC, network policy) |
| eks-security | Yes, a few problems | rbac_misconfiguration, psa_restricted_blocks_recreation, network_policy_block, expired TLS, Valkey auth |
| eks-best-practices | Some | eks-recon routes troubleshooting to it (SKILL.md:29), so it is the one skill SREGym's own diagnosis prompt would reach |
| eks-upgrade-check | No | No problem plants deprecated APIs or version skew (Problem List.md) |
| eks-cost-intelligence | No | Needs Cost Explorer and billing data, which a sandbox run does not have |
| eks-design, eks-build, eks-platform-engineering, eks-genai, eks-mcp-server, eks-well-architected-review, eks-ingress-migration | No | Design, build or advisory output, or one problem only (ingress_misroute); eks-genai has no GPU problems |
| ECS skills, graviton-migration, terraform-skill, update-docs, skill-creator | No | Not EKS incident state |

The mitigation stage does not fit our read-only skills (readonly-rbac.yaml:57) and stays off (`--stages diagnosis`, README.md:146).

## 5. Questions and their answers

1. **Does Calico create the `adminnetworkpolicy` tier SREGym's setup check reads (setup_check.py:379-393)?** On Calico 3.31 or earlier, yes; from 3.32, no: answered in section 2 (Filtered egress row), with its fallback.
2. **Wall time and tokens per attempt on EKS:** estimated in section 3 (:75 and :85); measured only on an EKS run, which waits on question 3's answer.
3. **Who pays, and in which account** ($39.56 to $110.32 for the cluster, section 3, plus model calls from $16.32 to $184.62, section 3, a lower bound): a later round of this trial takes it if the note finds an EKS adaptation feasible, and sizes it from this note.
4. **Is incident diagnosis being measured?** No. The use in section 4 runs our skills' own prompts on seeded-fault fixtures and grades whether the report names the planted state. That measures the skills' existing jobs (fact report, operational review, security review), not incident diagnosis.
5. **Grade with SREGym's LLM judge or with our runner's expectations?** Our runner's expectations. SREGym's judge grades a diagnosis against a root cause, and the use in section 4 grades our skills' reports against what they claim to do.
6. **Where Claude Code reads skills under `CLAUDE_CONFIG_DIR`, and the containerd socket for Chaos Mesh on AL2023:** answered in section 2 (the `claudecode` agent client row and the Chaos Mesh noise row); the socket is /run/containerd/containerd.sock [W2].
7. **The license** is MIT [S1 LICENSE.txt]. Vendoring or forking it into an aws-samples repo needs the repo owners' usual open-source review before any code lands in a public repo.

## Sources

| Id | Source | Path:line or URL | Sha or access date | Supports |
|---|---|---|---|---|
| S1 | SREGym/SREGym | README.md:16, :21, :31-33, :66-69, :139-201, :254-269; LICENSE.txt:1 | 148dded7ca2737ded1085e7dc7bbf2a8fcfe7861 | What it is, 90 problems, managed-K8s note, stages, isolation, egress, models, MIT |
| S2 | SREGym paper, arXiv 2605.07161 | https://arxiv.org/abs/2605.07161 | 2026-11-16 | Identity, authors, 90 problems |
| S3 | SREGym/SREGym | Problem List.md (129 rows, fault-level column) | 148dded7 | Fault-level tally |
| S4 | SREGym/SREGym | docs/SREGym-Lite.md:3, :5, :13-16, :39 | 148dded7 | Lite size and host needs |
| S5 | SREGym/SREGym | sregym/conductor/problem_sets.py:3-21 | 148dded7 | Lite problem list |
| S6 | SREGym/SREGym | sregym/conductor/problems/base.py:6-50 | 148dded7 | Problem shape, root cause format |
| S7 | SREGym/SREGym | sregym/generators/fault/inject_remote_os.py:1, :47-49, :95-122, :192-213, :270, :302; inject_os.py:39-45; inject_tt.py:15-23 | 148dded7 | SSH, docker exec, local sudo and TrainTicket injectors, kubelet path |
| S8 | SREGym/SREGym | sregym/conductor/problems/node_clock_drift.py:346-404; sregym/conductor/oracles/conntrack_mitigation.py:54-69 | 148dded7 | Privileged nsenter pod pattern |
| S9 | SREGym/SREGym | sregym/generators/noise/manager.py:358-390 (runtime detection :369-380, chart 2.8.0 :386) | 148dded7 | Chaos Mesh by Helm, containerd settings |
| S10 | SREGym/SREGym | sregym/conductor/oracles/llm_as_a_judge/llm_as_a_judge_oracle.py:8-12; judge.py:56, :506; oracles/mitigation.py:21-60 | 148dded7 | Oracles, judge limits |
| S11 | SREGym/SREGym | sregym/service/k8s_proxy.py:1-15, :471, :476-486, :480, :519 | 148dded7 | Proxy, hidden namespaces, one-time token |
| S12 | SREGym/SREGym | agents.yaml:1-80; clients/claudecode/claudecode_agent.py:258-264, :273, :281-290, :311-320; clients/claudecode/driver.py:178-186, :297-328 | 148dded7 | Agents, Claude Code auth, model mapping, config dir |
| S13 | SREGym/SREGym | scripts/ansible/README.md:5-6; scripts/ansible/setup_cluster.yml:44, :197-253 | 148dded7 | Self-managed nodes, kernel, cri-dockerd |
| S14 | SREGym/SREGym | kind/setup_kind_cluster.sh:3, :21-22, :76-88; kind/kind-config.yaml:11-31; sregym/setup_check.py:379-393; sregym/service/cluster_egress.py:111-123 | 148dded7 | Calico CNI and tier need, kind topology |
| S15 | SREGym/SREGym | sregym/service/apps/deathstarbench/application.py:396, :446; sregym/service/cluster_state.py:24-36; sregym/conductor/problems/mongo_storage_faults.py:1-5, :53 | 148dded7 | OpenEBS hostpath, storage faults |
| S16 | SREGym/SREGym | sregym/conductor/problems/pod_cidr_exhaustion_hotel_reservation.py:14-28; sregym/conductor/problems/service_dns_resolution_failure.py:33; sregym/conductor/problems/calico_route_reflector_label_drift.py | 148dded7 | Calico IPAM and BGP problems; the CoreDNS edit |
| B1 | EKS Best Practices Guide | latest/bpg/security/automode.adoc:110-122, :425-426 | edc514fac86518b50129401c0cffd1f7981d7ec5 | Auto Mode: no SSH, immutable, read-only root |
| B2 | EKS Best Practices Guide | latest/bpg/security/index.adoc:40-49 | edc514fa | AWS manages control plane and etcd |
| B3 | EKS Best Practices Guide | latest/bpg/security/network.adoc:48-65 (flag at :62-65), :442-444 | edc514fa | VPC CNI network policy flag; Calico works with EKS |
| B4 | EKS Best Practices Guide | latest/bpg/security/iam.adoc:125 | edc514fa | EKS token TTL 15 minutes |
| B5 | EKS Best Practices Guide | latest/bpg/reliability/dataplane.adoc:179-187 | edc514fa | Node Monitoring Agent and auto repair |
| B6 | EKS Best Practices Guide | latest/bpg/networking/vpc-cni.adoc:136 | edc514fa | Managed add-ons overwrite configuration drift every 15 minutes |
| B7 | EKS Best Practices Guide | latest/bpg/networking/ip-optimization-strategies.adoc:12-14, :24 | edc514fa | VPC CNI pod IPs come from the VPC; IP exhaustion |
| W1 | Tigera, Calico on EKS | https://docs.tigera.io/calico/latest/getting-started/kubernetes/managed-public-cloud/eks; tigera/docs calico_versioned_docs/version-3.31/getting-started/kubernetes/managed-public-cloud/eks.mdx:24, :46, :138-141 at 202505f37590d507b2344368a4ca64800c338dae | 2026-11-16 | Policy-only vs Calico CNI; VPC CNI network policy conflicts with Calico; control plane cannot reach Calico pods |
| W2 | awslabs/amazon-eks-ami | nodeadm/internal/kubelet/config.go:32-33, :365; nodeadm/internal/containerd/config.go:20 | 91c23c49ed0f00d2df7da318a898de915b04773d | AL2023 kubelet config path; containerd socket |
| W3 | AWS docs, ClusterNetworkPolicy | https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy.html | 2026-11-16 | Admin tier policies on VPC CNI 1.21.0 or later; an existing policy solution must be removed |
| W4 | AWS EKS pricing | https://aws.amazon.com/eks/pricing/ | 2026-11-16 | $0.10 per cluster per hour, standard support |
| W5 | AWS Price List, GetProducts | AmazonEC2 (m7i.2xlarge Linux shared on-demand; NAT Gateway; gp3), AWSDataTransfer (IntraRegion; AWS Outbound), US West (Oregon) | 2026-11-16 | Section 3 prices |
| W6 | tigera/docs | calico_versioned_docs/version-3.31/network-policy/policy-tiers/tiered-policy.mdx:57 | 202505f37590d507b2344368a4ca64800c338dae | Calico 3.31 creates the `adminnetworkpolicy` tier |
| W7 | tigera/docs | calico_versioned_docs/version-3.33/operations/upgrading/upgrade-notes.mdx:222 | 202505f3 | 3.32 removed AdminNetworkPolicy support |
| W10 | Claude Code docs, skills | https://code.claude.com/docs/en/skills (line 163 of the .md) | 2026-11-16 | Personal skills path |
| W11 | Claude Code docs, .claude directory | https://code.claude.com/docs/en/claude-directory (line 11 of the .md) | 2026-11-16 | `CLAUDE_CONFIG_DIR` moves every `~/.claude` path |
| W12 | projectcalico/calico, tag v3.31.7 | libcalico-go/lib/clientv3/client.go:259-289 (tier at :279); node/pkg/lifecycle/startup/startup.go:240, :1252; kube-controllers/cmd/kube-controllers/main.go:127 | 94bd1d5b0e04459d4d1c83653e0335a9201248b8 | The `adminnetworkpolicy` tier is created at start with no CNI condition |
| W13 | AWS docs, node auto repair | https://docs.aws.amazon.com/eks/latest/userguide/node-repair.html; https://docs.aws.amazon.com/eks/latest/APIReference/API_NodeRepairConfig.html ("Node auto repair is disabled by default.") | 2026-11-16 | Node auto repair is opt-in on managed node groups, disabled by default |
| R1 | This repo | skills/eks-recon/SKILL.md:28-29; skills/eks-operation-review/SKILL.md:14; misc/evals/setup/readonly-rbac.yaml:1-6, :57; misc/evals/*/evals.json (live_only counts) | 7efa0776 | Our skills' scope, read-only RBAC, live case count |
