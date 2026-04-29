# misc/evals/Makefile — drives skill-creator eval machinery for the 4 in-scope skills.
#
# All module-mode scripts require cwd = skills/skill-creator/ (scripts/ is a Python
# package with an empty __init__.py, so `python3 -m scripts.<name>` is mandatory).
# Recipes `cd` into that directory before invoking Python, and pass eval-set / output
# paths as absolute paths ($(EVALS_ROOT)/…) so the cwd change is invisible to callers.
#
# Override on the command line:
#   make triggering-eks-recon MODEL=claude-opus-4-7
#   make benchmark-eks-recon BENCHMARK_DIR=/abs/path/to/run-dir
#
# MODEL default is the current Claude flagship. The `claude` CLI has no cheap
# availability probe (`--help` accepts any --model string, including bogus
# ones), so we don't try to auto-detect — override if your env exposes a
# different alias.

SHELL          := /bin/bash

EVALS_ROOT     := $(CURDIR)
REPO_ROOT      := $(abspath $(CURDIR)/../..)
SKILLS         := $(shell find $(EVALS_ROOT) -maxdepth 1 -mindepth 1 -type d ! -name 'workspace' ! -name '_template' ! -name 'scripts' ! -name 'history' ! -name 'setup' ! -name '.*' -printf '%f\n' | sort)
SC_DIR         := $(REPO_ROOT)/skills/skill-creator

# ---------- model / provider configuration ------------------------------------
# PROVIDER selects how `claude -p` reaches a model:
#   bedrock    (default) — sets CLAUDE_CODE_USE_BEDROCK=1 and uses a Bedrock
#                          inference-profile ID. Required on AWS-only setups.
#   anthropic            — uses the Anthropic API. Expects ANTHROPIC_API_KEY
#                          to be exported in the caller's environment.
# Override per invocation: `make score PROVIDER=anthropic MODEL=claude-opus-4-7`.
# Defaults for MODEL are provider-aware; explicit MODEL= always wins.
PROVIDER       ?= bedrock

ifeq ($(PROVIDER),bedrock)
  MODEL        ?= global.anthropic.claude-opus-4-7
  export CLAUDE_CODE_USE_BEDROCK := 1
else ifeq ($(PROVIDER),anthropic)
  MODEL        ?= claude-opus-4-7
else
  $(error PROVIDER must be 'bedrock' or 'anthropic', got '$(PROVIDER)')
endif

NUM_WORKERS    ?= 10
MAX_ITER       ?= 5
RUNS_PER_QUERY ?= 3

# Per-skill default locations (override with WORKSPACE=… / BENCHMARK_DIR=…)
workspace_dir   = $(EVALS_ROOT)/$(1)/workspace
benchmark_dir   = $(EVALS_ROOT)/$(1)/workspace
triggering_json = $(EVALS_ROOT)/$(1)/triggering.json
evals_json      = $(EVALS_ROOT)/$(1)/evals.json

VALIDATE_T   := $(addprefix validate-,$(SKILLS))
TRIGGERING_T := $(addprefix triggering-,$(SKILLS))
OPTIMIZE_T   := $(addprefix optimize-,$(SKILLS))
BENCHMARK_T  := $(addprefix benchmark-,$(SKILLS))
REPORT_T     := $(addprefix report-,$(SKILLS))
PACKAGE_T    := $(addprefix package-,$(SKILLS))
REVIEW_T     := $(addprefix review-,$(SKILLS))
TASK_T       := $(addprefix task-,$(SKILLS))

# Task-axis defaults (PLAN §2). RUNS_PER_PROMPT=1 is cheap dev; bump to 3
# for stddev. INCLUDE_LIVE_ONLY=1 enables prompts that require a real
# cluster (eks-recon currently). KUBECONFIG and AWS_SESSION_POLICY feed
# the sandbox so those live prompts run against a read-only scope.
RUNS_PER_PROMPT   ?= 1
INCLUDE_LIVE_ONLY ?= 0
READONLY_SECRETS  := $(EVALS_ROOT)/.secrets
KUBECONFIG_RO     ?= $(READONLY_SECRETS)/kubeconfig.readonly
AWS_POLICY_RO     ?= $(READONLY_SECRETS)/readonly-session-policy.json
AWS_REGION        ?= us-west-2

.PHONY: help list-skills validate-all triggering-all task-all score-full \
        init-evals init-evals-finalize check-evals-coverage hygiene \
        score score-dry \
        $(VALIDATE_T) $(TRIGGERING_T) $(OPTIMIZE_T) \
        $(BENCHMARK_T) $(REPORT_T) $(PACKAGE_T) $(REVIEW_T) $(TASK_T)

help:
	@echo "Per-skill targets (SKILL in: $(SKILLS)):"
	@echo "  validate-<skill>    A  quick_validate.py          (deterministic)"
	@echo "  triggering-<skill>  B  run_triggering.py            (LIVE — needs claude -p)"
	@echo "  optimize-<skill>    D  run_loop.py                 (LIVE)"
	@echo "  benchmark-<skill>   E  aggregate_benchmark.py      (deterministic)"
	@echo "  report-<skill>      F  generate_report.py          (deterministic)"
	@echo "  package-<skill>     G  package_skill.py            (deterministic)"
	@echo "  review-<skill>      K  eval-viewer/generate_review --static  (deterministic)"
	@echo "  task-<skill>        H  run_task_evals.py           (LIVE — subject + grader)"
	@echo ""
	@echo "Meta targets:"
	@echo "  validate-all, triggering-all, task-all"
	@echo "  score               run triggering for every skill and rewrite README scorecard"
	@echo "  score-dry           render the scorecard to stdout without editing README"
	@echo "  score-full          task-all + score (full task + triggering refresh)"
	@echo ""
	@echo "New-skill onboarding:"
	@echo "  init-evals SKILL=<name> [SIBLINGS=\"a,b,c\"]   scaffold misc/evals/<name>/ from _template/"
	@echo "  init-evals-finalize SKILL=<name>              hygiene floor before PR (same checks CI runs)"
	@echo "  check-evals-coverage                          verify every skills/*/ has a misc/evals/*/ entry"
	@echo "  hygiene                                       pre-flight every misc/evals/*/ (no model calls)"
	@echo ""
	@echo "Overrides: PROVIDER (bedrock|anthropic), MODEL, NUM_WORKERS, MAX_ITER, RUNS_PER_QUERY,"
	@echo "           RUNS_PER_PROMPT, INCLUDE_LIVE_ONLY, KUBECONFIG_RO, AWS_POLICY_RO, WORKSPACE, BENCHMARK_DIR"
	@echo "Defaults : PROVIDER=$(PROVIDER) MODEL=$(MODEL) RUNS_PER_QUERY=$(RUNS_PER_QUERY) NUM_WORKERS=$(NUM_WORKERS)"
	@echo "           RUNS_PER_PROMPT=$(RUNS_PER_PROMPT) INCLUDE_LIVE_ONLY=$(INCLUDE_LIVE_ONLY)"

list-skills:
	@echo $(SKILLS)

# ---------- A  quick_validate (deterministic; plain script-mode) --------------
$(VALIDATE_T): validate-%:
	python3 $(SC_DIR)/scripts/quick_validate.py $(REPO_ROOT)/skills/$*

validate-all: $(VALIDATE_T)

# ---------- B  run_triggering (LIVE) ------------------------------------------
# Local replacement for skill-creator/scripts/run_eval.py (PLAN §1.5). Stages
# one skill per query into a mktemp sandbox with a clean HOME so plugin-level
# and user-level skill clones can't compete for trigger routing. Detects
# triggering by parsing stream-json Skill tool_use events on the canonical
# skill name. See misc/evals/scripts/run_triggering.py for the full design.
$(TRIGGERING_T): triggering-%:
	@test -f $(call triggering_json,$*) || \
	  { echo "missing: $(call triggering_json,$*)"; exit 1; }
	python3 $(EVALS_ROOT)/scripts/run_triggering.py \
	  --eval-set   $(call triggering_json,$*) \
	  --skill-path $(REPO_ROOT)/skills/$* \
	  --num-workers $(NUM_WORKERS) \
	  --runs-per-query $(RUNS_PER_QUERY) \
	  --model $(MODEL)

triggering-all: $(TRIGGERING_T)

# ---------- D  run_loop (LIVE; iterative description optimizer) ---------------
$(OPTIMIZE_T): optimize-%:
	@test -f $(call triggering_json,$*) || \
	  { echo "missing: $(call triggering_json,$*)"; exit 1; }
	mkdir -p $(call workspace_dir,$*)
	cd $(SC_DIR) && python3 -m scripts.run_loop \
	  --eval-set   $(call triggering_json,$*) \
	  --skill-path $(REPO_ROOT)/skills/$* \
	  --model $(MODEL) \
	  --max-iterations $(MAX_ITER) \
	  --num-workers $(NUM_WORKERS) \
	  --runs-per-query $(RUNS_PER_QUERY) \
	  --results-dir $(call workspace_dir,$*) \
	  --report none

# ---------- E  aggregate_benchmark (deterministic) ----------------------------
# Expects BENCHMARK_DIR to contain eval-*/<config>/run-*/grading.json.
$(BENCHMARK_T): benchmark-%:
	@: $${BENCHMARK_DIR:=$(call benchmark_dir,$*)} ; \
	  test -d "$$BENCHMARK_DIR" || \
	    { echo "benchmark dir not found: $$BENCHMARK_DIR"; \
	      echo "pass BENCHMARK_DIR=<dir> containing eval-*/…/grading.json"; exit 1; } ; \
	  cd $(SC_DIR) && python3 -m scripts.aggregate_benchmark "$$BENCHMARK_DIR" \
	    --skill-name $* \
	    --skill-path $(REPO_ROOT)/skills/$*

# ---------- F  generate_report (deterministic; reads run_loop results JSON) ---
# Expects RESULTS_JSON=<path to run_loop results.json>.
$(REPORT_T): report-%:
	@: $${RESULTS_JSON:=$(call workspace_dir,$*)/results.json} ; \
	  test -f "$$RESULTS_JSON" || \
	    { echo "results JSON not found: $$RESULTS_JSON"; \
	      echo "pass RESULTS_JSON=<path> (default: <workspace>/results.json)"; exit 1; } ; \
	  cd $(SC_DIR) && python3 -m scripts.generate_report "$$RESULTS_JSON" \
	    --skill-name $* \
	    -o $(call workspace_dir,$*)/report.html

# ---------- G  package_skill (deterministic) ----------------------------------
$(PACKAGE_T): package-%:
	mkdir -p $(EVALS_ROOT)/$*/workspace
	cd $(SC_DIR) && python3 -m scripts.package_skill $(REPO_ROOT)/skills/$* $(EVALS_ROOT)/$*/workspace

# ---------- K  eval-viewer/generate_review --static (deterministic) -----------
# Expects WORKSPACE to be a directory created by run_loop / run_eval.
$(REVIEW_T): review-%:
	@: $${WORKSPACE:=$(call workspace_dir,$*)} ; \
	  test -d "$$WORKSPACE" || \
	    { echo "workspace not found: $$WORKSPACE"; \
	      echo "pass WORKSPACE=<dir> from a prior optimize-$* run"; exit 1; } ; \
	  python3 $(SC_DIR)/eval-viewer/generate_review.py "$$WORKSPACE" \
	    --skill-name $* \
	    --static $(call workspace_dir,$*)/review.html

# ---------- init-evals (scaffold a new misc/evals/<skill>/ from _template/) ----
# Usage:
#   make init-evals SKILL=<name>                         — 2-entry template copy (legacy path)
#   make init-evals SKILL=<name> SIBLINGS="a,b,c"        — pre-fills SIBLING_MAP placeholders
#                                                          (agent still fills in scope + negatives)
#
# The SIBLINGS= arg renders the new skill's README.md with one placeholder bullet per
# sibling between the SIBLING_MAP markers. The `- **\`sibling\`**` shape matches what
# run_all_evals.py's parser expects; the agent (or author) then fills in the scope
# blurb, adds negative-prompt entries via update_sibling_map.py, and splices the
# negative indices into each bullet. Empty SIBLINGS= falls back to the default
# 2-sibling placeholder already in _template/README.md.
init-evals:
	@if [ -z "$(SKILL)" ]; then \
	  echo "usage: make init-evals SKILL=<skill-name> [SIBLINGS=\"a,b,c\"]"; \
	  exit 1; \
	fi
	@if [ -e "$(EVALS_ROOT)/$(SKILL)" ]; then \
	  echo "error: $(EVALS_ROOT)/$(SKILL) already exists"; \
	  exit 1; \
	fi
	@if [ ! -d "$(EVALS_ROOT)/_template" ]; then \
	  echo "error: template dir not found: $(EVALS_ROOT)/_template"; \
	  exit 1; \
	fi
	cp -r $(EVALS_ROOT)/_template $(EVALS_ROOT)/$(SKILL)
	find $(EVALS_ROOT)/$(SKILL) -type f ! -name '.gitkeep' -exec sed -i.bak 's/<REPLACE>/$(SKILL)/g' {} +
	find $(EVALS_ROOT)/$(SKILL) -name '*.bak' -delete
	@if [ -n "$(SIBLINGS)" ]; then \
	  python3 $(EVALS_ROOT)/scripts/render_siblings.py \
	    --readme $(EVALS_ROOT)/$(SKILL)/README.md \
	    --siblings "$(SIBLINGS)"; \
	fi
	@echo ""
	@echo "✓ Scaffolded $(EVALS_ROOT)/$(SKILL)/"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Edit $(EVALS_ROOT)/$(SKILL)/triggering.json — add 16+ trigger prompts (≥8 positives, ≥8 negatives)"
	@echo "  2. Edit $(EVALS_ROOT)/$(SKILL)/evals.json      — add ≥2 task prompts with ≥3 expectations each"
	@echo "  3. Edit $(EVALS_ROOT)/$(SKILL)/README.md       — fill in <REPLACE> markers; update SIBLING_MAP bullets"
	@echo "  4. Run: make init-evals-finalize SKILL=$(SKILL)  — hygiene floor; same checks CI runs"

# ---------- init-evals-finalize (local mirror of the CI hygiene gate) ----------
# Runs the same hygiene pre-flight that .github/workflows/evals.yml enforces,
# scoped to one skill. No model calls, no cluster. Exits 0 when the eval set is
# ready to open a PR. Exits 1 with actionable diagnostics otherwise.
init-evals-finalize:
	@if [ -z "$(SKILL)" ]; then \
	  echo "usage: make init-evals-finalize SKILL=<skill-name>"; \
	  exit 1; \
	fi
	python3 $(EVALS_ROOT)/scripts/check_hygiene.py --skill $(SKILL)

# ---------- H  run_task_evals (LIVE; subject + grader per prompt × config) ----
# Executes evals.json prompts under with_skill / without_skill, grades each run,
# aggregates via aggregate_benchmark. Results land under <skill>/workspace/runs/
# and the workspace/latest symlink is updated. Appends a kind="task" row to
# misc/evals/history/<skill>.jsonl.
#
# Live-cluster prompts (live_only=true in evals.json) are skipped unless
# INCLUDE_LIVE_ONLY=1. When enabled, the runner also needs a read-only
# kubeconfig + an AWS session-policy file to scope what the subject can see.
$(TASK_T): task-%:
	@test -f $(call evals_json,$*) || \
	  { echo "missing: $(call evals_json,$*)"; exit 1; }
	@extra="" ; \
	 if [ "$(INCLUDE_LIVE_ONLY)" = "1" ]; then \
	   extra="$$extra --include-live-only" ; \
	   if [ -f "$(KUBECONFIG_RO)" ]; then \
	     extra="$$extra --kubeconfig $(KUBECONFIG_RO)" ; \
	   fi ; \
	   if [ -f "$(AWS_POLICY_RO)" ]; then \
	     extra="$$extra --aws-session-policy $(AWS_POLICY_RO) --aws-region $(AWS_REGION)" ; \
	   fi ; \
	 fi ; \
	 python3 $(EVALS_ROOT)/scripts/run_task_evals.py \
	   --skill $* \
	   --runs $(RUNS_PER_PROMPT) \
	   --model $(MODEL) \
	   $$extra

task-all: $(TASK_T)

score-full: task-all score

# ---------- score (Phase 1 — triggering scorecard) ----------------------------
# Runs triggering evals for every skill, enriches the metrics, appends a row
# to misc/evals/history/<skill>.jsonl (committed), and rewrites the scorecard
# between <!-- SCORECARD_START/END --> in misc/evals/README.md.
#
# No flag-forwarding here: the Python runner has no own defaults for model /
# runs-per-query / num-workers and only shells out to `make triggering-<skill>`
# with those overrides when the user passed them on its own CLI. The Makefile
# is the single source of truth for defaults — including PROVIDER / MODEL.
score:
	python3 $(EVALS_ROOT)/scripts/run_all_evals.py

score-dry:
	python3 $(EVALS_ROOT)/scripts/run_all_evals.py --dry-run

# ---------- hygiene (deterministic pre-flight; no model, no cluster) ----------
# Runs quick_validate + schema checks (triggering.json positives/negatives,
# evals.json prompt/expectation counts, SIBLING_MAP parseability and negative
# attribution) for every skill under misc/evals/. Exits non-zero on warnings.
hygiene:
	python3 $(EVALS_ROOT)/scripts/check_hygiene.py

# ---------- check-evals-coverage (every skills/*/ has a misc/evals/*/ entry) --
check-evals-coverage:
	@expected=$$(find $(REPO_ROOT)/skills -maxdepth 1 -mindepth 1 -type d -printf '%f\n' \
	  | grep -vx skill-creator | grep -vx terraform-skill | sort); \
	 found=$$(find $(EVALS_ROOT) -maxdepth 1 -mindepth 1 -type d -printf '%f\n' \
	  | grep -vx _template | grep -vx workspace | grep -vx scripts | grep -vx history | sort); \
	 missing=$$(comm -23 <(echo "$$expected") <(echo "$$found")); \
	 if [ -n "$$missing" ]; then \
	   echo "Missing misc/evals/ entries for:"; \
	   echo "$$missing" | sed 's/^/  - /'; \
	   echo ""; \
	   echo "Run: make init-evals SKILL=<name>"; \
	   exit 1; \
	 fi; \
	 echo "✓ All skills have misc/evals/ entries"
