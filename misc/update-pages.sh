#!/usr/bin/env bash
# update-pages.sh
#
# Generates Docusaurus wrappers for every tracked *.md under skills/,
# steering/, and examples/ into misc/website/docs/, plus manifests consumed
# by the homepage SkillGrid and examples grid.
#
# Inputs (sources of truth):
#   skills/**/*.md     (except skills/README.md — marker-generated)
#   steering/**/*.md
#   examples/**/*.md   (README.md → index.md wrappers)
#   examples/**/*.html (copied to static/)
#   examples/**/*.png  (copied to static/)
#
# Outputs (regenerated; tracked in git):
#   misc/website/docs/skills/<name>/index.md       wrapper for SKILL.md
#   misc/website/docs/skills/<name>/<sub>/<f>.md   wrapper for sub-files
#   misc/website/docs/skills/index.md              card grid (overwritten)
#   misc/website/docs/steering/<rel-path>.md       wrappers for steering
#   misc/website/docs/examples/<path>/index.md     wrapper for README.md
#   misc/website/docs/examples/index.md            card grid (overwritten)
#   misc/website/static/examples/                  .html + .png assets
#   misc/website/static/manifests/skills.json
#   misc/website/static/manifests/examples.json
#
# misc/website/docs/steering/index.md is HAND-WRITTEN and never touched.
#
# Usage:
#   ./misc/update-pages.sh              # regenerate in place
#   ./misc/update-pages.sh --check      # fail if generated artifacts are stale
#   ./misc/update-pages.sh --dry-run    # print what would be written; no edits
#
# --check is what the `docs-sync` CI job runs alongside
# update-all-references.sh: regenerate in place, then `git diff --exit-code`
# on the output paths. Non-zero exit means someone edited a wrapper by hand
# or added/edited a skill/workflow without running this script.
# Fix: `./misc/update-pages.sh && git add … && commit`.

set -euo pipefail

MODE="run"
if [[ "${1:-}" == "--check" ]]; then
  MODE="check"
elif [[ "${1:-}" == "--dry-run" ]]; then
  MODE="dry-run"
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

SKILLS_OUT="$REPO_ROOT/misc/website/docs/skills"
STEERING_OUT="$REPO_ROOT/misc/website/docs/steering"
EXAMPLES_OUT="$REPO_ROOT/misc/website/docs/examples"
MANIFEST="$REPO_ROOT/misc/website/static/manifests/skills.json"
EXAMPLES_MANIFEST="$REPO_ROOT/misc/website/static/manifests/examples.json"
SKILLS_DIR="$REPO_ROOT/skills"
EXAMPLES_DIR="$REPO_ROOT/examples"
EXAMPLES_STATIC="$REPO_ROOT/misc/website/static/examples"

GH_BASE="https://github.com/aws-samples/sample-apex-skills/blob/main"

# Files this script may touch — the blast radius of --check.
TOUCHED_PATHS=(
  "misc/website/docs/skills"
  "misc/website/docs/steering"
  "misc/website/docs/examples"
  "misc/website/static/manifests"
  "misc/website/static/examples"
)

# --- Parse one frontmatter key from a markdown file -----------------------
parse_frontmatter() {
  local file="$1"
  local key="$2"
  awk -v key="$key" '
    /^---$/ { block++; next }
    block == 1 && $0 ~ "^" key ":" {
      sub("^" key ":[ ]*", "")
      sub("^\"", ""); sub("\"$", "")
      sub("^'\''", ""); sub("'\''$", "")
      print
      exit
    }
    block >= 2 { exit }
  ' "$file"
}

# --- Extract first # heading from a markdown file -------------------------
first_heading() {
  local file="$1"
  awk '
    /^---$/ { block++; next }
    block == 1 { next }
    /^# / { sub(/^# */, ""); print; exit }
  ' "$file"
}

# --- Derive title from filename -------------------------------------------
title_from_filename() {
  local base="$1"
  base="${base%.md}"
  echo "$base" | sed 's/-/ /g; s/\b\(.\)/\u\1/g'
}

# --- Strip leading YAML frontmatter from a markdown file ------------------
strip_frontmatter() {
  local file="$1"
  awk '
    BEGIN { mode = "preamble" }
    mode == "preamble" && NR == 1 && /^---[[:space:]]*$/ { mode = "in_fm"; next }
    mode == "preamble" { mode = "body"; print; next }
    mode == "in_fm" && /^---[[:space:]]*$/ { mode = "body"; next }
    mode == "in_fm" { next }
    mode == "body" { print }
  ' "$file"
}

# --- YAML-safe scalar via JSON encoding -----------------------------------
yaml_scalar() {
  python3 -c 'import json, sys; print(json.dumps(sys.argv[1], ensure_ascii=False))' "$1"
}

# --- Link rewriting filter (stdin → stdout) -------------------------------
# Rewrites:
#   - SKILL.md → index.md in relative .md links
#   - non-.md relative targets → GitHub blob URL
#   - external URLs and anchors → pass through
rewrite_links() {
  local src="$1"
  python3 -c '
import re, sys, os, signal
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

src = sys.argv[1]
GH_BASE = sys.argv[2]
src_dir = os.path.dirname(src)
is_example = src.startswith("examples/")

def rewrite(m):
    prefix = m.group(1)  # "!" for images, "" for links
    text, target = m.group(2), m.group(3)
    if target.startswith(("http://", "https://", "#", "mailto:")):
        return m.group(0)
    anchor = ""
    query = ""
    if "#" in target:
        target, anchor = target.rsplit("#", 1)
        anchor = "#" + anchor
    if "?" in target:
        target, query = target.split("?", 1)
        query = "?" + query
    if not target:
        return m.group(0)
    resolved = os.path.normpath(os.path.join(src_dir, target))

    # For examples/ sources: static assets (.png, .html) resolve to /sample-apex-skills/examples/...
    if is_example and resolved.startswith("examples/") and not target.endswith(".md"):
        examples_prefix = "examples/"
        static_url = "/sample-apex-skills/examples/" + resolved[len(examples_prefix):]
        if target.endswith(".png"):
            return f"![{text}](pathname://{static_url}{query}{anchor})"
        elif target.endswith(".html"):
            # Emit both a link and an iframe embed
            link = f"[{text}](pathname://{static_url}{query}{anchor})"
            iframe = (
                "\n\n<iframe src=\"" + static_url + query + "\" "
                "width=\"100%\" height=\"600px\" "
                "style={{border:\"1px solid var(--ifm-color-emphasis-300)\", borderRadius:\"8px\"}}>"
                "</iframe>\n"
            )
            return link + iframe
        else:
            return f"[{text}]({GH_BASE}/{resolved}{query}{anchor})"

    if resolved.startswith(".."):
        return f"[{text}]({GH_BASE}/{target}{query}{anchor})"
    if not resolved.startswith(("skills/", "steering/", "examples/")):
        return f"[{text}]({GH_BASE}/{resolved}{query}{anchor})"
    if not target.endswith(".md"):
        return f"[{text}]({GH_BASE}/{resolved}{query}{anchor})"
    # .md links within skills/steering/examples — rewrite for Docusaurus
    if os.path.basename(resolved) == "SKILL.md":
        resolved = os.path.join(os.path.dirname(resolved), "index.md")
    elif os.path.basename(resolved) == "README.md" and resolved.startswith("examples/"):
        resolved = os.path.join(os.path.dirname(resolved), "index.md")
    new_target = os.path.relpath(resolved, src_dir)
    # Strip .md extension for Docusaurus routing
    if new_target.endswith(".md"):
        new_target = new_target[:-3]
    # index → directory path
    if new_target.endswith("/index"):
        new_target = new_target[:-5]
    elif new_target == "index":
        new_target = "."
    return f"[{text}]({new_target}{query}{anchor})"

for line in sys.stdin:
    sys.stdout.write(re.sub(r"(!?)\[([^\]]*)\]\(([^)]+)\)", rewrite, line))
' "$src" "$GH_BASE"
}

# --- Detect vendored skill and emit appropriate admonition ----------------
# A vendored skill has a LICENSE* file in its directory.
# Team-owned (source URL matches aws-samples/aws/awslabs/amazon orgs) gets
# an info admonition. External third-party gets a caution admonition.
vendored_skill_admonition() {
  local src="$1"
  # Only applies to files under skills/<name>/
  [[ "$src" == skills/*/SKILL.md || "$src" == skills/*/* ]] || return 0
  local skill_name="${src#skills/}"
  skill_name="${skill_name%%/*}"
  local skill_dir="$REPO_ROOT/skills/$skill_name"

  # Check for LICENSE* file
  local license_file=""
  for f in "$skill_dir"/LICENSE*; do
    [[ -f "$f" ]] && license_file="$f" && break
  done
  [[ -n "$license_file" ]] || return 0

  # Extract metadata from THIRD_PARTY_NOTICES.md (authoritative source)
  local notices="$REPO_ROOT/THIRD_PARTY_NOTICES.md"
  local author license_id source_url
  if [[ -f "$notices" ]]; then
    source_url="$(awk -v name="$skill_name" '
      $0 ~ "^## " name { found=1; next }
      found && /Source:/ { sub(/.*Source:[* ]*/, ""); sub(/[* ]*$/, ""); print; exit }
    ' "$notices")"
    author="$(awk -v name="$skill_name" '
      $0 ~ "^## " name { found=1; next }
      found && /Copyright:/ { sub(/.*Copyright:[* ]*/, ""); sub(/[* ]*$/, ""); print; exit }
    ' "$notices")"
  fi
  # Fallback: frontmatter metadata
  if [[ -z "$author" ]]; then
    local skill_md="$skill_dir/SKILL.md"
    author="$(awk '/author:/{sub(/.*author: */, ""); print; exit}' "$skill_md" 2>/dev/null)"
  fi
  license_id="$(parse_frontmatter "$skill_dir/SKILL.md" "license" 2>/dev/null)"
  [[ -z "$license_id" ]] && license_id="Apache-2.0"
  [[ -z "$source_url" ]] && source_url="$GH_BASE/skills/$skill_name"
  [[ -z "$author" ]] && author="third party"

  # Determine ownership: team-owned if source URL matches AWS orgs
  local is_team=false
  if [[ "$source_url" == *github.com/aws-samples/* || \
        "$source_url" == *github.com/aws/* || \
        "$source_url" == *github.com/awslabs/* || \
        "$source_url" == *github.com/amazon* ]]; then
    is_team=true
  fi

  if $is_team; then
    local repo_name="${source_url##*/}"
    cat <<EOF

:::info[Vendored skill]
This skill is sourced from [$repo_name]($source_url), also maintained by the APEX team.
:::

EOF
  else
    cat <<EOF

:::caution[Third-party skill]
This skill is maintained by **$author** under the $license_id license. Upstream: [$source_url]($source_url)
:::

EOF
  fi
}

# --- Build a generic wrapper to stdout ------------------------------------
build_wrapper() {
  local src="$1"
  local title="$2"
  local description="$3"
  local title_yaml desc_yaml
  title_yaml="$(yaml_scalar "$title")"
  desc_yaml="$(yaml_scalar "$description")"

  cat <<EOF
---
title: $title_yaml
description: $desc_yaml
custom_edit_url: $GH_BASE/$src
format: md
---

:::info[Source]
This page is generated from [$src]($GH_BASE/$src). Edit the source, not this page.
:::

EOF
  vendored_skill_admonition "$src"
  strip_frontmatter "$REPO_ROOT/$src" | rewrite_links "$src"
}

# --- Compute output path for a source file --------------------------------
compute_out_path() {
  local src="$1"
  if [[ "$src" == skills/*/SKILL.md ]]; then
    local folder="${src#skills/}"
    folder="${folder%/SKILL.md}"
    echo "$SKILLS_OUT/$folder/index.md"
  elif [[ "$src" == skills/* ]]; then
    local rel="${src#skills/}"
    echo "$SKILLS_OUT/$rel"
  elif [[ "$src" == steering/* ]]; then
    local rel="${src#steering/}"
    echo "$STEERING_OUT/$rel"
  elif [[ "$src" == examples/*/README.md ]]; then
    local rel="${src#examples/}"
    rel="${rel%/README.md}"
    echo "$EXAMPLES_OUT/$rel/index.md"
  elif [[ "$src" == examples/* ]]; then
    local rel="${src#examples/}"
    echo "$EXAMPLES_OUT/$rel"
  fi
}

# --- Derive title for any source file -------------------------------------
derive_title() {
  local file="$1"
  local t
  t="$(parse_frontmatter "$file" "name")"
  if [[ -n "$t" ]]; then echo "$t"; return; fi
  t="$(first_heading "$file")"
  if [[ -n "$t" ]]; then echo "$t"; return; fi
  title_from_filename "$(basename "$file")"
}

# --- Build skills/index.md card grid to stdout ----------------------------
build_skills_index() {
  cat <<'EOF'
---
sidebar_position: 3
title: Skills
description: "Browse all APEX skills for AWS platform engineering — EKS architecture, Terraform modules, upgrade readiness, cluster operations, and more."
---

# Skills

> _This page is auto-generated by [`misc/update-pages.sh`](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/update-pages.sh). Do not edit manually._

EOF
  for skill_dir in "$SKILLS_DIR"/*/; do
    local skill_md="$skill_dir/SKILL.md"
    [[ -f "$skill_md" ]] || continue
    local folder name description
    folder="$(basename "$skill_dir")"
    name="$(parse_frontmatter "$skill_md" "name")"
    description="$(parse_frontmatter "$skill_md" "description")"
    [[ -n "$name" ]] || continue
    [[ -n "$description" ]] || description="_(no description in frontmatter)_"
    echo "## [$name](./$folder/)"
    echo ""
    echo "$description"
    echo ""
  done
}

# --- Build skills.json manifest to stdout ---------------------------------
build_manifest() {
  python3 - "$SKILLS_DIR" <<'PY'
import json, os, re, sys

skills_dir = sys.argv[1]


def parse_fm(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$', line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if (v.startswith('"') and v.endswith('"')) or (
            v.startswith("'") and v.endswith("'")
        ):
            v = v[1:-1]
        fm[k] = v
    return fm


out = []
for entry in sorted(os.listdir(skills_dir)):
    sd = os.path.join(skills_dir, entry)
    sm = os.path.join(sd, "SKILL.md")
    if not os.path.isfile(sm):
        continue
    fm = parse_fm(sm)
    name = fm.get("name") or entry
    out.append({
        "name": name,
        "description": fm.get("description", ""),
        "path": f"/docs/skills/{entry}",
    })

print(json.dumps(out, indent=2, ensure_ascii=False))
PY
}

# --- Recursive cleanup: remove wrappers not in the expected set -----------
cleanup_stale_tree() {
  local base_dir="$1"
  shift
  local -A keep_set
  for p in "$@"; do keep_set["$p"]=1; done

  [[ -d "$base_dir" ]] || return 0
  while IFS= read -r -d '' f; do
    local rel="${f#"$base_dir"/}"
    if [[ -z "${keep_set[$rel]:-}" ]]; then
      rm "$f"
    fi
  done < <(find "$base_dir" -name '*.md' -print0)
  find "$base_dir" -type d -empty -delete 2>/dev/null || true
}

# --- Build examples/index.md card grid to stdout --------------------------
build_examples_index() {
  cat <<'EOF'
---
sidebar_position: 5
title: Examples
description: "Hands-on walkthroughs demonstrating APEX skills against real AWS infrastructure — deploy, run, and assess platform engineering workflows."
---

# Examples

> _This page is auto-generated by [`misc/update-pages.sh`](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/update-pages.sh). Do not edit manually._

Examples are self-contained walkthroughs demonstrating APEX skills against real infrastructure. Each example deploys resources, runs an APEX workflow, and shows expected results.

EOF
  while IFS= read -r -d '' readme; do
    local rel="${readme#"$EXAMPLES_DIR"/}"
    local dir_rel="${rel%/README.md}"
    local name description
    name="$(parse_frontmatter "$readme" "name")"
    description="$(parse_frontmatter "$readme" "description")"
    [[ -n "$name" ]] || continue
    [[ -n "$description" ]] || description="_(no description in frontmatter)_"
    echo "## [$name](./$dir_rel/)"
    echo ""
    echo "$description"
    echo ""
  done < <(find "$EXAMPLES_DIR" -name 'README.md' -print0 | sort -z)
}

# --- Build examples.json manifest to stdout --------------------------------
build_examples_manifest() {
  python3 - "$EXAMPLES_DIR" <<'PY'
import json, os, re, sys

examples_dir = sys.argv[1]


def parse_fm(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$', line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if (v.startswith('"') and v.endswith('"')) or (
            v.startswith("'") and v.endswith("'")
        ):
            v = v[1:-1]
        fm[k] = v
    return fm


out = []
for root, dirs, files in sorted(os.walk(examples_dir)):
    dirs.sort()
    if "README.md" not in files:
        continue
    readme_path = os.path.join(root, "README.md")
    fm = parse_fm(readme_path)
    name = fm.get("name")
    if not name:
        continue
    rel_dir = os.path.relpath(root, examples_dir)
    out.append({
        "name": name,
        "description": fm.get("description", ""),
        "path": f"/docs/examples/{rel_dir}",
    })

print(json.dumps(out, indent=2, ensure_ascii=False))
PY
}

# --- Copy examples static assets (.html, .png) to website/static/examples/ -
copy_examples_static() {
  mapfile -t STATIC_FILES < <(git ls-files -- 'examples/**/*.html' 'examples/**/*.png')
  for asset in "${STATIC_FILES[@]}"; do
    local rel="${asset#examples/}"
    local dest="$EXAMPLES_STATIC/$rel"
    if [[ "$MODE" == "dry-run" ]]; then
      echo "COPY $asset → $dest"
    else
      mkdir -p "$(dirname "$dest")"
      cp "$REPO_ROOT/$asset" "$dest"
    fi
  done
}

# =========================================================================
# Generate
# =========================================================================

if [[ "$MODE" == "dry-run" ]]; then
  echo "=== DRY RUN — would write the following ==="
fi

# Collect all tracked .md under skills/ and steering/
mapfile -t ALL_MD < <(git ls-files -- 'skills/**/*.md' 'steering/*.md' 'steering/**/*.md' 'examples/**/*.md')

declare -a EXPECTED_SKILL_FILES=("index.md")
declare -a EXPECTED_STEERING_FILES=("index.md")
declare -a EXPECTED_EXAMPLES_FILES=("index.md")

# --- Per-file wrappers ---
for src in "${ALL_MD[@]}"; do
  # Skip skills/README.md (marker-generated, not a docs page)
  [[ "$src" == "skills/README.md" ]] && continue

  out_file="$(compute_out_path "$src")"
  [[ -n "$out_file" ]] || continue

  # Track expected file for cleanup
  if [[ "$src" == skills/* ]]; then
    EXPECTED_SKILL_FILES+=("${out_file#"$SKILLS_OUT"/}")
  elif [[ "$src" == steering/* ]]; then
    EXPECTED_STEERING_FILES+=("${out_file#"$STEERING_OUT"/}")
  elif [[ "$src" == examples/* ]]; then
    EXPECTED_EXAMPLES_FILES+=("${out_file#"$EXAMPLES_OUT"/}")
  fi

  title="$(derive_title "$REPO_ROOT/$src")"
  description="$(parse_frontmatter "$REPO_ROOT/$src" "description")"

  if [[ "$MODE" == "dry-run" ]]; then
    echo "--- $out_file ---"
    build_wrapper "$src" "$title" "${description:-}" | head -10
    echo "  [... body truncated ...]"
    echo ""
  else
    mkdir -p "$(dirname "$out_file")"
    build_wrapper "$src" "$title" "${description:-}" > "$out_file.tmp"
    mv "$out_file.tmp" "$out_file"
  fi
done

# --- Skills index (card grid) ---
if [[ "$MODE" == "dry-run" ]]; then
  echo "--- $SKILLS_OUT/index.md ---"
  build_skills_index | head -20
  echo "  [... truncated ...]"
  echo ""
else
  mkdir -p "$SKILLS_OUT"
  build_skills_index > "$SKILLS_OUT/index.md.tmp"
  mv "$SKILLS_OUT/index.md.tmp" "$SKILLS_OUT/index.md"
fi

# --- Manifest ---
if [[ "$MODE" == "dry-run" ]]; then
  echo "--- $MANIFEST ---"
  build_manifest
  echo ""
else
  mkdir -p "$(dirname "$MANIFEST")"
  build_manifest > "$MANIFEST.tmp"
  mv "$MANIFEST.tmp" "$MANIFEST"
fi

# --- Examples index (card grid) ---
if [[ "$MODE" == "dry-run" ]]; then
  echo "--- $EXAMPLES_OUT/index.md ---"
  build_examples_index | head -20
  echo "  [... truncated ...]"
  echo ""
else
  mkdir -p "$EXAMPLES_OUT"
  build_examples_index > "$EXAMPLES_OUT/index.md.tmp"
  mv "$EXAMPLES_OUT/index.md.tmp" "$EXAMPLES_OUT/index.md"
fi

# --- Examples manifest ---
if [[ "$MODE" == "dry-run" ]]; then
  echo "--- $EXAMPLES_MANIFEST ---"
  build_examples_manifest
  echo ""
else
  mkdir -p "$(dirname "$EXAMPLES_MANIFEST")"
  build_examples_manifest > "$EXAMPLES_MANIFEST.tmp"
  mv "$EXAMPLES_MANIFEST.tmp" "$EXAMPLES_MANIFEST"
fi

# --- Examples static assets (.html, .png) ---
copy_examples_static

# --- Stale-wrapper cleanup (only in real-write mode, not --check) ---
if [[ "$MODE" == "run" ]]; then
  cleanup_stale_tree "$SKILLS_OUT" "${EXPECTED_SKILL_FILES[@]}"
  cleanup_stale_tree "$STEERING_OUT" "${EXPECTED_STEERING_FILES[@]}"
  cleanup_stale_tree "$EXAMPLES_OUT" "${EXPECTED_EXAMPLES_FILES[@]}"
fi

# --- Dry-run exits here ---
if [[ "$MODE" == "dry-run" ]]; then
  echo "=== No changes written ==="
  exit 0
fi

# --- --check: regen happened in place above; now diff against committed state
if [[ "$MODE" == "check" ]]; then
  diff_dirty=false
  if ! git diff --quiet -- "${TOUCHED_PATHS[@]}"; then
    diff_dirty=true
  fi
  untracked="$(git ls-files --others --exclude-standard -- "${TOUCHED_PATHS[@]}")"

  if $diff_dirty || [[ -n "$untracked" ]]; then
    echo ""
    echo "ERROR: Docusaurus wrappers / manifest are stale."
    if $diff_dirty; then
      echo ""
      echo "Diff:"
      git --no-pager diff -- "${TOUCHED_PATHS[@]}"
    fi
    if [[ -n "$untracked" ]]; then
      echo ""
      echo "Untracked (newly generated) files:"
      printf '  %s\n' "$untracked"
    fi
    echo ""
    echo "Fix: run ./misc/update-pages.sh locally, commit the result."
    exit 1
  fi
  echo "✓ Docusaurus wrappers + manifests are in sync with skills/, steering/, and examples/"
  exit 0
fi

# --- Run mode summary ---
skill_count="$(find "$SKILLS_OUT" -name '*.md' | wc -l)"
steering_count="$(find "$STEERING_OUT" -name '*.md' | wc -l)"
examples_count="$(find "$EXAMPLES_OUT" -name '*.md' | wc -l)"
examples_static_count="$(find "$EXAMPLES_STATIC" -type f 2>/dev/null | wc -l)"
echo "✅ Generated Docusaurus wrappers and manifests:"
echo "   Skills:    $skill_count files in misc/website/docs/skills/"
echo "   Steering:  $steering_count files in misc/website/docs/steering/"
echo "   Examples:  $examples_count files in misc/website/docs/examples/"
echo "   Static:    $examples_static_count files in misc/website/static/examples/"
echo "   Manifests: misc/website/static/manifests/{skills,examples}.json"
