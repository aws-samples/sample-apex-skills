---
sidebar_position: 1
title: "ECS Skills: AI agent skills for Amazon ECS"
sidebar_label: ECS skills
description: "APEX agent skills for Amazon ECS: architecture and launch type choice, Terraform builds, deployments and CI/CD, security, operational reviews and GPU workloads."
---

# ECS skills

APEX skills for Amazon Elastic Container Service (ECS). They cover Day 0 architecture and compute-model selection (Fargate, EC2, Managed Instances, Express Mode, ECS Anywhere), Terraform builds, deployment strategies and CI/CD pipelines, security hardening and compliance, operational-excellence reviews, observability design, modernizing existing apps, and GPU, ML and GenAI workloads. The .NET on Fargate skill, dotnet-aws-ecs, is listed under General. See [Getting started](../../getting-started.md) to install them.

- [**ecs-architect**](./ecs-architect/index.md): Choose the ECS deployment model for a new workload: Fargate, EC2, Managed Instances, Express Mode or ECS Anywhere, capacity providers and task sizing
- [**ecs-build**](./ecs-build/index.md): Generate apply-ready Terraform for ECS clusters, services and task definitions on Fargate, EC2 Auto Scaling or Managed Instances
- [**ecs-devops**](./ecs-devops/index.md): Deploy and release to ECS: blue/green and canary deployments, CI/CD pipelines and rollbacks
- [**ecs-genai**](./ecs-genai/index.md): GPU, ML and GenAI workloads on ECS: GPU instances, Inferentia, Trainium and Neuron, launch type choice, training and model inference
- [**ecs-modernize**](./ecs-modernize/index.md): Assess an existing VMware or EC2 app from its source code, decide replatform or rearchitect, and migrate it onto ECS
- [**ecs-observability**](./ecs-observability/index.md): ECS observability architecture: logs, metrics and traces with CloudWatch, Container Insights, X-Ray, ADOT, Managed Prometheus and Grafana, or FireLens
- [**ecs-operation-review**](./ecs-operation-review/index.md): Structured ECS operational excellence assessment of a live estate across 8 domains with GREEN/AMBER/RED ratings
- [**ecs-recon**](./ecs-recon/index.md): ECS environment discovery: compute and capacity providers, task definitions, deployments, scaling, networking, security, observability and IaC/CI-CD
- [**ecs-security**](./ecs-security/index.md): ECS security and compliance: task and execution roles, iam:PassRole, trust policies, secrets injection and shared responsibility on Fargate and EC2
