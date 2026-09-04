# 🔒 Security — Data Protection

**11 questions** — Encryption at rest (EBS, EFS, StorageClass), secrets management & rotation, service mesh, mTLS, and Ingress TLS.

> **Scoring is authoritative in the consolidated Security scorer in [identity-access.md](identity-access.md).**
> The per-question `Detection:` tags below are explanatory only; the scorer decides measured vs governance.

Scoring (applies to every question): percentage-based — ≥90% → `all`, ≥70% → `most`, >0% → `some`, 0% → `none`; boolean — true/present → `all`, false/absent → `none`. ASK USER responses: "Yes, fully" → `all`, "Mostly" → `most`, "Partially" → `some`, "No" → `none`, "Doesn't apply" → `not-applicable`.

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

> EBS encryption protects data at rest from unauthorized access.

**Commands:**
```bash
aws ec2 describe-volumes --region <REGION> --query "Volumes[].Encrypted"
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.encryptionConfig"
```

**Remediation:** Encrypt EBS volumes: `aws ec2 modify-volume --volume-id <id> --encrypted`. Update StorageClass with `encrypted: "true"`.

---

### sec-22: Do you enable encryption at rest for Amazon EFS file systems used by Pods?

**Detection:** ✋ ASK USER

> Assess encryption at rest for shared file storage used by EKS workloads.

**Remediation:** Enable encryption at rest for EFS: create the file system with `--encrypted` flag or update via console. Use KMS CMK for key management.

---

### sec-25: Are StorageClasses configured with encryption enabled for new volumes?

**Detection:** 🔬 AUTO-DETECTABLE

> Encrypted StorageClasses ensure all new PVCs are automatically encrypted.

**Commands:**
```bash
kubectl get storageclasses -o json
# Check parameters.encrypted == "true"
```

**Remediation:** Update StorageClasses to include `encrypted: "true"` in parameters. Create a new default StorageClass with encryption enabled.

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

**Remediation:** Enable strict mTLS in Istio: create a PeerAuthentication resource with mtls mode STRICT. For Linkerd, mTLS is enabled by default. Apply cluster-wide by setting the resource in the istio-system namespace.

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
