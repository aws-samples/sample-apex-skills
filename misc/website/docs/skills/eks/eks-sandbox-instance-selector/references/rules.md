---
title: "Calculation rules and sources"
description: "Each row below matches one rule in scripts/select.py."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-sandbox-instance-selector/references/rules.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-sandbox-instance-selector/references/rules.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-sandbox-instance-selector/references/rules.md). Edit the source, not this page.
:::

# Calculation rules and sources

Each row below matches one rule in `scripts/select.py`. A source is either an AWS documentation page (checked on 2026-11-25) or a measurement on EKS test nodes. Measured values come from a few nodes only; treat them as estimates.

Documentation pages:

- EC2: [Isolate workloads with AWS Nitro Sandboxes](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/amazon-ec2-nitro-sandboxes.html), section "Considerations and limitations"
- EKS: [Scale cluster compute with Karpenter and Cluster Autoscaler](https://docs.aws.amazon.com/eks/latest/userguide/autoscaling.html), section "Autoscaling with Nitro Sandboxes"
- EKS: [Considerations](https://docs.aws.amazon.com/eks/latest/userguide/sandboxing-limitations.html) (sandboxing), section "Auto Mode sandbox provisioning constraints"

| Item | Rule | Source |
|---|---|---|
| Supported types | c/m/r/x/z families from the EC2 list, minus the excluded sizes it lists (most x86 families don't support .large; Graviton doesn't support .medium) and flex types | EC2 page, "Supported instance types"; copied into `SUPPORTED` in `scripts/build_data.py` |
| Auto Mode exclusions | r5a, r5ad and m5ad are not available on Auto Mode for now. Auto Mode does not provision multi-NUMA types; the selector estimates those as 96 or more vCPU, because there is no published list | EKS Considerations page; the 96-vCPU cut is an estimate |
| Slots | 5 sandboxes per node vCPU, at most 896 per instance | EC2 page, "Number of Nitro Sandboxes and vCPUs"; EKS autoscaling page. Measured values match on 2, 4 and 8 vCPU nodes |
| vCPU budget | Sum of guest vCPUs of all sandboxes ≤ 5 × node vCPU | EC2 page (with CPU overcommit) and EKS autoscaling page. One test went over it and was not blocked; the selector still uses the documented rule |
| Guest vCPU | CPU request rounded up, at least 1; the limit has no effect | Measured (m6g.large) |
| Memory per pod | memory request + 256 MiB (isolated-sandbox) or 512 MiB (confidential-sandbox) | EKS autoscaling page, "Memory overhead" |
| Minimum memory | Warn below 256 MiB per sandbox | EC2 page, "Memory" |
| Node allocatable CPU | vCPU − EKS standard reserve (60m + 10m from 2 vCPU + 5m for each of vCPU 3–4 + 2.5m for each vCPU from 5); Auto Mode reserves 150m more; minus DaemonSet CPU | Measured: r7g.2xlarge (standard EKS), c5a.xlarge and m6g.large (Auto Mode) |
| Node allocatable memory | physical memory × 0.9646 − 85 MiB − (255 + 11 × max-pods + 100) MiB − 75 MiB more on Auto Mode − extra sandbox reserve (default 12% of physical memory) − DaemonSet memory | Fitted from measurements. The sandbox reserve has one data point, m6g.large (calculated 6107 MiB, measured 6085 MiB). c8gn.large calculates to 2647 MiB but measured under 2624 MiB, so small types can be a few tens of MiB too high |
| max-pods | Standard EKS: ENI × (IP − 1) + 2; Auto Mode: ENI × (IP − 1); capped at 110 (under 30 vCPU) or 250 by default | Measured values match on 3 nodes. The cap is the usual EKS AMI default; not verified whether Auto Mode applies it |
| Sandboxes per node | min(slots, vCPU budget, 896, max-pods − DaemonSet pods, allocatable memory ÷ memory per pod, allocatable CPU ÷ CPU request). The smallest is the "first limit" | — |
| x86 SMT | On types with two threads per core, a core runs only one sandbox at a time, so sandbox compute is bounded by physical cores. With 1 guest vCPU about half the CPU is usable; an even vCPU count uses all of it; an odd count n is estimated as n/(n+1). Applied to CPU bin packing by default (`--no-smt` turns it off) | EC2 page, "CPU on instances with two threads per core"; the n/(n+1) factor is an estimate, not measured |
| CPU delivered | min(1, allocatable CPU × SMT factor ÷ (CPU request × sandboxes per node)) | Estimate |
| Sort order | With `--count`: total cost = ceil(count ÷ per node) × hourly price. With `--count 0`: hourly price ÷ per node | — |
| Price | Linux on-demand, shared tenancy, per hour | AWS Price List API (`source_date` in `data/data.json`) |

Not included: CPU used by the sandbox itself (guest kernel, Firecracker); EBS and network bandwidth; Spot prices; the memory pool's own use (2 MiB per sandbox, and in confidential mode 16 MiB per virtual device, EC2 page "Memory"), which the scheduler does not count.

## Measured differences between standard EKS and Auto Mode nodes

| Item | Standard EKS | Auto Mode | Notes |
|---|---|---|---|
| CPU reserve | EKS standard formula (r7g.2xlarge: 90m) | standard formula + 150m | Two data points, c5a.xlarge and m6g.large. Probably reserved for components that don't run as pods |
| Memory reserve | 255 MiB + 11 MiB × max-pods + 100 MiB | standard formula + 75 MiB | One data point, c5a.xlarge |
| max-pods | ENI × (IP − 1) + 2 | ENI × (IP − 1) | The +2 is probably for host-network DaemonSets such as aws-node and kube-proxy |
| DaemonSet pods | CNI, kube-proxy and others run as pods and count as overhead (default estimate 3 pods / 150m / 200 MiB) | 0 | Measured on Auto Mode nodes |

Standard EKS also needs an AMI with the Nitro Sandbox components and Nitro Enclaves turned on ([Create and update a Nitro Sandbox AMI](https://docs.aws.amazon.com/eks/latest/userguide/sandboxing-ami-create-update.html)).
