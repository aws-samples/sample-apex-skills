# Platform for AI/ML and Data Engineering

The same golden-path model — Backstage template → Git → ArgoCD → controllers — extends to ML and data teams. The platform handles the undifferentiated heavy lifting (infra, GitOps, SSO, observability) so ML/data engineers focus on models and pipelines.

## Why platform engineering for AI/ML

ML delivery has hard problems (data lineage, reproducibility, large images, GPU scheduling, drift) and an end-to-end lifecycle (data prep → model dev → serving → monitoring) that benefits from MLOps collaboration between data scientists, ML engineers, and ops. A platform standardizes that lifecycle: productivity, scalability, consistency, faster time-to-market, resource efficiency, security, and compliance — by default.

**OSS-first on Kubernetes.** The platform favors Kubernetes-native OSS so ML/data workloads run on the same substrate as everything else: Ray, JupyterHub, Spark-on-K8s (and, in the broader landscape, Kubeflow, MLflow, Airflow).

## The image pre-pull pattern (key platform decision)

AI/ML container images are large (Jupyter 4GB+, framework images 3GB+), so cold starts are painful. The platform runs a **DaemonSet that pre-pulls these images to nodes in the background**, so notebooks/serving pods start near-instantly. This is an opinionated platform-level solution to a problem every ML team would otherwise hit independently.

## Golden path: model development — JupyterHub

JupyterHub provides multi-user, self-service notebooks on Kubernetes. Components: Hub (auth/management), Proxy (routing), and per-user notebook servers.

- **Integrated with Keycloak SSO** — same identity as the rest of the platform; users just log in.
- Platform manages compute provisioning, packages, and notebook persistence; ML engineers get a ready environment (e.g. build a scikit-learn classifier with no infra setup).
- Extension points: real datasets, GPU instance types, save models to S3, connect MLflow.

## Golden path: model serving — Ray Serve

Ray on Kubernetes (Ray cluster + Ray K8s Operator + Ray Serve) for scalable, low-latency model serving.

```
Backstage "Ray Service" template → Git repo (manifests) → ArgoCD → Ray Serve resources → inference endpoint
```
- ML engineer supplies: name, namespace, worker replicas, model, max tokens. Platform supplies: provisioning, GitOps pipeline, Ray Dashboard observability, the endpoint.
- Auto-scaling, multi-framework, zero-downtime updates, operator-managed — the model is replaceable with the team's own.
- Test the endpoint with a simple `curl` POST to `/generate`.

## Golden path: data engineering — Spark Operator

Spark-on-Kubernetes via the Spark Operator, jobs expressed as `SparkApplication` CRDs and orchestrated by Argo Workflows.

```
Backstage "Spark job" template → Git repo (manifests) → ArgoCD → Argo Workflows → Spark Operator → SparkApplication → driver/executor pods
```
- Data engineer supplies: app name + the `mainApplicationFile` (the PySpark script). Platform supplies: Spark infra, workflow orchestration, and observability (Backstage Spark tab + Argo Workflows UI).
- `kubectl get sparkapplications.sparkoperator.k8s.io -A` to inspect runs.

## The throughline

ML serving, data jobs, and apps all follow the identical loop — a Backstage template generates a Git repo, ArgoCD deploys it, and a controller (Ray/Spark Operator, or KubeVela for apps) reconciles it. One platform, one delivery model, three audiences. That uniformity is the payoff: the platform team maintains one set of paved paths; ML and data teams self-serve exactly like app teams.
