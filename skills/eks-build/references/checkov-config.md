# Checkov Configuration

Checkov is a static analysis tool for Terraform that detects security misconfigurations and compliance violations before deployment. This configuration file (`.checkov.yaml`) should be placed at the project root.

## What It Validates

- Security best practices for AWS resources (encryption, public access, IAM)
- Terraform configuration correctness
- Compliance with CIS, SOC2, HIPAA, and PCI-DSS benchmarks
- Network security (security groups, NACLs, public exposure)

## How to Use

Place the `.checkov.yaml` file at the root of your generated project (`projects/<project-name>/code/.checkov.yaml`). Run checkov from that directory:

```bash
cd projects/<project-name>/code
checkov -d .
```

The configuration uses soft-fail mode so CI pipelines report findings without blocking. Review the JUnit XML output (`checkov-report.xml`) for integration with CI test report widgets.

## Configuration

```yaml
###############################################################################
# Checkov Configuration
# https://www.checkov.io/2.Basics/CLI%20Command%20Reference.html
###############################################################################

# Scan only Terraform files
framework:
  - terraform

# Skip provider cache and module cache directories
skip-path:
  - "*/.terraform"
  - ".terraform"

# Soft-fail: report findings but exit 0 (non-blocking in CI)
soft-fail: true

# Skip CKV_TF_1 (require commit hash for module sources) -- we use Terraform
# registry modules with version pins, which is standard practice.
# CKV_TF_2 (require version tag) already covers our use case.
skip-check:
  - CKV_TF_1

# Compact output for CI logs
compact: true
quiet: true

# JUnit XML output for CI test report widget
output:
  - junitxml

output-file-path: checkov-report.xml
```

## Skipped Checks

| Check | Reason |
|-------|--------|
| CKV_TF_1 | Requires commit hash pinning for module sources. We use Terraform Registry modules with semantic version pins, which `CKV_TF_2` already validates. Commit hashes make upgrades painful and provide minimal security benefit for registry modules. |

## Adding Custom Skips

When generated code intentionally deviates from a checkov rule (e.g., a public-facing ALB that must exist), add the check ID to `skip-check` with a comment explaining why:

```yaml
skip-check:
  - CKV_TF_1    # Registry modules use version pins
  - CKV_AWS_91  # ALB must be public-facing per requirements
```

Alternatively, use inline suppression in Terraform:

```hcl
resource "aws_lb" "public" {
  #checkov:skip=CKV_AWS_91:ALB is intentionally public-facing
  internal = false
  # ...
}
```
