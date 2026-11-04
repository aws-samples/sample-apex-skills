#!/usr/bin/env bash
# Example Claude Code PreToolUse hook: deny Bash commands that use common
# mutating verbs of kubectl, helm, eksctl, terraform and aws, typed as a bare
# command. It misses others (for example `aws s3 cp`, `kubectl debug`,
# `terraform state rm`) and any command behind a path, quotes, `bash -c` or
# `$(...)`. Part of the "Read-only operating profile" recipe
# (misc/website/docs/read-only-operating-profile.md).
#
# This is a best-effort text match, a second layer only. The real guardrail
# is the read-only RBAC (readonly-rbac.yaml) and IAM session policy
# (readonly-session-policy.json): a command this hook misses still cannot
# write under those credentials, but other credentials left on the host (an
# admin kubeconfig, an AWS profile) stay usable by the agent's shell.
#
# Register it in .claude/settings.json:
#   {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
#     {"type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/deny-write-hook.sh"}]}]}}
#
# Contract (https://code.claude.com/docs/en/hooks.md): the hook reads the
# tool call as JSON on stdin (tool_name, tool_input.command, ...). To block,
# it prints hookSpecificOutput.permissionDecision "deny" with a reason and
# exits 0. Needs jq; without jq, or if the hook errors, Claude Code runs the
# command anyway.
set -euo pipefail

input="$(cat)"
tool="$(jq -r '.tool_name // empty' <<<"${input}")"
[[ "${tool}" == "Bash" ]] || exit 0
cmd="$(jq -r '.tool_input.command // empty' <<<"${input}")"

# Reads that the verb patterns below would catch: `kubectl auth can-i` and
# `aws eks update-kubeconfig` (local kubeconfig only), as a single command
# with only flags before the subcommand.
flags='([[:space:]]+-[^[:space:]]*([[:space:]]+[^-[:space:]][^[:space:]]*)?)*[[:space:]]+'
read_only="^[[:space:]]*(kubectl${flags}auth[[:space:]]+can-i|aws${flags}eks[[:space:]]+update-kubeconfig)([[:space:]][^;&|\$\`()]*)?$"
if [[ "${cmd}" =~ ${read_only} ]]; then
  exit 0
fi

# Mutating verbs per CLI. Read verbs (get, describe, list, logs, top,
# aws ... describe-*/list-*/get-*) do not match.
patterns=(
  '(^|[;&|[:space:]])kubectl[[:space:]]+([^;&|]*[[:space:]])?(apply|create|delete|edit|patch|replace|scale|annotate|label|taint|cordon|uncordon|drain|exec|attach|cp|run|expose|autoscale|set|rollout[[:space:]]+(restart|undo|pause|resume))([[:space:]]|$)'
  '(^|[;&|[:space:]])helm[[:space:]]+([^;&|]*[[:space:]])?(install|upgrade|uninstall|delete|rollback)([[:space:]]|$)'
  '(^|[;&|[:space:]])eksctl[[:space:]]+([^;&|]*[[:space:]])?(create|delete|upgrade|scale|set|unset|drain|update)([[:space:]]|$)'
  '(^|[;&|[:space:]])terraform[[:space:]]+([^;&|]*[[:space:]])?(apply|destroy|import|taint|untaint)([[:space:]]|$)'
  '(^|[;&|[:space:]])aws[[:space:]]+([^;&|]*[[:space:]])?(create|delete|update|put|modify|terminate|run|start|stop|reboot|attach|detach|associate|disassociate|register|deregister|tag|untag|enable|disable|reset|replace|restore|invoke)-[a-z0-9-]+'
  '(^|[;&|[:space:]])aws[[:space:]]+([^;&|]*[[:space:]])?s3[[:space:]]+(rm|mv|mb|rb|sync)([[:space:]]|$)'
)

for p in "${patterns[@]}"; do
  if [[ "${cmd}" =~ ${p} ]]; then
    jq -n --arg m "${BASH_REMATCH[0]}" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: ("Read-only profile: \"" + ($m | gsub("^[;&| ]+|[[:space:]]+$"; "")) + "\" changes cluster or account state. Ask the user to run it, or switch to your normal credentials for this task.")
      }
    }'
    exit 0
  fi
done
exit 0
