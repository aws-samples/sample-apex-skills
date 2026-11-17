---
title: "example-eks-design-to-build"
description: "Dummy example of a customer runbook that chains eks-design into eks-build. Copy it and adapt the steps, gates and names to your own process."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex/runbooks/example-eks-design-to-build.md
format: md
---

:::info[Source]
This page is generated from [skills/apex/runbooks/example-eks-design-to-build.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex/runbooks/example-eks-design-to-build.md). Edit the source, not this page.
:::


# Example runbook: design a cluster, then build it

This is a dummy example, not a procedure APEX runs on its own. The router follows it only when you name it. Copy it to a new file in this folder, rename it, and change the steps, gates and names to fit your team. A runbook may tighten a safety rule, never loosen one.

## When to use it

A new EKS cluster, from a blank page to a Terraform project, in one engagement.

## Steps

1. **Design.** Use the `eks-design` skill to produce the design document.
   - Our constraints to state up front: `<your Regions>`, `<air-gapped or not>`, `<compliance regime>`.
   - Gate: the design goes to `<your architecture review board>`. Stop here until the user says it is approved.
2. **Carry the design forward.** Pass the design's decisions to the next step: the cluster name, the compute strategy, add-on management, the upgrade strategy and the constraints. Do not ask them again.
3. **Build.** Use the `eks-build` skill to generate the Terraform project from those decisions.
   - Our naming: `<your naming convention>`.
   - Our pipeline: `<your CI system>`; generate pipeline code for it.
   - Gate: show the generated project and its quality check result. Nothing is applied: the team runs `terraform plan` and `apply` through `<your change process>`.
4. **Hand back.** The design document, the project path and a short list of what the team runs next.

## After the runbook

Suggest a next skill only if it fits, for example `eks-security` to harden the cluster before go-live. Run it only when the user asks.
