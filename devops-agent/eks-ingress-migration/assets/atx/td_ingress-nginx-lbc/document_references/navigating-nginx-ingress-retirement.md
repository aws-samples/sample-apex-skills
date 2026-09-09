# Navigating the NGINX Ingress Retirement: A Practical Guide to Migration on AWS

*Source: [AWS Networking & Content Delivery Blog](https://aws.amazon.com/blogs/networking-and-content-delivery/navigating-the-nginx-ingress-retirement-a-practical-guide-to-migration-on-aws/)*

The Kubernetes SIG Network and Security Response Committee has announced that Ingress NGINX will be retired in March 2026. If your organization runs workloads on Kubernetes — whether on Amazon Elastic Kubernetes Service (Amazon EKS), self-managed clusters on EC2, or hybrid environments — this upcoming change requires immediate planning and attention.

This change impacts approximately 50% of cloud-native environments currently dependent on Ingress NGINX. The Kubernetes Steering and Security Response Committees' joint statement made clear that fundamental architectural limitations render long-term maintenance impossible. As a result, after March 2026, organizations will receive no security patches, bug fixes, or updates of any kind. Organizations that continue running outdated Ingress NGINX will face escalating security risks from unpatched vulnerabilities, potential compliance violations under SOC 2, PCI-DSS, and HIPAA frameworks, and operational risks from permanently unresolved issues.

This blog post demonstrates how to migrate your Ingress configurations from NGINX Ingress Controller to AWS Load Balancer Controller through progressive enhancements, using a consistent example.

## Are You Affected?

Before diving into migration strategies, determine whether your clusters are running Ingress NGINX. Run the following command against each of your clusters:

```bash
kubectl get pods --all-namespaces --selector app.kubernetes.io/name=ingress-nginx
```

If this returns results, you have Ingress NGINX deployed and should plan your migration. Note that existing deployments will continue to function after retirement — but they will be exposed to any future vulnerabilities with no patches available.

## Migration Guidance: AWS Load Balancer Controller

Kubernetes provides two primary methods for exposing Services to external clients: Service of type LoadBalancer and Ingress resources. Both can be deployed leveraging AWS Elastic Load Balancing, but serve different purposes:

- **Network Load Balancer (NLB)** handles high-volume traffic at Layer 4 (TCP/UDP), making it ideal for performance-critical workloads requiring low latency and high throughput.
- **Application Load Balancer (ALB)** operates at Layer 7 (HTTP/HTTPS), providing advanced routing capabilities for web applications including path-based and host-based routing, authentication, and request transformation (URL and host header rewrite).

The AWS Load Balancer Controller automates the provisioning, configuration, and lifecycle management of both ALBs and NLBs as you deploy workloads in your Amazon EKS cluster, eliminating manual load balancer management and ensuring your infrastructure scales seamlessly with your applications. In addition, as of v3.0, AWS recently announced the general availability of AWS Load Balancer Controller support for Kubernetes Gateway API as well.

## AWS Load Balancer Controller vs. NGINX Ingress Controller

While both controllers implement the Kubernetes Ingress API, they differ fundamentally in architecture and capabilities.

### Architecture

**NGINX Ingress:**

- Runs as in-cluster pods acting as reverse proxy
- All traffic flows through NGINX pods (potential bottlenecks include CPU and memory saturation, connection limitations, and network throughput saturation)
- Requires LoadBalancer Service for external access

**AWS Load Balancer Controller:**

- Provisions native AWS load balancers outside the cluster
- Routes traffic directly to pods with intermediate when using Amazon VPC CNI
- Offloads processing to AWS infrastructure

### Feature Comparison, Operations, and Cost

- **NGINX Ingress Controller** offers a rich ecosystem of annotations and supports advanced NGINX features like rate limiting, custom headers, and Lua scripting, with all configurations stored in Kubernetes and certificate management via Secrets. However, it's limited to NGINX's feature set and requires self-management of pod health, updates, and scaling.
- **AWS Load Balancer Controller** provides native integrations with AWS services including ACM for automatic certificate discovery and renewal, WAF for web application firewall protection, Shield for DDoS protection, and Cognito/OIDC for authentication. It also supports advanced ALB capabilities like weighted target groups, Lambda targets, JWT validation, and Trust Store-based mutual TLS, with access to the latest AWS innovations including QUIC protocol support, Target Optimizer, and native URI rewrite functionality.
- **Operationally**, NGINX requires you to maintain pod infrastructure, handle configuration reloads, and monitor via NGINX metrics, consuming cluster resources for load balancing. AWS Load Balancer Controller leverages AWS-managed infrastructure where AWS handles patching and availability, applies configuration changes directly to AWS resources, provides native CloudWatch metrics and ALB access logs, and eliminates in-cluster resource overhead for load balancing.
- **From a cost perspective**, NGINX incurs fixed costs for EC2 instances running NGINX pods plus a LoadBalancer Service (typically NLB), with scaling costs increasing linearly as you add pod replicas. AWS Load Balancer Controller uses a usage-based model charging for ALB/NLB hours plus Load Balancer Capacity Units (LCUs) based on actual connections, requests, and data processed, with automatic scaling requiring no additional configuration.

## Example Walkthrough

One approach is to map your existing NGINX functionality to AWS Load Balancer Controller capabilities while retaining your Ingress objects — simply transitioning their management to AWS Load Balancer Controller.

Let's explore this approach through a practical example using `rewrite.bar.com`, implementing two common use cases: URL rewriting and TLS termination.

### Pre-requisites

- Familiarity with EKS Cluster Management
- An existing Amazon EKS Cluster with an existing node group
- AWS Load Balancer Controller installed in the cluster
- Tools required on a machine with access to the AWS and Kubernetes API Server:
  - AWS CLI
  - eksctl
  - kubectl
  - Helm
  - Docker

### Step 1: Basic URI Rewrite

In Oct 2025, AWS announced the general availability of rewriting URLs and host headers natively on Application Load Balancers (ALB). You can use this feature to implement regex matches based on request parameters and rewrite both host headers and URLs before routing to your targets.

Let's look at a use-case to route traffic from `rewrite.bar.com/something/*` to your backend service at `/*`, removing the `/something` prefix from the path.

**NGINX Ingress configuration:**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: rewrite
  namespace: default
  annotations:
    nginx.ingress.kubernetes.io/use-regex: "true"
    nginx.ingress.kubernetes.io/rewrite-target: /$2
spec:
  ingressClassName: nginx
  rules:
  - host: rewrite.bar.com
    http:
      paths:
      - path: /something(/|$)(.*)
        pathType: ImplementationSpecific
        backend:
          service:
            name: http-svc
            port:
              number: 80
```

How it works:

- Uses regex pattern `/something(/|$)(.*)` to capture everything after `/something/`
- The captured group `(.*)` is stored in `$2`
- `rewrite-target: /$2` rewrites the path to just the captured content

**AWS Load Balancer Controller equivalent:**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: rewrite
  namespace: default
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/transforms.http-svc: |
      [
        {
          "type": "url-rewrite",
          "urlRewriteConfig": {
            "rewrites": [
              {
                "regex": "^\\/something\\/(.*)$",
                "replace": "/$1"
              }
            ]
          }
        }
      ]
spec:
  ingressClassName: alb
  rules:
  - host: rewrite.bar.com
    http:
      paths:
      - path: /something
        pathType: Prefix
        backend:
          service:
            name: http-svc
            port:
              number: 80
```

How it works:

- Uses `transforms.http-svc` annotation (must match your service name)
- Regex `^\\/something\\/(.*)$` captures everything after `/something/`
- `replace: "/$1"` rewrites to the captured group
- Note: Forward slashes must be escaped as `\\/` in JSON

**Key Considerations:**

- The transform annotation name (`transforms.http-svc`) must exactly match your service name
- Use `\\/` instead of `/` in your regex patterns within the JSON
- Test your regex patterns carefully — AWS ALB regex syntax may differ slightly from NGINX
- The `pathType: Prefix` works for most cases; use `Exact` if you need strict matching

### Step 2: Add TLS Termination

Now that we have established the rewrite URI use-case, let's secure the application with HTTPS, terminating TLS at the load balancer level.

**NGINX Ingress with TLS:**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: rewrite
  namespace: default
  annotations:
    nginx.ingress.kubernetes.io/use-regex: "true"
    nginx.ingress.kubernetes.io/rewrite-target: /$2
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - rewrite.bar.com
    secretName: nginx-tls-secret
  rules:
  - host: rewrite.bar.com
    http:
      paths:
      - path: /something(/|$)(.*)
        pathType: ImplementationSpecific
        backend:
          service:
            name: http-svc
            port:
              number: 80
```

Certificate setup (NGINX):

```bash
# Create Kubernetes Secret with your certificate
kubectl create secret tls nginx-tls-secret \
  --cert=path/to/tls.crt \
  --key=path/to/tls.key \
  --namespace=default
```

**AWS Load Balancer Controller with TLS:**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: rewrite
  namespace: default
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:us-west-2:123456789012:certificate/12345678-1234-1234-1234-123456789012
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
    alb.ingress.kubernetes.io/ssl-redirect: '443'
    alb.ingress.kubernetes.io/ssl-policy: ELBSecurityPolicy-TLS-1-2-2017-01
    alb.ingress.kubernetes.io/transforms.http-svc: |
      [
        {
          "type": "url-rewrite",
          "urlRewriteConfig": {
            "rewrites": [
              {
                "regex": "^\\/something\\/(.*)$",
                "replace": "/$1"
              }
            ]
          }
        }
      ]
spec:
  ingressClassName: alb
  rules:
  - host: rewrite.bar.com
    http:
      paths:
      - path: /something
        pathType: Prefix
        backend:
          service:
            name: http-svc
            port:
              number: 80
```

> **Note:** When doing TLS termination with AWS Load Balancer Controller, certificates are managed through AWS Certificate Manager (ACM) and live outside the cluster, unlike NGINX Ingress where certificates are stored as Kubernetes Secrets within the cluster.

Certificate setup (AWS LBC):

```bash
# Request certificate in AWS Certificate Manager
aws acm request-certificate \
  --domain-name rewrite.bar.com \
  --validation-method DNS \
  --region us-west-2

# Get the certificate ARN
aws acm list-certificates --region us-west-2

# Use the ARN in your certificate-arn annotation
```

**Certificate discovery feature:**

AWS Load Balancer Controller can automatically discover ACM certificates based on your Ingress hostnames, eliminating the need to specify `certificate-arn`:

```yaml
# Enable certificate discovery (no certificate-arn needed)
alb.ingress.kubernetes.io/certificate-discovery: "true"
```

**Key Considerations:**

- Multiple certificates: Use comma-separated ARNs for multiple domains
- SSL policies: Choose appropriate security policy (TLS 1.2 minimum recommended)
- HTTP redirect: Always configure `ssl-redirect` to ensure HTTPS enforcement

## Migration Checklist

### Pre-migration

- Audit existing NGINX Ingress configurations
- Identify all custom annotations and features used
- Request/import certificates in AWS Certificate Manager
- Review AWS Load Balancer Controller documentation
- Plan IngressGroup strategy for shared ALBs

### During migration

- Install AWS Load Balancer Controller in cluster
- Convert NGINX annotations to AWS LBC annotations
- Update `ingressClassName` from `nginx` to `alb`
- Test URI rewrite patterns thoroughly
- Monitor ALB metrics and logs

### Post migration

- Remove NGINX Ingress Controller (after validation)
- Clean up unused Kubernetes Secrets (certificates)
- Set up ALB access logging (recommended)
- Configure WAF rules (if needed)
- Enable Shield Advanced (if needed)

## Recommendation

If you're currently running Ingress NGINX, migrate to AWS Load Balancer Controller to eliminate the security and compliance risks associated with running an unmaintained controller. This provides immediate benefits including AWS-managed infrastructure, native integrations with ACM, WAF, and Shield, and elimination of in-cluster proxy overhead.

To ensure your architecture remains future-proof, plan to adopt Kubernetes Gateway API — the CNCF's next-generation standard for traffic management. Gateway API addresses the fundamental design limitations that led to Ingress NGINX's deprecation and provides:

- Standards-based portability across implementations
- Role-oriented design separating infrastructure
- Enhanced capabilities including cross-namespace routing and weighted traffic splitting
- Type-safe CRDs with schema validation

AWS Load Balancer Controller v3.0 supports Gateway API with native AWS integrations and advanced ALB features. The recommended migration path is to first migrate from Ingress NGINX to AWS Load Balancer Controller using Ingress resources as demonstrated in this guide, then transition from Ingress to Gateway API resources when your organization is ready.

## Next Steps: Take Action Today

1. **Identify all impacted clusters** by running the provided `kubectl` command across environments to understand exposure.
2. **Assess current NGINX Ingress configurations** by documenting annotations, custom settings, and dependencies to determine the best migration path.
3. **Start with a proof of concept** by selecting a non-production workload and migrating it using the walkthrough examples.
4. **Use insights from the POC** to build a production migration timeline.
5. **Engage your AWS Solutions Architect or Technical Account Manager** for guidance on evaluation and migration acceleration.

## Conclusion

The evolution away from Ingress NGINX represents a significant moment for the Kubernetes ecosystem and an opportunity to modernize your infrastructure. By migrating to AWS-native solutions like the Load Balancer Controller or standards-based alternatives, you can reduce operational complexity, improve security posture, and position your platform for the next generation of cloud-native networking. For detailed configuration examples and best practices, refer to the [AWS Load Balancer Controller documentation](https://kubernetes-sigs.github.io/aws-load-balancer-controller/).

---

*Authors: Sai Charan Teja Gopaluni (Senior Specialist Solutions Architect), Ikenna Izugbokwe (Principal Solutions Architect), Zac Nixon (Senior Software Engineer, Elastic Load Balancing)*

*Content was rephrased for compliance with licensing restrictions.*
