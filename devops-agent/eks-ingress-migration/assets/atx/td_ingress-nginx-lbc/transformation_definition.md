# NGINX Ingress to AWS Load Balancer Controller Migration

## Objective

Migrate Kubernetes Ingress resource configurations from NGINX Ingress Controller to AWS Load Balancer Controller, converting all NGINX-specific annotations, TLS/certificate management, and routing rules to their AWS Load Balancer Controller equivalents so that the cluster no longer depends on the retiring NGINX Ingress Controller.

## Summary

This transformation converts Kubernetes Ingress manifests that use NGINX Ingress Controller annotations and configurations to use AWS Load Balancer Controller annotations and patterns instead. The migration involves changing the ingressClassName from "nginx" to "alb", replacing all "nginx.ingress.kubernetes.io" annotations with their "alb.ingress.kubernetes.io" equivalents, converting URI rewrite rules from NGINX rewrite-target syntax to ALB transforms annotation syntax, migrating TLS termination from Kubernetes Secrets to AWS Certificate Manager (ACM) references, and updating path definitions and pathType values to be compatible with ALB routing. Any Helm charts, Kustomize overlays, or CI/CD pipeline references that deploy or manage NGINX Ingress resources must also be updated accordingly.

## Entry Criteria

1. The repository contains one or more Kubernetes Ingress resource YAML manifests with `ingressClassName: nginx` or the deprecated annotation `kubernetes.io/ingress.class: "nginx"`.
2. Ingress manifests contain one or more annotations prefixed with `nginx.ingress.kubernetes.io/`.
3. The target Amazon EKS cluster has AWS Load Balancer Controller installed or the team has a plan to install it prior to deploying the migrated manifests.
4. If TLS is used, the corresponding certificates are available in or can be imported into AWS Certificate Manager (ACM) in the target region.

## Implementation Steps

1. Identify all Ingress resource files in the repository by searching for YAML files that contain `ingressClassName: nginx` or the annotation `kubernetes.io/ingress.class: "nginx"`.

2. Change the `ingressClassName` field from `nginx` to `alb` in each Ingress manifest. If the deprecated annotation `kubernetes.io/ingress.class: "nginx"` is used instead, remove it and add `spec.ingressClassName: alb`.

3. Add the following baseline AWS Load Balancer Controller annotations to each Ingress manifest if they are not already present:
   - `alb.ingress.kubernetes.io/scheme` set to `internet-facing` or `internal` depending on the original exposure intent.
   - `alb.ingress.kubernetes.io/target-type` set to `ip` (recommended for Amazon VPC CNI direct pod routing) or `instance` as appropriate.

4. Convert NGINX URI rewrite annotations to ALB transform annotations:
   - Remove the `nginx.ingress.kubernetes.io/use-regex: "true"` annotation.
   - Remove the `nginx.ingress.kubernetes.io/rewrite-target` annotation.
   - Add an `alb.ingress.kubernetes.io/transforms.<service-name>` annotation where `<service-name>` matches the backend service name referenced in the Ingress rules. The value must be a JSON array containing a url-rewrite object. For example, an NGINX rewrite pattern of `/something(/|$)(.*)` with `rewrite-target: /$2` becomes:
     ```
     alb.ingress.kubernetes.io/transforms.http-svc: |
       [
         {
           "type": "url-rewrite",
           "urlRewriteConfig": {
             "rewrites": [
               {
                 "regex": "^\\\\/something\\\\/(.*)$",
                 "replace": "/$1"
               }
             ]
           }
         }
       ]
     ```
   - Ensure forward slashes in regex patterns within the JSON value are escaped as `\\\\/`.
   - Adjust NGINX capture group numbering to ALB capture group numbering (NGINX `$2` may become ALB `$1` depending on the pattern structure since ALB regex may not need the intermediate separator group).

5. Update the `spec.rules[].http.paths[].path` values:
   - Replace NGINX regex path patterns (e.g., `/something(/|$)(.*)`) with simpler prefix paths (e.g., `/something`).
   - Change `pathType` from `ImplementationSpecific` to `Prefix` (or `Exact` if strict matching is required).

6. Migrate TLS termination configuration:
   - Remove the `spec.tls` section that references Kubernetes Secrets for certificate storage.
   - Add the `alb.ingress.kubernetes.io/certificate-arn` annotation with the ARN of the corresponding ACM certificate. If multiple certificates are needed, use comma-separated ARNs. Alternatively, if ACM certificates match the Ingress hostnames, use `alb.ingress.kubernetes.io/certificate-discovery: "true"` to enable automatic certificate discovery.
   - Add `alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'` to configure both HTTP and HTTPS listeners.
   - Add `alb.ingress.kubernetes.io/ssl-redirect: '443'` to enforce HTTPS redirection.
   - Add `alb.ingress.kubernetes.io/ssl-policy` with an appropriate TLS policy such as `ELBSecurityPolicy-TLS-1-2-2017-01` (TLS 1.2 minimum is recommended).

7. Convert other common NGINX Ingress annotations to their AWS Load Balancer Controller equivalents:
   - `nginx.ingress.kubernetes.io/proxy-body-size` — no direct annotation equivalent; configure via ALB target group attributes or application-level settings.
   - `nginx.ingress.kubernetes.io/proxy-read-timeout` and `nginx.ingress.kubernetes.io/proxy-send-timeout` — map to `alb.ingress.kubernetes.io/target-group-attributes` with `deregistration_delay.timeout_seconds` or ALB idle timeout settings.
   - `nginx.ingress.kubernetes.io/cors-*` annotations — handle at the application level or via AWS WAF rules.
   - `nginx.ingress.kubernetes.io/auth-url` and `nginx.ingress.kubernetes.io/auth-signin` — map to `alb.ingress.kubernetes.io/auth-type`, `alb.ingress.kubernetes.io/auth-idp-cognito` or `alb.ingress.kubernetes.io/auth-idp-oidc` annotations as appropriate.
   - Remove any remaining `nginx.ingress.kubernetes.io/*` annotations that have no ALB equivalent, and add a comment in the manifest noting the removed annotation for review.

   <possible_quality_improvement>
   A comprehensive mapping table of all NGINX annotations currently used in the target codebase to their AWS Load Balancer Controller equivalents would improve accuracy for this step. Providing the full set of NGINX annotations in use across the repository would enable a more targeted and complete mapping.
   </possible_quality_improvement>

8. If Ingress resources should share a single ALB to reduce cost and operational overhead, add the `alb.ingress.kubernetes.io/group.name` annotation with a shared group name to the relevant Ingress manifests and optionally set `alb.ingress.kubernetes.io/group.order` to control rule evaluation priority.

9. Update any Helm chart `values.yaml` files, Kustomize overlays, or CI/CD pipeline configurations that reference NGINX Ingress-specific settings (ingress class name, annotation keys, or NGINX controller deployment) to reflect the new AWS Load Balancer Controller annotations and patterns.

10. Remove Kubernetes Secret resources that were only used for NGINX Ingress TLS certificate storage and are no longer referenced after migration to ACM.

## Validation / Exit Criteria

1. No Ingress manifest in the repository contains `ingressClassName: nginx` or the annotation `kubernetes.io/ingress.class: "nginx"`.
2. No Ingress manifest contains any annotation prefixed with `nginx.ingress.kubernetes.io/`.
3. Every Ingress manifest specifies `ingressClassName: alb` and includes at minimum the `alb.ingress.kubernetes.io/scheme` and `alb.ingress.kubernetes.io/target-type` annotations.
4. All URI rewrite rules are expressed using `alb.ingress.kubernetes.io/transforms.<service-name>` annotations with valid JSON url-rewrite configurations, and the corresponding path and pathType fields use Prefix or Exact matching rather than regex patterns.
5. All TLS-enabled Ingress manifests reference ACM certificate ARNs (or enable certificate discovery) and include ssl-redirect, listen-ports, and ssl-policy annotations.
6. Kubernetes YAML manifests pass schema validation (e.g., `kubectl apply --dry-run=client`).
7. Helm charts and Kustomize overlays render correctly with the updated values and produce valid Ingress manifests with ALB annotations.
8. No orphaned Kubernetes TLS Secrets remain that were exclusively used by the former NGINX Ingress configuration.
