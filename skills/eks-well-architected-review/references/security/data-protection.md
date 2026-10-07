# 🔒 Security — Data Protection

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**12 questions** — Encryption at rest (EBS, EFS, StorageClass), secrets management & rotation, service mesh, mTLS, and Ingress TLS.

> **Scoring is authoritative in the consolidated Security scorer in [identity-access.md](identity-access.md).**
> The per-question `Detection:` tags below are explanatory only; the scorer decides measured vs governance.

Scoring (applies to every question): percentage-based — ≥90% → `all`, ≥70% → `most`, >0% → `some`, 0% → `none`; boolean — true/present → `all`, false/absent → `none`.

---

## Table of Contents

1. [Secrets management](#secrets-management)
   - [sec-8: Is an external secrets manager operator (e.g. External Secrets Operator) deployed on the cluster?](#sec-8-is-an-external-secrets-manager-operator-eg-external-secrets-operator-deployed-on-the-cluster)
   - [sec-24: Do you leverage AWS Secrets Manager and Config Provider (ASCP), EKS secrets encryption, or third-party solutions like HashiCorp Vault to manage secrets in EKS?](#sec-24-do-you-leverage-aws-secrets-manager-and-config-provider-ascp-eks-secrets-encryption-or-third-party-solutions-like-hashicorp-vault-to-manage-secrets-in-eks)
   - [sec-34: Do you implement automatic rotation of secrets, credentials, and TLS certificates?](#sec-34-do-you-implement-automatic-rotation-of-secrets-credentials-and-tls-certificates)
   - [sec-35: Do you implement automatic rotation of secrets, credentials, database passwords, and TLS certificates used by your EKS workloads, using tools like AWS Secrets Manager, External Secrets Operator, or cert-manager?](#sec-35-do-you-implement-automatic-rotation-of-secrets-credentials-database-passwords-and-tls-certificates-used-by-your-eks-workloads-using-tools-like-aws-secrets-manager-external-secrets-operator-or-cert-manager)
2. [Protect data at rest](#protect-data-at-rest)
   - [sec-21: Are EBS volumes used by the cluster encrypted at rest?](#sec-21-are-ebs-volumes-used-by-the-cluster-encrypted-at-rest)
   - [sec-38: Is the cluster configured to envelope-encrypt Kubernetes Secrets with a customer-managed KMS key?](#sec-38-is-the-cluster-configured-to-envelope-encrypt-kubernetes-secrets-with-a-customer-managed-kms-key)
   - [sec-22: Do you enable encryption at rest for Amazon EFS file systems used by Pods?](#sec-22-do-you-enable-encryption-at-rest-for-amazon-efs-file-systems-used-by-pods)
   - [sec-25: Are StorageClasses configured with encryption enabled for new volumes?](#sec-25-are-storageclasses-configured-with-encryption-enabled-for-new-volumes)
3. [Protect data in transit](#protect-data-in-transit)
   - [sec-23: Do you enable encryption in transit for Amazon EFS when using the EFS CSI driver?](#sec-23-do-you-enable-encryption-in-transit-for-amazon-efs-when-using-the-efs-csi-driver)
   - [sec-27: Is a service mesh control plane (Istio, Linkerd or Consul) deployed?](#sec-27-is-a-service-mesh-control-plane-istio-linkerd-or-consul-deployed)
   - [sec-28: Do workload pods carry a service-mesh sidecar (the data path for service-to-service mTLS)?](#sec-28-do-workload-pods-carry-a-service-mesh-sidecar-the-data-path-for-service-to-service-mtls)
   - [sec-29: Are Ingress resources configured with TLS termination?](#sec-29-are-ingress-resources-configured-with-tls-termination)

---

## Secrets management

### sec-8: Is an external secrets manager operator (e.g. External Secrets Operator) deployed on the cluster?

**Detection:** 🔬 AUTO-DETECTABLE

> External secrets managers provide rotation, auditing, and centralized control over sensitive data.
> **This detection is a Deployment name match plus a readiness check, and nothing more.** It passes only
> when a Deployment whose name contains `external-secrets`, other than the chart's `-webhook`,
> `-cert-controller` and `-bitwarden-sdk-server` companions, has `readyReplicas` above zero, so a controller
> scaled to zero or with no Ready pod fails even while a companion runs; it reads Deployments only, so an
> operator installed as a StatefulSet or DaemonSet is invisible to it; and — the limit that matters most — it
> never looks at the outcome, because no `ExternalSecret` or `SecretStore` object is collected. A pass says an
> operator appears to be installed, not that any Secret here is sourced from AWS Secrets Manager or rotated.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for external-secrets in deployment names
```

**Remediation:** Deploy External Secrets Operator: `helm repo add external-secrets https://charts.external-secrets.io && helm repo update && helm install external-secrets external-secrets/external-secrets`. Migrate K8s Secrets to AWS Secrets Manager references.

---

### sec-24: Do you leverage AWS Secrets Manager and Config Provider (ASCP), EKS secrets encryption, or third-party solutions like HashiCorp Vault to manage secrets in EKS?

**Detection:** ✋ ASK USER

> Assess secrets management practices and tools for secure credential storage.

**Remediation:** Use AWS Secrets Manager with ASCP or External Secrets Operator for secrets management. Enable automatic rotation on all secrets.

---

### sec-34: Do you implement automatic rotation of secrets, credentials, and TLS certificates?

**Detection:** ✋ ASK USER

> Secret rotation limits the blast radius of credential compromise.

**Remediation:** Deploy cert-manager for TLS rotation: `helm repo add jetstack https://charts.jetstack.io && helm repo update && helm install cert-manager jetstack/cert-manager --set crds.enabled=true`. Configure External Secrets Operator with rotation policies.

---

### sec-35: Do you implement automatic rotation of secrets, credentials, database passwords, and TLS certificates used by your EKS workloads, using tools like AWS Secrets Manager, External Secrets Operator, or cert-manager?

**Detection:** ✋ ASK USER

> Assess the implementation of automated secrets rotation to reduce the risk of credential compromise and meet security compliance requirements.

**Remediation:** Use AWS Secrets Manager with ASCP or External Secrets Operator for secrets management. Enable automatic rotation on all secrets.

---

## Protect data at rest

### sec-21: Are EBS volumes used by the cluster encrypted at rest?

**Detection:** 🔬 AUTO-DETECTABLE

> EBS encryption protects data at rest from unauthorized access. **On EKS Auto Mode this question has two halves and AWS answers only one of them.** The node's own disks are AWS's: "On EKS Auto Mode nodes, the root and data Amazon EBS volumes are encrypted and configured to be deleted upon termination of the instance" (AWS's EKS Auto Mode security whitepaper, under "Instance configuration": https://docs.aws.amazon.com/whitepapers/latest/security-overview-amazon-eks-auto-mode/eks-auto-mode-data-plane.html), with an optional customer-managed key via the `NodeClass`. The volumes your workloads ask for are still yours: AWS draws the line itself, in a single bullet under "Data protection" on https://docs.aws.amazon.com/eks/latest/userguide/auto-security.html — "EKS Auto Mode manages the volumes attached to EC2 instances at creation time, including root and data volumes. EKS Auto Mode does not fully manage EBS volumes created using Kubernetes persistent storage features" — and, in the first bullet under "Storage security" on that same page, recommends what you must do about it: "AWS recommends that you enable encryption for EBS Volumes provisioned by Kubernetes persistent storage features." So an Auto Mode cluster gets no blanket pass here: every volume that carries a tag naming the cluster, is attached to one of its EC2 nodes, or is named by a PersistentVolume, is still counted, and the StorageClass that decides the next PersistentVolume's encryption is scored separately by **sec-25**.
> **EKS Hybrid Nodes:** The population is every EBS volume that carries a tag naming this cluster, is named by a PersistentVolume, or is attached to one of its EC2 nodes, and that node set is EC2 only — a hybrid node is never in it, so nothing reaches this measurement through one. AWS documents that Amazon EBS volumes and the EBS CSI driver are not compatible with hybrid nodes, so whatever storage they use is not covered, and wherever this question reports a ratio the detail names how many hybrid nodes were left out.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
aws ec2 describe-volumes --region <REGION> --query "Volumes[].Encrypted"
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.encryptionConfig"
# EKS Auto Mode hides its managed instances and their volumes from list calls, so a bare
# describe-volumes can come back empty on a cluster that has plenty. The collector recovers them by
# id; if you run this by hand, pass the ids from the nodes and the PersistentVolumes:
kubectl get pv -o json | jq -r '.items[].spec.csi.volumeHandle'
```

**Remediation:** EBS volumes **cannot be encrypted in place** — `ModifyVolume` has no encryption
parameter, and AWS states "You can't directly encrypt existing unencrypted volumes or snapshots"
(https://docs.aws.amazon.com/ebs/latest/userguide/ebs-encryption.html, under "Encrypt unencrypted
resources"). For a PersistentVolume's volume: snapshot it, create an encrypted volume from the
snapshot, then create a new static PersistentVolume whose `spec.csi.volumeHandle` is the new volume id
and bind the workload to a new PersistentVolumeClaim on it (this needs downtime for the pod using that
volume). Detaching the old volume and attaching the new one by hand does not work: a PersistentVolume's
volume source cannot be changed after creation, so the driver keeps attaching the old volume. For a
node's root or data volume: turn on encryption for new volumes (account-level default below, or the
node group's launch template or Karpenter `EC2NodeClass` block device mappings), then replace the
nodes — a root volume cannot be detached while its instance is running.

```bash
aws ec2 create-snapshot --volume-id <vol-id> --description "pre-encryption"
aws ec2 create-volume --snapshot-id <snap-id> --availability-zone <az> \
  --encrypted --kms-key-id <key-arn> --volume-type gp3
```

To stop it recurring, turn on account-level default encryption so *new* volumes are always encrypted,
and set `encrypted: "true"` in the StorageClass so dynamically provisioned volumes are covered:

```bash
aws ec2 enable-ebs-encryption-by-default --region <region>
```

On EKS Auto Mode, apply that same account-level default and the StorageClass parameter (see sec-25 for
the Auto Mode provisioner name) — the node root and data volumes need no action, and a customer-managed
key for them is set through the `NodeClass` field `spec.ephemeralStorage.kmsKeyID`, not through this
question.

---

---

### sec-38: Is the cluster configured to envelope-encrypt Kubernetes Secrets with a customer-managed KMS key?

**Detection:** 🔬 AUTO-DETECTABLE — reads `cluster.encryptionConfig` from `cluster.json`.

<!-- MAINTAINER NOTE — not report content. Deliberately placed outside the blockquote and the
     Remediation block so the renderer does not extract it (see question_prose() in
     assets/render-report.py, which takes the first `>` blockquote and the Remediation text only).
     cluster.encryptionConfig is collected on every run and this question is what scores it; sec-21
     covers EBS volumes only. Without it, a cluster with no customer-managed envelope-encryption key
     would take no penalty and get no mention. Do not write that Secrets are unencrypted without
     encryptionConfig: that is wrong on every reachable version, because default envelope encryption
     is on for 1.28+ and no supported cluster is below 1.28. The real gap is the customer-managed key,
     not encryption.

     The rationale states the 1.28 floor explicitly rather than saying "every EKS cluster" with no
     version, plus the "every supported version is >=1.31" reasoning that makes the floor a
     non-issue. The Remediation's irreversibility citation leads with
     eksctl/kms-encryption.html (no version gate) and keeps
     userguide/enable-kms.html only as labeled pre-1.28 historical context — that page's own banner
     reads "This procedure is deprecated and only applies to EKS clusters running Kubernetes version
     1.27 or lower," which is a page this skill will never assess a cluster old enough to need. -->

> Every EKS cluster running Kubernetes 1.28 or higher already envelope-encrypts Kubernetes API data, Secrets included — AWS enables it by default with KMS v2 and an AWS-owned key and states it "doesn't require any action on your part" (https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html). That floor is a non-issue in practice: every Kubernetes version still in standard or extended support today is 1.31 or higher, so no cluster this review assesses falls below it. What this question measures is whose key it is. Under the AWS-owned key there is no key policy you can scope, no CloudTrail record of the key being used in your account, and no key you can disable, so the encryption is real but you can neither evidence nor control it; naming your own KMS key gives you all three, which is what an auditor means by control of the key. It is a separate control from disk encryption: etcd is encrypted at the disk level on every cluster irrespective of Kubernetes version, and envelope encryption does not cover data on nodes or EBS volumes — that is sec-21.
> **What a pass proves is configuration, not ciphertext.** The verdict is read from
> `cluster.encryptionConfig`, which records the key this cluster envelope-encrypts *writes* with. Secrets
> that already existed when the key was associated are not re-encrypted for you: only a write re-encrypts
> one, so a Secret moves to the new key the next time it is updated and any Secret nobody writes stays
> under the previous key. On a cluster where the key was added after the fact some Secrets may still sit
> under the AWS-owned key. Nothing in the collected data distinguishes the two states. Closing the gap takes a
> forced rewrite of every existing Secret — annotating them all so each is written back through the new
> provider — and this check cannot tell you whether that has ever been done.

**Commands:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query 'cluster.encryptionConfig'
```

**Remediation:** Choose the key as if it were permanent, because it is. AWS states that once KMS
encryption is enabled on a cluster, "it cannot be disabled or updated to use a different KMS key"
(https://docs.aws.amazon.com/eks/latest/eksctl/kms-encryption.html — this guidance carries no version
gate, since eksctl uses the same underlying API on every supported cluster). The stronger, older
phrasing — "You can't disable secrets encryption after enabling it. This action is irreversible" — comes
from a procedure AWS now marks "deprecated and only applies to EKS clusters running Kubernetes version
1.27 or lower" (https://docs.aws.amazon.com/eks/latest/userguide/enable-kms.html); it is cited here only
as pre-1.28 historical context, since it says the same thing the unrestricted page above already says.
Before running anything:

- **The key** must be symmetric, usable for encrypt and decrypt, and in the cluster's Region; give it an alias, a named owner and a deletion policy. A key in another account works only if the calling principal has access to it.
- **The permissions belong to the caller, not to the cluster.** `kms:DescribeKey` and `kms:CreateGrant` must be permitted "for the principal that calls the `create-cluster` API" — the human or pipeline identity running the command, not the cluster IAM role. And do not gate `kms:CreateGrant` with `kms:GrantIsForAWSResource`: AWS states that condition "is not supported for the CreateCluster action, and should not be used in KMS policies to control `kms:CreateGrant` permissions". Both quotes in this bullet are from https://docs.aws.amazon.com/eks/latest/userguide/enable-kms.html, whose deprecation banner is scoped to "This procedure": these two notes are about the KMS key policy for `CreateCluster` and AWS states them with no version qualifier. Copying the usual EBS key-policy stanza, which carries that condition, is how this fails.

```bash
aws eks associate-encryption-config --cluster-name <CLUSTER> --region <REGION> \
  --encryption-config '[{"resources":["secrets"],"provider":{"keyArn":"<KMS_KEY_ARN>"}}]'
# Asynchronous — poll until Successful before doing anything else:
aws eks describe-update --name <CLUSTER> --update-id <UPDATE_ID> --region <REGION>
```

`resources` is deprecated and no longer decides what gets encrypted — all Kubernetes API data is
covered either way — but if you send it, `["secrets"]` is the only accepted value
(https://docs.aws.amazon.com/eks/latest/APIReference/API_EncryptionConfig.html).

Existing Secrets are **not** re-encrypted for you: only a write re-encrypts one, so a Secret nobody
updates stays under the previous key. AWS's eksctl guide rewrites them as part of enabling the key:
"In addition to enabling KMS encryption on the EKS cluster, eksctl also re-encrypts all existing
Kubernetes secrets using the new KMS key by updating them with the annotation
`eksctl.io/kms-encryption-timestamp`" (https://docs.aws.amazon.com/eks/latest/eksctl/kms-encryption.html).
After the AWS CLI command above, do the same yourself by annotating them, which forces a write through
the new provider:

```bash
kubectl get secrets --all-namespaces -o json \
  | kubectl annotate --overwrite -f - kms-encryption-timestamp="$(date -u +%FT%TZ)"
```

That rewrites every Secret in every namespace, `kube-system` and the add-on namespaces included, so
expect a burst of API writes and every controller that watches Secrets to react; run it in a window
where that is acceptable.

**Afterwards the key is a single point of failure for the control plane, not a containment switch.**
Disabling it places the cluster "immediately ... in an unhealthy/degraded state", with 30 days to
re-enable before restoration stops being assured; deleting it degrades cluster health "beyond
recovery"; and if the grant is revoked (`KMS_GRANT_REVOKED`) "your cluster will not be recoverable"
(https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html). Restrict
`kms:DisableKey`, `kms:ScheduleKeyDeletion` and `kms:RevokeGrant` to key administrators and alarm on
the key's state. If the reason you want your own key is to be able to cut access to the data during an
incident, this control does not give you that: revoking it takes the cluster down with the Secrets.

---

### sec-22: Do you enable encryption at rest for Amazon EFS file systems used by Pods?

**Detection:** ✋ ASK USER

> Assess encryption at rest for shared file storage used by EKS workloads.

**Remediation:** Encryption at rest cannot be turned on for an existing EFS file system — AWS states "After you create an EFS file system, you cannot change its encryption setting" (https://docs.aws.amazon.com/efs/latest/ug/encryption-at-rest.html). Create new file systems encrypted (the console does this by default; with the CLI pass `--encrypted`, and `--kms-key-id` for a customer managed KMS key). For an existing unencrypted one, use EFS replication to copy it into a new encrypted file system, then fail over to it and point the workloads at the new file system ID; a PersistentVolume's `volumeHandle` cannot be edited, so that means new PersistentVolumes and claims.

---

### sec-25: Are StorageClasses configured with encryption enabled for new volumes?

**Detection:** 🔬 AUTO-DETECTABLE

> Encrypted StorageClasses ensure all new PVCs are automatically encrypted. This is entirely the operator's object on **every** compute shape, EKS Auto Mode included — AWS creates no StorageClass for you there ("EKS Auto Mode does not create a `StorageClass` for you. You must create a `StorageClass` referencing `ebs.csi.eks.amazonaws.com` to use the storage capability of EKS Auto Mode" — https://docs.aws.amazon.com/eks/latest/userguide/create-storage-class.html) and recommends that you "enable encryption for EBS Volumes provisioned by Kubernetes persistent storage features" (https://docs.aws.amazon.com/eks/latest/userguide/auto-security.html, under "Storage security"). Auto Mode's driver has a different name from the self-managed one, so a StorageClass named for the wrong provisioner provisions nothing. **All three EBS provisioner names are counted, and an Auto Mode cluster usually has more than one class.** A real Auto Mode cluster commonly still carries the legacy in-tree `gp2` class next to its `ebs.csi.eks.amazonaws.com` one, and `gp2` sets no `encrypted` parameter — so a ratio like `1/2` here means one class provisions encrypted volumes and one does not, not that the cluster is half covered. Whichever class is marked default is the one that decides what an unqualified PVC gets, so check that first.

**Commands:**
```bash
kubectl get storageclasses -o json
# Check parameters.encrypted == "true", on any of the three EBS provisioners:
#   ebs.csi.aws.com             self-managed / add-on EBS CSI driver
#   ebs.csi.eks.amazonaws.com   EKS Auto Mode
#   kubernetes.io/aws-ebs       in-tree legacy
```

**Remediation:** Update StorageClasses to include `encrypted: "true"` in parameters. Create a new default
StorageClass with encryption enabled. **This covers only volumes provisioned after the change** — a
StorageClass has no effect on PVCs and volumes that already exist. For those, see sec-21's remediation:
EBS volumes cannot be encrypted in place, so an existing unencrypted volume needs the snapshot-and-recreate
path and a new PersistentVolume bound to the new volume.

On EKS Auto Mode the StorageClass must name Auto Mode's own provisioner, or nothing provisions:

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: auto-ebs-sc
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: ebs.csi.eks.amazonaws.com
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Delete
parameters:
  type: gp3
  encrypted: "true"
  # kmsKeyId: <key-arn>   # optional: a customer-managed key instead of the AWS managed key
```

---

## Protect data in transit

### sec-23: Do you enable encryption in transit for Amazon EFS when using the EFS CSI driver?

**Detection:** ✋ ASK USER

> Evaluate encryption in transit for EFS connections from Pods.

**Remediation:** The EFS CSI driver mounts with TLS by default (`encryptInTransit` defaults to `"true"`), so no `tls` mount option is needed — listing `tls` under `mountOptions` is deprecated. What turns encryption in transit off is a PersistentVolume whose `spec.csi.volumeAttributes` sets `encryptInTransit: "false"` (the driver matches the key in any case and parses the value as a Go boolean, so `"0"`, `"f"`, `"F"`, `"false"`, `"FALSE"` and `"False"` count too, while any other spelling fails the mount), which mounts over plain NFSv4 unless the volume uses an EFS access point (an access-point mount is always TLS); find those with `kubectl get pv -o json | jq -r '.items[] | select(.spec.csi.driver=="efs.csi.aws.com" and any(.spec.csi.volumeAttributes // {} | to_entries[]; (.key | ascii_downcase) == "encryptintransit" and (.value | test("^(0|f|F|false|FALSE|False)$")))) | .metadata.name'`. A PersistentVolume's volume source cannot be edited after creation, so replace each with a new PersistentVolume and claim that omits the attribute.

---

### sec-27: Is a service mesh control plane (Istio, Linkerd or Consul) deployed?

**Detection:** 🔬 AUTO-DETECTABLE

> Service meshes provide mTLS, traffic policies, and observability between services. **This detection
> looks for a mesh control plane by name, and a control plane is not enforcement.** It matches Deployments
> in a namespace named exactly `istio-system`, `linkerd` (or a Linkerd extension namespace: `linkerd-viz`,
> `linkerd-jaeger`, `linkerd-multicluster`, `linkerd-smi`) or `consul`, and Deployments whose names contain
> `istiod`, `linkerd` or `consul-connect`. A mesh installed into a namespace with any other name is found only
> by those Deployment names; it reads Deployments only, so a mesh whose control plane runs as a StatefulSet
> or DaemonSet is missed entirely;
> and even a correct match says only that a control plane exists. Two naming notes:
> **AWS App Mesh is not matched at all** (it is an AWS-managed control
> plane with no `istiod`-like Deployment in the cluster for this pattern to find, and AWS has announced
> its end of support), and **Consul is matched**. Whether any workload carries a sidecar is sec-28;
> whether traffic between workloads is actually encrypted is not judged by either question.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for istio-system, linkerd namespaces
kubectl get pods -A -o json
# Look for istio-proxy or linkerd-proxy containers
```

**Remediation:** Deploy Istio or Linkerd service mesh: `istioctl install --set profile=default`. Inject sidecars into workload namespaces.

---

### sec-28: Do workload pods carry a service-mesh sidecar (the data path for service-to-service mTLS)?

**Detection:** 🔬 AUTO-DETECTABLE

> mTLS ensures all service-to-service communication is encrypted and authenticated, and a mesh sidecar
> is what carries it. **This detection measures sidecar presence only — not whether mTLS is enforced.**
> It counts the workload pods (namespaces outside `kube-*` and `amazon-*`, phase neither `Succeeded`
> nor `Failed`, and not the mesh's own pods: the mesh namespaces `istio-system`, `istio-ingress`, `istio-egress`, `linkerd` (and `linkerd-viz`/`-jaeger`/`-multicluster`/`-smi`)
> and `consul`, and pods
> labelled as Linkerd control plane, Istio ztunnel or an Istio gateway, which run the proxy themselves) whose `spec.containers` include a container named `istio-proxy`, `linkerd-proxy`,
> `envoy-sidecar` or `consul-dataplane` (Istio, Linkerd, Consul; exact names, plus Consul's `-<service>`
> multi-port form), and the state follows that ratio.
> No mesh configuration is read — not Istio `PeerAuthentication`, not Linkerd policy, not Consul
> `ProxyDefaults` or `ServiceDefaults` — so a mesh left in a permissive mode that still accepts
> plaintext scores the same as one enforcing mTLS. A sidecar injected as a native sidecar under
> `initContainers` is not seen. Confirm the effective mode per workload (for Istio,
> `istioctl x describe pod <pod>`) before reading a pass as encryption.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get pods -A -o json
# Count workload pods with an istio-proxy, linkerd-proxy, envoy-sidecar or consul-dataplane container vs total
```

**Remediation:** In Istio the sidecars already encrypt traffic to each other; the control is the
PeerAuthentication `mode`. A `STRICT` policy in `istio-system` applies to the **whole mesh** and drops
every plaintext connection the moment it is applied — pods in namespaces you have not injected, Jobs
and operators without a sidecar, and anything reaching a pod from outside the mesh. Phase it instead:

- **Stay PERMISSIVE while you inject.** `kubectl label namespace <ns> istio-injection=enabled`, then restart the workloads in that namespace so they pick up a sidecar. PERMISSIVE accepts both plaintext and mTLS, so nothing breaks mid-rollout.
- **Verify there is no plaintext left** in that namespace before tightening it: `istioctl x describe pod <pod>` reports the effective mTLS mode, and `istio_requests_total` filtered to `connection_security_policy!="mutual_tls"` shows what is still arriving unencrypted.
- **Then STRICT, one namespace at a time**, watching client-side errors (connection resets, HTTP 000 in Envoy logs) after each one.
- **`istio-system` last**, once every namespace is already STRICT on its own, so the mesh-wide policy changes nothing that has not already been proven.

```yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: default
  namespace: <ns>          # istio-system applies mesh-wide — leave that until last
spec:
  mtls:
    mode: STRICT
```

Keep per-port `PERMISSIVE` exceptions (`spec.portLevelMtls`) for anything that genuinely cannot be
meshed, rather than reverting the namespace. For Linkerd, mTLS is on by default for meshed pod-to-pod
TCP traffic; the equivalent tightening there is an authorization policy that rejects unmeshed traffic,
not a mesh-wide switch.

---

### sec-29: Are Ingress resources configured with TLS termination?

**Detection:** 🔬 AUTO-DETECTABLE

> TLS on Ingress ensures traffic from clients to the cluster is encrypted. **What this proves is that a
> certificate is configured on the Ingress object, not that plaintext is refused on the wire.** An
> `alb.ingress.kubernetes.io/certificate-arn` annotation counts unless `alb.ingress.kubernetes.io/listen-ports`
> is set and names no `HTTPS` listener; unset, the AWS Load Balancer Controller defaults it to `[{"HTTPS": 443}]`
> when a certificate is named and to `[{"HTTP": 80}]` when not. So a non-empty `spec.tls` counts on an `alb`-class
> Ingress (`spec.ingressClassName` or legacy `kubernetes.io/ingress.class` = `alb`; an IngressClass of another
> name is judged as non-ALB) only beside an `HTTPS` listen-ports entry, elsewhere unless listen-ports is set and names no
> `HTTPS` listener. NOT read: `ssl-redirect` or the nginx equivalents, so TLS on 443 while port 80 still serves HTTP passes. **A Fail is still not proof
> of plaintext exposure**: a certificate can sit somewhere this does not look — a default TLS
> certificate on the ingress controller itself, an Istio `Gateway` instead of the `Ingress`, ALB
> certificate discovery from ACM against the host rules when the annotation is absent (that still needs
> an HTTPS `listen-ports` entry to create an HTTPS listener).
> It also reads `Ingress` objects only: a `Service` of `type: LoadBalancer` publishing a port directly
> is outside the denominator, which is why the no-Ingress case reports "not assessed" rather than a pass.

**Commands:**
```bash
kubectl get ingresses -A -o json
# Check spec.tls and the alb.ingress.kubernetes.io/certificate-arn annotation; listen-ports, if set, needs an HTTPS entry (and on an alb-class Ingress, spec.tls without certificate-arn needs one even when unset)
```

**Remediation:** The mechanism depends on which controller fronts the Ingress, and picking the wrong one is work that changes nothing about what is on the wire. Read `spec.ingressClassName` (or the legacy `kubernetes.io/ingress.class` annotation) first, then:

- **AWS Load Balancer Controller (`alb`).** `spec.tls` does not configure an ALB listener — adding it, or a cert-manager Certificate to back it, leaves the listeners exactly as they were. Attach an ACM certificate with `alb.ingress.kubernetes.io/certificate-arn`, publish HTTPS only with `alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS":443}]'`, and where port 80 has to stay reachable add `alb.ingress.kubernetes.io/ssl-redirect: '443'` so it redirects instead of serving. Confirm it on the load balancer and not on the Ingress: `aws elbv2 describe-listeners --load-balancer-arn <arn>` should show no HTTP listener that forwards to a target group.
- **In-cluster controllers (nginx, Traefik, an Istio gateway).** Here `spec.tls` IS the mechanism: add it naming a Secret that holds the certificate, and use cert-manager for automatic provisioning and renewal. On nginx also set `nginx.ingress.kubernetes.io/ssl-redirect: "true"` so port 80 redirects rather than serving plaintext.

Either way, adding a certificate does not by itself close port 80 — the redirect or the listener list is the part that does.

---
