# Runner trial: cost estimate

Repo line cites are at commit 7efa0776.

Stated before any paid run. Spent so far: $0 (no trial run has run). All prices are AWS list prices read 2026-11-16. The subject model for the claude harness is `global.anthropic.claude-opus-4-6-v1` (misc/evals/Makefile:35, misc/evals/scripts/run_task_evals.py:1025); Claude Code also calls Haiku 4.5 inside a run, C2's judge is Haiku, Codex runs gpt-5.6-sol and C3 uses its built-in evaluators' models. The trial is budgeted at $205 for all candidates together, unless the maintainers set another limit with the spend decision. Only C2's run has a hard stop (`--max-cost-usd 60`); the C1 driver stops before its next run once the subjects' recorded cost reaches the limit (the stop counts only the subjects' recorded cost: grader calls, T6 query runs and a run that times out or crashes before its first result event add nothing; on Claude Code older than 2.1.277, or after an earlier turn that exited abnormally, T5's earlier turns add nothing; and the run that crosses the limit completes), and the C3 calls are stopped by hand when the running total reaches the limit.

## Per-run basis

Measured figures come from the result event (`total_cost_usd`, `duration_ms`) of earlier runs on opus-4-6, kept in the gitignored `misc/evals/<skill>/workspace/runs/<timestamp>/eval-<id>/<arm>/run-1/events.jsonl` files of a local checkout (June 2026). Only runs whose recorded prompt (`eval_metadata.json`) equals today's case prompt are counted. Each of the four cases below has the same id and the same prompt today. These are earlier local runs (not in the repo); the counted runs' timestamps and `total_cost_usd` are listed below.

| Case | Source case | With the skill (runs, $ per run) | Without (runs, $ per run) | Basis |
|---|---|---|---|---|
| T3 | eks-build id 1 | 5, $0.831 to $1.211 | 5, $0.501 to $1.018 | measured |
| T5 | eks-build id 3 | 5, $1.377 to $1.813 | 5, $0.549 to $0.739 | measured |
| T4 | eks-upgrade-check id 4 | 1, $0.309 | 1, $0.177 | measured, one run each |
| T7 | eks-recon id 1 | 3, $0.158 to $0.769 | 3, $0.192 to $0.241 | measured |
| T1 | eks-security id 4 | none recorded | none recorded | assumed $0.30 to $0.80: T1 is an offline report case like T4; the span is T4's and T7's measured runs ($0.158 to $0.769), and the range is set at the top of that span, since T1 also reads three fixture files |
| T2 | eks-recon id 3 | none recorded | none recorded | assumed $0.30 to $0.80, on the same basis as T1 (two fixture files) |
| T6 | eks-mcp-server triggering | per-query cost not recorded | n/a | assumed $0.05 to $0.30 per query run: no triggering run records a cost, since the runner stops the process at the Skill call or at its 90 s timeout (misc/evals/scripts/run_triggering.py:191, :530); the shortest measured full run, T7 with the skill at 26.5 s, cost $0.158 |

Counted runs (`total_cost_usd`, rounded to the cent; with the skill / without):

| Case | Run timestamp | With | Without |
|---|---|---|---|
| T3 | 2026-06-02T02-18-38Z | $1.15 | $0.50 |
| T3 | 2026-06-03T15-59-08Z | $1.21 | $0.52 |
| T3 | 2026-06-03T16-47-18Z | $1.04 | $1.02 |
| T3 | 2026-06-03T17-38-25Z | $1.13 | $0.78 |
| T3 | 2026-06-04T00-12-12Z | $0.83 | $0.82 |
| T5 | 2026-06-02T02-18-38Z | $1.81 | $0.69 |
| T5 | 2026-06-03T15-59-08Z | $1.40 | $0.55 |
| T5 | 2026-06-03T16-47-18Z | $1.38 | $0.64 |
| T5 | 2026-06-03T17-38-25Z | $1.49 | $0.74 |
| T5 | 2026-06-04T00-12-12Z | $1.40 | $0.56 |
| T4 | 2026-06-04T00-12-12Z | $0.31 | $0.18 |
| T7 | 2026-06-03T18-02-22Z | $0.66 | $0.19 |
| T7 | 2026-06-04T00-40-22Z | $0.16 | $0.24 |
| T7 | 2026-06-04T01-24-22Z | $0.77 | $0.21 |

The grader's cost is not recorded anywhere: the runner reads the grader's stream in memory and writes only grading.json (misc/evals/scripts/run_task_evals.py:581-680). It is assumed at $0.10 to $0.40 per call: at the Opus 4.6 prices below that is 15,000 to 60,000 input and 1,000 to 4,000 output tokens per call. The grader reads skills/skill-creator/agents/grader.md (9,049 bytes) and the run's transcript.md (3,272 to 61,013 bytes over the counted runs), about 3,000 to 18,000 tokens at 4 bytes per token, plus Claude Code's own system prompt and the outputs it opens.

Model prices behind the measured figures (AWS Price List, AmazonBedrockFoundationModels, us-west-2, Claude Opus 4.6, Global): $5.00 per 1M input tokens, $25.00 per 1M output tokens, $6.25 per 1M 5-minute cache-write tokens (the measured runs wrote no 1-hour cache), $0.50 per 1M cache-read tokens. One measured run, eks-build id 1 with the skill at 2026-06-04T00-12-12Z, reproduces from its `modelUsage` token counts (421 input, 10,108 output, 56,454 5-minute cache-write, 446,286 cache-read) at these prices to its recorded $0.8307.

## Per candidate

Run counts are those in cases.md.

**C1, homegrown runner (claude harness).** 48 task runs, 6 triggering query runs and 48 grader calls. The driver grades T1, T4 and T7 only (24 grader calls), so the 48 figure is conservative.
- T3: 6 with-skill runs (3 with, 3 old against new) x $0.831 to $1.211, plus 3 without x $0.501 to $1.018 = $6.49 to $10.32.
- T5: 3 x $1.377 to $1.813, plus 3 x $0.549 to $0.739 = $5.78 to $7.66.
- T4: 6 x $0.309, plus 3 x $0.177 = $2.39 (one measured run per arm).
- T7: 3 x $0.158 to $0.769, plus 3 x $0.192 to $0.241 = $1.05 to $3.03.
- T1 and T2: 9 runs each x $0.30 to $0.80 = $2.70 to $7.20 each.
- T6: 6 x $0.05 to $0.30 = $0.30 to $1.80.
- Grader: 48 x $0.10 to $0.40 = $4.80 to $19.20 (the driver's 24 calls: $2.40 to $9.60).
- C1 total, claude harness: **$26.21 to $58.80**.

**C1, Kiro (T1 x 3).** Kiro CLI 3.3.0 bills to its own subscription. It adds no AWS charge; its runs draw on the Kiro subscription's credits (kiro.dev/pricing). Its 3 runs are graded by C1's grader: 3 x $0.10 to $0.40 = **$0.30 to $1.20**.

**C1, Codex (T1 x 3).** Codex CLI runs `us.openai.gpt-5.6-sol` on Bedrock in us-west-2. AWS Price List, AmazonBedrockFoundationModels, model "OpenAI GPT-5.6 Sol", us-west-2, "AWS Marketplace software usage" rows: regional standard $4.40 per 1M input tokens, $22.00 per 1M output tokens, $0.44 per 1M cache-read tokens. No Codex run on these cases is recorded. Assumed $0.50 to $2.64 per run (estimate). The lower figure is the cheapest measured claude run (T7 with the skill, 2026-06-04T00-40-22Z: 104,291 input tokens counting cache writes and reads, and 1,153 output tokens, from its `modelUsage`) priced as uncached input at the regional rate, $0.46 plus $0.03 = $0.48, rounded up to $0.50; the upper figure is 500,000 input and 20,000 output tokens at the regional rate. 3 runs = $1.50 to $7.92, plus 3 grader calls at $0.10 to $0.40 = **$1.80 to $9.12**.

**C2, `claude plugin eval`.** 30 task runs (no old-against-new mode; T5 cannot run) and 6 triggering query runs, with the Haiku judge.
- Subject: the C1 subject figures less the 12 old-against-new runs and T5's 6 runs = $16.19 - $5.78 = $10.41 to $30.24 - $7.66 = $22.58.
- Judge: 30 x $0.02 to $0.10 = $0.60 to $3.00. Basis: the grader's token span above at Claude Haiku 4.5's Global price ($1.00 per 1M input and $5.00 per 1M output tokens, AWS Price List, AmazonBedrockFoundationModels, us-west-2) gives $0.02 to $0.08, rounded up to $0.10.
- C2 total: **$11.01 to $25.58**, run with `--max-cost-usd 60`, which stops the suite and exits 2.

**C3, AgentCore Evaluations (on-demand Evaluate).** It runs no agent of its own. It scores the spans of C1's 48 task runs with 3 built-in evaluators each, 144 evaluations: `Builtin.GoalSuccessRate` given the case's pass condition as `assertions`, `Builtin.Correctness`, and the trajectory matcher `Builtin.TrajectoryAnyOrderMatch` (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/ground-truth-evaluations.html, read 2026-11-16). S2 for C3 is the GoalSuccessRate judgment, an LLM reading, not the condition checked directly. The trajectory matchers make no LLM calls ("no LLM calls, so token usage is zero", same page), so 96 of the 144 evaluations are priced, at $2.40 per 1M input tokens and $12.00 per 1M output tokens (AWS Price List, AmazonBedrockAgentCore, us-west-2, effective 2026-11-05).
- At the pricing page's example size (15,000 input and 300 output tokens per evaluation): 96 x $0.0396 = $3.80.
- At the 200,000 input-token ceiling per evaluation (200,000 input and 300 output tokens per evaluation): 96 x $0.4836 = $46.43.
- C3 total: **$3.80 to $46.43**. This assumes Evaluate accepts spans never ingested into CloudWatch, which AWS does not document; if it does not, C3 also needs Transaction Search, whose spans are billed as Application Signals data, not log ingestion: $0.35 per GB ingested for the first 10 TB (AWS Price List, AmazonCloudWatch, usagetype USW2-Application-Signals-Bytes), plus $0.00000075 per span indexed beyond the free 1% (usagetype USW2-XRay-Spans-Indexed; docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Enable-TransactionSearch.html), read 2026-11-17; the trial's span volume is not measured, so that charge is not in the total. The Price List row does not say "spans": the link from span ingestion to that usagetype rests on the CloudWatch pricing page's free-tier row, "100GB data ingested for Application Signals including complete visibility into application transaction spans" (aws.amazon.com/cloudwatch/pricing, read 2026-11-17).

**T7 cluster.** T7 reads an existing test cluster read-only, so it adds no charge.

## Total

**$43.12 to $141.13**: C1 claude harness $26.21 to $58.80, Kiro $0.30 to $1.20, Codex $1.80 to $9.12, C2 $11.01 to $25.58, C3 $3.80 to $46.43.

Gate: the first paid run is C1 on T4, one run: `python3 misc/runner-trial/drive_c1.py --case T4 --paid --out <new dir> --spend-limit-usd 0.01 --credential-note '<credential>'` stops after the first subject run, provided that run records a cost; one that times out or crashes before its first result event records none, and the driver goes on to the next run. Do not run --paid on the trial host (drive_c1.py; cases.md, Credentials and permissions). The gate's T4 run-1 is paid again in the full run. The gate run is outside the total. The gate run checks only the measured basis; each assumed row (T1, T2, T6, grader, Codex, C3) is re-stated from its own first run, and the trial stops if a re-stated figure takes the total above that budget.
