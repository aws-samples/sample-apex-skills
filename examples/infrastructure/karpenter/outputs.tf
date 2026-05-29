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

output "karpenter_manifests_path" {
  description = "Path to rendered Karpenter manifests (cluster name substituted)"
  value       = local_file.karpenter_manifests.filename
}
