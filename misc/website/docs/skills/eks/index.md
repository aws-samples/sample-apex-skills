---
sidebar_position: 1
title: "EKS Skills: AI agent skills for Amazon EKS"
sidebar_label: EKS skills
description: "APEX agent skills for Amazon EKS: design, Terraform builds, cluster discovery, operational, cost, security and upgrade reviews, ingress migration and GenAI."
---

# EKS skills

APEX skills for Amazon Elastic Kubernetes Service (EKS). They cover designing a cluster and generating its Terraform, finding out what a live cluster runs, reviewing its operations, cost, security and upgrade readiness, migrating off NGINX Ingress, and running GenAI workloads. See [Getting started](../../getting-started.md) to install them.

- [**eks-best-practices**](./eks-best-practices/index.md): EKS architecture advice: compute, networking, security, reliability, cost, scaling, observability, multi-tenancy, upgrades, hybrid and surge readiness
- [**eks-build**](./eks-build/index.md): Generate production-ready EKS Terraform projects with optional ArgoCD GitOps, air-gapped support and 29+ addon configurations
- [**eks-cost-intelligence**](./eks-cost-intelligence/index.md): Live EKS cost efficiency assessment across 6 dimensions with a 0-100 Cost Score and dollar-quantified findings
- [**eks-design**](./eks-design/index.md): Generate EKS architecture design documents with Mermaid diagrams, ADRs, security architecture and validation reports, guided by Well-Architected practices
- [**eks-genai**](./eks-genai/index.md): GenAI and LLM workloads on EKS: GPU vs Trainium/Inferentia, vLLM and Ray serving, distributed training, ML storage and AI gateways
- [**eks-ingress-migration**](./eks-ingress-migration/index.md): Assess a live cluster's NGINX/Ingress estate and plan migration to Gateway API, the AWS Load Balancer Controller or AWS Transform
- [**eks-mcp-server**](./eks-mcp-server/index.md): Set up and troubleshoot the EKS MCP Server in your AI assistant; for cluster work once MCP works, use eks-recon, eks-operation-review or eks-upgrade-check
- [**eks-operation-review**](./eks-operation-review/index.md): EKS operational excellence assessment across 10 areas, GREEN/AMBER/RED rated, with prioritized recommendations and deprecated-API review with no target version
- [**eks-platform-engineering**](./eks-platform-engineering/index.md): Internal Developer Platform design on EKS: Backstage, ArgoCD, Kargo, progressive delivery, golden paths and DORA metrics
- [**eks-recon**](./eks-recon/index.md): EKS cluster discovery: compute, networking, security facts, add-ons, workloads, storage, IaC and CI/CD, reported as facts with no scoring
- [**eks-security**](./eks-security/index.md): Read-only EKS security reviews (CVEs, security events, posture) and hardening: CIS, HIPAA, PCI-DSS, FedRAMP, SOC 2, GuardDuty, Pod Identity, image signing
- [**eks-upgrade-check**](./eks-upgrade-check/index.md): Assess EKS cluster upgrade readiness with a 0-100 score across 8 areas including deprecated APIs, add-on compatibility and workload risks
- [**eks-well-architected-review**](./eks-well-architected-review/index.md): Unofficial, deterministic Well-Architected style review of a live EKS cluster (Linux nodes only) across five pillars; run only on an explicit WAFR request
