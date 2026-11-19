module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.29"

  name               = local.name
  kubernetes_version = "1.32"

  enable_cluster_creator_admin_permissions = true
  endpoint_public_access                   = true

  addons = {
    coredns = {
      configuration_values = jsonencode({ computeType = "Fargate" })
    }
    eks-pod-identity-agent = {}
    kube-proxy             = {}
    vpc-cni                = {}
  }

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  create_security_group      = false
  create_node_security_group = false

  fargate_profiles = {
    karpenter = {
      selectors = [
        { namespace = "karpenter" }
      ]
    }
    coredns = {
      selectors = [
        {
          namespace = "kube-system"
          labels    = { k8s-app = "kube-dns" }
        }
      ]
    }
  }

  tags = merge(local.tags, {
    "karpenter.sh/discovery" = local.name
  })
}
