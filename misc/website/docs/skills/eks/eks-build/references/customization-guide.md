---
title: "EKS Infrastructure Customization Guide"
description: "Covers environment-specific constraints that require modifications to the baseline patterns."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-build/references/customization-guide.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-build/references/customization-guide.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-build/references/customization-guide.md). Edit the source, not this page.
:::

# EKS Infrastructure Customization Guide

Covers environment-specific constraints that require modifications to the baseline patterns.

---

## 1. Air-Gapped / VPC-Endpoint-Only Networks

Clusters with no internet egress must reach AWS services through VPC endpoints. Every image pull, Helm fetch, and API call must stay within the VPC. One exception: when ECR is reached through interface VPC endpoints, the first pull of an image through an ECR pull-through cache rule needs a route to the internet from the VPC ([ECR pull-through cache considerations](https://docs.aws.amazon.com/AmazonECR/latest/userguide/pull-through-cache.html)). For a VPC with no egress, seed the cache first: pull each image and tag once through its pull-through URI from a network with a route. Later pulls of that tag are served from the cache, so seed again for each new tag.

**Required VPC endpoints** (all Interface type except S3 which is Gateway):
`eks`, `eks-auth`, `ecr.api`, `ecr.dkr`, `s3` (Gateway), `sts`, `ec2`,
`elasticloadbalancing`, `autoscaling`, `logs`, `ssm`, and `oidc-eks` to set up IRSA from inside the VPC ([private cluster requirements](https://docs.aws.amazon.com/eks/latest/userguide/private-clusters.html)). The `ebs` endpoint serves the EBS direct APIs (snapshot data); add it only for a workload that calls them ([EBS direct APIs endpoint](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-apis-vpc-endpoints.html)).
All interface endpoints must have private DNS enabled and share the worker node subnets and security groups.

**ECR pull-through cache** -- mirror every public registry into private ECR:
```bash
# No upstream credentials needed
aws ecr create-pull-through-cache-rule --ecr-repository-prefix ecr-public  --upstream-registry-url public.ecr.aws
aws ecr create-pull-through-cache-rule --ecr-repository-prefix k8s         --upstream-registry-url registry.k8s.io
aws ecr create-pull-through-cache-rule --ecr-repository-prefix quay        --upstream-registry-url quay.io

# Docker Hub and ghcr.io need a Secrets Manager secret (keys username, accessToken),
# named with the ecr-pullthroughcache/ prefix, in the same account and Region as the rule
aws secretsmanager create-secret --name ecr-pullthroughcache/docker-hub --secret-string file://docker-hub-creds.json
aws secretsmanager create-secret --name ecr-pullthroughcache/ghcr       --secret-string file://ghcr-creds.json
aws ecr create-pull-through-cache-rule --ecr-repository-prefix docker-hub  --upstream-registry-url registry-1.docker.io \
  --credential-arn <DOCKER_HUB_SECRET_ARN>
aws ecr create-pull-through-cache-rule --ecr-repository-prefix ghcr        --upstream-registry-url ghcr.io \
  --credential-arn <GHCR_SECRET_ARN>
```
Sources: [Creating a pull through cache rule](https://docs.aws.amazon.com/AmazonECR/latest/userguide/pull-through-cache-creating-rule.html), [Storing upstream credentials in a Secrets Manager secret](https://docs.aws.amazon.com/AmazonECR/latest/userguide/pull-through-cache-creating-secret.html).

Reference each image by its pull-through URI, `<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/<prefix>/<upstream repository>:<tag>`. For example, `quay.io/jetstack/cert-manager-controller` becomes `<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/quay/jetstack/cert-manager-controller:<tag>`. Docker Hub official images need the `/library` part, as in `docker-hub/library/<image>` ([Pulling an image with a pull through cache rule](https://docs.aws.amazon.com/AmazonECR/latest/userguide/pull-through-cache-working-pulling.html)). This guide sets up no node-level mirror, so every image value a chart exposes (sub-images and hook Jobs included), and every other add-on, workload and init container, needs the same rewrite. Section 3 gives the override values for 7 common add-ons; any other add-on you enable needs the same rewrite, built from its chart's values.yaml. AWS add-ons pull from an Amazon EKS ECR repository in each Region (through the ECR interface endpoints and the S3 gateway endpoint), so they need no rewrite; check where a community or Marketplace add-on pulls from ([Amazon container image registries for Amazon EKS add-ons](https://docs.aws.amazon.com/eks/latest/userguide/add-ons-images.html)). Kubelet's ECR credential provider authenticates these pulls with the node role. The principal behind an image's first pull also needs `ecr:BatchImportUpstreamImage`, plus `ecr:CreateRepository` while the cache repository does not exist yet ([IAM permissions for pull through cache](https://docs.aws.amazon.com/AmazonECR/latest/userguide/pull-through-cache-iam.html)). A managed node group role (`AmazonEC2ContainerRegistryReadOnly`) carries neither; Karpenter and Auto Mode node roles (`AmazonEC2ContainerRegistryPullOnly`) carry `ecr:BatchImportUpstreamImage` but not `ecr:CreateRepository`. Grant what is missing to the principal behind the first pull: the node role, or in a VPC with no egress the identity that seeds the cache (see the first-pull note at the top of this section).

**Helm chart mirroring** -- push OCI artifacts to ECR or host tarballs in S3 (reachable via the S3 gateway endpoint):
```bash
helm push cert-manager-<VERSION>.tgz oci://<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/charts
```
Override each addon's `repository` in `addons.yaml`. **No public registry references are permitted** in any Helm values, pod specs, or init containers.

---

## 2. Enterprise Proxy

Three layers need proxy injection: node OS, container runtime, and pods.

**Node bootstrap** (AL2023 launch template user data in `compute.yaml`):
```yaml
pre_bootstrap_user_data: |
  cat <<'PROXY' > /etc/profile.d/proxy.sh
  export HTTP_PROXY="http://<PROXY_HOST>:<PROXY_PORT>"
  export HTTPS_PROXY="http://<PROXY_HOST>:<PROXY_PORT>"
  export NO_PROXY="169.254.169.254,169.254.170.2,10.0.0.0/8,.internal,.eks.amazonaws.com,.s3.amazonaws.com,.ecr.amazonaws.com"
  PROXY
  source /etc/profile.d/proxy.sh
```

**containerd systemd override** (append to `pre_bootstrap_user_data`):
```bash
mkdir -p /etc/systemd/system/containerd.service.d
cat <<'EOF' > /etc/systemd/system/containerd.service.d/http-proxy.conf
[Service]
Environment="HTTP_PROXY=http://<PROXY_HOST>:<PROXY_PORT>"
Environment="HTTPS_PROXY=http://<PROXY_HOST>:<PROXY_PORT>"
Environment="NO_PROXY=169.254.169.254,169.254.170.2,10.0.0.0/8,.internal,.eks.amazonaws.com,.s3.amazonaws.com,.ecr.amazonaws.com"
EOF
systemctl daemon-reload && systemctl restart containerd
```

**NO_PROXY must include (all layers)**: `169.254.169.254` (IMDS), `10.0.0.0/8` (VPC CIDR -- adjust as needed), `.internal`, `.eks.amazonaws.com`, `.s3.amazonaws.com`, `.ecr.amazonaws.com`, `.dkr.ecr.amazonaws.com`. Pods that use a proxy also need the Pod Identity Agent addresses, `169.254.170.23` and `fd00:ec2::23` (IPv4 and IPv6; write it without brackets: Go and curl do not match the bracketed form the AWS page shows). `169.254.170.2` is the ECS task-role address, unused on EKS; it is harmless to keep.

**Proxy-aware addon config** -- inject env vars via Helm `set` in `addons.yaml`:
```yaml
aws_load_balancer_controller:
  config:
    set:
      - { name: env.HTTP_PROXY,  value: "http://<PROXY_HOST>:<PROXY_PORT>" }
      - { name: env.HTTPS_PROXY, value: "http://<PROXY_HOST>:<PROXY_PORT>" }
      # Helm set splits values on commas, so escape each one as \, (single quotes keep the backslash).
      - { name: env.NO_PROXY,    value: '169.254.169.254\,169.254.170.2\,169.254.170.23\,fd00:ec2::23\,10.0.0.0/8\,.internal\,.eks.amazonaws.com' }
```
Apply the same pattern to: `cluster_autoscaler`, `external_dns`, `external_secrets`, `cert_manager`, `velero`, and `ingress_nginx`.

---

## 3. Private Container Registry

All images must come from an approved private registry. Override every addon's image references and restrict what the cluster can pull.

**ECR pull-through cache** (Section 1 rules and prefixes): each value is `<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/<prefix>/<full upstream path>`. Overrides in `addons.yaml` (upstream paths from each chart's values.yaml at aws-load-balancer-controller 3.6.2, cluster-autoscaler 9.60.0, cert-manager v1.21.3, external-secrets 2.14.0, velero 12.2.4, metrics-server 3.14.0 and external-dns 1.23.0; re-check at the chart version you pin):
```yaml
aws_load_balancer_controller:
  config:
    set:
      - { name: image.repository, value: "<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/ecr-public/eks/aws-load-balancer-controller" }
cluster_autoscaler:
  config:
    set:
      - { name: image.repository, value: "<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/k8s/autoscaling/cluster-autoscaler" }
cert_manager:
  config:
    set:
      # chart v1.20.0+; covers controller, webhook, cainjector, acmesolver and startupapicheck (imageNamespace stays jetstack)
      - { name: imageRegistry, value: "<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/quay" }
external_secrets:
  config:
    set:
      # covers controller, webhook and cert-controller
      - { name: global.repository, value: "<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/ghcr/external-secrets/external-secrets" }
velero:
  config:
    set:
      - { name: image.repository,         value: "<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/docker-hub/velero/velero" }
      # replaces the AWS plugin initContainer the blueprints-addons module sets (velero/velero-plugin-for-aws)
      # <PLUGIN_TAG>: the plugin minor the velero-plugin-for-aws README compatibility matrix pairs with
      # the chart's Velero version (chart 12.2.x ships Velero 1.18.x, so plugin v1.14.x); not the
      # module's v1.7.1, which pairs with Velero 1.11
      - name: initContainers
        value: |
          - name: velero-plugin-for-aws
            image: <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/docker-hub/velero/velero-plugin-for-aws:<PLUGIN_TAG>
            imagePullPolicy: IfNotPresent
            volumeMounts:
              - mountPath: /target
                name: plugins
metrics_server:
  config:
    set:
      - { name: image.repository, value: "<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/k8s/metrics-server/metrics-server" }
external_dns:
  config:
    set:
      - { name: image.repository, value: "<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/k8s/external-dns/external-dns" }
```

**Separate private registry** (not ECR): mirror each image under its full upstream path and set the same keys to `<REGISTRY_HOST>/<full upstream path>` (cert-manager: `imageRegistry: <REGISTRY_HOST>`).

**ImagePullSecret** (separate private registry only) -- create a `kubernetes.io/dockerconfigjson` Secret in each namespace, then inject it via Kyverno mutation policy or by patching the default ServiceAccount.

**Kyverno registry restriction policy** -- deploy a `ValidatingPolicy` (legacy: a `ClusterPolicy` with `validationFailureAction: Enforce`) that matches all Pods and validates both `containers[*].image` and `initContainers[*].image` against an allow-list: `<REGISTRY_HOST>/*`, `<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/*` and the Amazon EKS add-on registry for your Region. Reject anything else at admission.

Note: Kyverno `ClusterPolicy` (`kyverno.io/v1`) is deprecated as of Kyverno v1.19 ([Kyverno v1.19 policy types](https://release-1-19-0.kyverno.io/docs/policy-types/overview/)); on v1.19+ write this rule as a `ValidatingPolicy` (`policies.kyverno.io/v1`). Kyverno v1.20 (a release candidate as of 2026-11-08) no longer executes ClusterPolicy; migrate before upgrading past 1.19.

---

## 4. Compliance-Strict

For FedRAMP, PCI-DSS, HIPAA -- hardening at every layer.

**Required security addons** (all must be enabled in `addons.yaml`):
```yaml
custom_addons:
  kyverno:
    enabled: true
    pod_security_standard: restricted        # Not 'baseline'
    validation_failure_action: Enforce       # Not 'Audit'
gatekeeper:   { enabled: true }
cert_manager: { enabled: true }
external_secrets: { enabled: true }
cis_benchmark:
  enabled: true
  mode: Enforce                              # Reject non-compliant workloads at admission
  exclude_namespaces: [kube-system, kube-public, kube-node-lease, kyverno, gatekeeper-system]
```

**EKS control plane hardening** in `cluster.yaml`:
```yaml
endpoint_public_access: false                # Private endpoint only
endpoint_private_access: true
kms_key_arn: "arn:aws:kms:<REGION>:<ACCOUNT_ID>:key/<KEY_ID>"
cluster_enabled_log_types: [api, audit, authenticator, controllerManager, scheduler]
permissions_boundary: null   # e.g. "arn:aws:iam::<ACCOUNT_ID>:policy/<BOUNDARY_NAME>"
```

**Permissions boundary**: Only when the customer answered yes to question 30 with an ARN, set `permissions_boundary` in `cluster.yaml`. Every role the customer named then carries it; the input name per module is in [baseline-defaults.md](baseline-defaults.md#permissions-boundary-optional).

CloudWatch log retention at 365 days:
```hcl
resource "aws_cloudwatch_log_group" "eks_audit" {
  name              = "/aws/eks/${local.cluster_config.name}/cluster"
  retention_in_days = 365
  kms_key_id        = local.cluster_config.kms_key_arn
}
```

**Node hardening** in `compute.yaml`:
```yaml
managed_node_groups:
  default:
    ami_type: AL2023_x86_64_STANDARD
    metadata_options:
      http_endpoint: enabled
      http_tokens: required                  # IMDSv2 enforced
      http_put_response_hop_limit: 1         # Blocks containers from IMDS
    block_device_mappings:
      xvda:
        device_name: /dev/xvda
        ebs: { volume_size: 100, volume_type: gp3, encrypted: true, kms_key_id: "<KMS_ARN>" }
    iam_role_additional_policies:
      AmazonSSMManagedInstanceCore: "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
    remote_access: {}                        # No SSH -- SSM Session Manager only
```

**PSS Baseline enforcement** -- set `pss_level: baseline` and `default_deny: true` on all platform namespaces. The `default_deny` flag auto-creates a NetworkPolicy that blocks all ingress and egress (`podSelector: {}`, `policyTypes: [Ingress, Egress]`). Addon-specific allow rules must be layered on top per namespace.

**KMS envelope encryption**: the `kms_key_arn` in `cluster.yaml` enables encryption for all Kubernetes Secrets at rest. The KMS key must grant `eks.amazonaws.com` in its key policy, reside in the same region, and have automatic rotation enabled.

**FIPS endpoints and pull-through cache**: the first pull of an image through an ECR pull-through cache rule does not work through the ECR FIPS endpoints; later pulls do ([ECR pull-through cache considerations](https://docs.aws.amazon.com/AmazonECR/latest/userguide/pull-through-cache.html)).
