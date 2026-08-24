variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-northeast-1"
}

variable "suffix" {
  description = "Suffix for resource names, so several people can run this in one account."
  type        = string
  default     = "demo"

  validation {
    condition     = can(regex("^[a-z0-9-]{1,20}$", var.suffix))
    error_message = "suffix must be 1-20 characters of lowercase letters, digits, or hyphens."
  }
}

variable "image_uri" {
  description = <<-EOT
    Full image URI (repo:tag) for the task definition. Left empty on the first
    apply: the ECR repository must exist before an image can be pushed into it,
    so the README's Part 3b applies once to create the repository, pushes, then
    applies again with this set. The ECS service is only created once this is
    non-empty.
  EOT
  type        = string
  default     = ""
}

variable "desired_count" {
  description = <<-EOT
    Fixed task count. Two tasks is the interesting setting: it is what makes the
    legacy app's session and local-state blockers observable (requests land on
    different tasks), and what shows the rearchitected app not caring.
  EOT
  type        = number
  default     = 2

  validation {
    condition     = var.desired_count >= 1 && var.desired_count <= 4
    error_message = "desired_count must be between 1 and 4 for this exercise."
  }
}

variable "health_check_path" {
  description = <<-EOT
    Target group health check path. The rearchitected app serves health from
    /api/health (HealthResource under @ApplicationPath("/api")); the legacy
    build used /orders/health, which the skill-generated Replatform environment
    sets from its own assessment finding.
  EOT
  type        = string
  default     = "/api/health"
}

variable "health_check_matcher" {
  description = <<-EOT
    HTTP status code(s) the ALB treats as healthy (Terraform matcher, e.g.
    "200" or "200-399"). Default "200". If health_check_path points at a path
    that answers with a redirect or auth challenge (302/401), set this to the
    codes actually returned so the target can reach a steady healthy state.
  EOT
  type        = string
  default     = "200"
}

variable "ingress_cidr" {
  description = <<-EOT
    CIDR allowed to reach the ALB on port 80. Defaults to 0.0.0.0/0 so the
    exercise works anywhere; narrow it to your own address for anything beyond a
    short-lived demo. The ALB serves plain HTTP (no TLS) because the exercise
    ships no certificate — do not put real data through it.
  EOT
  type        = string
  default     = "0.0.0.0/0"
}

variable "cpu_architecture" {
  description = <<-EOT
    CPU architecture of the pushed image, for the Fargate task definition. It
    must match what you built: the README's Part 3b builds with
    --platform linux/amd64, so X86_64 is correct even on an Apple Silicon
    laptop. Set ARM64 only if you build natively for Graviton.
  EOT
  type        = string
  default     = "X86_64"

  validation {
    condition     = contains(["X86_64", "ARM64"], var.cpu_architecture)
    error_message = "cpu_architecture must be X86_64 or ARM64."
  }
}
