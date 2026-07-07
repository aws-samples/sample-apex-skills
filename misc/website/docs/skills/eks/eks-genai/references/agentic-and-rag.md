---
title: "Agentic AI & RAG Patterns on EKS"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/agentic-and-rag.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-genai/references/agentic-and-rag.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/agentic-and-rag.md). Edit the source, not this page.
:::

# Agentic AI & RAG Patterns on EKS

Patterns for retrieval-augmented generation and tool-using agents running on Amazon EKS — orchestration frameworks, vector store selection, tracing, and per-agent cost attribution.

---

## RAG Architecture on EKS

RAG = retrieval → augment → generate. The retrieval step fetches context from a vector store; the augment step injects it into the prompt; the generation step calls the LLM. Every piece runs as Kubernetes workloads co-located with the inference engine.

### Orchestration Frameworks

| Framework | When to use | EKS deployment pattern |
|-----------|-------------|------------------------|
| **LlamaIndex** | Document-heavy RAG, structured extraction, query pipelines | Application pods (CPU NodePool); connects to vLLM via OpenAI-compatible API through LiteLLM |
| **LangChain** | Broad ecosystem, many pre-built retriever integrations, chat-with-data apps | Same as LlamaIndex — orchestration is CPU-bound; model calls go to the GPU/Neuron NodePool |

Decision rule: pick LlamaIndex when the task is *retrieval quality* (index tuning, reranking, metadata filtering); pick LangChain when the task is *tool breadth* (many integrations, existing chains). Both are first-class; don't mix in the same service unless the team is already fluent in both.

### Vector Store Options

Ranked by recommendation priority for EKS-centric deployments:

| Vector store | When to default | Latency | Ops burden | Cost profile |
|--------------|-----------------|---------|-----------|--------------|
| **Bedrock Knowledge Bases** | Greenfield RAG; team wants managed ingestion + chunking + embedding + retrieval | Low (managed) | Zero | Per-query pricing; good for moderate QPS |
| **Amazon S3 Vectors** | Cost-optimized RAG at scale; vector data already in S3; batch-heavy patterns | Medium (S3 API) | Zero — serverless | Storage-class pricing; no provisioned capacity |
| **PGVector on Aurora PostgreSQL** | Existing Aurora footprint; need transactional + vector in one DB; compliance requires single data plane | Low (RDS) | Medium — manage Aurora cluster | Provisioned RDS pricing |
| **OpenSearch k-NN** | High-QPS real-time search + vector hybrid; faceted filtering alongside similarity | Low | Medium — manage domain (or Serverless) | Instance + storage or per-OCU |

Decision rule: default → **Bedrock Knowledge Bases** unless self-managed is required for compliance/data-residency/cost. For cost-at-scale with simple patterns → **S3 Vectors**. For transactional workloads → **PGVector on Aurora**. For hybrid keyword + semantic search → **OpenSearch k-NN**.

### Embeddings

- Default → **Amazon Titan Embeddings v2** (via Bedrock) — zero self-hosting, strong multilingual quality.
- Self-host embeddings on EKS only when: (a) data cannot leave the VPC; (b) embedding volume justifies dedicated capacity (>10M embeddings/day); (c) custom fine-tuned embedding model.
- Self-hosted embedding models (`bge-large`, `e5-mistral`) run on CPU or single-GPU pods — they don't need the heavy GPU NodePool.

### Amazon S3 Vectors — Cost-Optimized RAG

S3 Vectors is the newest option and the workshop-validated default for cost-sensitive RAG on EKS. Key characteristics:

- **Serverless** — no provisioned capacity, no cluster management.
- **S3-native** — vectors stored alongside source documents in the same bucket namespace; IAM policies apply uniformly.
- **Batch-friendly** — ideal for offline indexing + real-time query patterns where ingestion latency of seconds is acceptable.
- **Cost** — storage-class pricing (S3 Standard or Infrequent Access); no per-query compute charge beyond standard S3 API costs.

Use S3 Vectors when: the RAG workload is cost-sensitive, query volume is moderate (< 1K QPS), and the team wants zero vector-DB ops overhead. Use OpenSearch k-NN or PGVector when query latency must be single-digit ms or when hybrid keyword+semantic search is required.

### Retrieval → Generate Flow

```text
User query
  → Embedding model (Bedrock Titan v2 or self-hosted)
  → Vector store similarity search (top-k chunks)
  → Reranker (optional — Cohere Rerank via Bedrock or self-hosted cross-encoder)
  → Prompt assembly (system prompt + retrieved context + user query)
  → LLM generation (vLLM on EKS via LiteLLM gateway)
  → Response to user
```

Each step is a discrete pod or managed-service call. The orchestrator (LlamaIndex/LangChain) runs in the application pod; it calls the vector store, reranker, and LLM as external services.

### Tracing with Langfuse

**Langfuse is non-negotiable for production RAG.** Without step-level tracing you cannot debug retrieval quality vs generation quality — the #1 RAG failure mode ("the model hallucinated" is often "the retriever returned irrelevant chunks").

Deploy Langfuse on EKS (Helm chart) or use Langfuse Cloud. Instrument every step:

```python
from langfuse.decorators import observe

@observe()
def rag_pipeline(query: str):
    embeddings = embed(query)            # traced as "embedding" span
    chunks = retrieve(embeddings)         # traced as "retrieval" span
    reranked = rerank(chunks, query)      # traced as "reranking" span
    response = generate(reranked, query)  # traced as "generation" span
    return response
```

Langfuse captures: latency per step, token counts, cost per LLM call, retrieval scores, and full input/output for debugging. Wire it into LiteLLM with `LITELLM_CALLBACKS=langfuse` for automatic gateway-level tracing.

Reference: [Advanced Agentic AI on EKS Workshop — Langfuse module](https://catalog.us-east-1.prod.workshops.aws/workshops/26ab2b07-9621-4e0c-bc44-3f7fef388cb7).

---

## Agentic AI Patterns on EKS

Agents = LLM + tool-use reasoning loop. The LLM decides *which tool to call*, calls it, observes the result, then decides the next action. Agents are stateful, multi-step, and often multi-model.

### Runtime Options

| Runtime | Positioning | When to default |
|---------|-------------|-----------------|
| **Bedrock AgentCore** | Managed agent runtime — AWS handles orchestration, state, tool dispatch, guardrails | Greenfield agentic; team wants managed; no need to self-host orchestration |
| **Strands Agents SDK** | AWS-published Python SDK for production autonomous agents; runs on EKS pods | Self-hosted agents; full control over tools/memory/orchestration; validated in GenAI-on-EKS workshop |
| **LangGraph** | Open-source stateful agent framework; graph-based orchestration | Complex multi-step workflows with branching/looping; team already on LangChain ecosystem |

Decision rule: default → **Bedrock AgentCore** for managed simplicity. Self-host on EKS with **Strands Agents SDK** when: the team needs custom tool dispatch, on-cluster model co-location, or cannot send prompts to a managed service (compliance). Use **LangGraph** when the workflow topology is non-trivial (parallel branches, conditional loops, human-in-the-loop).

### Tool-Use Reasoning Loop

```text
User request
  → Agent runtime (Strands / LangGraph pod on CPU NodePool)
  → LLM call via LiteLLM → vLLM (self-hosted) or Bedrock (managed)
  → LLM returns tool_call (function name + args)
  → Agent executes tool (API call, DB query, code exec, retrieval)
  → Tool result injected into conversation
  → LLM decides: respond OR call another tool
  → Loop until done or max-steps reached
```

Key deployment concerns:
- Agent orchestration pods are **CPU-only** — don't waste GPU on the reasoning loop.
- Model serving (vLLM) is on the **GPU/Neuron NodePool** — agent calls it via HTTP through LiteLLM.
- Set `max_steps` on every agent to prevent infinite loops (runaway tool-calling burns tokens).
- Use Kubernetes **resource quotas** per namespace to cap agent-driven token consumption per tenant.

### Per-Agent Cost Attribution

```text
Agent pod → LiteLLM (per-key cost tracking) → Langfuse (per-trace cost rollup)
```

- **LiteLLM** tracks token usage per API key / virtual key. Assign a unique key per agent or tenant.
- **Langfuse** aggregates cost at the trace level — every agent invocation (5-20 LLM calls + tools) rolls up into a single cost figure.
- Export cost data to CloudWatch Metrics or S3 for billing integration.

### Reference Architecture — Agentic AI on EKS

The canonical reference is the [Advanced Agentic AI Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/26ab2b07-9621-4e0c-bc44-3f7fef388cb7):

| Component | Implementation |
|-----------|---------------|
| AI gateway | LiteLLM (routes self-hosted + Bedrock) |
| Agent framework | LangGraph + Strands Agents SDK |
| Tracing | Langfuse (self-hosted on EKS) |
| Self-hosted model | Qwen 3 8B via vLLM on Neuron or GPU |
| Managed model | Claude on Amazon Bedrock |
| Chat UI | Open WebUI |
| Observability | kube-prometheus-stack + DCGM/Neuron Monitor |

Also in `awslabs/ai-on-eks`: [`blueprints/agentic-ai`](https://github.com/awslabs/ai-on-eks) — RAG + LangGraph reference.

---

## Escalation Criteria

Escalate to SpecReq when:
- Agentic workflows include **autonomous code execution** or shell access — Security TFC review required.
- Cross-tenant **prompt injection / data leakage** risk in multi-agent platforms — isolation architecture review.
- RAG pipeline handles **regulated data** (HIPAA/PCI) and vector store selection has compliance implications.
- Customer needs **>5 concurrent agent types** with different tool-permission boundaries.

---

## Sources

- [Architect and Deploy Advanced Agentic AI on EKS Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/26ab2b07-9621-4e0c-bc44-3f7fef388cb7)
- [Guidance for Scalable Model Inference and Agentic AI on Amazon EKS](https://aws.amazon.com/solutions/guidance/scalable-model-inference-and-agentic-ai-on-amazon-eks/)
- [`awslabs/ai-on-eks` — blueprints/agentic-ai](https://github.com/awslabs/ai-on-eks)
- [Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [Amazon S3 Vectors](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors.html)
- [Strands Agents SDK](https://github.com/strands-agents/sdk-python)
- [Bedrock AgentCore](https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html)
