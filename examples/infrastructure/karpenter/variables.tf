variable "name_suffix" {
  description = "Suffix for cluster name (cluster will be ex-karpenter-<suffix>)"
  type        = string
  default     = "check"

  validation {
    condition     = length(var.name_suffix) <= 16
    error_message = "name_suffix must be 16 characters or fewer: the cluster IAM role name prefix ex-karpenter-<suffix>-cluster- is limited to 38 characters."
  }
}

variable "region" {
  description = "AWS region for the cluster"
  type        = string
  default     = "us-west-2"
}
