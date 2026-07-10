# Version Management

> **Part of:** [ecs-build](../SKILL.md)

**Do NOT use hardcoded versions.** Always look up current versions from the authoritative sources below before generating code, then pin what you verified.

## Version Lookup Process

Before generating a project, look up **every** module and provider version. Never reuse versions from a previous generation -- they go stale.

Use these methods in order of preference:

1. **Web search** (recommended) -- e.g. `terraform-aws-modules/ecs latest version`, `hashicorp aws provider latest release`.
2. **Terraform Registry API** -- `https://registry.terraform.io/v1/modules/terraform-aws-modules/ecs/aws` and `https://registry.terraform.io/v1/providers/hashicorp/aws` return the latest version as JSON.
3. **GitHub releases** -- the releases pages below.
4. **Terraform CLI** (if available) -- `terraform init -upgrade` in a scratch dir surfaces resolved versions.

### Lookup rules

- **Terraform modules:** pin with `~>` at the verified major.minor (e.g. `~> <MAJOR>.<MINOR>`), allowing patch drift only.
- **AWS provider:** `~> <MAJOR>.0` at the verified major.
- **ECS-optimized AMIs (EC2 launch type):** do NOT hardcode AMI IDs -- resolve at apply time via the SSM public parameter, the service-managed freshness path:
  ```hcl
  data "aws_ssm_parameter" "ecs_ami" {
    name = "/aws/service/ecs/optimized-ami/amazon-linux-2023/recommended/image_id"
  }
  ```
  Parameter paths per OS/architecture: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/retrieve-ecs-optimized_AMI.html
- **Fargate platform version:** generate `platform_version = "LATEST"` unless the user pins one (SOCI and >= 8 vCPU need Linux PV 1.4.0 -- as of 2026-07-10, 1.4.0 IS the current Linux PV, so `LATEST` satisfies them).
- **Managed Instances:** no AMI or agent versions to manage -- AWS owns the Bottlerocket AMI and patching. Nothing to look up.
- **ECS agent (EC2 only):** comes with the ECS-optimized AMI; feature floors that matter: Service Connect >= 1.67.2, region-specific endpoints >= 1.25.1.

## Authoritative Version Sources

| Component | Source |
|---|---|
| terraform-aws-modules/ecs | https://registry.terraform.io/modules/terraform-aws-modules/ecs/aws · https://github.com/terraform-aws-modules/terraform-aws-ecs/releases |
| hashicorp/aws provider | https://registry.terraform.io/providers/hashicorp/aws · https://github.com/hashicorp/terraform-provider-aws/releases |
| terraform-aws-modules/vpc (if generating the VPC) | https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws |
| terraform-aws-modules/alb (if generating the ALB) | https://registry.terraform.io/modules/terraform-aws-modules/alb/aws |
| ECS-optimized AMI | SSM public parameters (see above) |
| Fargate platform versions | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/platform-linux-fargate.html |
| ECS feature history | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/document_history.html · https://aws.amazon.com/about-aws/whats-new/containers/ |

## Dated floor facts (re-verify, do not trust beyond their date)

Facts verified 2026-07-10 against https://github.com/terraform-aws-modules/terraform-aws-ecs/blob/master/README.md and the registries above:

- `terraform-aws-modules/ecs` current major line is **v7.x** (latest v7.5.0, published 2026-03-18). v7 natively supports Managed Instances capacity providers (cluster submodule `managed_instances_provider`, creates the infrastructure role by default) -- **do not generate against v6 or earlier** for MI projects.
- Module minimums: **Terraform >= 1.5.7**, **AWS provider >= 6.34** (provider latest 6.54.0, 2026-07-08).
- Native `deployment_configuration.strategy` (BLUE_GREEN/LINEAR/CANARY) and `managed_instances_provider` require a recent 6.x provider -- if `terraform validate` rejects these blocks, the provider pin is too old; raise it, do not remove the feature.

These are floors as of the verification date. The lookup process above overrides this section whenever it returns newer versions.
