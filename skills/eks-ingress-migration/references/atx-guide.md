# AWS Transform (ATX) — Automated Migration Path

## Purpose
Guide customers who have AWS Transform (ATX) access through the fully automated NGINX→ALB manifest migration. ATX reads the Transform Definition (TD) and rewrites all matching Ingress manifests automatically.

## When to Recommend ATX

- Customer has ATX workspace access (contact AWS SA for onboarding)
- Customer has many Ingress manifests (>10) — manual conversion is error-prone
- Customer wants consistent, validated output across all manifests
- Customer prefers automated tooling over manual annotation rewriting

## What ATX Does

ATX uses the Transform Definition as an instruction set for its orchestrator agents:

1. **Scans** the source repo for files matching entry criteria (any YAML with `ingressClassName: nginx` or `kubernetes.io/ingress.class: "nginx"`)
2. **Applies** each implementation step from the TD to every matching file
3. **Validates** output against exit criteria automatically
4. **Produces** a set of proposed file changes (diff) for review

No custom agent code needed — the TD is the complete instruction set.

## How to Use

### Step 1: Locate the Transform Definition

The TD is included in this skill at:
```
references/atx/td_ingress-nginx-lbc/transformation_definition.md
```

Supporting files:
```
references/atx/td_ingress-nginx-lbc/summaries.md
references/atx/td_ingress-nginx-lbc/document_references/navigating-nginx-ingress-retirement.md
```

### Step 2: Upload TD to ATX Workspace

Load the TD into your ATX workspace. The TD contains:
- **Entry criteria** — how ATX identifies files to transform
- **Implementation steps** — the 10-step conversion process
- **Exit criteria** — validation rules for the output

### Step 3: Create a Transformation Job

Point ATX at the repository containing your NGINX Ingress manifests. ATX will:
1. Find all matching Ingress YAML files
2. Execute the 10 implementation steps on each
3. Produce migrated manifests with ALB annotations
4. Validate against exit criteria

### Step 4: Review the Output

ATX produces a diff. Verify:
- ✅ `ingressClassName` is `alb` everywhere
- ✅ No `nginx.ingress.kubernetes.io/*` annotations remain
- ✅ Rewrite `transforms.<svc>` JSON is valid
- ✅ ACM certificate references present on TLS ingresses
- ✅ `ssl-redirect`, `listen-ports`, `ssl-policy` set
- ✅ Orphaned TLS Secrets removed

Then merge the changes.

## What the TD Converts (10 Steps)

| Step | Action |
|------|--------|
| 1 | Identify all NGINX Ingress files |
| 2 | Swap `ingressClassName: nginx` → `alb` (handle deprecated annotation) |
| 3 | Add baseline ALB annotations (`scheme`, `target-type`) |
| 4 | Convert URI rewrites → `transforms.<svc>` JSON |
| 5 | Simplify regex paths to `Prefix`/`Exact` pathType |
| 6 | Migrate TLS from K8s Secrets → ACM (`certificate-arn` or `certificate-discovery`) |
| 7 | Map remaining annotations (timeouts, CORS, auth, body-size) |
| 8 | Add `group.name` for ALB sharing (if applicable) |
| 9 | Update Helm/Kustomize/CI references |
| 10 | Remove orphaned TLS Secrets |

## Sample Before/After

The skill includes 8 sample patterns demonstrating the transformation:

| Sample | Pattern |
|--------|---------|
| `01-basic-rewrite` | `rewrite-target` + regex → `transforms.<svc>` url-rewrite |
| `02-tls-rewrite` | TLS Secret → ACM `certificate-arn` |
| `03-multi-path` | Multiple paths/services → per-service transforms + idle timeout |
| `04-cors-auth` | CORS + external auth → ALB OIDC |
| `05-deprecated-class` | `kubernetes.io/ingress.class` annotation → `ingressClassName: alb` |
| `06-multi-host-tls` | Multiple hosts/TLS secrets → `certificate-discovery` |
| `07-simple-no-rewrite` | Host + TLS only → `ssl-redirect` + ACM cert |
| `08-internal` | `whitelist-source-range` → `scheme: internal` + security groups |

See `references/samples/nginx/` (input) and `references/samples/alb/` (ATX output) directories.

## Exit Criteria (ATX Validates Automatically)

1. No `ingressClassName: nginx` or `kubernetes.io/ingress.class: "nginx"` remains
2. No active `nginx.ingress.kubernetes.io/*` annotations (only in `# REMOVED:` comments)
3. Every Ingress has `ingressClassName: alb` + `scheme` + `target-type`
4. All rewrites use `transforms.<svc>` with valid url-rewrite JSON
5. All TLS ingresses have ACM references + `ssl-redirect` + `listen-ports` + `ssl-policy`
6. Orphaned TLS Secrets removed
7. `kubectl apply --dry-run=client` passes on all output files

## After ATX Migration

Once ATX has transformed your manifests:

1. Ensure AWS Load Balancer Controller **v2.7.2+** (ALB Ingress path) is installed — or use EKS Auto Mode's built-in `eks.amazonaws.com/alb`
2. Verify ACM certificates are provisioned and in ISSUED state
3. `kubectl apply --dry-run=client -f <migrated-file>` to validate
4. Deploy to staging first
5. Use DNS weighted routing to shift traffic from old CLB to new ALB
6. Remove NGINX Ingress Controller after validation
7. Clean up orphaned TLS Secrets

## Report Integration

When the assessment skill detects ATX is a viable path, the report should include:

**In the Migration Approach section:**
> **Automated Path (ATX):** Your manifests are compatible with AWS Transform.
> The Transform Definition is included at `references/atx/td_ingress-nginx-lbc/transformation_definition.md`.
> Point ATX at your source repo to automatically convert all {N} Ingress resources to ALB annotations.
> Estimated ATX execution: minutes (vs. {X} hours manual).

**In the Recommendations section:**
> - Upload the included TD to your ATX workspace
> - Create a transformation job targeting your Ingress manifest repository
> - Review the diff and merge
> - Follow post-migration steps (ACM certs, deploy to staging, DNS cutover)
