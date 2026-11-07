# SkillSpector baseline

- Scanner: SkillSpector v2.13.4 (commit 54824463), static analysis only (`--no-llm`).
- Scanned: every skill under `skills/` and `devops-agent/` on aws-samples/sample-apex-skills: the `skills/` and `devops-agent/` trees at b5b2575, unchanged at main tip 68f94d3, one report per skill.
- Scan date: 2026-11-06.
- The scan is advisory. It does not replace review, and a finding here is a pattern match, not a verdict.
- The workflow does not read this file; compare each annotation against it by hand.
- Coverage: 20 of 34 reports are partial and some static analyzers ran degraded; these 7 partially inspected files are named nowhere else in this file: devops-agent/eks-ingress-migration/references/porting-notes.md, skills/ecs-modernize/assets/replatform-terraform/main.tf, skills/eks-operation-review/references/report-generation.md, skills/eks-well-architected-review/references/cost-optimization.md, skills/eks-well-architected-review/references/performance-efficiency.md, skills/eks-well-architected-review/references/reliability.md, skills/skill-creator/eval-viewer/viewer.html. Findings are a lower bound: a skill or file with no row has not been shown clean.
- Each finding below was checked by hand at the cited file:line and given one verdict:
  - `true positive`: a real security problem in the skill, to fix. Never a suppression: each row says it is open and names its issue, or names the merge that fixed it.
  - `accepted`: the behaviour is real but intended and documented for this skill, or a scanner coverage gap (rule AE1) that is not a defect.
  - `false positive`: the matched text is benign (a control being documented, a read-only command, a word inside a name or prose).
- To refresh: rerun the same command for each skill directory (`skillspector scan <skill dir> --no-llm --format json --output <file>`, for example `skills/eks-security`), compare against this file by file, rule and line, and review every new row the same way. Line numbers move when a file changes, so a moved row needs a fresh look, not a copied verdict.

## Counts

Total findings: 497.

| Verdict | HIGH | MEDIUM | LOW | Total |
|---|---|---|---|---|
| true positive | 0 | 3 | 0 | 3 |
| accepted | 135 | 25 | 3 | 163 |
| false positive | 240 | 73 | 18 | 331 |
| Total | 375 | 101 | 21 | 497 |

## skills/apex

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/apex/SKILL.md:3 | EA2 | MEDIUM | false positive | description says no account or cluster change without confirmation: the opposite of autonomous action |
| skills/apex/SKILL.md:151 | PE3 | HIGH | false positive | names the default ~/.kube/config path in the rule that records and restores the user's kubectl context; no credential read |
| skills/apex/SKILL.md:151 | PE3 | HIGH | false positive | same shared rule: describes the local kubeconfig write by update-kubeconfig and requires restoring the prior context |
| skills/apex/SKILL.md:151 | PE3 | HIGH | false positive | same shared rule: describes the local kubeconfig write by update-kubeconfig and requires restoring the prior context |
| skills/apex/SKILL.md:151 | PE3 | HIGH | false positive | same shared rule: describes the local kubeconfig write by update-kubeconfig and requires restoring the prior context |
| skills/apex/SKILL.md:154 | PE3 | HIGH | false positive | rule forbids outputting secrets, credentials or kubeconfig contents: a control |
| skills/apex/runbooks/eks-operation-review/eks-operation-review.md:72 | EA1 | MEDIUM | false positive | forbids tool calls on activation until the user asks: a restriction, not unrestricted access |
| skills/apex/runbooks/eks-operation-review/eks-operation-review.md:152 | RP1 | MEDIUM | true positive | open, not suppressed: https://github.com/aws-samples/sample-apex-skills/pull/375 (open draft) changes the vendored runbook and its sync script to drop this line. The troubleshooting step still runs `uvx awslabs.eks-mcp-server@latest` on main at 4e68e6d, after the eks-mcp-server setup fix (PR 366); it should run the version the user chose in that setup |

## skills/dotnet-aws-ecs

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/dotnet-aws-ecs/references/cdk-template-guide.md:216 | RA2 | MEDIUM | false positive | `pList` matched inside the listener name `HttpListener`; no persistence |
| skills/dotnet-aws-ecs/references/cloudformation-template-guide.md:361 | RA2 | MEDIUM | false positive | `PList` matched inside the CloudFormation resource name HTTPListener; no persistence |
| skills/dotnet-aws-ecs/references/cloudformation-template-guide.md:478 | RA2 | MEDIUM | false positive | `PList` matched inside the CloudFormation resource name HTTPListener; no persistence |
| skills/dotnet-aws-ecs/references/deployment-guide-template.md:56 | YR4 | HIGH | accepted | the YARA match is the U+200B characters at lines 297-335, used to escape nested code fences inside a markdown example; they carry no hidden text |
| skills/dotnet-aws-ecs/references/deployment-guide-template.md:297 | P2 | HIGH | accepted | U+200B before a nested ``` fence inside a ```markdown example, an escape so the outer block does not close; no hidden instruction (a four-backtick outer fence would avoid invisible characters) |
| skills/dotnet-aws-ecs/references/deployment-guide-template.md:301 | P2 | HIGH | accepted | U+200B before a nested ``` fence inside a ```markdown example, an escape so the outer block does not close; no hidden instruction (a four-backtick outer fence would avoid invisible characters) |
| skills/dotnet-aws-ecs/references/deployment-guide-template.md:311 | P2 | HIGH | accepted | U+200B before a nested ``` fence inside a ```markdown example, an escape so the outer block does not close; no hidden instruction (a four-backtick outer fence would avoid invisible characters) |
| skills/dotnet-aws-ecs/references/deployment-guide-template.md:317 | P2 | HIGH | accepted | U+200B before a nested ``` fence inside a ```markdown example, an escape so the outer block does not close; no hidden instruction (a four-backtick outer fence would avoid invisible characters) |
| skills/dotnet-aws-ecs/references/deployment-guide-template.md:325 | P2 | HIGH | accepted | U+200B before a nested ``` fence inside a ```markdown example, an escape so the outer block does not close; no hidden instruction (a four-backtick outer fence would avoid invisible characters) |
| skills/dotnet-aws-ecs/references/deployment-guide-template.md:335 | P2 | HIGH | accepted | U+200B before a nested ``` fence inside a ```markdown example, an escape so the outer block does not close; no hidden instruction (a four-backtick outer fence would avoid invisible characters) |
| skills/dotnet-aws-ecs/references/dockerfile-guide.md:146 | PE3 | HIGH | false positive | `.env` is listed in a .dockerignore to keep secrets out of the image: a control |
| skills/dotnet-aws-ecs/references/dockerfile-guide.md:201 | RP1 | MEDIUM | false positive | local test run of the image the guide just built (`<app-name>`); no registry pull, so no tag-swap risk |

## skills/ecs-architect

No findings.

## skills/ecs-build

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/ecs-build/SKILL.md:262 | AS3 | MEDIUM | false positive | citation URL to an external skill used as a source; the skill does not enumerate or read other installed skills |
| skills/ecs-build/references/baseline-defaults.md:54 | AS3 | MEDIUM | false positive | citation URL to an external skill used as a source; the skill does not enumerate or read other installed skills |
| skills/ecs-build/scripts/validate_project.sh:543 | RA2 | MEDIUM | false positive | `PLIST` matched inside the shell variable SKIPLIST in the validator's summary; no persistence |
| skills/ecs-build/scripts/validate_project.sh:544 | RA2 | MEDIUM | false positive | `PLIST` matched inside the shell variable SKIPLIST in the validator's summary; no persistence |
| skills/ecs-build/scripts/validate_project.sh:544 | RA2 | MEDIUM | false positive | `PLIST` matched inside the shell variable SKIPLIST in the validator's summary; no persistence |
| skills/ecs-build/scripts/validate_project.sh:546 | RA2 | MEDIUM | false positive | `PLIST` matched inside the shell variable SKIPLIST in the validator's summary; no persistence |
| skills/ecs-build/scripts/validate_project.sh:549 | RA2 | MEDIUM | false positive | `PLIST` matched inside the shell variable SKIPLIST in the validator's summary; no persistence |

## skills/ecs-devops

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/ecs-devops/SKILL.md:213 | AE1 | HIGH | accepted | points to references/cicd-pipelines.md (11 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/ecs-devops/SKILL.md:239 | AE1 | HIGH | accepted | points to references/cicd-pipelines.md (11 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |

## skills/ecs-genai

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/ecs-genai/references/compute-hardware.md:122 | PE2 | MEDIUM | accepted | sudo in the documented GPU-sharing user data (EC2 user data runs as root anyway); user-run on their own instance |
| skills/ecs-genai/references/compute-hardware.md:122 | TM1 | HIGH | accepted | AWS-documented EC2 user data that replaces /etc/sysconfig/docker to make nvidia the default runtime for GPU sharing; run by the user on their own instance |
| skills/ecs-genai/references/compute-hardware.md:123 | PE2 | MEDIUM | accepted | sudo in the documented GPU-sharing user data (EC2 user data runs as root anyway); user-run on their own instance |
| skills/ecs-genai/references/compute-hardware.md:123 | TM2 | HIGH | accepted | same user data: `sudo tee -a` writes the new Docker OPTIONS line; documented GPU-sharing setup |
| skills/ecs-genai/references/compute-hardware.md:124 | PE2 | MEDIUM | accepted | sudo in the documented GPU-sharing user data (EC2 user data runs as root anyway); user-run on their own instance |

## skills/ecs-modernize

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/ecs-modernize/SKILL.md:107 | AE1 | HIGH | accepted | points to references/code-transformation-agent-led.md (54 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/ecs-modernize/SKILL.md:207 | EA2 | MEDIUM | false positive | requires asking before overwriting an existing file: a confirmation gate |
| skills/ecs-modernize/references/blocker-detection.md:145 | RA2 | MEDIUM | false positive | lists host init/cron dependencies as migration blockers to detect; creates no persistence |
| skills/ecs-modernize/references/code-transformation-agent-led.md:453 | EA2 | MEDIUM | false positive | forbids touching an unapproved branch without approval: a confirmation gate |
| skills/ecs-modernize/references/deploy-verify-handoff.md:275 | EA2 | MEDIUM | false positive | tells the agent not to fabricate a verification result; no autonomous action |
| skills/ecs-modernize/references/report-generation.md:108 | OH3 | MEDIUM | false positive | filename sanitising rule ('no trimming' of hyphens); output is bounded |
| skills/ecs-modernize/references/report-generation.md:130 | EA2 | MEDIUM | false positive | requires clear approval before overwriting: a confirmation gate |

## skills/ecs-observability

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/ecs-observability/SKILL.md:90 | PE2 | MEDIUM | false positive | documents that ECS Exec commands run as root, next to the controls that govern Exec; no root command is run |
| skills/ecs-observability/references/launch-type-matrix.md:14 | EA2 | MEDIUM | false positive | tells the agent to check docs live before asserting support: the opposite of acting without verification |
| skills/ecs-observability/references/log-delivery.md:77 | EA2 | MEDIUM | false positive | tells the agent not to extend log-driver support without verification |

## skills/ecs-operation-review

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/ecs-operation-review/SKILL.md:1 | LP3 | MEDIUM | accepted | frontmatter declares no allowed-tools; the skill's read-only tool use is stated in its body, so this is a metadata gap, not a defect |
| skills/ecs-operation-review/SKILL.md:72 | EA1 | MEDIUM | false positive | forbids tool calls on activation until the user asks: a restriction |

## skills/ecs-recon

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/ecs-recon/SKILL.md:62 | PE3 | HIGH | false positive | names where AWS credentials can come from and says to test with `aws sts get-caller-identity`; it never reads the files |
| skills/ecs-recon/SKILL.md:62 | PE3 | HIGH | false positive | names where AWS credentials can come from and says to test with `aws sts get-caller-identity`; it never reads the files |
| skills/ecs-recon/SKILL.md:101 | AE1 | HIGH | accepted | points to references/iac.md (28 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/ecs-recon/references/autoscaling.md:26 | PE1 | LOW | false positive | the line lists read-only IAM actions; `permissions:` is a heading, not a wildcard grant |
| skills/ecs-recon/references/cicd.md:32 | PE1 | LOW | false positive | the line lists read-only IAM actions; `permissions:` is a heading, not a wildcard grant |
| skills/ecs-recon/references/compute.md:28 | PE1 | LOW | false positive | the line lists read-only IAM actions; `permissions:` is a heading, not a wildcard grant |
| skills/ecs-recon/references/deployment.md:28 | PE1 | LOW | false positive | the line lists read-only IAM actions; `permissions:` is a heading, not a wildcard grant |
| skills/ecs-recon/references/iac.md:31 | PE1 | LOW | false positive | the line lists read-only IAM actions; `permissions:` is a heading, not a wildcard grant |
| skills/ecs-recon/references/networking.md:29 | PE1 | LOW | false positive | the line lists read-only IAM actions; `permissions:` is a heading, not a wildcard grant |
| skills/ecs-recon/references/networking.md:308 | SSRF1 | HIGH | false positive | App Mesh EgressIgnoredIPs example value in a task definition; no request to the metadata endpoint |
| skills/ecs-recon/references/networking.md:417 | AR2 | HIGH | false positive | asks for factual reporting without judgement in a recon skill; not suppressing safety warnings |
| skills/ecs-recon/references/observability.md:27 | PE1 | LOW | false positive | the line lists read-only IAM actions; `permissions:` is a heading, not a wildcard grant |
| skills/ecs-recon/references/security.md:27 | PE1 | LOW | false positive | the line lists read-only IAM actions; `permissions:` is a heading, not a wildcard grant |
| skills/ecs-recon/references/task-definitions.md:25 | PE1 | LOW | false positive | the line lists read-only IAM actions; `permissions:` is a heading, not a wildcard grant |

## skills/ecs-security

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/ecs-security/SKILL.md:56 | AE1 | HIGH | accepted | points to references/identity-and-access.md (14 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/ecs-security/SKILL.md:87 | SSRF1 | HIGH | false positive | documents how to block task access to IMDS (ECS_AWSVPC_BLOCK_IMDS, iptables DROP, hop limit 1): a control |
| skills/ecs-security/SKILL.md:88 | AE1 | HIGH | accepted | points to references/identity-and-access.md (14 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/ecs-security/SKILL.md:102 | AE1 | HIGH | accepted | points to references/identity-and-access.md (14 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/ecs-security/SKILL.md:125 | AE1 | HIGH | accepted | points to references/identity-and-access.md (14 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/ecs-security/references/shared-responsibility.md:16 | PE3 | HIGH | false positive | shared-responsibility prose on task credential isolation; no credential access |

## skills/eks-best-practices

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/eks-best-practices/SKILL.md:54 | AE1 | HIGH | accepted | points to references/hybrid-deployments.md (46 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-best-practices/SKILL.md:115 | AE1 | HIGH | accepted | points to references/hybrid-deployments.md (46 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-best-practices/SKILL.md:144 | AE1 | HIGH | accepted | points to references/networking.md (28 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-best-practices/SKILL.md:393 | AE1 | HIGH | accepted | points to references/observability.md (31 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-best-practices/SKILL.md:407 | AE1 | HIGH | accepted | points to references/argocd-patterns.md (18 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-best-practices/SKILL.md:421 | AE1 | HIGH | accepted | points to references/networking.md (28 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-best-practices/SKILL.md:431 | AE1 | HIGH | accepted | points to references/observability.md (31 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-best-practices/SKILL.md:433 | AE1 | HIGH | accepted | points to references/argocd-patterns.md (18 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-best-practices/SKILL.md:436 | AE1 | HIGH | accepted | points to references/hybrid-deployments.md (46 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-best-practices/references/cluster-upgrades.md:465 | PE4 | HIGH | false positive | names the Docker socket to detect dependencies before the dockershim removal; no socket mount |
| skills/eks-best-practices/references/observability.md:426 | EA2 | MEDIUM | false positive | describes the CloudWatch add-on deploying DCGM Exporter; no agent action |
| skills/eks-best-practices/references/reliability-advanced.md:110 | AR3 | HIGH | false positive | table describes Gatekeeper behaviour; not an instruction to the agent |
| skills/eks-best-practices/references/scalability.md:153 | PE3 | HIGH | false positive | sample kubeconfig YAML showing a client setting (compression); no credentials |
| skills/eks-best-practices/references/scalability.md:385 | PE2 | MEDIUM | false positive | `sudo ipvsadm -L` is a read-only listing on the node to validate IPVS mode, run by the operator |
| skills/eks-best-practices/references/security-runtime-network.md:94 | PE3 | HIGH | false positive | lists /etc/shadow access as a Falco runtime-detection signal; no file read |
| skills/eks-best-practices/references/security.md:296 | TM4 | HIGH | false positive | advises against privileged: true and host namespaces: a control |
| skills/eks-best-practices/references/security.md:301 | PE2 | MEDIUM | false positive | explains that containers run as root by default, as context for dropping capabilities |
| skills/eks-best-practices/references/security.md:418 | PE3 | HIGH | false positive | example update-kubeconfig with a placeholder cross-account role ARN; standard client setup |

## skills/eks-build

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/eks-build/SKILL.md:122 | AE1 | HIGH | accepted | points to scripts/validate_project.sh (23 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-build/SKILL.md:277 | PE3 | HIGH | false positive | standard `aws eks update-kubeconfig` in post-deploy access instructions; no credential read |
| skills/eks-build/references/customization-guide.md:56 | SSRF1 | HIGH | false positive | 169.254.169.254 sits in the NO_PROXY exclusion list so IMDS is not sent through the proxy; no request to it |
| skills/eks-build/references/customization-guide.md:68 | SSRF1 | HIGH | false positive | 169.254.169.254 sits in the NO_PROXY exclusion list so IMDS is not sent through the proxy; no request to it |
| skills/eks-build/references/customization-guide.md:73 | SSRF1 | HIGH | false positive | 169.254.169.254 sits in the NO_PROXY exclusion list so IMDS is not sent through the proxy; no request to it |
| skills/eks-build/references/customization-guide.md:82 | SSRF1 | HIGH | false positive | 169.254.169.254 sits in the NO_PROXY exclusion list so IMDS is not sent through the proxy; no request to it |
| skills/eks-build/references/lessons-learned.md:107 | TM1 | HIGH | accepted | documented outage recovery (remove the Multus CNI config on nodes) for a feature the skill ships disabled; run by the operator |
| skills/eks-build/references/lessons-learned.md:482 | TM2 | HIGH | accepted | documented manual workaround for the provider's capability-delete hang on teardown of the generated stack; user-run |
| skills/eks-build/references/lessons-learned.md:483 | EA2 | MEDIUM | accepted | same teardown workaround: destroy of the generated test stack after removing the hung capabilities; user-run, not an agent step |

## skills/eks-cost-intelligence

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/eks-cost-intelligence/README.md:53 | PE1 | LOW | false positive | lists read-only IAM actions; `permissions:` is a heading, not a wildcard grant |
| skills/eks-cost-intelligence/SKILL.md:1 | LP3 | MEDIUM | accepted | frontmatter declares no allowed-tools; the read-only tool use is stated in the body: a metadata gap, not a defect |
| skills/eks-cost-intelligence/SKILL.md:45 | PE3 | HIGH | false positive | prerequisite line naming ~/.aws/credentials as where `aws configure` stores credentials; no read |
| skills/eks-cost-intelligence/SKILL.md:66 | AE1 | HIGH | accepted | points to references/cost-estimation-fallback.md (26 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-cost-intelligence/SKILL.md:90 | AE1 | HIGH | accepted | points to references/cost-data-collection.md (44 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-cost-intelligence/SKILL.md:120 | PE3 | HIGH | false positive | tells the agent to stop and ask the user to add a kubeconfig entry and to leave current-context unchanged: a control |
| skills/eks-cost-intelligence/SKILL.md:260 | AE1 | HIGH | accepted | points to references/cost-data-collection.md (44 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-cost-intelligence/SKILL.md:270 | EA1 | MEDIUM | false positive | forbids tool calls on activation until the user asks: a restriction |
| skills/eks-cost-intelligence/SKILL.md:295 | AE1 | HIGH | accepted | points to references/cost-data-collection.md (44 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-cost-intelligence/SKILL.md:297 | AE1 | HIGH | accepted | points to references/cost-estimation-fallback.md (26 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-cost-intelligence/references/cost-estimation-fallback.md:25 | P4 | MEDIUM | false positive | prefers live pricing API over static tables; a data-source preference |
| skills/eks-cost-intelligence/references/observability-costs.md:567 | PE3 | HIGH | false positive | jq `select(.env != null)` then filters to log-level variable names only; no credential file |
| skills/eks-cost-intelligence/references/observability-costs.md:582 | PE3 | HIGH | false positive | jq `select(.env != null)` then filters to log-level variable names only; no credential file |
| skills/eks-cost-intelligence/references/observability-costs.md:628 | PE3 | HIGH | false positive | comment: parse containers[].env for LOG_LEVEL patterns only |

## skills/eks-design

No findings.

## skills/eks-genai

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/eks-genai/SKILL.md:57 | AE1 | HIGH | accepted | points to references/distributed-training.md (13 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-genai/SKILL.md:117 | AE1 | HIGH | accepted | points to references/distributed-training.md (13 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-genai/SKILL.md:125 | AE1 | HIGH | accepted | points to references/use-cases.md (13 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |

## skills/eks-ingress-migration

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/eks-ingress-migration/SKILL.md:1 | LP3 | MEDIUM | accepted | frontmatter declares no allowed-tools; the read-only tool use is stated in the body: a metadata gap, not a defect |
| skills/eks-ingress-migration/SKILL.md:34 | AE1 | HIGH | accepted | points to references/report-generation.md (66 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-ingress-migration/SKILL.md:69 | AE1 | HIGH | accepted | points to references/atx-guide.md (12 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-ingress-migration/SKILL.md:76 | AE1 | HIGH | accepted | points to references/report-generation.md (66 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-ingress-migration/SKILL.md:80 | AE1 | HIGH | accepted | points to references/atx-guide.md (12 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-ingress-migration/SKILL.md:84 | EA1 | MEDIUM | false positive | forbids tool calls on activation until the user asks: a restriction |
| skills/eks-ingress-migration/SKILL.md:118 | PE1 | LOW | false positive | heading for a list of read-only IAM actions, not a wildcard grant |
| skills/eks-ingress-migration/SKILL.md:175 | PE3 | HIGH | false positive | tells the agent to stop and ask the user to add a kubeconfig entry and to leave current-context unchanged: a control |
| skills/eks-ingress-migration/SKILL.md:262 | AE1 | HIGH | accepted | points to references/report-generation.md (66 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-ingress-migration/SKILL.md:326 | AE1 | HIGH | accepted | points to references/report-generation.md (66 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-ingress-migration/SKILL.md:331 | AE1 | HIGH | accepted | points to references/report-generation.md (66 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-ingress-migration/SKILL.md:333 | AE1 | HIGH | accepted | points to references/report-generation.md (66 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-ingress-migration/references/report-generation.md:689 | MP3 | HIGH | false positive | report-template instruction to relabel a rule as review and hand-port; no agent memory is touched |
| skills/eks-ingress-migration/tools/report_to_html.py:291 | YR4 | HIGH | false positive | HTML report builds a data: URI download link for a generated YAML manifest; no tool metadata |

## skills/eks-mcp-server

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/eks-mcp-server/SKILL.md:3 | RP1 | MEDIUM | true positive | fixed on main by https://github.com/aws-samples/sample-apex-skills/pull/366 (merged as 6fdc1cf): the setup examples ran the server unpinned (`awslabs.eks-mcp-server@latest` in references/self-hosted-setup.md, `mcp-proxy-for-aws@latest` in references/aws-hosted-setup.md); both now read `@<version>`, the version the user chooses in SKILL.md Step 1b. The runbook's own run is the row above |
| skills/eks-mcp-server/SKILL.md:32 | PE3 | HIGH | false positive | explains the self-hosted mode supports kubeconfig/OIDC auth; setup prose, no credential read |
| skills/eks-mcp-server/SKILL.md:32 | PE3 | HIGH | false positive | explains the self-hosted mode supports kubeconfig/OIDC auth; setup prose, no credential read |
| skills/eks-mcp-server/SKILL.md:115 | EA1 | MEDIUM | false positive | forbids tool calls on activation; starts with Step 0 then asks: a restriction |
| skills/eks-mcp-server/references/aws-hosted-setup.md:14 | SC2 | LOW | accepted | official uv installer via curl / sh, shown as a user-run prerequisite; the vendor's documented install |
| skills/eks-mcp-server/references/self-hosted-setup.md:10 | SC2 | LOW | accepted | official uv installer via curl / sh, shown as a user-run prerequisite; the vendor's documented install |
| skills/eks-mcp-server/references/self-hosted-setup.md:12 | PE3 | HIGH | false positive | prerequisite: a valid kubeconfig for kubeconfig mode; setup prose |
| skills/eks-mcp-server/references/self-hosted-setup.md:12 | PE3 | HIGH | false positive | prerequisite: a valid kubeconfig for kubeconfig mode; setup prose |
| skills/eks-mcp-server/references/self-hosted-setup.md:22 | PE3 | HIGH | false positive | auth-mode table row naming kubeconfig mode; setup prose |
| skills/eks-mcp-server/references/self-hosted-setup.md:58 | RA2 | MEDIUM | true positive | open, not suppressed: https://github.com/aws-samples/sample-apex-skills/issues/236 (open) tracks this. Rule name is wrong (no persistence), but the text tells users to attach IAMFullAccess, AmazonVPCFullAccess, AWSCloudFormationFullAccess and eks:* for write mode with no scoping (line 60 on main at 4e68e6d), and the basic configuration examples turn on `--allow-write` and `--allow-sensitive-data-access`; IAMFullAccess is a privilege-escalation path. https://github.com/aws-samples/sample-apex-skills/pull/317 (open) adds a least-privilege note and keeps the IAMFullAccess line |
| skills/eks-mcp-server/references/self-hosted-setup.md:89 | PE3 | HIGH | false positive | section heading for kubeconfig mode |
| skills/eks-mcp-server/references/self-hosted-setup.md:102 | PE3 | HIGH | false positive | MCP config example sets EKS_AUTH_MODE=kubeconfig; the server reads the user's own kubeconfig as designed |
| skills/eks-mcp-server/references/self-hosted-setup.md:103 | PE3 | HIGH | false positive | MCP config example sets KUBECONFIG to the default path for the server it launches; no extra read |
| skills/eks-mcp-server/references/self-hosted-setup.md:103 | PE3 | HIGH | false positive | MCP config example sets KUBECONFIG to the default path for the server it launches; no extra read |
| skills/eks-mcp-server/references/self-hosted-setup.md:111 | PE3 | HIGH | false positive | note that AWS tools are disabled in kubeconfig mode; setup prose |
| skills/eks-mcp-server/references/self-hosted-setup.md:154 | PE3 | HIGH | false positive | explains how to switch auth mode by env var; setup prose |
| skills/eks-mcp-server/references/self-hosted-setup.md:162 | PE3 | HIGH | false positive | env var table row for EKS_AUTH_MODE; setup prose |
| skills/eks-mcp-server/references/self-hosted-setup.md:163 | PE3 | HIGH | false positive | env var table row: KUBECONFIG defaults to ~/.kube/config; documents the server's own config input |
| skills/eks-mcp-server/references/self-hosted-setup.md:163 | PE3 | HIGH | false positive | env var table row: KUBECONFIG defaults to ~/.kube/config; documents the server's own config input |
| skills/eks-mcp-server/references/self-hosted-setup.md:163 | PE3 | HIGH | false positive | env var table row: KUBECONFIG defaults to ~/.kube/config; documents the server's own config input |
| skills/eks-mcp-server/references/self-hosted-setup.md:173 | PE3 | HIGH | false positive | tells the operator to match the MCP endpoint to describe-cluster before any request: a control |
| skills/eks-mcp-server/references/self-hosted-setup.md:173 | PE3 | HIGH | false positive | tells the operator to match the MCP endpoint to describe-cluster before any request: a control |
| skills/eks-mcp-server/references/self-hosted-setup.md:195 | PE3 | HIGH | false positive | troubleshooting row for kubeconfig RBAC or path; setup prose |
| skills/eks-mcp-server/references/self-hosted-setup.md:198 | PE3 | HIGH | false positive | troubleshooting row for kubeconfig RBAC or path; setup prose |
| skills/eks-mcp-server/references/self-hosted-setup.md:198 | PE3 | HIGH | false positive | troubleshooting row for kubeconfig RBAC or path; setup prose |

## skills/eks-operation-review

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/eks-operation-review/LICENSE:12 | EA3 | LOW | false positive | license warranty disclaimer text ('NOT LIMITED TO') |
| skills/eks-operation-review/SKILL.md:1 | LP3 | MEDIUM | accepted | frontmatter declares no allowed-tools; the read-only tool use is stated in the body: a metadata gap, not a defect |
| skills/eks-operation-review/SKILL.md:24 | PE3 | HIGH | false positive | prerequisite: pre-flight sets up kubeconfig via `aws eks update-kubeconfig`; standard client setup |
| skills/eks-operation-review/SKILL.md:24 | PE3 | HIGH | false positive | prerequisite: pre-flight sets up kubeconfig via `aws eks update-kubeconfig`; standard client setup |
| skills/eks-operation-review/references/autoscaling.md:85 | EA2 | MEDIUM | false positive | says placement cannot be verified without live reads and routes it to Investigate Manually |

## skills/eks-platform-engineering

No findings.

## skills/eks-recon

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/eks-recon/SKILL.md:53 | PE3 | HIGH | false positive | prerequisite note that kubeconfig setup may be needed |
| skills/eks-recon/SKILL.md:194 | PE3 | HIGH | false positive | detect the region from kubeconfig or CLI; no credential read |
| skills/eks-recon/SKILL.md:212 | PE3 | HIGH | false positive | fallback order note: credentials may come from config files, instance profile or env; no file read |
| skills/eks-recon/SKILL.md:217 | PE3 | HIGH | false positive | use the region in a cluster ARN shown in kubeconfig; no credential read |
| skills/eks-recon/SKILL.md:220 | PE3 | HIGH | false positive | names where AWS credentials can come from and says to test with `aws sts get-caller-identity`; it never reads the files |
| skills/eks-recon/SKILL.md:220 | PE3 | HIGH | false positive | names where AWS credentials can come from and says to test with `aws sts get-caller-identity`; it never reads the files |
| skills/eks-recon/SKILL.md:222 | PE3 | HIGH | false positive | requires binding kubectl to the named cluster before detection: a wrong-cluster control |
| skills/eks-recon/agents/addons-recon.md:42 | AR2 | HIGH | false positive | recon reports add-on status as facts and leaves judgement to other skills; not suppressing warnings |
| skills/eks-recon/references/cicd.md:431 | PE3 | HIGH | false positive | `kubeconfig` is a Flux documentation URL anchor |
| skills/eks-recon/references/cluster-basics.md:173 | PE3 | HIGH | false positive | runs `kubectl config current-context` to parse the region; read-only |
| skills/eks-recon/references/iac.md:417 | EA2 | MEDIUM | false positive | tells the agent to report detected IaC tools as facts rather than ask; read-only, no high-impact action |
| skills/eks-recon/references/networking.md:283 | PE3 | HIGH | false positive | jq reads named aws-node CNI env settings from the DaemonSet spec; no credential file |
| skills/eks-recon/references/networking.md:290 | PE3 | HIGH | false positive | jq reads named aws-node CNI env settings from the DaemonSet spec; no credential file |
| skills/eks-recon/references/networking.md:294 | PE3 | HIGH | false positive | jq reads named aws-node CNI env settings from the DaemonSet spec; no credential file |
| skills/eks-recon/references/networking.md:298 | PE3 | HIGH | false positive | jq reads named aws-node CNI env settings from the DaemonSet spec; no credential file |
| skills/eks-recon/references/report-comparison.md:42 | PE3 | HIGH | false positive | the line forbids echoing a supplied kubeconfig: a control |

## skills/eks-security

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/eks-security/SKILL.md:1 | LP3 | MEDIUM | accepted | frontmatter declares no allowed-tools; the read-only tool use is stated in the body: a metadata gap, not a defect |
| skills/eks-security/SKILL.md:42 | AE1 | HIGH | accepted | points to assets/collect.sh (27 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-security/SKILL.md:42 | AE1 | HIGH | accepted | points to assets/posture_collect.sh (25 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-security/SKILL.md:54 | PE3 | HIGH | false positive | documents the optional --kubeconfig flag of its read-only collector |
| skills/eks-security/SKILL.md:92 | PE3 | HIGH | false positive | documents the optional --kubeconfig flag of its read-only collector |
| skills/eks-security/SKILL.md:138 | AE1 | HIGH | accepted | points to references/runtime-security.md (5 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-security/SKILL.md:250 | AE1 | HIGH | accepted | points to references/runtime-security.md (5 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-security/assets/collect.sh:10 | PE3 | HIGH | false positive | usage text for the optional --kubeconfig flag |
| skills/eks-security/assets/collect.sh:29 | PE3 | HIGH | false positive | usage text for the optional --kubeconfig flag |
| skills/eks-security/assets/collect.sh:42 | PE3 | HIGH | false positive | argument parsing stores the --kubeconfig path |
| skills/eks-security/assets/collect.sh:62 | PE3 | HIGH | false positive | validates the --kubeconfig path (readable file, no control characters) before use: input checking |
| skills/eks-security/assets/collect.sh:71 | PE2 | MEDIUM | false positive | chmod 700 restricts the output dir to the owner: tightens access |
| skills/eks-security/assets/collect.sh:77 | PE3 | HIGH | false positive | passes the user-chosen kubeconfig to kubectl for read-only calls |
| skills/eks-security/assets/collect.sh:98 | TM2 | HIGH | false positive | `rm -f --` removes the collector's own temp/error files inside its output dir; quoted paths, no wildcard outside it |
| skills/eks-security/assets/collect.sh:141 | TM2 | HIGH | false positive | `rm -f --` removes the collector's own temp/error files inside its output dir; quoted paths, no wildcard outside it |
| skills/eks-security/assets/collect.sh:168 | TM1 | HIGH | false positive | `rm -f --` removes the collector's own temp files inside $OUT; scoped and quoted |
| skills/eks-security/assets/collect.sh:168 | TM2 | HIGH | false positive | `rm -f --` removes the collector's own temp/error files inside its output dir; quoted paths, no wildcard outside it |
| skills/eks-security/assets/collect.sh:412 | TM1 | HIGH | false positive | `rm -f --` removes the collector's own temp files inside $OUT; scoped and quoted |
| skills/eks-security/assets/collect.sh:415 | TM1 | HIGH | false positive | removes the collector's dot-prefixed scratch JSON files inside $OUT only |
| skills/eks-security/assets/collect.sh:416 | PE2 | MEDIUM | false positive | chmod 600 restricts collected JSON to the owner: tightens access |
| skills/eks-security/assets/components.json:18 | E1 | MEDIUM | accepted | advisory source catalogue entry for the public GitHub advisory API; read-only GET, nothing sent beyond the request URL |
| skills/eks-security/assets/posture_collect.sh:12 | PE3 | HIGH | false positive | usage text for the optional --kubeconfig flag |
| skills/eks-security/assets/posture_collect.sh:50 | PE3 | HIGH | false positive | usage text for the optional --kubeconfig flag |
| skills/eks-security/assets/posture_collect.sh:63 | PE3 | HIGH | false positive | argument parsing stores the --kubeconfig path |
| skills/eks-security/assets/posture_collect.sh:87 | PE3 | HIGH | false positive | validates the --kubeconfig path (readable file, no control characters) before use: input checking |
| skills/eks-security/assets/posture_collect.sh:87 | PE3 | HIGH | false positive | validates the --kubeconfig path (readable file, no control characters) before use: input checking |
| skills/eks-security/assets/posture_collect.sh:88 | PE3 | HIGH | false positive | validates the --kubeconfig path (readable file, no control characters) before use: input checking |
| skills/eks-security/assets/posture_collect.sh:88 | PE3 | HIGH | false positive | validates the --kubeconfig path (readable file, no control characters) before use: input checking |
| skills/eks-security/assets/posture_collect.sh:97 | PE2 | MEDIUM | false positive | chmod 700 restricts the output dir to the owner: tightens access |
| skills/eks-security/assets/posture_collect.sh:105 | PE3 | HIGH | false positive | kubectl wrapper passes the given kubeconfig for read-only get and auth can-i calls |
| skills/eks-security/assets/posture_collect.sh:131 | PE3 | HIGH | false positive | kubectl wrapper passes the given kubeconfig for read-only get and auth can-i calls |
| skills/eks-security/assets/posture_collect.sh:211 | PE3 | HIGH | false positive | kubectl wrapper passes the given kubeconfig for read-only get and auth can-i calls |
| skills/eks-security/assets/posture_collect.sh:263 | TM1 | HIGH | false positive | `rm -f --` removes the posture collector's own scratch files inside $P; scoped and quoted |
| skills/eks-security/assets/posture_collect.sh:293 | TM1 | HIGH | false positive | `rm -f --` removes the posture collector's own scratch files inside $P; scoped and quoted |
| skills/eks-security/assets/posture_collect.sh:317 | TM1 | HIGH | false positive | `rm -f --` removes the posture collector's own scratch files inside $P; scoped and quoted |
| skills/eks-security/assets/posture_collect.sh:363 | TM1 | HIGH | false positive | `rm -f --` removes the posture collector's own scratch files inside $P; scoped and quoted |
| skills/eks-security/assets/posture_reduce.sh:117 | TM4 | HIGH | false positive | check catalogue entry recommending removal of privileged: true: a control |
| skills/eks-security/assets/posture_reduce.sh:196 | PE2 | MEDIUM | false positive | chmod 600 restricts collected JSON to the owner: tightens access |
| skills/eks-security/assets/posture_score.sh:605 | AR3 | HIGH | false positive | scorer message explaining that Gatekeeper templates without Constraint objects enforce nothing; not an agent instruction |
| skills/eks-security/assets/posture_score.sh:609 | AR3 | HIGH | false positive | scorer message explaining that Gatekeeper templates without Constraint objects enforce nothing; not an agent instruction |
| skills/eks-security/assets/posture_score.sh:615 | AR3 | HIGH | false positive | scorer message explaining that Gatekeeper templates without Constraint objects enforce nothing; not an agent instruction |
| skills/eks-security/assets/posture_score.sh:616 | AR3 | HIGH | false positive | scorer message explaining that Gatekeeper templates without Constraint objects enforce nothing; not an agent instruction |
| skills/eks-security/assets/posture_score.sh:631 | TM4 | HIGH | false positive | comment describing a non-compliant sidecar the check is meant to catch |
| skills/eks-security/references/advisory-sources.md:14 | E1 | MEDIUM | accepted | documents the read-only GitHub advisory API lookup; nothing sent beyond the request URL |
| skills/eks-security/references/posture-check.md:13 | PE3 | HIGH | false positive | command table documenting the optional --kubeconfig flag |

## skills/eks-upgrade-check

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/eks-upgrade-check/LICENSE:12 | EA3 | LOW | false positive | license warranty disclaimer text ('NOT LIMITED TO') |
| skills/eks-upgrade-check/SKILL.md:64 | PE3 | HIGH | false positive | prerequisite line naming ~/.aws/credentials as where `aws configure` stores credentials; no read |
| skills/eks-upgrade-check/SKILL.md:66 | PE1 | LOW | false positive | heading for a list of read-only IAM actions, not a wildcard grant |
| skills/eks-upgrade-check/SKILL.md:213 | EA1 | MEDIUM | false positive | forbids tool calls on activation until the user asks: a restriction |

## skills/eks-well-architected-review

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/eks-well-architected-review/SKILL.md:10 | PE3 | HIGH | accepted | allowed-tools grants `aws eks update-kubeconfig:*`, needed to bind the review to one cluster; references/workflow.md:444-446 documents that it can write any --kubeconfig path |
| skills/eks-well-architected-review/SKILL.md:48 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:50 | AE1 | HIGH | accepted | points to assets/render-report.py (315 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:61 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:61 | AE1 | HIGH | accepted | points to assets/render-report.py (315 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:87 | AE1 | HIGH | accepted | points to assets/render-report.py (315 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:95 | PE3 | HIGH | false positive | read-only rule text: update-kubeconfig writes only the work-dir kubeconfig |
| skills/eks-well-architected-review/SKILL.md:96 | PE3 | HIGH | false positive | read-only rule text: update-kubeconfig writes only the work-dir kubeconfig |
| skills/eks-well-architected-review/SKILL.md:98 | PE3 | HIGH | false positive | read-only rule text: update-kubeconfig writes only the work-dir kubeconfig |
| skills/eks-well-architected-review/SKILL.md:105 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:130 | AE1 | HIGH | accepted | points to assets/render-report.py (315 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:130 | AE1 | HIGH | accepted | points to assets/reduce.sh (181 KB, bundled in the skill); the scanner inspected it only in part (runtime_limit, static_parse_limit): a coverage gap, not a defect |
| skills/eks-well-architected-review/SKILL.md:131 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:163 | AE1 | HIGH | accepted | points to assets/collect.sh (147 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-well-architected-review/SKILL.md:163 | PE3 | HIGH | false positive | profile and assume-role guidance for update-kubeconfig; standard client setup |
| skills/eks-well-architected-review/SKILL.md:167 | PE3 | HIGH | false positive | profile and assume-role guidance for update-kubeconfig; standard client setup |
| skills/eks-well-architected-review/SKILL.md:169 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:173 | AE1 | HIGH | accepted | points to assets/collect.sh (147 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-well-architected-review/SKILL.md:176 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:182 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:184 | AE1 | HIGH | accepted | points to assets/collect.sh (147 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-well-architected-review/SKILL.md:190 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:205 | PE3 | HIGH | false positive | Step 1 writes a kubeconfig inside the work dir, not ~/.kube/config: a containment control |
| skills/eks-well-architected-review/SKILL.md:205 | PE3 | HIGH | false positive | Step 1 writes a kubeconfig inside the work dir, not ~/.kube/config: a containment control |
| skills/eks-well-architected-review/SKILL.md:205 | PE3 | HIGH | false positive | Step 1 writes a kubeconfig inside the work dir, not ~/.kube/config: a containment control |
| skills/eks-well-architected-review/SKILL.md:206 | PE3 | HIGH | false positive | read-only `kubectl get nodes` against the work-dir kubeconfig |
| skills/eks-well-architected-review/SKILL.md:206 | PE3 | HIGH | false positive | read-only `kubectl get nodes` against the work-dir kubeconfig |
| skills/eks-well-architected-review/SKILL.md:214 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:214 | PE3 | HIGH | false positive | pointer to the workflow section on the kubeconfig step |
| skills/eks-well-architected-review/SKILL.md:220 | PE3 | HIGH | false positive | collector invocation passing the work-dir kubeconfig |
| skills/eks-well-architected-review/SKILL.md:220 | PE3 | HIGH | false positive | collector invocation passing the work-dir kubeconfig |
| skills/eks-well-architected-review/SKILL.md:223 | AE1 | HIGH | accepted | points to assets/collect.sh (147 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-well-architected-review/SKILL.md:230 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:230 | PE3 | HIGH | false positive | pointer to the workflow section on the kubeconfig step |
| skills/eks-well-architected-review/SKILL.md:232 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:250 | AE1 | HIGH | accepted | points to assets/render-report.py (315 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:252 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:256 | AE1 | HIGH | accepted | points to assets/reduce.sh (181 KB, bundled in the skill); the scanner inspected it only in part (runtime_limit, static_parse_limit): a coverage gap, not a defect |
| skills/eks-well-architected-review/SKILL.md:260 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:284 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:296 | AE1 | HIGH | accepted | points to assets/reduce.sh (181 KB, bundled in the skill); the scanner inspected it only in part (runtime_limit, static_parse_limit): a coverage gap, not a defect |
| skills/eks-well-architected-review/SKILL.md:298 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:307 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:316 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:335 | AE1 | HIGH | accepted | points to assets/render-report.py (315 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:338 | AE1 | HIGH | accepted | points to assets/collect.sh (147 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/eks-well-architected-review/SKILL.md:342 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:353 | AE1 | HIGH | accepted | points to assets/render-report.py (315 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:353 | AE1 | HIGH | accepted | points to assets/reduce.sh (181 KB, bundled in the skill); the scanner inspected it only in part (runtime_limit, static_parse_limit): a coverage gap, not a defect |
| skills/eks-well-architected-review/SKILL.md:366 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:380 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:388 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:408 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:413 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:437 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:437 | AE1 | HIGH | accepted | points to assets/render-report.py (315 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:439 | AE1 | HIGH | accepted | points to assets/render-report.py (315 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:452 | AE1 | HIGH | accepted | points to assets/render-report.py (315 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:453 | AE1 | HIGH | accepted | points to references/workflow.md (105 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:455 | AE1 | HIGH | accepted | points to assets/render-report.py (315 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/eks-well-architected-review/SKILL.md:475 | AE1 | HIGH | accepted | points to assets/reduce.sh (181 KB, bundled in the skill); the scanner inspected it only in part (runtime_limit, static_parse_limit): a coverage gap, not a defect |
| skills/eks-well-architected-review/assets/collect.sh:1 | LP1 | HIGH | accepted | collector calls the AWS and Kubernetes APIs by design, read-only; SKILL.md allowed-tools lists those reads, so 'network' is declared in substance |
| skills/eks-well-architected-review/assets/collect.sh:9 | PE3 | HIGH | false positive | usage text for the optional --kubeconfig flag |
| skills/eks-well-architected-review/assets/collect.sh:9 | PE3 | HIGH | false positive | usage text naming kubectl's default ~/.kube/config; no extra read |
| skills/eks-well-architected-review/assets/collect.sh:9 | PE3 | HIGH | false positive | usage text naming kubectl's own KUBECONFIG default |
| skills/eks-well-architected-review/assets/collect.sh:40 | PE2 | MEDIUM | false positive | comment on the chmod 700 of the work dir: tightens access |
| skills/eks-well-architected-review/assets/collect.sh:42 | RA2 | MEDIUM | false positive | comment on umask scope inside the work dir; no persistence |
| skills/eks-well-architected-review/assets/collect.sh:55 | PE3 | HIGH | false positive | usage text for the optional --kubeconfig flag |
| skills/eks-well-architected-review/assets/collect.sh:57 | PE3 | HIGH | false positive | usage text for the optional --kubeconfig flag |
| skills/eks-well-architected-review/assets/collect.sh:58 | PE3 | HIGH | false positive | usage text naming kubectl's default ~/.kube/config; no extra read |
| skills/eks-well-architected-review/assets/collect.sh:58 | PE3 | HIGH | false positive | usage text naming kubectl's own KUBECONFIG default |
| skills/eks-well-architected-review/assets/collect.sh:61 | PE3 | HIGH | false positive | argument parsing stores the --kubeconfig path |
| skills/eks-well-architected-review/assets/collect.sh:61 | PE3 | HIGH | false positive | comment: KUBECONFIG is read by kubectl itself, not by the script |
| skills/eks-well-architected-review/assets/collect.sh:69 | PE3 | HIGH | false positive | argument parsing stores the --kubeconfig path |
| skills/eks-well-architected-review/assets/collect.sh:189 | PE3 | HIGH | false positive | comment: without --kubeconfig, kubectl only reads its own default config |
| skills/eks-well-architected-review/assets/collect.sh:189 | PE3 | HIGH | false positive | comment: kubectl only reads its default config when --kubeconfig is absent |
| skills/eks-well-architected-review/assets/collect.sh:189 | PE3 | HIGH | false positive | comment: kubectl only reads its default config when --kubeconfig is absent |
| skills/eks-well-architected-review/assets/collect.sh:194 | PE3 | HIGH | false positive | refuses a --kubeconfig path with control characters or that is unreadable: input checking |
| skills/eks-well-architected-review/assets/collect.sh:196 | PE3 | HIGH | false positive | refuses a --kubeconfig path with control characters or that is unreadable: input checking |
| skills/eks-well-architected-review/assets/collect.sh:197 | PE3 | HIGH | false positive | error hint telling the user how to create the kubeconfig with update-kubeconfig |
| skills/eks-well-architected-review/assets/collect.sh:197 | PE3 | HIGH | false positive | error hint telling the user how to create the kubeconfig with update-kubeconfig |
| skills/eks-well-architected-review/assets/collect.sh:262 | PE2 | MEDIUM | false positive | comment explaining when the chmod 700 is skipped for a pre-created dir |
| skills/eks-well-architected-review/assets/collect.sh:307 | PE2 | MEDIUM | false positive | comment on the chmod 700 of the work dir: tightens access |
| skills/eks-well-architected-review/assets/collect.sh:406 | PE2 | MEDIUM | false positive | chmod 700 restricts the work dir it created to the owner |
| skills/eks-well-architected-review/assets/collect.sh:559 | PE3 | HIGH | false positive | read-only `kubectl auth can-i` probe with the given kubeconfig |
| skills/eks-well-architected-review/assets/collect.sh:765 | PE3 | HIGH | false positive | comment explaining a preflight design choice about update-kubeconfig |
| skills/eks-well-architected-review/assets/collect.sh:769 | PE3 | HIGH | false positive | comment explaining a preflight design choice about update-kubeconfig |
| skills/eks-well-architected-review/assets/collect.sh:892 | PE3 | HIGH | false positive | error hint listing update-kubeconfig and a can-i check as fixes |
| skills/eks-well-architected-review/assets/collect.sh:892 | PE3 | HIGH | false positive | error hint listing update-kubeconfig and a can-i check as fixes |
| skills/eks-well-architected-review/assets/collect.sh:893 | PE3 | HIGH | false positive | error hint listing update-kubeconfig and a can-i check as fixes |
| skills/eks-well-architected-review/assets/collect.sh:922 | RA2 | MEDIUM | false positive | comment on making the work dir private from creation; no persistence |
| skills/eks-well-architected-review/assets/collect.sh:965 | PE3 | HIGH | false positive | comment on multi-cluster kubeconfigs and why the context is checked |
| skills/eks-well-architected-review/assets/collect.sh:982 | PE3 | HIGH | false positive | kubectl wrapper passes the work-dir kubeconfig for read-only calls |
| skills/eks-well-architected-review/assets/collect.sh:982 | PE3 | HIGH | false positive | kubectl wrapper passes the work-dir kubeconfig for read-only calls |
| skills/eks-well-architected-review/assets/collect.sh:983 | PE3 | HIGH | false positive | kubectl wrapper passes the work-dir kubeconfig for read-only calls |
| skills/eks-well-architected-review/assets/collect.sh:1124 | PE3 | HIGH | false positive | comments on comparing the kubeconfig CA with describe-cluster to prove cluster identity |
| skills/eks-well-architected-review/assets/collect.sh:1171 | PE3 | HIGH | false positive | comments on comparing the kubeconfig CA with describe-cluster to prove cluster identity |
| skills/eks-well-architected-review/assets/collect.sh:1177 | PE3 | HIGH | false positive | comments on comparing the kubeconfig CA with describe-cluster to prove cluster identity |
| skills/eks-well-architected-review/assets/collect.sh:1182 | PE3 | HIGH | false positive | comments on comparing the kubeconfig CA with describe-cluster to prove cluster identity |
| skills/eks-well-architected-review/assets/collect.sh:1185 | PE3 | HIGH | false positive | comments on comparing the kubeconfig CA with describe-cluster to prove cluster identity |
| skills/eks-well-architected-review/assets/collect.sh:1191 | PE3 | HIGH | false positive | comments on comparing the kubeconfig CA with describe-cluster to prove cluster identity |
| skills/eks-well-architected-review/assets/collect.sh:1222 | PE3 | HIGH | false positive | comment on kubeconfig CA file vs embedded CA forms |
| skills/eks-well-architected-review/assets/collect.sh:1223 | PE3 | HIGH | false positive | comment on kubeconfig CA file vs embedded CA forms |
| skills/eks-well-architected-review/assets/collect.sh:1224 | PE3 | HIGH | false positive | comment on kubeconfig CA file vs embedded CA forms |
| skills/eks-well-architected-review/assets/collect.sh:1229 | PE3 | HIGH | false positive | comment on resolving a relative CA path against the kubeconfig's directory |
| skills/eks-well-architected-review/assets/collect.sh:1230 | PE3 | HIGH | false positive | comment on resolving a relative CA path against the kubeconfig's directory |
| skills/eks-well-architected-review/assets/collect.sh:1234 | PE3 | HIGH | false positive | resolves the kubeconfig's directory only to locate the CA certificate it names, for the identity check; the CA is public material |
| skills/eks-well-architected-review/assets/collect.sh:1234 | PE3 | HIGH | false positive | resolves the kubeconfig's directory only to locate the CA certificate it names, for the identity check; the CA is public material |
| skills/eks-well-architected-review/assets/collect.sh:1245 | PE3 | HIGH | false positive | error text when cluster identity cannot be verified: a wrong-cluster control |
| skills/eks-well-architected-review/assets/collect.sh:1248 | PE3 | HIGH | false positive | error text when cluster identity cannot be verified: a wrong-cluster control |
| skills/eks-well-architected-review/assets/collect.sh:1250 | PE3 | HIGH | false positive | error hint to rerun update-kubeconfig for the right cluster |
| skills/eks-well-architected-review/assets/collect.sh:1250 | PE3 | HIGH | false positive | error hint to rerun update-kubeconfig for the right cluster |
| skills/eks-well-architected-review/assets/collect.sh:1259 | PE3 | HIGH | false positive | error hint to rerun update-kubeconfig for the right cluster |
| skills/eks-well-architected-review/assets/collect.sh:1259 | PE3 | HIGH | false positive | error hint to rerun update-kubeconfig for the right cluster |
| skills/eks-well-architected-review/assets/collect.sh:1262 | AR1 | HIGH | false positive | comment: disclose a tunnelled route rather than refuse the run; not an anti-refusal instruction to the agent |
| skills/eks-well-architected-review/assets/collect.sh:1265 | PE3 | HIGH | false positive | notice that the cluster is reached through a proxy or tunnel; disclosure, no credential read |
| skills/eks-well-architected-review/assets/collect.sh:1273 | PE3 | HIGH | false positive | notice about dual CA trust during rotation |
| skills/eks-well-architected-review/assets/collect.sh:1892 | PE3 | HIGH | false positive | error hint naming update-kubeconfig as a fix |
| skills/eks-well-architected-review/assets/reduce.sh:355 | AR2 | HIGH | false positive | comment describing a silent-drop bug the code guards against |
| skills/eks-well-architected-review/assets/reduce.sh:387 | AR2 | HIGH | false positive | comment describing a double-count bug the code guards against |
| skills/eks-well-architected-review/assets/render-report.py:638 | EA2 | MEDIUM | false positive | code comment on record-key validation; no autonomous action |
| skills/eks-well-architected-review/assets/render-report.py:1767 | P9 | HIGH | false positive | 112 empty lines between functions; checked: every padded line is empty, nothing hidden (cosmetic) |
| skills/eks-well-architected-review/assets/render-report.py:3348 | AR2 | HIGH | false positive | comment on avoiding a misleading report; no instruction to drop caveats |
| skills/eks-well-architected-review/assets/render-report.py:4735 | TM3 | MEDIUM | false positive | comments on writing the report with mode 0600 so it is never world-readable: a control |
| skills/eks-well-architected-review/assets/render-report.py:4739 | TM3 | MEDIUM | false positive | comments on writing the report with mode 0600 so it is never world-readable: a control |
| skills/eks-well-architected-review/assets/render-report.py:4742 | TM3 | MEDIUM | false positive | comments on writing the report with mode 0600 so it is never world-readable: a control |
| skills/eks-well-architected-review/assets/render-report.py:4755 | TM3 | MEDIUM | false positive | comments on writing the report with mode 0600 so it is never world-readable: a control |
| skills/eks-well-architected-review/assets/score.sh:93 | PE2 | MEDIUM | false positive | comment: collect.sh chmod 700s only a work dir it made |
| skills/eks-well-architected-review/assets/score.sh:93 | PE2 | MEDIUM | false positive | comment: collect.sh chmod 700s only a work dir it made |
| skills/eks-well-architected-review/references/operational-excellence.md:613 | P2 | HIGH | false positive | HTML maintainer note on sourcing and remediation design; no agent directive |
| skills/eks-well-architected-review/references/operational-excellence.md:619 | EA2 | MEDIUM | false positive | maintainer note requiring a verification step in remediations |
| skills/eks-well-architected-review/references/operational-excellence.md:665 | P2 | HIGH | false positive | HTML maintainer note on sourcing and remediation design; no agent directive |
| skills/eks-well-architected-review/references/operational-excellence.md:854 | P2 | HIGH | false positive | HTML maintainer note on sourcing and remediation design; no agent directive |
| skills/eks-well-architected-review/references/security/data-protection.md:151 | P2 | HIGH | false positive | HTML maintainer note on encryption facts and citations; no agent directive |
| skills/eks-well-architected-review/references/security/identity-access.md:13 | AR2 | HIGH | false positive | tells the agent to run the scorer and not hand-grade the JSON; not suppressing warnings |
| skills/eks-well-architected-review/references/security/identity-access.md:714 | AR3 | HIGH | false positive | scorer message explaining that Gatekeeper templates without Constraint objects enforce nothing |
| skills/eks-well-architected-review/references/security/identity-access.md:718 | AR3 | HIGH | false positive | scorer message explaining that Gatekeeper templates without Constraint objects enforce nothing |
| skills/eks-well-architected-review/references/security/identity-access.md:724 | AR3 | HIGH | false positive | scorer message explaining that Gatekeeper templates without Constraint objects enforce nothing |
| skills/eks-well-architected-review/references/security/identity-access.md:725 | AR3 | HIGH | false positive | scorer message explaining that Gatekeeper templates without Constraint objects enforce nothing |
| skills/eks-well-architected-review/references/security/identity-access.md:740 | TM4 | HIGH | false positive | comment describing a non-compliant sidecar the check is meant to catch |
| skills/eks-well-architected-review/references/security/identity-access.md:1109 | P2 | HIGH | false positive | HTML maintainer note on RBAC remediation safety; no agent directive |
| skills/eks-well-architected-review/references/security/network.md:282 | AR2 | HIGH | false positive | remediation warns a port change breaks clients with no warning; advises checking first |
| skills/eks-well-architected-review/references/security/workload-security.md:427 | TM4 | HIGH | false positive | remediation text explaining the risk of privileged: true and how to remove it |
| skills/eks-well-architected-review/references/security/workload-security.md:440 | TM4 | HIGH | false positive | remediation text explaining the risk of privileged: true and how to remove it |
| skills/eks-well-architected-review/references/security/workload-security.md:553 | P2 | HIGH | false positive | HTML maintainer note on IMDS hop-limit sources; no agent directive |
| skills/eks-well-architected-review/references/security/workload-security.md:594 | SSRF1 | HIGH | false positive | IMDSv2 hardening prose explaining the SSRF risk of IMDSv1; no request to the endpoint |
| skills/eks-well-architected-review/references/security/workload-security.md:597 | SSRF1 | HIGH | false positive | IMDSv2 hardening prose explaining the SSRF risk of IMDSv1; no request to the endpoint |
| skills/eks-well-architected-review/references/workflow.md:39 | PE3 | HIGH | false positive | table-of-contents entry and anchor naming the kubeconfig section |
| skills/eks-well-architected-review/references/workflow.md:39 | PE3 | HIGH | false positive | table-of-contents entry and anchor naming the kubeconfig section |
| skills/eks-well-architected-review/references/workflow.md:200 | PE3 | HIGH | false positive | explains why a preflight check exists despite update-kubeconfig succeeding |
| skills/eks-well-architected-review/references/workflow.md:203 | PE3 | HIGH | false positive | explains why a preflight check exists despite update-kubeconfig succeeding |
| skills/eks-well-architected-review/references/workflow.md:224 | RA2 | MEDIUM | false positive | explains why an empty results file is not treated as a run marker; no persistence |
| skills/eks-well-architected-review/references/workflow.md:224 | RA2 | MEDIUM | false positive | explains why an empty results file is not treated as a run marker; no persistence |
| skills/eks-well-architected-review/references/workflow.md:229 | PE2 | MEDIUM | false positive | documents that a created work dir is chmod 700: tightens access |
| skills/eks-well-architected-review/references/workflow.md:252 | PE3 | HIGH | false positive | describes the work-dir kubeconfig and the CA trust check |
| skills/eks-well-architected-review/references/workflow.md:253 | PE3 | HIGH | false positive | describes the work-dir kubeconfig and the CA trust check |
| skills/eks-well-architected-review/references/workflow.md:361 | PE2 | MEDIUM | false positive | documents that a created work dir is chmod 700: tightens access |
| skills/eks-well-architected-review/references/workflow.md:407 | PE3 | HIGH | false positive | argues against a broad file grant because it would reach ~/.aws/credentials and ~/.ssh: a control |
| skills/eks-well-architected-review/references/workflow.md:442 | PE3 | HIGH | false positive | states update-kubeconfig writes only a local kubeconfig inside the work directory |
| skills/eks-well-architected-review/references/workflow.md:442 | PE3 | HIGH | false positive | states update-kubeconfig writes only a local kubeconfig inside the work directory |
| skills/eks-well-architected-review/references/workflow.md:443 | PE3 | HIGH | false positive | states update-kubeconfig writes only a local kubeconfig inside the work directory |
| skills/eks-well-architected-review/references/workflow.md:443 | PE3 | HIGH | false positive | states update-kubeconfig writes only a local kubeconfig inside the work directory |
| skills/eks-well-architected-review/references/workflow.md:443 | PE3 | HIGH | false positive | states update-kubeconfig writes only a local kubeconfig inside the work directory |
| skills/eks-well-architected-review/references/workflow.md:444 | PE3 | HIGH | false positive | notes the shared ~/.kube/config is left untouched and names the allowed-tools grant |
| skills/eks-well-architected-review/references/workflow.md:444 | PE3 | HIGH | false positive | states the shared ~/.kube/config is left untouched |
| skills/eks-well-architected-review/references/workflow.md:445 | PE3 | HIGH | false positive | discloses that the update-kubeconfig grant can write a YAML file anywhere: documentation of a limit |
| skills/eks-well-architected-review/references/workflow.md:446 | PE3 | HIGH | false positive | warns that without the flag update-kubeconfig would overwrite ~/.kube/config: documentation of a risk |
| skills/eks-well-architected-review/references/workflow.md:451 | PE3 | HIGH | false positive | states every run writes only inside the work directory |
| skills/eks-well-architected-review/references/workflow.md:453 | PE3 | HIGH | false positive | states every run writes only inside the work directory |
| skills/eks-well-architected-review/references/workflow.md:455 | PE3 | HIGH | false positive | discloses the kubeconfig exec plugin may write the AWS CLI cache |
| skills/eks-well-architected-review/references/workflow.md:549 | PE3 | HIGH | false positive | explains a preflight case for connector kubeconfigs |
| skills/eks-well-architected-review/references/workflow.md:620 | PE3 | HIGH | false positive | explains kubectl authenticates via the kubeconfig exec plugin |
| skills/eks-well-architected-review/references/workflow.md:637 | PE3 | HIGH | false positive | lists what lives in the work directory |
| skills/eks-well-architected-review/references/workflow.md:638 | RA2 | MEDIUM | false positive | explains the mkdir -m 700 that keeps collected identifiers private; no persistence |
| skills/eks-well-architected-review/references/workflow.md:638 | RA2 | MEDIUM | false positive | explains the mkdir -m 700 that keeps collected identifiers private; no persistence |
| skills/eks-well-architected-review/references/workflow.md:658 | PE3 | HIGH | false positive | explains the CA-based cluster identity check |
| skills/eks-well-architected-review/references/workflow.md:661 | PE3 | HIGH | false positive | explains the CA-based cluster identity check |
| skills/eks-well-architected-review/references/workflow.md:671 | PE3 | HIGH | false positive | explains the CA-based cluster identity check |
| skills/eks-well-architected-review/references/workflow.md:675 | PE3 | HIGH | false positive | explains the CA-based cluster identity check |
| skills/eks-well-architected-review/references/workflow.md:682 | PE3 | HIGH | false positive | explains the CA-based cluster identity check |
| skills/eks-well-architected-review/references/workflow.md:685 | PE3 | HIGH | false positive | section heading |
| skills/eks-well-architected-review/references/workflow.md:687 | PE3 | HIGH | false positive | describes the --kubeconfig flag pointing at the work-dir file |
| skills/eks-well-architected-review/references/workflow.md:687 | PE3 | HIGH | false positive | describes the --kubeconfig flag pointing at the work-dir file |
| skills/eks-well-architected-review/references/workflow.md:688 | PE3 | HIGH | false positive | states kubectl only reads its default config without the flag |
| skills/eks-well-architected-review/references/workflow.md:688 | PE3 | HIGH | false positive | states kubectl only reads its default config without the flag |
| skills/eks-well-architected-review/references/workflow.md:689 | PE3 | HIGH | false positive | notes the flag is optional |
| skills/eks-well-architected-review/references/workflow.md:707 | PE3 | HIGH | false positive | exit-status table listing kubeconfig validation refusals |
| skills/eks-well-architected-review/references/workflow.md:707 | PE3 | HIGH | false positive | exit-status table listing kubeconfig validation refusals |
| skills/eks-well-architected-review/references/workflow.md:867 | AR2 | HIGH | false positive | explains bad values would be dropped with no warning, which is why they are validated |

## skills/graviton-migration

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/graviton-migration/SKILL.md:20 | AE1 | HIGH | accepted | points to references/scanner-workflow.md (17 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/graviton-migration/SKILL.md:41 | RP1 | MEDIUM | accepted | arm-mcp:latest is shown, but SKILL.md:49 tells the user to pin a tag or sha256 digest and confirm the image before first pull |
| skills/graviton-migration/SKILL.md:41 | TM1 | LOW | false positive | `--rm` (remove container on exit) matched as rm; no file deletion |
| skills/graviton-migration/SKILL.md:45 | RP1 | MEDIUM | accepted | arm-mcp:latest is shown, but SKILL.md:49 tells the user to pin a tag or sha256 digest and confirm the image before first pull |
| skills/graviton-migration/SKILL.md:50 | RP1 | MEDIUM | accepted | arm-mcp:latest is shown, but SKILL.md:49 tells the user to pin a tag or sha256 digest and confirm the image before first pull |
| skills/graviton-migration/SKILL.md:131 | RP1 | MEDIUM | accepted | arm-mcp:latest is shown, but SKILL.md:49 tells the user to pin a tag or sha256 digest and confirm the image before first pull |
| skills/graviton-migration/SKILL.md:136 | AS2 | HIGH | false positive | asks the harness to list its MCP tools to confirm the server loaded; no reading of other agents' config |
| skills/graviton-migration/SKILL.md:144 | RP1 | MEDIUM | accepted | arm-mcp:latest is shown, but SKILL.md:49 tells the user to pin a tag or sha256 digest and confirm the image before first pull |
| skills/graviton-migration/SKILL.md:146 | AS2 | HIGH | false positive | troubleshooting: a local JSON syntax check of the user's own .mcp.json |
| skills/graviton-migration/references/agent-scope-boundaries.md:39 | PE3 | HIGH | false positive | guardrail telling the user to remove secrets such as .git-credentials before mounting: a control |
| skills/graviton-migration/references/multi-arch-pipelines.md:77 | PE5 | HIGH | accepted | `docker run --privileged` of tonistiigi/binfmt to register QEMU emulators in a CI build job; required by binfmt, tag pinned by placeholder, skipped on native runners |
| skills/graviton-migration/references/multi-arch-pipelines.md:77 | RP1 | MEDIUM | false positive | the image tag is the `<pinned-tag>` placeholder, not :latest |
| skills/graviton-migration/references/multi-arch-pipelines.md:77 | TM1 | LOW | false positive | `--rm` (remove container on exit) matched as rm; no file deletion |
| skills/graviton-migration/references/multi-arch-pipelines.md:97 | PE5 | HIGH | accepted | `docker run --privileged` of tonistiigi/binfmt to register QEMU emulators in a CI build job; required by binfmt, tag pinned by placeholder, skipped on native runners |
| skills/graviton-migration/references/multi-arch-pipelines.md:97 | RP1 | MEDIUM | false positive | the image tag is the `<pinned-tag>` placeholder, not :latest |
| skills/graviton-migration/references/multi-arch-pipelines.md:97 | TM1 | LOW | false positive | `--rm` (remove container on exit) matched as rm; no file deletion |

## skills/skill-creator

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/skill-creator/SKILL.md:1 | LP3 | MEDIUM | accepted | frontmatter declares no allowed-tools; scripts are invoked as the body documents: a metadata gap, not a defect |
| skills/skill-creator/SKILL.md:238 | RA2 | MEDIUM | accepted | nohup runs the local eval review viewer in the background for the session; user-facing and documented, no persistence across sessions |
| skills/skill-creator/SKILL.md:364 | AE1 | HIGH | accepted | points to assets/eval_review.html (7 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| skills/skill-creator/eval-viewer/generate_review.py:291 | AST4 | MEDIUM | accepted | fixed-argv `lsof -ti :port` with no shell, to free the viewer port |
| skills/skill-creator/scripts/improve_description.py:33 | E2 | HIGH | accepted | copies the parent environment (minus CLAUDECODE) to the child `claude -p` it launches for evals so auth works; nothing is sent elsewhere |
| skills/skill-creator/scripts/improve_description.py:35 | AST4 | MEDIUM | accepted | fixed-argv `claude -p` call with no shell, the tool's documented purpose |
| skills/skill-creator/scripts/run_eval.py:23 | AS1 | HIGH | accepted | walks up to the project .claude/ dir to place the eval command file where `claude -p` finds it; documented in the docstring |
| skills/skill-creator/scripts/run_eval.py:83 | E2 | HIGH | accepted | copies the parent environment (minus CLAUDECODE) to the child `claude -p` it launches for evals so auth works; nothing is sent elsewhere |
| skills/skill-creator/scripts/run_eval.py:85 | AST4 | MEDIUM | accepted | fixed-argv Popen of `claude -p` with no shell, the eval runner's documented purpose |

## skills/terraform-skill

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| skills/terraform-skill/SKILL.md:26 | EA2 | MEDIUM | false positive | rule forbids -auto-approve on destroy and requires confirmation: a control |
| skills/terraform-skill/SKILL.md:43 | AE1 | HIGH | accepted | points to references/state-management.md (45 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/terraform-skill/SKILL.md:44 | AE1 | HIGH | accepted | points to references/state-management.md (45 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/terraform-skill/SKILL.md:45 | AE1 | HIGH | accepted | points to references/state-management.md (45 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/terraform-skill/SKILL.md:47 | EA2 | MEDIUM | false positive | names 'no approval model' as a compliance gap to fix |
| skills/terraform-skill/SKILL.md:49 | AE1 | HIGH | accepted | points to references/state-management.md (45 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/terraform-skill/SKILL.md:51 | AE1 | HIGH | accepted | points to references/state-management.md (45 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/terraform-skill/SKILL.md:54 | AE1 | HIGH | accepted | points to references/state-management.md (45 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/terraform-skill/SKILL.md:201 | AE1 | HIGH | accepted | points to references/state-management.md (45 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/terraform-skill/SKILL.md:215 | AE1 | HIGH | accepted | points to references/state-management.md (45 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/terraform-skill/SKILL.md:227 | AE1 | HIGH | accepted | points to references/state-management.md (45 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/terraform-skill/SKILL.md:299 | AE1 | HIGH | accepted | points to references/state-management.md (45 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| skills/terraform-skill/references/ci-cd-workflows.md:503 | EA2 | MEDIUM | false positive | shown under 'DON'T' as an anti-pattern |
| skills/terraform-skill/references/ci-cd-workflows.md:594 | EA2 | MEDIUM | false positive | listed as an LLM-mistake anti-pattern |
| skills/terraform-skill/references/code-patterns.md:1049 | EA2 | MEDIUM | false positive | anti-pattern: emitting features without checking the version floor |
| skills/terraform-skill/references/security-compliance.md:43 | SC2 | LOW | accepted | official Trivy installer via curl / sh, shown as a user-run install option beside brew |
| skills/terraform-skill/references/security-compliance.md:78 | TM1 | HIGH | false positive | shows checkov --skip-check syntax; skipping a check is the user's choice, no agent action |
| skills/terraform-skill/references/security-compliance.md:410 | PE3 | HIGH | false positive | `.env` is listed in a .gitignore to keep secrets out of git: a control |
| skills/terraform-skill/references/security-compliance.md:631 | EA2 | MEDIUM | false positive | names 'no approval model' as a compliance gap to fix |
| skills/terraform-skill/references/state-management.md:454 | EA2 | MEDIUM | false positive | describes lock files being deleted automatically by Terraform |
| skills/terraform-skill/references/state-management.md:489 | EA4 | MEDIUM | false positive | documents Terraform's default lock timeout; no unbounded access |
| skills/terraform-skill/references/state-management.md:548 | EA2 | MEDIUM | false positive | anti-pattern bullet: removing a lock without checking |
| skills/terraform-skill/references/state-management.md:583 | EA2 | MEDIUM | accepted | lock-timeout wrapper example; apply runs in the user's automation, and the skill's CI guidance (references/ci-cd-workflows.md:89-115) gates apply on a saved plan and an environment |
| skills/terraform-skill/references/state-management.md:606 | EA2 | MEDIUM | accepted | CI concurrency example; the snippet shows lock control only, and the skill's CI guidance (references/ci-cd-workflows.md:89-115) gates apply on a saved plan and an environment |
| skills/terraform-skill/references/state-management.md:615 | EA2 | MEDIUM | accepted | CI concurrency example; the snippet shows lock control only, and the skill's CI guidance (references/ci-cd-workflows.md:89-115) gates apply on a saved plan and an environment |
| skills/terraform-skill/references/state-management.md:685 | PE1 | LOW | false positive | heading for a minimal-permission IAM policy |
| skills/terraform-skill/references/state-management.md:1184 | TM2 | HIGH | accepted | backup retention: deletes state backups older than the newest 30 inside its own backup dir |
| skills/terraform-skill/references/state-management.md:1783 | TM1 | HIGH | false positive | shown as anti-pattern ('Dangerous'), with force-unlock after investigation as the fix |
| skills/terraform-skill/references/state-management.md:1804 | EA2 | MEDIUM | false positive | listed as an anti-pattern: never auto-approve destroy |
| skills/terraform-skill/references/state-management.md:1818 | EA2 | MEDIUM | false positive | listed as an anti-pattern: never auto-approve destroy |

## skills/update-docs

No findings.

## devops-agent/eks-cost-intelligence

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| devops-agent/eks-cost-intelligence/SKILL.md:157 | EA2 | MEDIUM | false positive | 'No confirmation required' only starts the read-only assessment after the cluster summary; no change is made |
| devops-agent/eks-cost-intelligence/SKILL.md:180 | AE1 | HIGH | accepted | points to references/spot-graviton-adoption.md (26 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| devops-agent/eks-cost-intelligence/SKILL.md:367 | AE1 | HIGH | accepted | points to references/spot-graviton-adoption.md (26 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| devops-agent/eks-cost-intelligence/references/cost-estimation-fallback.md:25 | P4 | MEDIUM | false positive | prefers live pricing API over static tables; a data-source preference, not behaviour manipulation |
| devops-agent/eks-cost-intelligence/references/observability-costs.md:355 | PE3 | HIGH | false positive | `.env` is the pod spec field containers[].env, read only for log-level variable names; no credential file |

## devops-agent/eks-ingress-migration

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| devops-agent/eks-ingress-migration/SKILL.md:40 | AE1 | HIGH | accepted | points to references/report-generation.md (67 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| devops-agent/eks-ingress-migration/SKILL.md:77 | AE1 | HIGH | accepted | points to references/atx-guide.md (12 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| devops-agent/eks-ingress-migration/SKILL.md:84 | AE1 | HIGH | accepted | points to references/report-generation.md (67 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| devops-agent/eks-ingress-migration/SKILL.md:88 | AE1 | HIGH | accepted | points to references/atx-guide.md (12 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| devops-agent/eks-ingress-migration/SKILL.md:305 | AE1 | HIGH | accepted | points to references/report-generation.md (67 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| devops-agent/eks-ingress-migration/SKILL.md:360 | AE1 | HIGH | accepted | points to references/report-generation.md (67 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| devops-agent/eks-ingress-migration/SKILL.md:365 | AE1 | HIGH | accepted | points to references/report-generation.md (67 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |
| devops-agent/eks-ingress-migration/SKILL.md:367 | AE1 | HIGH | accepted | points to references/report-generation.md (67 KB, bundled in the skill); the scanner inspected it only in part (obfuscated_instruction_text, static_parse_limit): a coverage gap, not a defect; flagged obfuscated_instruction_text (a remove/replace directive with a quoted marker the static parser could not resolve); the directive at the target is ordinary editing prose, and no AE6 was raised |

## devops-agent/eks-operation-review

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| devops-agent/eks-operation-review/SKILL.md:76 | AE1 | HIGH | accepted | points to references/report-generation.md (13 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| devops-agent/eks-operation-review/SKILL.md:119 | AE1 | HIGH | accepted | points to references/report-generation.md (13 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| devops-agent/eks-operation-review/SKILL.md:162 | AE1 | HIGH | accepted | points to references/report-generation.md (13 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| devops-agent/eks-operation-review/SKILL.md:194 | AE1 | HIGH | accepted | points to references/report-generation.md (13 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| devops-agent/eks-operation-review/references/autoscaling.md:85 | EA2 | MEDIUM | false positive | says placement cannot be verified without live reads and routes it to Investigate Manually; no autonomous action |
| devops-agent/eks-operation-review/references/porting-notes.md:159 | PE3 | HIGH | false positive | porting note: names the current kubeconfig context and the standard `aws eks update-kubeconfig` setup; no credential read |
| devops-agent/eks-operation-review/references/porting-notes.md:163 | PE3 | HIGH | false positive | porting note: names the current kubeconfig context and the standard `aws eks update-kubeconfig` setup; no credential read |

## devops-agent/eks-recon

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| devops-agent/eks-recon/SKILL.md:134 | AE1 | HIGH | accepted | points to references/compute.md (23 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| devops-agent/eks-recon/SKILL.md:142 | AE1 | HIGH | accepted | points to references/cicd.md (28 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| devops-agent/eks-recon/SKILL.md:145 | AE1 | HIGH | accepted | points to references/compute.md (23 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| devops-agent/eks-recon/SKILL.md:279 | AE1 | HIGH | accepted | points to references/compute.md (23 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| devops-agent/eks-recon/references/cicd.md:295 | PE3 | HIGH | false positive | `kubeconfig` is a Flux documentation URL anchor |
| devops-agent/eks-recon/references/networking.md:297 | PE3 | HIGH | false positive | reads the aws-node DaemonSet env (CNI settings) from the pod spec; no credential file |
| devops-agent/eks-recon/references/porting-notes.md:13 | PE3 | HIGH | false positive | porting table naming local kubeconfig as one access path; no credential read |
| devops-agent/eks-recon/references/report-comparison.md:46 | PE3 | HIGH | false positive | the line forbids echoing a supplied kubeconfig: a control, not access |

## devops-agent/eks-security

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| devops-agent/eks-security/SKILL.md:137 | AE1 | HIGH | accepted | points to references/runtime-security.md (5 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| devops-agent/eks-security/SKILL.md:250 | AE1 | HIGH | accepted | points to references/runtime-security.md (5 KB, bundled in the skill); the scanner inspected it only in part (static_parse_limit): a coverage gap, not a defect |
| devops-agent/eks-security/references/advisory-sources.md:14 | E1 | MEDIUM | accepted | documents a read-only GET to the public GitHub advisory API to resolve a GHSA id; nothing is sent beyond the request URL |
| devops-agent/eks-security/references/porting-notes.md:21 | PE3 | HIGH | false positive | porting table naming kubeconfig plus a read-only ClusterRole as the access model |

## devops-agent/eks-upgrade-check

| File:line | Rule | Severity | Verdict | Reason |
|---|---|---|---|---|
| devops-agent/eks-upgrade-check/references/porting-notes.md:203 | PE3 | HIGH | false positive | porting note: names the current kubeconfig context and the standard `aws eks update-kubeconfig` setup; no credential read |
| devops-agent/eks-upgrade-check/references/porting-notes.md:207 | PE3 | HIGH | false positive | porting note: names the current kubeconfig context and the standard `aws eks update-kubeconfig` setup; no credential read |
