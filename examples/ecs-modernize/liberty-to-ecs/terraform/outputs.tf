output "alb_url" {
  description = "Base URL of the application load balancer."
  value       = "http://${aws_lb.this.dns_name}"
}

output "app_url" {
  description = "URL of the app's health endpoint, path-appropriate for this build."
  value       = "http://${aws_lb.this.dns_name}${var.health_check_path}"
}

output "ecr_repository_url" {
  description = "ECR repository to push the image to."
  value       = aws_ecr_repository.app.repository_url
}

output "cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "service_name" {
  description = "ECS service name, or a note when no service exists yet."
  value = coalesce(
    one(aws_ecs_service.rearchitect[*].name),
    "not created yet — image_uri is empty"
  )
}

output "log_group" {
  description = "CloudWatch log group carrying the container logs."
  value       = aws_cloudwatch_log_group.app.name
}

output "sticky_sessions_enabled" {
  description = <<-EOT
    Always false here: the rearchitected app holds no server-side session, so
    affinity buys nothing. The Replatform environment the skill generates has it
    ON, driven by the in_process_session blocker — comparing the two is the point.
  EOT
  value       = false
}

output "archive_bucket" {
  description = "S3 bucket holding externalized order archives (Rearchitect path only)."
  value       = aws_s3_bucket.archive.bucket
}
