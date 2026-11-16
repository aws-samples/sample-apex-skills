# Runner trial: cost estimate

Stated before any paid run. Spent so far: $0 (no trial run has run). All prices are AWS list prices read 2026-11-16, and every candidate uses one model: `global.anthropic.claude-opus-4-6-v1` (misc/evals/Makefile:35, misc/evals/scripts/run_task_evals.py:1025). Spending is capped at $205 for the whole trial, all candidates together.

## Per-run basis

Measured figures come from the result event (`total_cost_usd`, `duration_ms`) of earlier runs on opus-4-6, kept in the gitignored `misc/evals/<skill>/workspace/runs/<timestamp>/eval-<id>/<arm>/run-1/events.jsonl` files of a local checkout (June 2026). Only runs whose recorded prompt (`eval_metadata.json`) equals today's case prompt are counted. Each of the four cases below has the same id and the same prompt today.

| Case | Source case | With the skill (runs, $ per run) | Without (runs, $ per run) | Basis |
|---|---|---|---|---|
| T3 | eks-build id 1 | 5, $0.831 to $1.211 | 5, $0.501 to $1.018 | measured |
| T5 | eks-build id 3 | 5, $1.377 to $1.813 | 5, $0.549 to $0.739 | measured |
| T4 | eks-upgrade-check id 4 | 1, $0.309 | 1, $0.177 | measured, one run each |
| T7 | eks-recon id 1 | 3, $0.158 to $0.769 | 3, $0.192 to $0.241 | measured |
| T1, T8 | eks-security id 4 | none recorded | none recorded | assumed $0.30 to $0.80 |
| T2 | eks-recon id 3 | none recorded | none recorded | assumed $0.30 to $0.80 |
| T6 | eks-mcp-server triggering | per-query cost not recorded | n/a | assumed $0.05 to $0.30 per query run |

The grader's cost is not recorded anywhere: the runner reads the grader's stream in memory and writes only grading.json (misc/evals/scripts/run_task_evals.py:581-686). It is assumed at $0.10 to $0.40 per call.

Model prices behind the measured figures (AWS Price List, AmazonBedrockFoundationModels, us-west-2, Claude Opus 4.6, Global): $5.00 per 1M input tokens, $25.00 per 1M output tokens, $6.25 per 1M cache-write tokens, $0.50 per 1M cache-read tokens. One measured run, eks-build id 1 with the skill at 2026-06-04T00-12-12Z, reproduces from its token counts at these prices to its recorded $0.8307.

## Per candidate

Run counts are those in cases.md.

**C1, homegrown runner (claude harness).** 54 task runs, 6 triggering query runs and 54 grader calls.
- T3: 6 with-skill runs (3 with, 3 old against new) x $0.831 to $1.211, plus 3 without x $0.501 to $1.018 = $6.49 to $10.32.
- T5: 3 x $1.377 to $1.813, plus 3 x $0.549 to $0.739 = $5.78 to $7.66.
- T4: 6 x $0.309, plus 3 x $0.177 = $2.39 (one measured run per arm).
- T7: 3 x $0.158 to $0.769, plus 3 x $0.192 to $0.241 = $1.05 to $3.03.
- T1 and T2: 9 runs each x $0.30 to $0.80 = $2.70 to $7.20 each.
- T8: 6 x $0.30 to $0.80 = $1.80 to $4.80.
- T6: 6 x $0.05 to $0.30 = $0.30 to $1.80.
- Grader: 54 x $0.10 to $0.40 = $5.40 to $21.60.
- C1 total: **$28.61 to $66.00**.

**C1, Kiro (T1 x 3).** Kiro CLI 3.3.0 runs under its own subscription (IAM Identity Center sign-in). It adds no AWS charge.

**C1, Codex (T1 x 3).** Codex CLI runs `us.openai.gpt-5.6-sol` on Bedrock in us-west-2. AWS Price List, AmazonBedrockFoundationModels, model "OpenAI GPT-5.6 Sol", us-west-2, "AWS Marketplace software usage" rows: regional standard $4.40 per 1M input tokens, $22.00 per 1M output tokens, $0.44 per 1M cache-read tokens; global standard $4.00, $20.00 and $0.40. No Codex run on these cases is recorded. Assumed $0.50 to $2.64 per run, the upper figure being 500,000 input and 20,000 output tokens at the regional rate. 3 runs = **$1.50 to $7.92**.

**C2, `claude plugin eval`.** 42 task runs (no old-against-new mode) and 6 triggering query runs, with the Haiku judge.
- Subject: the C1 subject figures less the 12 old-against-new runs = $17.99 to $35.04.
- Judge: 42 x $0.02 to $0.10 (assumed) = $0.84 to $4.20.
- C2 total: **$18.83 to $39.24**, run with `--max-cost-usd 60`, which stops the suite and exits 2.

**C3, AgentCore Evaluations (on-demand Evaluate).** It runs no agent of its own. It scores the spans of C1's 54 task runs with 3 built-in evaluators each, 162 evaluations, at $2.40 per 1M input tokens and $12.00 per 1M output tokens (AWS Price List, AmazonBedrockAgentCore, us-west-2, effective 2026-11-05).
- At the pricing page's example size (15,000 input and 300 output tokens per evaluation): 162 x $0.0396 = $6.42.
- At the 200,000 input-token ceiling per evaluation: 162 x $0.4836 = $78.34.
- C3 total: **$6.42 to $78.34**. CloudWatch adds nothing on this path: no span is ingested.

**T7 cluster.** T7 reads an existing test cluster read-only, so it adds no charge. The cluster's control plane is $0.10 per hour on standard support (AWS Price List, AmazonEKS, US West (Oregon)), paid whether or not the trial runs.

## Total

**$55.36 to $191.50**, under the $205 cap.

Gate: the first paid run is C1 on T4, one run. The total is re-stated from its measured cost, and the trial stops if the re-stated upper figure is above $205.
