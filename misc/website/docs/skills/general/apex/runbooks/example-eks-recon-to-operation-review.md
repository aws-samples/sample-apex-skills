---
title: "example-eks-recon-to-operation-review"
description: "Dummy example of a customer runbook that chains eks-recon into eks-operation-review. Copy it and adapt the steps, gates and names to your own process."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex/runbooks/example-eks-recon-to-operation-review.md
format: md
---

:::info[Source]
This page is generated from [skills/apex/runbooks/example-eks-recon-to-operation-review.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex/runbooks/example-eks-recon-to-operation-review.md). Edit the source, not this page.
:::


# Example runbook: discover a cluster, then review its operations

This is a dummy example, not a procedure APEX runs on its own. The router follows it only when you name it. Copy it to a new file in this folder, rename it, and change the steps, gates and names to fit your team. A runbook may tighten a safety rule, never loosen one.

## When to use it

A running EKS cluster you have not reviewed before: first find out what is there, then score its operational posture.

## Steps

1. **Pick the cluster.** Ask the user which cluster and kube context to use. Our rule: only clusters in `<your non-production accounts>` without a change ticket.
2. **Discover.** Use the `eks-recon` skill to report what is running: EKS version, compute strategy, add-ons, networking, observability.
   - Gate: show the recon report and stop until the user confirms it is the right cluster.
3. **Carry the report forward.** Pass the recon report to the next step: the EKS version, the compute strategy and the add-on inventory. Do not ask them again.
4. **Review.** Use the `eks-operation-review` skill for the full review. Every read stays read-only; remediation snippets in the report are for the team to run.
   - Our extra rule: `<for example, treat any RED on logging as a blocker for go-live>`.
5. **Hand back.** The recon report, the review report and its RED items in priority order, filed to `<your ticket system>`.

## After the runbook

Suggest a next skill only if it fits, for example `eks-upgrade-check` when the review flags the cluster version, or `eks-cost-intelligence` for spend. Run it only when the user asks.
