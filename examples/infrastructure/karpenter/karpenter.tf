locals {
  namespace = "karpenter"
}

resource "local_file" "karpenter_manifests" {
  content = templatefile("${path.module}/karpenter.yaml", {
    cluster_name = local.name
  })
  filename = "${path.module}/rendered/karpenter.yaml"
}

module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 21.29"

  cluster_name = module.eks.cluster_name
  namespace    = local.namespace

  # The controller policy can exceed the 6,144-character managed policy limit;
  # inline policies on a role allow 10,240 in total.
  enable_inline_policy = true

  node_iam_role_use_name_prefix = false
  node_iam_role_name            = local.name

  # IRSA trust for the controller role (custom trust policy)
  create_pod_identity_association         = false
  iam_role_source_assume_policy_documents = [data.aws_iam_policy_document.karpenter_irsa.json]

  tags = local.tags
}

data "aws_iam_policy_document" "karpenter_irsa" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:sub"
      values   = ["system:serviceaccount:${local.namespace}:karpenter"]
    }

    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "helm_release" "karpenter" {
  name             = "karpenter"
  namespace        = local.namespace
  create_namespace = true
  repository       = "oci://public.ecr.aws/karpenter"
  chart            = "karpenter"
  version          = "1.0.2"
  wait             = false

  values = [
    <<-EOT
    dnsPolicy: Default
    settings:
      clusterName: ${module.eks.cluster_name}
      clusterEndpoint: ${module.eks.cluster_endpoint}
      interruptionQueue: ${module.karpenter.queue_name}
    serviceAccount:
      annotations:
        eks.amazonaws.com/role-arn: ${module.karpenter.iam_role_arn}
    webhook:
      enabled: false
    EOT
  ]

  # Pods created before their Fargate profile stay Pending, so wait for module.eks
  # (which holds the karpenter Fargate profile).
  depends_on = [module.eks]
}
