variable "name_suffix" {
  description = "Suffix for cluster name (cluster will be ex-karpenter-<suffix>)"
  type        = string
  default     = "check"
}

variable "region" {
  description = "AWS region for the cluster"
  type        = string
  default     = "us-west-2"
}
