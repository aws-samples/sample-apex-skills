# ADR 0008: A standalone solution skill sizes nodes for Nitro Sandbox pods

- **Status**: Proposed
- **Date**: 2026-11-25

## Context

AWS Nitro Sandboxes run each EKS pod that sets `runtimeClassName: isolated-sandbox` or `confidential-sandbox` in its own hardware-isolated VM. Issue 446 tracks bringing the feature into the skills, one skill per pull request.

Sizing nodes for sandbox pods is a question none of the current skills answers. The density rules are new: at most 5 sandboxes per node vCPU and at most 896 per instance, a vCPU budget of 5 times the node's vCPUs across all sandboxes, a fixed memory overhead of 256 MiB or 512 MiB per pod, guest vCPUs rounded up from the CPU request, and on x86 types with two threads per core one sandbox per core at a time ([EC2 considerations](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/amazon-ec2-nitro-sandboxes.html), [EKS autoscaling](https://docs.aws.amazon.com/eks/latest/userguide/autoscaling.html)). Which of these limits a node reaches first depends on the pod's requests, the instance type and its price, so the answer is a calculation over every supported type, not a rule of thumb.

Options weighed:

- **Add the rules to an existing skill** (eks-best-practices, eks-design or eks-security). The rules alone don't give an answer: the user wants a type, a node count and a cost, which needs the instance and price data and the arithmetic, and none of those skills ships a script for it. Prose arithmetic over hundreds of types would be slow and error-prone.
- **Query live AWS APIs at run time.** Always current, but needs AWS credentials (`pricing:GetProducts`, `ec2:DescribeInstanceTypes`), takes about 20 seconds and 10 MB per Region, and makes results change between runs. The data that goes stale fastest, the list of types that support Nitro Sandboxes, comes from the EC2 documentation, which no API returns. Prices barely move: in us-west-2, none of 1,374 on-demand Linux prices changed between 2026-11-18 and 2026-11-25.
- **A standalone solution skill with a bundled script and dated data.** Deterministic and offline; the data goes stale and needs a refresh.

## Decision

Add `eks-sandbox-instance-selector`, a standalone solution skill ([ADR 0004](0004-naming.md)). Its `scripts/select.py` (Python standard library only) reads the bundled `data/data.json` (each supported type's specs once, and a Linux on-demand price table per Region with its pull date; 18 Regions: the 17 commercial Regions that need no opt-in, plus ap-east-1) and computes, for each type, sandboxes per node, the first limit reached, node count and cost, then prints the recommendations and a NodePool requirements snippet. `scripts/fetch_raw.sh` and `scripts/build_data.py` refresh the data with read-only AWS calls, for all default Regions or for one Region, which is merged in and leaves the others as they are. A normal answer runs neither; the skill offers a one-Region refresh only when the user's Region is missing or the user asks for current prices.

The skill asks for six required inputs before it recommends anything (Region, cluster type, RuntimeClass, number of sandboxes, CPU request, memory request) and shows a default with each question; the script rejects a run without them.

The skill takes no class in this change. It fits `script` (its own script does the task), but no skill has joined a class yet; it joins in a later pull request together with the other skills.

## Consequences

- Users get a type, a node count, a cost and the reason (the first limit reached) without a cluster or AWS credentials.
- The data and the supported-type list go stale. Prices carry their date in the output; the supported-type list in `scripts/build_data.py` is copied by hand from the EC2 page and must be updated when that page changes.
- The allocatable CPU and memory formulas are fitted from a few measured nodes, not published by AWS. `references/rules.md` marks each rule as documented or measured, and the skill tells the user to check Allocatable on a real node.
- The router gains one EKS routing row and lists the skill under Day 0 (Design); eks-security, eks-best-practices, eks-cost-intelligence and eks-design gain sibling negatives.

## Open

- Whether Auto Mode caps max-pods at 110 or 250 as the EKS AMI does is not verified; the script caps by default (`--no-podcap` turns it off).
- Auto Mode does not provision multi-NUMA types, and there is no published list; the script estimates them as types with 96 or more vCPU.
- Regions that need opt-in, other than ap-east-1, are not bundled; a user adds one with a one-Region refresh. Should the bundle cover every commercial Region (about 500 KB instead of about 320 KB)?
