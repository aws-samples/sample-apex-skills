---
name: eks-sandbox-instance-selector
description: Picks EC2 instance types for Amazon EKS nodes that run AWS Nitro Sandboxes (pods with runtimeClassName isolated-sandbox or confidential-sandbox). From the sandbox pod's CPU and memory request, the sandbox count, the Region and the cluster type (EKS Auto Mode, or standard EKS with Karpenter or node groups), a bundled script computes for each supported instance type how many sandboxes fit on one node, which limit is reached first (sandbox slots, vCPU budget, memory, CPU, max-pods), the node count and the on-demand cost, then gives the lowest-cost Graviton and x86 picks and a NodePool requirements snippet. Use when someone asks which instance type or family to use for Nitro Sandbox pods, how many sandboxes fit on a node, how many nodes N sandboxes need, or what sandbox capacity costs. Not for whether to use Nitro Sandboxes or how to harden them (eks-security), general EKS compute advice for ordinary pods (eks-best-practices), a cost audit of a live cluster (eks-cost-intelligence), or ECS tasks.
---

# EKS Sandbox Instance Selector

Turns a Nitro Sandbox pod spec into: how many sandboxes fit on one node, which limit is reached first, how many nodes the user needs, and what they cost. The results are estimates to shorten the list of instance types; the user tests the final types on a cluster.

The skill reads no cluster and needs no AWS credentials to answer: `scripts/select.py` works offline on the bundled `data/data.json`: instance specs, and on-demand prices for 18 Regions (the 17 commercial Regions that need no opt-in, plus ap-east-1), each Region with the date its prices were pulled.

## Step 1: Get the required inputs

These six change the result, so never fill them in yourself:

| Input | Option | Why it matters |
|---|---|---|
| Region | `--region` | Prices and available types differ by Region |
| Cluster type | `--mode auto` (EKS Auto Mode) or `--mode std` (standard EKS: Karpenter or node groups) | Node reserves, max-pods and DaemonSet overhead differ |
| RuntimeClass | `--runtime-class isolated` or `confidential` | Memory overhead per pod is 256 MiB or 512 MiB; this changes the type when memory fills first. It is also a security choice only the user can make |
| Number of sandboxes | `--count N`, or `--count 0` to sort by cost per sandbox | Small counts favor smaller types (a large node is not filled); large or unknown counts favor large types |
| CPU request | `--cpu-req`, in vCPU | Sets the guest vCPU count and the CPU bin packing |
| Memory request | `--mem-req`, in MiB | Sets the memory bin packing |

If the user's message or the conversation so far doesn't state one or more of them, ask for the missing ones before you run the script, all in one turn, with your harness's ask tool (`AskUserQuestion` in Claude Code), or in plain text where there is none. Show a default with every question, so the user can accept it or give their own value:

| Input | Options (first = default) |
|---|---|
| Region | us-west-2, us-east-1, eu-west-1, ap-northeast-1; any other Region in `data/data.json` through the user's own answer |
| Cluster type | EKS Auto Mode, standard EKS (Karpenter or node groups) |
| RuntimeClass | isolated-sandbox (overhead 256 MiB), confidential-sandbox (overhead 512 MiB) |
| Number of sandboxes | 100, 10, 1000, not sure (sort by cost per sandbox, `--count 0`) |
| CPU request | 1 vCPU, 0.25 vCPU, 0.5 vCPU, 2 vCPU |
| Memory request | 2048 MiB, 512 MiB, 1024 MiB, 4096 MiB |

If an ask tool takes fewer questions than are missing (Claude Code's takes 4), ask in two rounds: Region, cluster type, RuntimeClass and number of sandboxes first, then the CPU and memory requests. Don't give a recommendation until you have all six. The script also rejects a run without them.

If the user's Region is not in `data/data.json` (the script lists the Regions it has), say so, and offer a Region that is, or a refresh of just that Region (see "Refresh the data"), which needs AWS credentials and takes about 20 seconds. Offer the same refresh when the user asks for current prices.

## Step 2: Optional inputs

For these, use the default when the user doesn't give one, and say in your answer which defaults you used:

| Option | Values | Default |
|---|---|---|
| `--cpu-lim` | vCPU; doesn't change the guest vCPU count | none |
| `--mem-lim` | MiB; scheduling uses only the request | none |
| `--arch` | `any` / `arm64` / `x86_64` | any |
| `--cats` | subset of `c,m,r,x` (x includes z) | c,m,r |
| `--min-gen` | 5 / 6 / 7 / 8 | 6 |

Switches: `--metal` (include metal sizes), `--allow-numa` (keep types with 96 or more vCPU), `--no-smt` (don't count x86 SMT CPU on physical cores), `--no-podcap` (don't cap max-pods at 110 or 250; for prefix delegation or a custom max-pods), `--sbres` (extra memory reserve on sandbox nodes, % of physical memory, default 12), `--ds-pods` / `--ds-cpu` / `--ds-mem` (DaemonSet overhead per node; default 0 on Auto Mode, 3 pods / 150m / 200 MiB on standard EKS), `--top` (table rows, default 30).

## Step 3: Run the script

Python 3 with the standard library only. In Claude Code the skill folder is `${CLAUDE_SKILL_DIR}`; in other harnesses use the path of this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/select.py" --region us-west-2 --mode auto \
  --runtime-class isolated --count 100 --cpu-req 1 --mem-req 2048
```

It prints Markdown: recommendations (lowest cost overall, Graviton and x86), notes, the candidate table and a NodePool requirements snippet.

## Step 4: Answer

- Give the recommended types with node count and cost, say which limit is reached first and what that means (for example, CPU fills first and a third of the memory stays idle).
- Pass on the notes the script prints, especially x86 SMT, a CPU request that is not a whole number, and a limit less than the request.
- Show only the table rows that matter.
- On standard EKS, state the DaemonSet overhead you assumed (the default 3 pods / 150m / 200 MiB is an estimate) and say that it can change the result; the user can sum the DaemonSet pod requests from `kubectl describe node` on their cluster and run again with `--ds-pods`, `--ds-cpu` and `--ds-mem`.
- Say the result is an estimate: the allocatable CPU and memory formulas are fitted from a few measured nodes, and small types can be off by a few tens of MiB. For exact numbers the user checks Allocatable in `kubectl describe node`.
- To compare options (isolated vs confidential, Auto Mode vs standard EKS), run the script once per option.

## Key points

- Guest vCPU = CPU request rounded up, at least 1; the limit has no effect. So 0.25 vCPU and 1 vCPU both give 1 guest vCPU, but the scheduler counts only 250m.
- Sandboxes per node = the smallest of: 5 slots per node vCPU, the vCPU budget (5 × node vCPU across all sandboxes), 896, max-pods, memory, CPU.
- On x86 types with two threads per core, a core runs one sandbox at a time, so sandbox compute is bounded by physical cores. Graviton has one thread per core.
- EKS Auto Mode selects the instance type itself: use the results to decide which families to allow in the NodePool.
- Every rule and its source (AWS documentation or a measurement) is in [references/rules.md](references/rules.md). Read it when the user asks why a number comes out the way it does.

## Refresh the data

`data/data.json` holds each supported type's specs once (they don't differ by Region) and a price table per Region. To add or refresh Regions (AWS credentials; read-only calls):

```bash
cd "${CLAUDE_SKILL_DIR}"
./scripts/fetch_raw.sh me-central-1        # one or more Regions; no argument = the 17 default Regions
python3 scripts/build_data.py              # updates those Regions in data/data.json, keeps the others
rm -rf raw                                 # raw/ is scratch, never committed
```

A Region that isn't enabled in the account still gets its prices (the Pricing API needs no opt-in); its types take their specs from the Regions already in the data, and a type with no specs anywhere is skipped and named in the output.

The supported families and excluded sizes are copied by hand into `SUPPORTED` in `scripts/build_data.py`, from the [EC2 Nitro Sandboxes considerations](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/amazon-ec2-nitro-sandboxes.html) (checked on 2026-11-25). When that page changes, update the table by hand. The families that EKS Auto Mode excludes for now are in `AUTO_MODE_BLOCKED`, from [EKS sandboxing considerations](https://docs.aws.amazon.com/eks/latest/userguide/sandboxing-limitations.html).
