# =============================================================================
# SKELETON — outputs
#
# The first three are consumed by the deploy procedure
# (references/deploy-verify-handoff.md) for steady-state verification, so they
# are not optional. The rest exist so the user can see what the conditioned
# decisions resolved to without reading the code.
# =============================================================================

output "alb_url" {
  description = "Base URL of the application."
  value       = "http://${aws_lb.app.dns_name}"
}

output "cluster_name" {
  description = "ECS cluster name — needed for steady-state verification."
  value       = aws_ecs_cluster.app.name
}

output "service_name" {
  description = "ECS service name — needed for steady-state verification."
  value       = aws_ecs_service.app.name
}

output "log_group" {
  description = "CloudWatch Logs group carrying the container logs."
  value       = aws_cloudwatch_log_group.app.name
}

output "session_affinity_enabled" {
  description = <<-EOT
    Whether ALB stickiness is on. True means an in_process_session blocker was
    reported; the value should be traceable to that blocker id. Remember it does
    not survive task replacement.
  EOT
  value       = var.session_affinity_required
}

output "task_definition_network_mode" {
  description = <<-EOT
    Always "bridge" on this path. Surfaced as an output because it is the
    element that distinguishes this environment from anything `ecs-build`
    generates, and it is worth being able to assert in a review.
  EOT
  value       = aws_ecs_task_definition.app.network_mode
}

output "autoscaling" {
  description = <<-EOT
    Always "none" on this path. Stated explicitly rather than left as a silent
    absence: the fixed fleet and fixed task count ARE the static configuration
    the Replatform path prescribes.
  EOT
  value       = "none"
}
