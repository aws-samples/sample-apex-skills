# APEX Skills Installer

Installs APEX skills for Claude Code and Kiro CLI. It clones the repo to `~/.apex-skills/` and links each skill into place, except that the installer on `main` links the maintainer skills only with `--maintainer`. It needs Node.js 18+ and git on macOS or Linux (on Windows, use WSL).

## Usage

```bash
npx apex-skills@1.3.0            # install (a run on an existing clone updates it)
npx apex-skills@1.3.0 --update   # update, with no questions
```

- A fresh install uses the newest `v1.x.y` release tag, not `main`. `--update` stays on the clone's major line.
- With steering (v1 release trees only), Claude Code gets the `/apex:*` commands and Kiro CLI gets the workflows as manual steering files in `~/.kiro/steering/`.
- The commands on this page pin installer 1.3.0 exactly, so they skip later 1.3.x releases. A plain `npx apex-skills` runs the version on npm's `latest` tag, which can differ from that pin (`npm view apex-skills version`).

Before upgrading from installer 1.2.0 or earlier, and before re-running after moving or renaming a home or project directory, copy out edited Kiro steering copies and remove or note links of your own into `~/.apex-skills`: with no install record the installer cannot tell them from its own.

On a default run, the installer on `main` (not yet released; run it from a clone with `node misc/installer/bin/cli.mjs`) removes the maintainer skill links (`skill-creator`, `steering-workflow-creator`, `update-docs`, `apex-new-skill`) that an older install made; run with `--maintainer` to keep them.

## Flags

| Flag | Description |
|------|-------------|
| `--claude-only` | Install for Claude Code only |
| `--kiro-only` | Install for Kiro CLI only |
| `--project` | Install into the current directory instead of `~` |
| `--kiro-hooks` | Also install the opt-in APEX guard hooks for Kiro CLI (see Installed paths). A release with no Kiro hook file gets a warning and no hooks. Not with `--claude-only` or `--uninstall`. `--update` keeps an installed set current |
| `--no-steering` | Skip steering and commands. Steering an earlier run installed stays |
| `--maintainer` | Also link the maintainer skills (`skill-creator`, `steering-workflow-creator`, `update-docs`, `apex-new-skill`), which a default run of the installer on `main` leaves out. The choice is saved for the install: later runs, `--update` included, keep the links. A full `--uninstall` removes them and clears the choice |
| `--update` | Move to the latest release of the clone's major line, or follow the `--branch` branch. Asks no questions |
| `-v, --version <tag>` | Pin to a tag (e.g. `v1.2.0`). A later run without `--version` or `--branch` moves to the latest release |
| `--branch <name>` | Follow a branch (e.g. `main`) instead of the latest release |
| `--uninstall` | Remove installed links and steering copies. Keeps the clone. Honours `--project`, `--claude-only` and `--kiro-only` |
| `-y, --yes` | Take the default answer to every question |
| `-h, --help` | Show help |

`--branch` and `--version` also take the `--branch=<name>` form.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Done |
| 1 | Error, for example git missing or no release tag found |
| 2 | Bad command line, for example an unknown flag, a missing value or a contradictory pair. Nothing changed |
| 3 | Done, but some paths were skipped or could not be written, or the install manifest was not saved. Listed on stderr |
| 130 | Cancelled by Ctrl-C or Ctrl-D at a terminal. At a question nothing changed; later, run it again to finish before `--uninstall` |

## Installed paths

| Tool | Skills | Steering (v1 release trees only) |
|------|--------|----------|
| Claude Code | `~/.claude/skills/{name}` | `~/.claude/commands/apex/`, `~/.claude/apex-steering` |
| Kiro CLI | `~/.kiro/skills/{name}` | `~/.kiro/steering/{workflow}.md` (copies, `inclusion: manual`) |

With `--kiro-hooks`, Kiro CLI also gets `~/.kiro/hooks/apex-hooks.json` and its scripts in `~/.kiro/apex-hooks/`. Each hook ships off: set its `"enabled"` field to `true` in that file to turn it on. A file you changed is kept by later runs and listed (exit code 3).

With `--project`, the same paths go under the current directory and the clone stays in `~/.apex-skills`. Add `--project` to the commands the installer prints (such as `--update`), and don't use it where `.claude` or `.kiro` links into `~`: either way it acts on the global install.

## Uninstall

```bash
npx apex-skills@1.3.0 --uninstall
rm -rf ~/.apex-skills  # optional, once no other install uses it: deletes the clone and your changes in it
```

`--uninstall` removes what the install manifest records (`~/.local/state/apex-skills/manifest.json`, or under `$XDG_STATE_HOME`) and still matches, Kiro hooks included. A path you changed is kept and listed (exit code 3). With no record (an install by 1.2.0 or earlier, or a moved home or project directory), it removes every link into `~/.apex-skills` in the skill, steering and command paths, your own included, and marked Kiro copies named after a workflow (with a v2 clone, which has no steering/, those copies are kept and listed).
