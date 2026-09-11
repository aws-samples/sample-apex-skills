---
title: "🔒 Security — Data Protection"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/security/data-protection.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/references/security/data-protection.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/security/data-protection.md). Edit the source, not this page.
:::

# 🔒 Security — Data Protection

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**12 questions** — Encryption at rest (EBS, EFS, StorageClass), secrets management & rotation, service mesh, mTLS, and Ingress TLS.

> **Scoring is authoritative in the consolidated Security scorer in [identity-access.md](identity-access).**
> The per-question `Detection:` tags below are explanatory only; the scorer decides measured vs governance.

Scoring (applies to every question): percentage-based — ≥90% → `all`, ≥70% → `most`, >0% → `some`, 0% → `none`; boolean — true/present → `all`, false/absent → `none`. ASK USER responses: "Yes, fully" → `all`, "Mostly" → `most`, "Partially" → `some`, "No" → `none`, "Doesn't apply" → `na`.

---

## Secrets management

### sec-8: Are Kubernetes Secrets managed using an external secrets manager (e.g., External Secrets Operator)?

**Detection:** 🔬 AUTO-DETECTABLE

> External secrets managers provide rotation, auditing, and centralized control over sensitive data.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for external-secrets in deployment names
```

**Remediation:** Deploy External Secrets Operator: `helm install external-secrets external-secrets/external-secrets`. Migrate K8s Secrets to AWS Secrets Manager references.

---

### sec-24: Do you leverage AWS Secrets Manager and Config Provider (ASCP), EKS secrets encryption, or third-party solutions like HashiCorp Vault to manage secrets in EKS?

**Detection:** ✋ ASK USER

> Assess secrets management practices and tools for secure credential storage.

**Remediation:** Use AWS Secrets Manager with ASCP or External Secrets Operator for secrets management. Enable automatic rotation on all secrets.

---

### sec-34: Do you implement automatic rotation of secrets, credentials, and TLS certificates?

**Detection:** ✋ ASK USER

> Secret rotation limits the blast radius of credential compromise.

**Remediation:** Deploy cert-manager for TLS rotation: `helm install cert-manager jetstack/cert-manager`. Configure External Secrets Operator with rotation policies.

---

### sec-35: Do you implement automatic rotation of secrets, credentials, database passwords, and TLS certificates used by your EKS workloads, using tools like AWS Secrets Manager, External Secrets Operator, or cert-manager?

**Detection:** ✋ ASK USER

> Assess the implementation of automated secrets rotation to reduce the risk of credential compromise and meet security compliance requirements.

**Remediation:** Use AWS Secrets Manager with ASCP or External Secrets Operator for secrets management. Enable automatic rotation on all secrets.

---

## Protect data at rest

### sec-21: Are EBS volumes used by the cluster encrypted at rest?

**Detection:** 🔬 AUTO-DETECTABLE

> EBS encryption protects data at rest from unauthorized access. **On EKS Auto Mode this question has two halves and AWS answers only one of them.** The node's own disks are AWS's: "On EKS Auto Mode nodes, the root and data Amazon EBS volumes are encrypted and configured to be deleted upon termination of the instance", with an optional customer-managed key via the `NodeClass`. The volumes your workloads ask for are still yours: AWS draws the line itself — "EKS Auto Mode manages the volumes attached to EC2 instances at creation time, including root and data volumes. EKS Auto Mode does not fully manage EBS volumes created using Kubernetes persistent storage features" — and then recommends what you must do about it: "AWS recommends that you enable encryption for EBS Volumes provisioned by Kubernetes persistent storage features." So an Auto Mode cluster gets no blanket pass here: every cluster-tagged volume is still counted, and the StorageClass that decides the next PersistentVolume's encryption is scored separately by **sec-25**.

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
parameter, and AWS states "You can't directly encrypt existing unencrypted volumes or snapshots." For
each existing unencrypted volume: snapshot it, create an encrypted volume from the snapshot, then
detach the old volume and attach the new one (this needs downtime for the pod using that volume).

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

### sec-38: Are Kubernetes Secrets encrypted with a customer-managed KMS key (envelope encryption)?

**Detection:** 🔬 AUTO-DETECTABLE — reads `cluster.encryptionConfig` from `cluster.json`.

<!-- MAINTAINER NOTE — not report content. Deliberately placed outside the blockquote and the
     Remediation block so the renderer does not extract it (see question_prose() in
     assets/render-report.py, which takes the first `>` blockquote and the Remediation text only).
     History: this question was promised and not delivered. sec-21's remediation prose named
     cluster-level Secrets encryption, and cluster.encryptionConfig has been collected on every run,
     but nothing scored it — so a cluster with no envelope encryption took no penalty and got no
     mention. The blockquote then claimed Secrets were unencrypted without encryptionConfig, which is
     wrong on every reachable version: default envelope encryption is on for 1.28+ and no supported
     cluster is below 1.28. The real gap is the customer-managed key, not encryption.

     2026-09-11 update: the rationale now states the 1.28 floor explicitly (it previously said "every
     EKS cluster" with no version), plus the "every supported version is >=1.31" reasoning that makes
     the floor a non-issue. The Remediation's irreversibility citation now leads with
     eksctl/kms-encryption.html (no version gate; fetched live, confirmed current) and keeps
     userguide/enable-kms.html only as labeled pre-1.28 historical context — that page's own banner
     reads "This procedure is deprecated and only applies to EKS clusters running Kubernetes version
     1.27 or lower," which is a page this skill will never assess a cluster old enough to need. -->

> Every EKS cluster running Kubernetes 1.28 or higher already envelope-encrypts Kubernetes API data, Secrets included — AWS enables it by default with KMS v2 and an AWS-owned key and states it "doesn't require any action on your part" (https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html). That floor is a non-issue in practice: every Kubernetes version still in standard or extended support today is 1.31 or higher, so no cluster this review assesses falls below it. What this question measures is whose key it is. Under the AWS-owned key there is no key policy you can scope, no CloudTrail record of the key being used in your account, and no key you can disable, so the encryption is real but you can neither evidence nor control it; naming your own KMS key gives you all three, which is what an auditor means by control of the key. It is a separate control from disk encryption: etcd is encrypted at the disk level on every cluster irrespective of Kubernetes version, and envelope encryption does not cover data on nodes or EBS volumes — that is sec-21.

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
- **The permissions belong to the caller, not to the cluster.** `kms:DescribeKey` and `kms:CreateGrant` must be permitted "for the principal that calls the `create-cluster` API" — the human or pipeline identity running the command, not the cluster IAM role. And do not gate `kms:CreateGrant` with `kms:GrantIsForAWSResource`: AWS states that condition "is not supported for the CreateCluster action, and should not be used in KMS policies to control `kms:CreateGrant` permissions" here. Copying the usual EBS key-policy stanza, which carries that condition, is how this fails.

```bash
aws eks associate-encryption-config --cluster-name <CLUSTER> --region <REGION> \
  --encryption-config '[{"resources":["secrets"],"provider":{"keyArn":"<KMS_KEY_ARN>"}}]'
# Asynchronous — poll until Successful before doing anything else:
aws eks describe-update --name <CLUSTER> --update-id <UPDATE_ID> --region <REGION>
```

`resources` is deprecated and no longer decides what gets encrypted — all Kubernetes API data is
covered either way — but if you send it, `["secrets"]` is the only accepted value
(https://docs.aws.amazon.com/eks/latest/APIReference/API_EncryptionConfig.html).

Existing Secrets are **not** re-encrypted for you, and nothing re-encrypts them lazily. AWS: "After
you enabled encryption on your cluster, you must encrypt all existing secrets with the new key" — by
annotating them, which forces a write through the new provider:

```bash
kubectl get secrets --all-namespaces -o json \
  | kubectl annotate --overwrite -f - kms-encryption-timestamp="$(date -u +%FT%TZ)"
```

That rewrites every Secret in every namespace, `kube-system` and the add-on namespaces included, so
expect a burst of API writes and every controller that watches Secrets to react; run it in a window
where that is acceptable. `kubectl replace` on the same objects is not a substitute — it resubmits
byte-identical objects and is not guaranteed to write anything.

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

**Remediation:** Enable encryption at rest for EFS: create the file system with `--encrypted` flag or update via console. Use KMS CMK for key management.

---

### sec-25: Are StorageClasses configured with encryption enabled for new volumes?

**Detection:** 🔬 AUTO-DETECTABLE

> Encrypted StorageClasses ensure all new PVCs are automatically encrypted. This is entirely the operator's object on **every** compute shape, EKS Auto Mode included — AWS creates no StorageClass for you there ("EKS Auto Mode does not create a `StorageClass` for you. You must create a `StorageClass` referencing `ebs.csi.eks.amazonaws.com` to use the storage capability of EKS Auto Mode") and recommends that you "enable encryption for EBS Volumes provisioned by Kubernetes persistent storage features". Auto Mode's driver has a different name from the self-managed one, so a StorageClass named for the wrong provisioner provisions nothing. **All three EBS provisioner names are counted, and an Auto Mode cluster usually has more than one class.** A real Auto Mode cluster commonly still carries the legacy in-tree `gp2` class next to its `ebs.csi.eks.amazonaws.com` one, and `gp2` sets no `encrypted` parameter — so a ratio like `1/2` here means one class provisions encrypted volumes and one does not, not that the cluster is half covered. Whichever class is marked default is the one that decides what an unqualified PVC gets, so check that first.

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
path.

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

**Remediation:** Enable encryption in transit for EFS by setting `mountOptions: [tls]` in the PersistentVolume spec when using the EFS CSI driver.

---

### sec-27: Is a service mesh (Istio, Linkerd, App Mesh) deployed for service-to-service security?

**Detection:** 🔬 AUTO-DETECTABLE

> Service meshes provide mTLS, traffic policies, and observability between services.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for istio-system, linkerd namespaces
kubectl get pods -A -o json
# Look for istio-proxy or linkerd-proxy containers
```

**Remediation:** Deploy Istio or Linkerd service mesh: `istioctl install --set profile=default`. Inject sidecars into workload namespaces.

---

### sec-28: Is mutual TLS (mTLS) enforced between services via a service mesh?

**Detection:** 🔬 AUTO-DETECTABLE

> mTLS ensures all service-to-service communication is encrypted and authenticated.

**Commands:**
```bash
kubectl get pods -A -o json
# Count pods with istio-proxy or linkerd-proxy sidecar vs total
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

> TLS on Ingress ensures traffic from clients to the cluster is encrypted.

**Commands:**
```bash
kubectl get ingresses -A -o json
# Check spec.tls configuration
```

**Remediation:** Configure TLS on Ingress resources: add `spec.tls` with a Secret containing the TLS certificate. Use cert-manager for automatic certificate provisioning.
