output "configure_kubectl" {
  description = "Command to configure kubectl"
  value       = "aws eks --region ${local.region} update-kubeconfig --name ${module.eks.cluster_name}"
}

output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "region" {
  description = "AWS region"
  value       = local.region
}
