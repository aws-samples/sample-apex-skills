# EKS Infrastructure Customization Guide

Covers environment-specific constraints that require modifications to the baseline patterns.

---

## 1. Air-Gapped / VPC-Endpoint-Only Networks

Clusters with no internet egress must reach AWS services through VPC endpoints. Every image pull, Helm fetch, and API call must stay within the VPC.

**Required VPC endpoints** (all Interface type except S3 which is Gateway):
`eks`, `eks-auth`, `ecr.api`, `ecr.dkr`, `s3` (Gateway), `sts`, `ec2`,
`elasticloadbalancing`, `autoscaling`, `logs`, `ebs`, `ssm`.
All interface endpoints must have private DNS enabled and share the worker node subnets and security groups.

**ECR pull-through cache** -- mirror every public registry into private ECR:
```bash
aws ecr create-pull-through-cache-rule --ecr-repository-prefix ecr-public  --upstream-registry-url public.ecr.aws
aws ecr create-pull-through-cache-rule --ecr-repository-prefix docker-hub  --upstream-registry-url registry-1.docker.io
aws ecr create-pull-through-cache-rule --ecr-repository-prefix quay        --upstream-registry-url quay.io
aws ecr create-pull-through-cache-rule --ecr-repository-prefix ghcr        --upstream-registry-url ghcr.io
```

**containerd mirror config** via AL2023 nodeadm in `compute.yaml`:
```yaml
cloudinit_pre_nodeadm:
  - content_type: application/node.eks.aws
    content: |
      [settings.container-registry.mirrors]
        [settings.container-registry.mirrors."docker.io"]
          endpoints = ["https://<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/docker-hub"]
        [settings.container-registry.mirrors."quay.io"]
          endpoints = ["https://<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/quay"]
        [settings.container-registry.mirrors."ghcr.io"]
          endpoints = ["https://<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/ghcr"]
```

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

**NO_PROXY must include**: `169.254.169.254` (IMDS), `169.254.170.2` (credential provider), `10.0.0.0/8` (VPC CIDR -- adjust as needed), `.internal`, `.eks.amazonaws.com`, `.s3.amazonaws.com`, `.ecr.amazonaws.com`, `.dkr.ecr.amazonaws.com`.

**Proxy-aware addon config** -- inject env vars via Helm `set` in `addons.yaml`:
```yaml
aws_load_balancer_controller:
  config:
    set:
      - { name: env.HTTP_PROXY,  value: "http://<PROXY_HOST>:<PROXY_PORT>" }
      - { name: env.HTTPS_PROXY, value: "http://<PROXY_HOST>:<PROXY_PORT>" }
      - { name: env.NO_PROXY,    value: "169.254.169.254,169.254.170.2,10.0.0.0/8,.internal,.eks.amazonaws.com" }
```
Apply the same pattern to: `cluster_autoscaler`, `external_dns`, `external_secrets`, `cert_manager`, `velero`, and `ingress_nginx`.

---

## 3. Private Container Registry

All images must come from an approved private registry. Override every addon's image references and restrict what the cluster can pull.

**Per-addon image repository overrides** in `addons.yaml`:
```yaml
aws_load_balancer_controller:
  config:
    set:
      - { name: image.repository, value: "<REGISTRY_HOST>/eks/aws-load-balancer-controller" }
cluster_autoscaler:
  config:
    set:
      - { name: image.repository, value: "<REGISTRY_HOST>/k8s/cluster-autoscaler" }
cert_manager:
  config:
    set:
      - { name: image.repository,            value: "<REGISTRY_HOST>/jetstack/cert-manager-controller" }
      - { name: webhook.image.repository,    value: "<REGISTRY_HOST>/jetstack/cert-manager-webhook" }
      - { name: cainjector.image.repository, value: "<REGISTRY_HOST>/jetstack/cert-manager-cainjector" }
external_secrets:
  config:
    set:
      - { name: image.repository, value: "<REGISTRY_HOST>/ghcr/external-secrets" }
velero:
  config:
    set:
      - { name: image.repository,        value: "<REGISTRY_HOST>/docker/velero/velero" }
      - { name: kubectl.image.repository, value: "<REGISTRY_HOST>/docker/bitnami/kubectl" }
metrics_server:
  config:
    set:
      - { name: image.repository, value: "<REGISTRY_HOST>/k8s/metrics-server" }
external_dns:
  config:
    set:
      - { name: image.repository, value: "<REGISTRY_HOST>/k8s/external-dns" }
```

**ImagePullSecret** -- create a `kubernetes.io/dockerconfigjson` Secret in each namespace, then inject it via Kyverno mutation policy or by patching the default ServiceAccount.

**Kyverno registry restriction policy** -- deploy a `ClusterPolicy` with `validationFailureAction: Enforce` that matches all Pods and validates both `containers[*].image` and `initContainers[*].image` against an allow-list: `<REGISTRY_HOST>/*` and `<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/*`. Reject anything else at admission.

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
```

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
