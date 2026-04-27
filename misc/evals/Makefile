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
SKILLS         := $(shell find $(EVALS_ROOT) -maxdepth 1 -mindepth 1 -type d ! -name 'workspace' ! -name '_template' ! -name '.*' -printf '%f\n' | sort)
SC_DIR         := $(REPO_ROOT)/skills/skill-creator
MODEL          ?= claude-opus-4-7
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

.PHONY: help list-skills validate-all triggering-all \
        init-evals check-evals-coverage \
        $(VALIDATE_T) $(TRIGGERING_T) $(OPTIMIZE_T) \
        $(BENCHMARK_T) $(REPORT_T) $(PACKAGE_T) $(REVIEW_T)

help:
	@echo "Per-skill targets (SKILL in: $(SKILLS)):"
	@echo "  validate-<skill>    A  quick_validate.py          (deterministic)"
	@echo "  triggering-<skill>  B  run_eval.py                 (LIVE — needs claude -p)"
	@echo "  optimize-<skill>    D  run_loop.py                 (LIVE)"
	@echo "  benchmark-<skill>   E  aggregate_benchmark.py      (deterministic)"
	@echo "  report-<skill>      F  generate_report.py          (deterministic)"
	@echo "  package-<skill>     G  package_skill.py            (deterministic)"
	@echo "  review-<skill>      K  eval-viewer/generate_review --static  (deterministic)"
	@echo ""
	@echo "Meta targets:"
	@echo "  validate-all, triggering-all"
	@echo ""
	@echo "New-skill onboarding:"
	@echo "  init-evals SKILL=<name>    scaffold misc/evals/<name>/ from _template/"
	@echo "  check-evals-coverage       verify every skills/*/ has a misc/evals/*/ entry"
	@echo ""
	@echo "Overrides: MODEL, NUM_WORKERS, MAX_ITER, RUNS_PER_QUERY, WORKSPACE, BENCHMARK_DIR"

list-skills:
	@echo $(SKILLS)

# ---------- A  quick_validate (deterministic; plain script-mode) --------------
$(VALIDATE_T): validate-%:
	python3 $(SC_DIR)/scripts/quick_validate.py $(REPO_ROOT)/skills/$*

validate-all: $(VALIDATE_T)

# ---------- B  run_eval (LIVE) ------------------------------------------------
$(TRIGGERING_T): triggering-%:
	@test -f $(call triggering_json,$*) || \
	  { echo "missing: $(call triggering_json,$*)"; exit 1; }
	cd $(SC_DIR) && python3 -m scripts.run_eval \
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
init-evals:
	@if [ -z "$(SKILL)" ]; then \
	  echo "usage: make init-evals SKILL=<skill-name>"; \
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
	@echo ""
	@echo "✓ Scaffolded $(EVALS_ROOT)/$(SKILL)/"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Edit $(EVALS_ROOT)/$(SKILL)/triggering.json — add 16+ trigger prompts"
	@echo "  2. Edit $(EVALS_ROOT)/$(SKILL)/evals.json      — add 2-4 task prompts"
	@echo "  3. Edit $(EVALS_ROOT)/$(SKILL)/README.md       — document the eval set"
	@echo "  4. Run: make validate-$(SKILL)"

# ---------- check-evals-coverage (every skills/*/ has a misc/evals/*/ entry) --
check-evals-coverage:
	@expected=$$(find $(REPO_ROOT)/skills -maxdepth 1 -mindepth 1 -type d -printf '%f\n' \
	  | grep -vx skill-creator | grep -vx terraform-skill | sort); \
	 found=$$(find $(EVALS_ROOT) -maxdepth 1 -mindepth 1 -type d -printf '%f\n' \
	  | grep -vx _template | grep -vx workspace | sort); \
	 missing=$$(comm -23 <(echo "$$expected") <(echo "$$found")); \
	 if [ -n "$$missing" ]; then \
	   echo "Missing misc/evals/ entries for:"; \
	   echo "$$missing" | sed 's/^/  - /'; \
	   echo ""; \
	   echo "Run: make init-evals SKILL=<name>"; \
	   exit 1; \
	 fi; \
	 echo "✓ All skills have misc/evals/ entries"
