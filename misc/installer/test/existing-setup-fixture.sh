#!/usr/bin/env bash
# Existing-setup fixture for the apex-skills installer (step 12 groundwork).
#
# Lays down a realistic agent setup that a user already has before they run the
# installer: their own skills, AGENTS.md and CLAUDE.md files, Kiro steering,
# Claude Code commands, agents and hooks, a memory directory, MCP configs, a
# knowledge base, plus symlinks of their own (relative, absolute, dangling and a
# whole skills directory linked into a dotfiles tree), odd modes and a file name
# with spaces. existing-setup-check.mjs then records every path, so a run of an
# installer over it can be checked for the Claude Code and Kiro paths it lays
# down: nothing of the user's may change. It has no Codex setup and its
# clashing names are v1.3.0 flat names; a v2 or Codex-target run needs those
# added first.
#
# Usage: misc/installer/test/existing-setup-fixture.sh <home> [<project>]
#   <home>     a throwaway HOME (created; must be empty or missing)
#   <project>  a throwaway project directory (default: <home>/work/app; must
#              be empty or missing: existing files are overwritten)
#
# Both Claude Code and Kiro CLI are detected by the 1.3.0 installer from the
# existence of ~/.claude and ~/.kiro, so the fixture creates both.
#
# Names chosen to collide with APEX v1.3.0 names (the installer must report and
# keep them, never replace them):
#   ~/.claude/skills/terraform-skill  the user's own link to the public
#                                     terraform-skill, which APEX also ships
#   ~/.claude/skills/eks-best-practices  a user's own skill directory under an
#                                     APEX skill name (an earlier hand copy)
#   ~/.kiro/skills/skill-creator      (inside the dotfiles tree) the user's
#                                     own copy of the common skill-creator skill
#   ~/.kiro/steering/design.md        a generic steering name that is also an
#                                     APEX Kiro workflow (steering/workflows/design.md)
#   <project>/.claude/skills/eks-build and <project>/.kiro/steering/eks-security.md
#                                     the same, for a --project install
#
# Documented 1.3.0 no-record cases (misc/installer/README.md, Installed paths
# and Uninstall), laid down so a run shows what they do rather than hiding
# them; under 1.3.0 the first two read as CHANGED or REMOVED:
#   ~/.kiro/steering/eks-upgrade-check.md and <project>/.kiro/steering/eks-genai.md
#       a Kiro steering copy carrying installer 1.3.0's marker line, edited by
#       the user (as left by an earlier install whose record is gone). With no
#       install record, "a marked file at a workflow name is overwritten"; the
#       recorded --uninstall after it then removes the installer's copy.
#   ~/.claude/skills/my-retired-pin
#       the user's own link into ~/.apex-skills that stays dangling. 1.3.0
#       removes it at the first install (bin/cli.mjs pruneArea: "With no
#       record for the area, remove dangling links into the clone"); the
#       README states that removal for --uninstall only.
#   ~/.claude/skills/my-eks-design, <project>/.claude/skills/my-eks-recon
#       the user's own links into ~/.apex-skills at non-APEX names (live once
#       the clone exists). A recorded run keeps them, so a chain of recorded
#       steps reads them as unchanged; with no record, --uninstall "removes
#       every link into ~/.apex-skills in the skill directories", and that
#       no-record --uninstall is not exercised by an install-first chain.
# The marker line is installer 1.3.0's text (bin/cli.mjs KIRO_MARKER); another
# installer version needs its own.
set -eu

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  sed -n '2,/^set -eu$/p' "$0" | sed '$d' >&2
  exit 2
fi
H="$1"
P="${2:-$1/work/app}"
case "$H" in /*) ;; *) echo "<home> must be an absolute path: $H" >&2; exit 2 ;; esac
case "$P" in /*) ;; *) echo "<project> must be an absolute path: $P" >&2; exit 2 ;; esac
if [ -e "$H" ] && [ -n "$(ls -A "$H")" ]; then echo "<home> $H is not empty" >&2; exit 2; fi
if [ -e "$P" ] && [ -n "$(ls -A "$P")" ]; then echo "<project> $P is not empty" >&2; exit 2; fi
umask 022

# put <path> <mode>: write stdin to <path> (parents created) and set its mode.
put() {
  mkdir -p "$(dirname "$1")"
  cat > "$1"
  chmod "$2" "$1"
}
# skill <dir> <name> <description>: a minimal SKILL.md with front matter.
skill() {
  printf -- '---\nname: %s\ndescription: %s\n---\n\n# %s\n\nThe user'"'"'s own skill. Not from APEX.\n' "$2" "$3" "$2" | put "$1/SKILL.md" 0644
}

# marked_copy <path> <title>: a Kiro steering copy with installer 1.3.0's marker
# line after its front matter, then the user's own edit.
KIRO_MARKER_130='<!-- apex-skills installer: generated copy of steering/workflows; installer 1.3.0 install, --update and --uninstall keep this file once you edit it and list it (exit code 3), but replace or delete it when there is no install record for this home or project directory (no manifest, or the directory was moved or renamed since); a 1.2.0 install or --update replaces it (a plain npx apex-skills runs the version that npm view apex-skills version prints); to be safe, save your own version under another name -->'
marked_copy() {
  printf -- '---\ninclusion: manual\n---\n%s\n# %s\n- The user'"'"'s own rule, added after the install.\n' "$KIRO_MARKER_130" "$2" | put "$1" 0644
}

mkdir -p "$H"
H="$(cd "$H" && pwd -P)"
mkdir -p "$P"
P="$(cd "$P" && pwd -P)"

# ---------------------------------------------------------------- dotfiles
# Skills the user keeps under version control in a dotfiles tree and links in.
skill "$H/dotfiles/skills/terraform-skill" terraform-skill "Terraform and OpenTofu guidance (installed by the user from upstream)"
skill "$H/dotfiles/skills/notes" notes "Personal notes skill"
skill "$H/dotfiles/kiro-skills/my-runbook" my-runbook "On-call runbook"
skill "$H/dotfiles/kiro-skills/skill-creator" skill-creator "The user's own copy of skill-creator"
put "$H/dotfiles/kiro-skills/my-runbook/references/escalation.md" 0644 <<'EOF'
# Escalation
Page the secondary after 15 minutes.
EOF

# ---------------------------------------------------------------- Claude Code
put "$H/.claude/CLAUDE.md" 0644 <<'EOF'
# Global instructions
- Prefer small commits.
- Ask before deleting files.
EOF
put "$H/.claude/settings.json" 0644 <<'EOF'
{
  "permissions": { "allow": ["Bash(git status)"] },
  "hooks": {}
}
EOF
skill "$H/.claude/skills/my-pr-review" my-pr-review "Review a pull request the way the user likes"
put "$H/.claude/skills/my-pr-review/scripts/check.sh" 0755 <<'EOF'
#!/bin/sh
echo "checking"
EOF
skill "$H/.claude/skills/eks-best-practices" eks-best-practices "The user's own EKS notes, under the same name as an APEX skill"
ln -s ../../dotfiles/skills/terraform-skill "$H/.claude/skills/terraform-skill"   # relative, collides
ln -s ../../dotfiles/skills/removed-helper "$H/.claude/skills/old-helper"         # dangling, relative
ln -s "$H/dotfiles/skills/notes" "$H/.claude/skills/notes"                         # absolute
ln -s ../../.apex-skills/skills/eks-design "$H/.claude/skills/my-eks-design"       # user's own link into the clone
ln -s ../../.apex-skills/skills/retired-skill "$H/.claude/skills/my-retired-pin"   # user's own, dangling, into the clone
put "$H/.claude/commands/deploy.md" 0644 <<'EOF'
Deploy the current branch to staging.
EOF
put "$H/.claude/commands/my review.md" 0644 <<'EOF'
Review the staged diff.
EOF
put "$H/.claude/commands/team/standup.md" 0644 <<'EOF'
Summarise yesterday's commits.
EOF
put "$H/.claude/agents/reviewer.md" 0644 <<'EOF'
---
name: reviewer
description: Reviews diffs
---
Review carefully.
EOF
put "$H/.claude/hooks/pre-commit-check.sh" 0755 <<'EOF'
#!/bin/sh
exit 0
EOF
# Memory: Claude Code keeps per-project memory under ~/.claude/projects/<cwd with / as ->/memory/.
MEM="$H/.claude/projects/$(printf '%s' "$P" | tr '/' '-')/memory"
put "$MEM/MEMORY.md" 0644 <<'EOF'
- [Prefer one-line commands](feedback_oneline.md)
EOF
put "$MEM/feedback_oneline.md" 0644 <<'EOF'
The user prefers one-line shell commands.
EOF
chmod 0700 "$H/.claude/projects"
# MCP config for Claude Code (user scope) lives in ~/.claude.json, 0600 as Claude Code writes it.
put "$H/.claude.json" 0600 <<'EOF'
{
  "mcpServers": {
    "my-docs": { "command": "uvx", "args": ["my-docs-mcp"] }
  }
}
EOF

# ---------------------------------------------------------------- Kiro
# ~/.kiro/skills is itself a link into the dotfiles tree.
mkdir -p "$H/.kiro"
ln -s ../dotfiles/kiro-skills "$H/.kiro/skills"
put "$H/.kiro/steering/product.md" 0644 <<'EOF'
# Product
Internal developer platform for the payments team.
EOF
put "$H/.kiro/steering/tech.md" 0644 <<'EOF'
# Tech
EKS 1.33, Terraform, ArgoCD.
EOF
# Edited by the user, with front matter, at an APEX workflow name.
put "$H/.kiro/steering/design.md" 0644 <<'EOF'
---
inclusion: always
---
# Design rules (edited by the user)
- Every service has an ADR.
- Diagrams in Mermaid.
EOF
# A marked 1.3.0 Kiro copy the user edited (no install record): see the header.
marked_copy "$H/.kiro/steering/eks-upgrade-check.md" "Upgrade checks (edited by the user)"
put "$H/.kiro/steering/conventions.md" 0644 <<'EOF'
---
inclusion: fileMatch
fileMatchPattern: "**/*.tf"
---
Use terraform fmt.
EOF
put "$H/.kiro/steering/AGENTS.md" 0644 <<'EOF'
# Agent rules
Never push to main.
EOF
put "$H/.kiro/settings/mcp.json" 0600 <<'EOF'
{
  "mcpServers": {
    "my-docs": { "command": "uvx", "args": ["my-docs-mcp"], "disabled": false }
  }
}
EOF
# Knowledge base: Kiro CLI's knowledge feature keeps its indexes under the
# Kiro home (path modelled on it, not taken from Kiro's code); ~/kb is a plain
# notes folder the user points agents at.
put "$H/.kiro/knowledge_bases/team-docs/index.json" 0644 <<'EOF'
{ "name": "team-docs", "files": 2 }
EOF
put "$H/kb/runbooks/database failover.md" 0644 <<'EOF'
# Database failover
Promote the replica.
EOF
put "$H/kb/README.md" 0644 <<'EOF'
Team knowledge base.
EOF

# ---------------------------------------------------------------- other home files
put "$H/.gitconfig" 0644 <<'EOF'
[user]
	name = Fixture User
	email = fixture@example.invalid
EOF
# Another tool's state beside where the installer writes its manifest.
put "$H/.local/state/other-tool/state.json" 0600 <<'EOF'
{ "last_run": "2026-01-01" }
EOF

# ---------------------------------------------------------------- project
put "$P/README.md" 0644 <<'EOF'
# app
EOF
put "$P/src/main.py" 0644 <<'EOF'
print("hello")
EOF
put "$P/AGENTS.md" 0644 <<'EOF'
# Project agent rules
Run the tests before committing.
EOF
put "$P/CLAUDE.md" 0644 <<'EOF'
@AGENTS.md
EOF
put "$P/.mcp.json" 0644 <<'EOF'
{
  "mcpServers": {
    "app-db": { "command": "npx", "args": ["-y", "app-db-mcp"] }
  }
}
EOF
put "$P/.claude/settings.json" 0644 <<'EOF'
{ "permissions": { "allow": ["Bash(make test)"] } }
EOF
skill "$P/.claude/skills/app-deploy" app-deploy "Deploy this app"
skill "$P/.claude/skills/eks-build" eks-build "This project's own EKS build notes, under an APEX skill name"
put "$P/.claude/commands/release.md" 0644 <<'EOF'
Cut a release.
EOF
skill "$P/.kiro/skills/app-runbook" app-runbook "This app's runbook"
ln -s "$H/.apex-skills/skills/eks-recon" "$P/.claude/skills/my-eks-recon"          # user's own link into the clone (absolute)
marked_copy "$P/.kiro/steering/eks-genai.md" "GenAI notes (edited by the user)"
put "$P/.kiro/steering/structure.md" 0644 <<'EOF'
# Structure
src/ holds the code.
EOF
put "$P/.kiro/steering/eks-security.md" 0644 <<'EOF'
---
inclusion: manual
---
# This project's own security checklist (same name as an APEX workflow)
EOF
put "$P/.kiro/settings/mcp.json" 0644 <<'EOF'
{ "mcpServers": {} }
EOF

echo "fixture: home $H, project $P"
