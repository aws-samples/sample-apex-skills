---
title: "AI Gateway for GenAI on EKS"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/ai-gateway.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-genai/references/ai-gateway.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/ai-gateway.md). Edit the source, not this page.
:::

# AI Gateway for GenAI on EKS

A multi-model GenAI deployment without a gateway is an operational liability — no unified API surface, no per-tenant cost attribution, no rate limiting, no fallback routing, no request tracing. This reference covers the canonical gateway stack: **LiteLLM** as the default multi-model proxy, **Envoy AI Gateway** as the L7 routing alternative, and **Open WebUI** as the chat front-end. The canonical data flow and the AWS Solutions Library guidance round out the picture.

## Decision Rule

> If you serve **more than one model** (self-hosted or Bedrock) OR need **per-tenant rate limiting / cost tracking** OR want a **unified OpenAI-compatible API** for your application layer — deploy a gateway. LiteLLM is the default. Skip the gateway only for single-model, single-tenant, internal-only deployments.

## The Canonical Flow

```text
User
  │
  ▼
Open WebUI  (chat UI — ALB ingress, ingressClassName: alb)
  │
  ▼
LiteLLM  (OpenAI-compatible proxy — multi-model routing, rate limiting, cost tracking)
  │
  ├──▶ vLLM (self-hosted on EKS — Llama / Mistral / Qwen on GPU/Neuron)
  ├──▶ Amazon Bedrock (Claude / Nova / Titan — via LiteLLM's Bedrock provider)
  └──▶ Other endpoints (header-routed — custom models, partner APIs)
  │
  ▼
Langfuse  (tracing — request/response capture, cost per call, latency per step)
```

This is the stack validated in the [Architect and Deploy Advanced Agentic AI on EKS Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/26ab2b07-9621-4e0c-bc44-3f7fef388cb7) and recommended by the [AWS Solutions Library: Scalable Model Inference and Agentic AI on Amazon EKS](https://aws.amazon.com/solutions/guidance/scalable-model-inference-and-agentic-ai-on-amazon-eks/).

## LiteLLM — The Default Gateway

### Why LiteLLM

LiteLLM is the primary AWS-recommended gateway for self-hosted GenAI on EKS. It provides a **single OpenAI-compatible API** that routes to any backend — self-hosted (vLLM, Triton, Ollama) or managed (Bedrock, Azure OpenAI, Vertex) — so the customer application needs only one SDK, one endpoint, one set of error codes.

### Core Capabilities

| Capability | What it does |
|------------|--------------|
| **OpenAI-compatible proxy** | Exposes `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings` regardless of backend model API format |
| **Multi-model routing** | Route by model name — `model: "llama-3-8b"` → vLLM; `model: "claude-sonnet"` → Bedrock |
| **Per-tenant rate limiting** | API keys with per-key RPM/TPM limits; prevents noisy-neighbor abuse in multi-tenant platforms |
| **Token cost accounting** | Tracks input/output tokens per request per API key; exports to DB for billing/chargeback |
| **Fallback / retry** | If primary model (self-hosted) is unavailable, fall back to secondary (Bedrock) — zero application change |
| **Load balancing** | Round-robin or least-connections across multiple vLLM replicas |
| **Langfuse integration** | Native callback — every request/response logged to Langfuse with model, tokens, latency, cost |
| **Bedrock provider** | Calls Bedrock FMs via IAM — one config line per Bedrock model; uses Pod Identity/IRSA for auth |

### Deployment on EKS

LiteLLM runs as a Kubernetes Deployment (typically 2–4 replicas for HA) behind an ALB ingress:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: litellm
  namespace: ai-gateway
spec:
  replicas: 3
  selector:
    matchLabels:
      app: litellm
  template:
    metadata:
      labels:
        app: litellm
    spec:
      serviceAccountName: litellm-sa    # Pod Identity → Bedrock access
      containers:
        - name: litellm
          image: ghcr.io/berriai/litellm:main-latest
          ports:
            - containerPort: 4000
          env:
            - name: LITELLM_MASTER_KEY
              valueFrom:
                secretKeyRef:
                  name: litellm-secrets
                  key: master-key
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: litellm-secrets
                  key: database-url
          volumeMounts:
            - name: config
              mountPath: /app/config.yaml
              subPath: config.yaml
      volumes:
        - name: config
          configMap:
            name: litellm-config
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: litellm-ingress
  annotations:
    alb.ingress.kubernetes.io/scheme: internal
    alb.ingress.kubernetes.io/target-type: ip
spec:
  ingressClassName: alb
  rules:
    - http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: litellm-service
                port:
                  number: 4000
```

### LiteLLM Config (Model Routing)

```yaml
# config.yaml — defines available models and their backends
model_list:
  - model_name: llama-3-8b
    litellm_params:
      model: openai/llama-3-8b         # vLLM exposes OpenAI-compatible API
      api_base: http://vllm-llama.inference.svc.cluster.local:8000/v1
      api_key: "not-needed"             # vLLM internal — no auth

  - model_name: claude-sonnet
    litellm_params:
      model: bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0
      # No api_base needed — LiteLLM uses AWS SDK with Pod Identity

  - model_name: nova-pro
    litellm_params:
      model: bedrock/amazon.nova-pro-v1:0

litellm_settings:
  success_callback: ["langfuse"]        # trace every request to Langfuse
  cache: true                           # enable response caching (Redis/Valkey)
```

### Per-Tenant Rate Limiting

LiteLLM's virtual key system allows per-tenant controls:

- Create an API key per tenant/team with RPM (requests per minute) and TPM (tokens per minute) limits.
- Exceeding limits returns HTTP 429 with retry-after — standard OpenAI error format.
- Token consumption per key is recorded in the LiteLLM database for cost attribution.

### Langfuse Integration

LiteLLM natively calls Langfuse on every request completion:

- **What's captured:** model name, input/output tokens, latency (TTFT + generation), cost (calculated from token pricing config), request/response content (configurable — can mask for PII).
- **Why it matters:** debugging RAG quality, identifying slow models, chargeback per tenant, compliance audit trail.
- **Deployment:** Langfuse runs as a separate Deployment in the same cluster (or hosted SaaS). LiteLLM connects via `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` env vars (from Secrets Manager via Secrets Store CSI).

## Envoy AI Gateway — L7 Routing Alternative

### When to Use Instead of (or Alongside) LiteLLM

| Use Envoy AI Gateway when… | Stick with LiteLLM alone when… |
|---|---|
| You need **L7 header-based routing at ingress** before reaching any gateway | LiteLLM's model-name routing is sufficient |
| Customer already standardized on **Envoy / Istio service mesh** | No existing Envoy footprint |
| Need **mTLS between gateway and backends** via Envoy's cert management | Standard in-cluster service discovery is enough |
| Multiple gateway instances (LiteLLM + custom) behind one ingress | Single gateway stack |

### What It Does

Envoy AI Gateway (available in `awslabs/ai-on-eks` `blueprints/gateways/envoy-ai-gateway/`) provides:

- **Header-based multi-model routing** — routes by `X-Model-Name` or custom header to different backend services.
- **Rate limiting at the Envoy layer** — Envoy's native rate-limit service; global or per-route.
- **L7 observability** — request/response metrics exposed to Prometheus; integrates with existing Envoy dashboards.

### Architecture Pattern (Envoy + LiteLLM Combined)

```text
Client → ALB → Envoy AI Gateway (L7 routing + rate limiting)
                    ├── /v1/chat/* → LiteLLM (multi-model proxy + cost tracking)
                    ├── /custom/*  → Custom inference service (direct)
                    └── /health    → Health check endpoint
```

This layered pattern gives you Envoy's battle-tested L7 routing + LiteLLM's model-specific intelligence (token counting, Bedrock integration, Langfuse tracing). Use the combined stack only when the customer's ingress requirements exceed what LiteLLM's built-in routing provides.

## Open WebUI — Chat Front-End

### What It Is

Open WebUI is an open-source ChatGPT-style web interface that connects to any OpenAI-compatible API. The workshop deploys it as the user-facing chat UI fronting the vLLM/LiteLLM backend.

### Deployment Pattern

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: open-webui
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
spec:
  ingressClassName: alb      # EKS Auto Mode ALB controller
  rules:
    - http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: open-webui
                port:
                  number: 8080
```

### Configuration

- **Backend URL:** Point Open WebUI at the LiteLLM service endpoint (`http://litellm-service.ai-gateway.svc.cluster.local:4000/v1`) — it discovers available models via the `/v1/models` endpoint.
- **Auth:** Open WebUI has built-in user management; or integrate with OIDC (Cognito, Okta) for enterprise SSO.
- **Model selection:** Users pick from the model list that LiteLLM exposes — each model routes to its backend (vLLM, Bedrock, etc.) transparently.

### When to Use

- **Internal teams** evaluating self-hosted models — instant ChatGPT-like UX without building a custom app.
- **Demo / proof-of-concept** — show stakeholders the self-hosted stack working end-to-end.
- **Multi-model comparison** — users can switch between models in the same conversation to compare quality.

### When NOT to Use

- **Production customer-facing** applications — build a custom UI with your application's auth, branding, and UX; call LiteLLM's API directly.
- **Agentic workflows** — agents call LiteLLM programmatically; no chat UI involved.

## AWS Solutions Library Guidance

The [Guidance for Scalable Model Inference and Agentic AI on Amazon EKS](https://aws.amazon.com/solutions/guidance/scalable-model-inference-and-agentic-ai-on-amazon-eks/) provides the enterprise-grade reference architecture:

- **EKS + Karpenter** for auto-scaling GPU/Neuron/Graviton nodes
- **LLM gateway** (LiteLLM pattern) for unified API + cost control
- **MCP server** for tool-use / function-calling integration
- **Agentic AI runtime** (Bedrock AgentCore or self-hosted LangGraph/Strands)
- **Observability** with Prometheus/Grafana + AMP/AMG
- **Security** with Pod Identity, VPC private endpoints, Secrets Manager

This guidance is the canonical architectural reference for enterprise customers — cite it when justifying the gateway pattern to architecture review boards.

## Gateway Security Considerations

| Concern | Mitigation |
|---------|-----------|
| **API key exposure** | Store LiteLLM master key + tenant keys in AWS Secrets Manager; mount via Secrets Store CSI |
| **Bedrock IAM** | LiteLLM pod uses EKS Pod Identity / IRSA to call Bedrock — never static credentials |
| **PII in requests** | Configure Langfuse to hash/mask sensitive fields; or deploy PII guardrails (Bedrock Guardrails) upstream |
| **Internal-only access** | ALB scheme `internal` + security group restricting to VPC CIDR only |
| **DDoS / abuse** | Envoy rate limiting at ingress + LiteLLM per-key rate limiting = defense in depth |

## Decision Table — Gateway Component Selection

| Need | Component | Deploy? |
|------|-----------|---------|
| Multi-model routing + unified API | LiteLLM | **Always** (for multi-model) |
| Per-tenant rate limiting + cost tracking | LiteLLM | **Always** (for multi-tenant) |
| Request/response tracing + cost audit | Langfuse | **Always** (production) |
| L7 header routing before gateway | Envoy AI Gateway | Only if existing Envoy mesh or complex ingress |
| Chat UI for internal teams | Open WebUI | Dev/test/demo; not production customer-facing |
| Bedrock FM access alongside self-hosted | LiteLLM Bedrock provider | Yes — single API for both |
| Agent tool-calling | Bedrock AgentCore or Strands SDK | See [agentic-and-rag.md](agentic-and-rag) |

## Sources

- [Architect and Deploy Advanced Agentic AI on EKS Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/26ab2b07-9621-4e0c-bc44-3f7fef388cb7)
- [Guidance for Scalable Model Inference and Agentic AI on Amazon EKS](https://aws.amazon.com/solutions/guidance/scalable-model-inference-and-agentic-ai-on-amazon-eks/)
- [`awslabs/ai-on-eks` — `blueprints/gateways/envoy-ai-gateway/`](https://github.com/awslabs/ai-on-eks)
- [LiteLLM Documentation](https://docs.litellm.ai/)
- [Open WebUI](https://github.com/open-webui/open-webui)
- [Langfuse — LLM Observability](https://langfuse.com/docs)
- [EKS AI/ML Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml.html)
