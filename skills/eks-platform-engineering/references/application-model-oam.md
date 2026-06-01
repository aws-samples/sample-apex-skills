# Application Model — OAM / KubeVela

The abstraction that lets developers describe an application — and its infrastructure dependencies — in one declarative file, without writing Deployments, Services, Ingresses, IAM, or ACK manifests directly.

## OAM concepts

- **Component** — a runnable unit of work (a web service, a worker, or even a resource like a DynamoDB table).
- **Trait** — an operational feature attached to a component (ingress, autoscaling, an IAM policy, monitoring).
- **Application** — the developer-facing CRD that composes components + their traits.

KubeVela implements OAM on Kubernetes. Developers write `kind: Application`; KubeVela renders it into the underlying Kubernetes (and, via custom components, AWS) resources.

## Separation of concerns

- **Platform engineers** author component and trait **definitions** (in CUE) — type-safe, composable templates. They own the "how."
- **Developers** reference a component/trait by `type` and set its parameters. They own the "what." They never see the rendered Deployment/Service.

A minimal app:
```yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: first-app
spec:
  components:
    - name: express-server
      type: webservice          # platform-defined component type
      properties:
        image: oamdev/hello-world
        ports: [{ port: 80, containerPort: 8000, expose: true }]
```
KubeVela renders this into a Deployment + Service: `kubectl get deployment,service -l app.oam.dev/name=first-app`.

## The platform's app components (the `appmod-service` pattern)

The PEEKS platform ships richer, opinionated components so a developer can request an app *and* its dependencies in one ordered manifest using `dependsOn`:

```yaml
spec:
  components:
    - name: dynamodb-table          # 1. the AWS resource (via ACK under the hood)
      type: dynamodb-table
      properties: { tableName: app-table, partitionKeyName: pk, sortKeyName: sk, region: us-west-2 }
      traits:
        - type: component-iam-policy
          properties: { service: dynamodb }
    - name: app-sa                  # 2. a service account scoped to that table (Pod Identity)
      type: dp-service-account
      properties: { componentNamesForAccess: [dynamodb-table], clusterName: peeks-spoke-dev, clusterRegion: us-west-2 }
      dependsOn: [dynamodb-table]
    - name: backend                 # 3. the app itself (canary via Argo Rollouts by default)
      type: appmod-service
      properties: { image: "<ecr-uri>:<tag>", port: 80, targetPort: 8080, replicas: 2, serviceAccount: app-sa }
      dependsOn: [app-sa]
      traits:
        - type: path-based-ingress
          properties: { rewritePath: true, http: { /app: 80 } }
```

What this single file produced: a DynamoDB table (ACK), a scoped IAM role + Pod Identity association, a canary-enabled Deployment + Service, and a path-based ingress — in dependency order. That is the power of the model: infrastructure + app + networking + security as one developer-authored unit.

Common `appmod-service` parameters: `image`, `replicas`, `port`/`targetPort`, `serviceAccount`, `resources`, `env`. Common traits: `path-based-ingress`, `component-iam-policy`. Plus the progressive-delivery gates (`functionalGate`/`performanceGate`/`metrics`) from `progressive-delivery.md`.

## CUE and extensibility

Component/trait definitions are written in CUE (e.g. the `webservice` definition lives in KubeVela's templates). CUE is chosen over raw YAML for type-safety and composition. Platform engineers add new component/trait types without changing the core platform; developers pick them up immediately by `type`. GenAI (Amazon Q) is commonly used to author new component definitions from an existing one + a CRD schema (see `genai-platform-engineering.md`).

## Why OAM here

- Developers ship faster — one file, no Kubernetes plumbing.
- Standards enforced centrally — every app gets the platform's ingress/IAM/rollout conventions by construction.
- GitOps-native — Applications are YAML in Git, reconciled by ArgoCD, rendered by KubeVela; multi-cluster from a single definition.
