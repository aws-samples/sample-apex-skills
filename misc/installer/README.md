# APEX Skills Installer

NPX-runnable installer for APEX platform engineering skills. Installs skills for Claude Code and Kiro CLI via symlinks from a local clone of the repository.

## Usage

```bash
npx apex-skills
```

Or to update an existing installation:

```bash
npx apex-skills --update
```

## What it does

1. Clones (or updates) the `sample-apex-skills` repo to `~/.apex-skills/`
2. Symlinks each skill directory into your AI tool's skills folder
3. Optionally installs steering workflows and slash commands

## Flags

| Flag | Description |
|------|-------------|
| `--claude-only` | Install for Claude Code only |
| `--kiro-only` | Install for Kiro CLI only |
| `--project` | Install to current project directory instead of global |
| `--no-steering` | Skip steering/commands setup |
| `--update` | Pull latest and re-symlink (non-interactive) |
| `--uninstall` | Remove symlinks (keeps cloned repo) |
| `-h, --help` | Show help |

## Requirements

- Node.js 18+
- git
- macOS or Linux (Windows is not supported; use WSL)

## Installed paths

| Tool | Skills | Steering |
|------|--------|----------|
| Claude Code | `~/.claude/skills/{name}` | `~/.claude/commands/apex/` |
| Kiro CLI | `~/.kiro/skills/{name}` | `~/.kiro/steering/` |

## Uninstall

```bash
npx apex-skills --uninstall
rm -rf ~/.apex-skills  # optional: remove cloned repo
```
