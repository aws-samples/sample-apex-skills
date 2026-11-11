# C3: posture check ("does my setup contain the next one?")

The question is not "is every setting perfect" but "if one pod is compromised tomorrow, does this cluster keep it contained?". This file describes what the four posture scripts in `assets/` do. The scripts are the authority: where this file and a script differ, the script is right and this file is the bug.

Each check reads only files the collector wrote, returns a result with the evidence it read, and carries a severity. A check whose input file was not collected (the read was denied or failed), or, for SEC-POSTURE-46 and -55, a node's instance was not read while the instances that were read would pass, is `unknown`, never pass.

## How it runs

Run from any directory with `aws`, `kubectl`, `jq` 1.6 or later, and `timeout` and `sha256sum` (GNU coreutils) on `PATH`. Every step is read-only; nothing is applied to the cluster.

| Step | Command | Writes | Exit codes |
|---|---|---|---|
| 1. Collect | `posture_collect.sh --cluster <name> --region <region> --context <kubectl-context> [--work <dir>] [--profile <aws-profile>] [--kubeconfig <file>] [--preflight-only]` | `<workdir>/posture/*.json` and `posture/meta.json` (0700 dir, 0600 files) | 0 collected (some files may be missing: `meta.json` `errors`); 2 usage or refusal, one JSON line `{"ok":false,"code":...,"error":...}` |
| 2. Score the copied checks | `posture_score.sh <workdir>` | `posture/results.jsonl`, one token per question | 0; 2 no collection, or already scored; 1 a collection file does not parse (a broken file is not a finding) |
| 3. Score the added checks | `posture_extra.sh <workdir> [--admin-allow <regex>]` | `posture/results-extra.jsonl` | as step 2 |
| 4. Reduce | `posture_reduce.sh <workdir>` | `<workdir>/posture.json` (schema `eks-security/posture@1`) | 0 written, coverage at or above the gate; 3 written but below the gate (score null); 2 refused, nothing written |
| 5. Render | `render_report.py --posture <workdir>/posture.json --out-md <file> [--out-html <file>]` | the report | 0; 3 rendered, coverage below the gate; 2 usage or input error |

Notes on the flags, from the scripts:

- `--context` is required: the collector does not use the current context. It then checks that the context's API endpoint and CA match `eks describe-cluster`, and stops (`context_mismatch`) if they do not.
- `--work` defaults to `./eks-security-<cluster>-<UTC yyyymmddThhmmZ>`. The work dir may already exist (pass the C1 collector's `--out` dir to share it), but `<workdir>/posture/` must not: the collector never overlays or removes an earlier collection (`work_in_use`).
- `--profile` sets `AWS_PROFILE` and unsets static key variables in the environment so the profile wins.
- `--preflight-only` runs the permission probes, writes `meta.json` and stops.
- `--admin-allow` (step 3 only) is a regular expression, matched with jq `test`, for principal ARNs that are expected to hold cluster admin through an access entry: the role that created the cluster, or a break-glass role. The EKS API does not name the cluster creator, so without this flag the creator's entry fails SEC-POSTURE-64.
- Steps 2 and 3 refuse a work dir that is already scored, so re-running cannot emit duplicate tokens.

The access needed is in [read-only-access.md](read-only-access.md), C3 section. The preflight probes each AWS action with a small real read (EC2 with `--dry-run`) and each Kubernetes read with `kubectl auth can-i`. A denied probe does not abort the run: the matching file is not collected, the denial is recorded in `meta.json`, and every check that needs the file reports `unknown`. Only a failed `eks:DescribeCluster`, an unreachable Kubernetes API or expired credentials stop the run.

The collected pod and workload JSON carries container environment values and arguments: treat the work dir as sensitive, keep it out of version control and delete it after the review. No Secret object is read; two named ConfigMaps are (`kube-system/aws-auth`, `kube-system/amazon-vpc-cni`).

## Layers, results, score and coverage

Every check counts toward one of seven containment layers: `node-credential`, `lateral-movement`, `privilege`, `identity`, `detection`, `api-exposure`, `supply-chain`. The exceptions are SEC-POSTURE-18, 19, 21 and 25 (encryption at rest and TLS settings, which a compromised pod does not depend on): they are scored and, when they fail or are unknown, listed in the checks table, but count toward no layer verdict; their `layer` field in posture.json is the catalog grouping only.

**Buckets.** A scorer counts the objects a check applies to and buckets the passing share, the same rule for both scorers (`posture_extra.sh`: "Same bucket rule as the WAR prelude b(): >=90% all, >=70% most, >0 some, 0 none, empty na"). Some checks are all-or-nothing and emit only `all` or `none`. A bucketed check at 90% or more reads pass; the report still lists it, with its failing objects, as `pass (exceptions)` (for example one node open to IMDS under SEC-POSTURE-55, or one namespace without default-deny under SEC-POSTURE-56).

**Result.** `posture_reduce.sh`: "state all -> pass; most, some, none -> fail; na -> na; unknown -> unknown." A check with no token at all is `unknown`. Governance checks (process questions with no cluster evidence) are always `unknown` and are left out of coverage, score and layer verdicts.

**Coverage gate.** Over the measured (non-governance) checks, a check is answered when its state is `all`, `most`, `some` or `none`; `na` and `unknown` are not answered. The rule in the reducer is `(($ac*2) >= $tot and $tot>0)`, that is, at least half of the measured checks answered (`gate: 0.5`). Below the gate `posture.json` is still written, `coverage.complete` is false and the score is null.

**Score.** `posture_reduce.sh`: "sum(points(state) * weight) / sum(weight) over answered checks, rounded; points all 100, most 75, some 50, none 0; weight high 3, medium 2, low 1". `na` and `unknown` are left out of both sums.

**Layer verdict.** `posture_reduce.sh`: "over the measured checks of the layer, unknown when none is answered; not-contained when any high-severity check fails; contained when every answered check passes and none is unknown; partly otherwise." The verdict uses results, so a `most` counts as a fail here.

**Workload namespaces.** Checks that judge workloads skip every namespace matching `^(kube-|amazon-)`, the filter the copied questions use. The scripts take no other exemption list; a team that runs agents in its own namespaces sees them counted, and reads the failing list in the evidence.

Each row of `posture.json` `checks` carries `id`, `war_id` (null for the added checks), `title`, `result`, `severity`, `evidence` (the scorer's detail plus up to 10 failing objects), `source_file`, `recommendation`, `layer` and `state`. Recommendations are printed advice for the team to review; nothing is changed.

## The added containment checks (SEC-POSTURE-55 to 64)

eks-well-architected-review's security pillar does not measure these, or measures them only in part. They are scored by `posture_extra.sh`.

| Id | Check | Evidence source file | Pass / fail rule | Layer | Severity |
|---|---|---|---|---|---|
| SEC-POSTURE-55 | Node instances block pod access to IMDS | `instances.json`, `nodes.json` | Per running Linux instance: pass when `MetadataOptions.HttpEndpoint` is `disabled`, or `HttpTokens` is `required` with `HttpPutResponseHopLimit` 1; bucketed over instances; failing instances grouped by node type (managed node group, Karpenter node pool, Auto Mode, other). Read off the running instance, so launch templates, Karpenter and Auto Mode are judged as in effect. Windows instances are not assessed; no Linux instance gives na. A Linux EC2 node with no instance record is named, and gives unknown when the instances that were read would score a pass (none read included) | node-credential | high |
| SEC-POSTURE-56 | Default-deny ingress per workload namespace | `networkpolicies.json`, `namespaces.json` | A namespace passes when it has a NetworkPolicy with an empty `podSelector`, `Ingress` in `policyTypes` (implied when absent) and no ingress rule; bucketed over workload namespaces. Objects only: enforcement is SEC-POSTURE-26 | lateral-movement | high |
| SEC-POSTURE-57 | Egress limited per workload namespace | `networkpolicies.json`, `namespaces.json` | A namespace passes when a NetworkPolicy with an empty `podSelector` lists `Egress` in `policyTypes`; bucketed. The allowed destinations are not judged | lateral-movement | medium |
| SEC-POSTURE-58 | No host namespaces in workload pods | `pods.json` | Any workload pod not finished (phase other than `Succeeded` or `Failed`) with `hostNetwork`, `hostPID` or `hostIPC` true fails the check (`none`); otherwise `all`; no workload pods gives na | privilege | high |
| SEC-POSTURE-59 | Authenticator log enabled | `cluster.json` | pass when `authenticator` is among the enabled `cluster.logging.clusterLogging` types | detection | medium |
| SEC-POSTURE-60 | GuardDuty EKS Audit Log Monitoring | `guardduty.json` | pass when an `ENABLED` detector has feature `EKS_AUDIT_LOGS` `ENABLED`; no detector, or the feature off, fails. Detector configuration only, findings are never read | detection | medium |
| SEC-POSTURE-61 | GuardDuty Runtime Monitoring | `guardduty.json` | pass when feature `RUNTIME_MONITORING` or `EKS_RUNTIME_MONITORING` is `ENABLED`; the `EKS_ADDON_MANAGEMENT` setting is reported. Whether the agent runs on every node is SEC-POSTURE-48 | detection | medium |
| SEC-POSTURE-62 | ECR registry scanning, continuous | `ecr-scanning.json` | `all` (pass): `ENHANCED` with a `CONTINUOUS_SCAN` rule whose filter is `*`; `some` (fail): `ENHANCED` with narrower or on-push rules only; `none`: `BASIC` or no rule | supply-chain | medium |
| SEC-POSTURE-63 | Workload images pinned by digest | `pods.json` | Per container and init container of unfinished workload pods: pass when the image ends in `@sha256:<64 hex>`; bucketed. A tag resolved at pull time does not count | supply-chain | low |
| SEC-POSTURE-64 | Cluster admin through an access policy | `accessentries.json`, `cluster.json` | Admin is `AmazonEKSClusterAdminPolicy` at any scope, or `AmazonEKSAdminPolicy` at cluster scope. Holders that match `--admin-allow` are listed under pass; any other holder fails the check (`none`) and its ARN and policy are listed. An entry's `kubernetesGroups` are not read: a group binding to cluster admin shows under SEC-POSTURE-10. A `CONFIG_MAP`-only cluster has no access entries: na (its `aws-auth` `system:masters` mappings are SEC-POSTURE-10); on it the cluster creator holds `system:masters` in no visible configuration, and the evidence prints `bootstrapClusterCreatorAdminPermissions=<value>`. When the cluster was created with `bootstrapClusterCreatorAdminPermissions` true and no `--admin-allow` is given, the evidence says one holder is likely the creator | identity | high |

SEC-POSTURE-64's recommendation proposes scoping, printed only: grant each listed principal what it needs at a narrower scope (`AmazonEKSAdminPolicy` with a namespace access scope, or a Kubernetes group bound to a narrower RBAC role), then remove the cluster-wide grant with `aws eks disassociate-access-policy --cluster-name <CLUSTER> --region <REGION> --principal-arn <ARN> --policy-arn arn:aws:eks::aws:cluster-access-policy/<the listed policy>`, keeping one break-glass admin role whose use is logged. AWS's EKS best practices recommend removing the creator's cluster-admin grant the same way ([Identity and Access Management](https://docs.aws.amazon.com/eks/latest/best-practices/identity-and-access-management.html), "Remove the cluster-admin permissions from the cluster creator principal"; policy scopes from [Review access policy permissions](https://docs.aws.amazon.com/eks/latest/userguide/access-policy-permissions.html), both read 2026-11-05).

GuardDuty feature names are those in the [GuardDuty API reference](https://docs.aws.amazon.com/guardduty/latest/APIReference/API_DetectorFeatureConfiguration.html), checked 2026-11-05.

## The copied checks (SEC-POSTURE-1 to 54)

These 54 checks are adapted from eks-well-architected-review's security pillar at commit 7965ae3, scored by `posture_score.sh` with the pillar's question ids (`war_id`) and severities kept. A full Well-Architected review, all pillars, stays in that skill. Three pillar questions are not copied: net-1 and net-3 (capacity items, not security controls) and sec-31 (retired, always na). Governance checks are marked G: always `unknown`, confirm them with the team.

| Layer | Checks (SEC-POSTURE id: war_id, severity) |
|---|---|
| node-credential | 20: sec-22 medium G; 22: sec-23 low G; 46: lens-11 high |
| lateral-movement | 23: sec-27 low; 24: sec-28 low; 26: sec-4 high; 27: sec-14 medium G; 32: net-4 medium |
| privilege | 6: sec-7 medium G; 7: sec-9 medium; 10: rbac-1 high; 11: rbac-2 medium; 12: rbac-3 medium; 33: sec-10 medium; 34: sec-11 high; 35: sec-16 medium; 36: adm-1 medium; 37: adm-2 medium; 38: adm-3 medium; 40: sec-15 medium; 41: podsec-1 medium; 42: podsec-2 high; 43: podsec-3 medium; 44: podsec-4 high; 45: podsec-5 medium |
| identity | 3: sec-3 medium G; 4: sec-5 low G; 5: sec-6 high; 8: sec-17 low; 9: sec-18 high; 13: rbac-4 medium; 14: sec-8 low; 15: sec-24 medium G; 16: sec-34 medium G; 17: sec-35 low G; 49: sec-13 medium G |
| detection | 48: sec-33 medium; 50: sec-19 medium G; 52: sec-26 high; 53: sec-36 low G; 54: sec-37 low G |
| api-exposure | 1: sec-1 medium; 2: sec-2 high; 28: sec-30 high; 29: net-2 high |
| no layer (scored; listed when failing) | 18: sec-21 high; 19: sec-38 high; 21: sec-25 medium; 25: sec-29 high |
| supply-chain | 30: lens-12 medium; 31: lens-13 low; 39: sec-12 low; 47: sec-32 low G; 51: sec-20 medium G. Admission policy for signed or allowed images is not read from the cluster in this version: SEC-POSTURE-47 is a governance question. |

Each check's title, source files and recommendation are in the catalog at the top of `assets/posture_reduce.sh`; each question's rule is its line in `assets/posture_score.sh`. Of the 64 checks, 15 are governance and 49 are measured, so the coverage gate needs 25 answered.

## Currency rule

The posture scripts do not read C1 output: no posture check judges component versions. Version exposure comes from a C1 sweep ([cve-advisory-review.md](cve-advisory-review.md)), reported beside the posture result. Only a gap to a published fixed version is a security finding. A component that is merely behind the latest release, with no advisory, is not: route it to eks-upgrade-check against a target version, or to eks-operation-review (version currency) with no target version. Issue 348's currency group (behind latest) is not checked in this version; add-on available versions are collected in inventory.json for a manual read.

## Repository checks (manual, not scripted)

No script reads a repository. When the team names a local repository path, the model may walk this list with file reads only (nothing is built or installed) and report it in its own section, never mixed into the posture score:

- a lockfile is committed for each package manifest found (for example `package-lock.json`, `poetry.lock`, `go.sum`);
- every Dockerfile `FROM` line pins its base image by digest;
- no manifest, Helm values file or Dockerfile uses the tag `latest`.

## Output

- `posture.json` as above, and the rendered report: failed and unknown checks, and passed checks with failing objects (`pass (exceptions)`), get one row each with result, severity and evidence; other passed checks and na are counted; the coverage line, the score (or "incomplete" below the gate), and one verdict row per containment layer.
- Fixes are the catalog's printed recommendations for the team to review (for example a default-deny NetworkPolicy per namespace, hop limit 1 in the launch template, the PSA label, scoping an admin access entry). Nothing is applied. The hardening knowledge behind each fix is in eks-best-practices and the layer references of this skill.
