#!/usr/bin/env bash
# shellcheck disable=SC2088,SC2116,SC2086  # literal ~ in messages; $(echo $x) flattens newlines on purpose
# Install-path test harness for the apex-skills npx installer (misc/installer/bin/cli.mjs).
#
# Every case runs the installer with HOME (and USERPROFILE) pointed at a fresh
# directory under a scratch work dir, so the real ~/.claude, ~/.kiro and
# ~/.apex-skills are never touched. The installer clones from a local fixture
# repository (built from this checkout's skills/ and steering/) through the
# APEX_SKILLS_REPO_URL override, so no network access is needed.
#
# Each installer run (run_cli) gets a scrubbed environment (env -i plus PATH,
# HOME, the fixture URL and hermetic git settings; no XDG_*, CLAUDE_CONFIG_DIR
# or GIT_* from the caller), a network fence (GIT_ALLOW_PROTOCOL=file and every
# proxy variable pointed at a closed port), and a timeout (RUN_TIMEOUT seconds,
# default 60), so a hang fails the case instead of blocking CI. stdout and
# stderr are captured apart ($OUT_STDOUT, $OUT_STDERR) and together ($OUT).
#
# Usage: misc/installer/test/install-paths.sh [--cli <path/to/cli.mjs>] [--pack] [--work <dir>] [--keep]
#   --cli   installer under test (default: misc/installer/bin/cli.mjs in this checkout) (must sit in <dir>/bin/ with <dir>/package.json)
#   --pack  test the npm pack tarball of misc/installer instead of the source tree
#   --work  scratch dir (default: a new mktemp dir); it must not exist or be empty
#   --keep  keep the scratch dir afterwards (default: remove it)
#
# Exit codes the cases expect from the installer: 0 done, 1 error, 2 bad flags,
# 3 done with skipped paths, 130 cancelled at a question (TT1, TT2).
#
# Cases:
#   R1  fresh install creates ~/.claude/apex-steering and every apex-steering import resolves
#   R2  --version pin after an install leaves no dangling skill links
#   R3  --update after a --version pin moves to the latest v1 release tag
#   R3b --update after a fresh --version clone moves to the latest v1 release tag
#   R4  --branch on an existing depth-1 install works, and --update follows that branch
#   R5  a dangling ~/.claude/skills/<name> link into the clone does not abort --update
#   R6  a real directory at ~/.claude/skills/<name> is reported and kept, not a crash
#   L1  the user's own symlinks at every global install path are reported and kept
#   L2  the same for every --project install path
#   K1  Kiro: workflows land as copies with inclusion: manual; user files are kept
#   K2  Kiro: a renamed, customized marked copy, a note quoting the marker and a
#       user file at a workflow name survive install, --update and --uninstall
#   K3  Kiro: install, --update and a --version pin keep an edited recorded copy at a
#       workflow name (exit 3), --uninstall keeps it too; once removed, install writes it again
#   K4  Kiro: the prune keeps an edited recorded copy of a workflow that left the repo
#       (exit 3) and removes the unchanged one; later runs and --uninstall keep it
#   U1  --uninstall removes every installer-made entry (Claude and Kiro), keeps user files
#   U2  --uninstall --project removes the project install and leaves the global one
#   I1  closed stdin (</dev/null): every prompt takes its default, the install finishes
#   I2  empty stdin (an empty pipe): the same
#   I3  piped answers to two prompts are read in order
#   N1  --no-steering, then --update keeps steering off; a run that asks the question adds it
#   N2  answering n is kept by --update; the choice is per install base (--project)
#   NK1 --no-steering, then a --claude-only run keeps steering off; the next --update adds none
#   NK2 --no-steering, then a --kiro-only run keeps steering off; the next --update adds none
#   E1  --update on a ~/.apex-skills that is not a git clone does not claim a detached HEAD
#   E2  a fresh clone of a missing --version names the ref and the ls-remote check
#   W1  native Windows (process.platform win32, simulated) stops with a clear message
#   X1  a run that skipped paths exits 3; after the conflict is moved it exits 0
#   X2  unknown, contradictory or incomplete flags exit 2 and change nothing
#   X3  --version=<tag> (the = form) pins like --version <tag>
#   S1  errors and warnings go to stderr, progress to stdout
#   Y1  -y takes every default without a prompt, even with answers on stdin
#   Y2  --yes finishes while stdin stays open (no EOF)
#   G1  every git call the installer makes has GIT_TERMINAL_PROMPT=0
#   RL1 skill and steering links are relative; they still resolve after HOME moves
#   RL2 absolute (v1.2.0) links and links spelled through ./ or .. become relative links
#   SL1 ~/.claude/skills itself a symlink to another directory
#   SL2 a dangling ~/.claude/skills symlink is reported and kept; the run finishes
#   AC1 every Claude Code skill path is taken: the run says nothing was installed there (exit 3)
#   SL3 self-referencing links at install paths and a link loop are reported and kept
#   M1  the install writes a manifest: entries per area, source URL, ref and commit
#   M2  XDG_STATE_HOME (absolute only) moves the manifest
#   M3  --uninstall after rm -rf ~/.apex-skills removes the recorded links and Kiro copies
#   M4  --uninstall keeps an edited recorded Kiro copy and a user link into the clone (exit 3)
#   M5  a corrupt or wrong-shape manifest is set aside with a warning; built-in rules apply
#   M6  a deleted manifest: --update falls back, prunes dangling clone links, writes a new one
#   N3  the no-steering choice survives rm -rf ~/.apex-skills
#   P1  --project without a global install still warns about the imports, on stderr
#   ENV1 XDG_*, CLAUDE_CONFIG_DIR and GIT_* in the caller's environment do not reach the installer
#   NF1 network fence: an https repo URL is refused at once, nothing is fetched
#   V1  a plain install uses the newest v1 release tag, not main, a pre-release or v2;
#       the manifest records the tag; --update stays; --uninstall leaves the clone
#   V2  release order is numeric (v1.10.9 over v1.10.8 and v1.9.0); that older tree installs cleanly
#   V3  a pre-release or v2 tag only by --version; --update from the v1 pre-release moves to the latest
#       v1 release (stderr note), from v2.0.0 to the latest v2 release
#   V4  an existing clone on main (an older installer's default) moves to the latest v1 release
#       on --update, with a migration note on stderr; unreleased skill links are pruned
#   V5  --branch main (fresh or on a clone) is followed by --update; --version then --update returns to releases
#   V6  no v1 release tag reachable (none, only v2 and pre-release tags, or offline): exit 1, nothing changed
#   V7  the real v1.2.0 tree installs with this installer (skipped when the checkout has no v1.2.0 tag)
#   V8  a clone on v2 stays on v2: --update moves it to the newest v2.x.y, a v2 pre-release pin too;
#       no v1 note
#   V9  a clone on v1 stays on v1 while v2 release tags exist, and install, a v1 --version pin and
#       --update print the one-line v2 note on stderr (exit code unchanged)
#   V10 the v2 note needs a v2.0.0 or later release tag: absent with only v2 pre-release and look-alike
#       tags, present once v2.0.0 is tagged; it names the newest later release in numeric order
#   V11 the major line comes from the tag at the clone's HEAD (the pinned one, when HEAD has several),
#       never from an install base's manifest record
#   V12 a clone on a v2 pre-release with no v2 release tag: --update and a plain run stay on the pin,
#       with a one-line note, exit 0
#   V13 the v2 note on every run that leaves the clone on v1 or a branch (--version, --branch main, --update)
#   V14 the manifest records v2 and ~/.apex-skills is removed: the new clone is on v2 (or the recorded pin)
#   V15 a release tag moved upstream: --update follows it and says so
#   MX1 one clone, a global v1 install and a --project v2 install: --update from either base stays on v2,
#       and no link dangles in either base
#   UN1 --uninstall keeps the record of an edited Kiro copy it kept; the next install keeps the edit
#   HS1 one HOME spelled several ways (a trailing slash, /./, a leading //) is one install base:
#       an edited Kiro copy is kept (exit 3) and --uninstall under another spelling keeps it too
#   SH1 a HOME reached through a symlink is the install base of its real path: an edited Kiro copy
#       is kept from either path and from a --project run in that home; a HOME the run creates too
#   SH2 --uninstall from a HOME reached through a symlink uses the real path's record: an edited
#       Kiro copy and the user's own link are kept, and no other install is named
#   KI1 a Ctrl-C right after a Kiro copy was updated, before the manifest was saved: the next run
#       takes the copy as the installer's (exit 0) and a later release updates it
#   UE1 --uninstall on a base with a record removes nothing in an area the record does not hold;
#       a base with no record still falls back to the 1.2.0 rules
#   PL1 --project links are absolute: they resolve after the project moves deeper
#   GD1 GIT_DIR, GIT_WORK_TREE and GIT_INDEX_FILE from the caller never point git at another repository
#   GH1 a HOME that is a git repository and a ~/.apex-skills that is not a clone: every run stops
#       (exit 1) and HOME's repository, refs and config are untouched
#   DC1 a changed file in the clone: --update names it, keeps it, never advises removing the clone
#   HN1 the steering-off hint names the clone's ref, so following it keeps a --version pin
#   NT1 a run that stops before the clone (no release tag) creates no ~/.claude or ~/.kiro
#   UP1 --update with neither ~/.claude nor ~/.kiro asks nothing, even with stdin open
#   SK1 a release with no skills/: --update stops and the clone, links and manifest stay as they were
#   CR1 a run that stops part way keeps the record of the links it did not reach; --uninstall removes
#       every installer link, a dangling one the record lacks included
#   NC1 --uninstall with no clone and no manifest keeps marked Kiro copies and says why
#   MS1 an install manifest that cannot be saved: exit 3, the warning says what later runs lose, and
#       the summary line names the failed save
#   MR1 an install manifest that cannot be read (chmod 000, a directory in its place): install, --update
#       and --uninstall stop (exit 1); no record, link or edited Kiro copy is lost
#   RO1 a read-only ~/.claude/skills: those links are listed (exit 3); Kiro and steering still install
#   HM1 HOME empty or relative: exit 1, nothing written
#   H1  --help lists every flag and the exit codes on stdout
#   NG1 no git in PATH: exit 1, message on stderr, nothing written
#   NG2 --uninstall with no git in PATH says ~/.apex-skills was not checked, not that it is not a clone
#   MC1 a manifest entry outside the base's .claude and .kiro (a sibling such as .claude-x included) is not trusted
#   US1 a scoped --uninstall (--claude-only, --kiro-only) with both tools installed removes only that tool
#   UL1 a recorded link the user replaced with a symlink of their own is kept by --uninstall (exit 3)
#   UA1 a user alias link into the clone survives --update; only dangling installer links are pruned
#   RU1 an APEX_SKILLS_REPO_URL that starts with - is refused before git sees it
#   OLD1 upgrade from an install made by the real installer at 6103231 (skipped without that commit)
#   TT1 at a terminal (a pty), Ctrl-C or Ctrl-D at the steering question: exit 130, nothing written;
#       a typed answer still installs (skipped without python3)
#   TT2 at a terminal with two questions: Ctrl-C at either exits 130, nothing written, no hang
#   CL1 a commit made on a pinned (detached) clone stops --update, a plain run, --version and --branch
#       (exit 1) and stays; once a branch holds it, --update moves on
#   IW1 a file or dangling symlink at ~/.claude (or <project>/.claude) and an unreadable
#       ~/.claude/skills are listed (exit 3), never a crash; no record is dropped
#   AD1 no advice says to remove ~/.apex-skills (not a clone, unreadable, a failed update with
#       only ignored files); it says to move it aside
#   PN1 a --version pin moves to the latest release on a later plain run; passing --version keeps it
#   NS1 steering installed, then --no-steering, then --update: the line counts the steering entries
#       still recorded as installed (not updated) and nothing is removed
#   BF1 --branch of a local branch that cannot fast-forward: says the clone is now on that branch
#       and how to go back (--version <recorded tag>); a clone already on that local branch does not
#       move and gets no "is now on" line
#   NS2 the only steering entries left after --no-steering and --uninstall are edited Kiro copies:
#       --update names them for removal by hand, not --uninstall; one unedited entry reads in the singular
#   UK1 --uninstall names rm -rf ~/.apex-skills only when no other install base uses the clone
#   UK2 --uninstall --claude-only after a Claude and Kiro install: no rm -rf line while the base
#       still records the Kiro entries (their links still resolve); --uninstall --kiro-only then names it
#   UK3 a partial --uninstall (a read-only ~/.claude/skills, with and without a manifest): no rm -rf
#       line while anything was kept (exit 3); once the rest is removed, the line is back
#   SC1 --claude-only -y and --kiro-only -y with both ~/.claude and ~/.kiro present leave the other
#       tree byte-identical
#   RW1 a read-only directory over recorded entries (a stale skill link, Kiro copies the prune
#       removes): with write access back, --uninstall leaves no installer entry
#   KD1 a Kiro copy whose write fails with a disk error (not a refused write): exit 1 with that
#       error, not listed as a path in the way
#   KR1 a read-only Kiro copy that already holds this release's text, as recorded: not written again, exit 0
#   KM1 recorded Kiro copies that lost their marker (emptied, replaced): listed once, as changed since
#   UB1 --uninstall under a read-only ~/.kiro/steering lists the copies it could not remove once,
#       not also as marked files that are not a recorded copy
#   NS3 steering off with some, not all, leftover entries edited: the line counts the edited ones
#   UR1 --uninstall after a --claude-only install names the Kiro paths the record lacks and leaves them
#   UF1 --uninstall with a plain file at ~/.apex-skills: says it is not a git clone, no rm -rf line
#   T1  harness self-test: an installer that never exits is killed at RUN_TIMEOUT
#   T2  harness self-test: the frontmatter check rejects unclosed, empty and inclusion-less frontmatter
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
CLI="$REPO_ROOT/misc/installer/bin/cli.mjs"
WORK=""
KEEP=0
PACK=0

while [ $# -gt 0 ]; do
  case "$1" in
    --cli) CLI="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"; shift 2 ;;
    --pack) PACK=1; shift ;;
    --work) WORK="$2"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    -h|--help) sed -n '3,/^set -u$/p' "$0" | sed '$d'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$WORK" ]; then
  WORK="$(mktemp -d "${TMPDIR:-/tmp}/apex-install-paths.XXXXXX")"
else
  mkdir -p "$WORK"
  if [ -n "$(ls -A "$WORK")" ]; then echo "work dir $WORK is not empty" >&2; exit 2; fi
fi
WORK="$(cd "$WORK" && pwd -P)"
cleanup() { if [ "$KEEP" -eq 0 ]; then rm -rf "$WORK"; fi; }
trap cleanup EXIT

# --pack: run every case against the published shape (npm pack of
# misc/installer, unpacked), so a file missing from package.json "files" fails.
if [ "$PACK" -eq 1 ]; then
  mkdir -p "$WORK/pack"
  tgz="$(cd "$REPO_ROOT/misc/installer" && npm pack --silent --pack-destination "$WORK/pack" 2>/dev/null | tail -n 1)"
  if [ -z "$tgz" ] || [ ! -f "$WORK/pack/$tgz" ]; then echo "npm pack failed" >&2; exit 2; fi
  tar -xzf "$WORK/pack/$tgz" -C "$WORK/pack"
  for f in package/package.json package/bin/cli.mjs; do
    [ -f "$WORK/pack/$f" ] || { echo "the tarball $tgz lacks $f" >&2; exit 2; }
  done
  CLI="$WORK/pack/package/bin/cli.mjs"
  echo "testing the packed tarball $tgz"
fi

# Preflight: an installer that cannot start (for example a loose cli.mjs with no
# ../package.json) must stop the run, not pass as a control that fails every case.
# One that hangs is killed after 60 s (perl's alarm, as in run_cli) and stops it too.
mkdir -p "$WORK/preflight-home"
HOME="$WORK/preflight-home" USERPROFILE="$WORK/preflight-home" perl -e 'alarm shift @ARGV; exec @ARGV or exit 127' 60 node "$CLI" --help >/dev/null 2>&1 || { echo "--cli $CLI does not start within 60 s (it needs ../package.json beside bin/)" >&2; exit 2; }
# Preflight: case SC1's tree check lists the tree with find -printf. BSD find
# (macOS) rejects -printf, and the listing would drop out of the hash without a
# sign, leaving a content-only check, so the run stops instead.
find "$WORK" -maxdepth 0 -printf x >/dev/null 2>&1 || { echo "find does not support -printf: case SC1's tree check needs GNU find (findutils)" >&2; exit 2; }

# Hermetic git: no system or global config from the real HOME.
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_TERMINAL_PROMPT=0
GITC=(git -c user.name=apex-test -c user.email=apex-test@example.invalid -c init.defaultBranch=main -c commit.gpgsign=false -c tag.gpgsign=false)

# Fixture tags. A plain install and --update of a v1 clone must pick LATEST_TAG:
# the newest v1.x.y release in numeric order. RC_TAG (a pre-release on main),
# the v2 line and the look-alike tags on the v2 commit must never be picked for
# v1; a clone on V2_TAG updates to the newest v2 release (v2.5.0, the same commit).
FIXTURE_TAG=v1.1.0          # an older release: TAG_DROPPED_SKILLS missing
MID_TAG=v1.2.0              # a v1.2.0-like release: MID_DROPPED_SKILL missing
LATEST_TAG=v1.3.0           # the newest v1 release (annotated): every skill
RC_TAG=v1.4.0-rc.0          # a pre-release on main, after LATEST_TAG
V2_TAG=v2.0.0               # the next major line: no steering/, a v2-only skill
V2_LOOKALIKES="v2.5.0 v1.50 v1.60.0x v1.70.0.1 release-v1.80.0 v0.9.0"
FIXTURE_BRANCH=feat/fixture-branch
TAG_DROPPED_SKILLS="eks-recon eks-genai"
MID_DROPPED_SKILL=eks-genai
BRANCH_SKILL=zz-fixture-branch-only
MAIN_SKILL=zz-main-unreleased
V2_SKILL=zz-v2-only

# ---------------------------------------------------------------- fixture repo
ORIGIN="$WORK/origin"
# skills/ and steering/ come from one commit: HEAD, or, once steering/ is gone
# from HEAD (the v2 layout), the parent of the last commit that touched it (the
# last v1 tree), so this v1 installer keeps a tree it can install.
FIXTURE_SRC=HEAD
if ! git -C "$REPO_ROOT" cat-file -e HEAD:steering 2>/dev/null; then
  last="$(git -C "$REPO_ROOT" rev-list -1 HEAD -- steering)"
  [ -n "$last" ] || { echo "no commit in this checkout has steering/; fetch the full history" >&2; exit 2; }
  FIXTURE_SRC="$last^"
  echo "HEAD has no steering/: the fixture tree is $FIXTURE_SRC ($(git -C "$REPO_ROOT" rev-parse --short "$FIXTURE_SRC"))"
fi
add_fixture_skill() { # <repo> <name> <note>
  mkdir -p "$1/skills/$2"
  printf -- '---\nname: %s\ndescription: fixture skill %s\n---\n' "$2" "$3" > "$1/skills/$2/SKILL.md"
}
build_fixture() {
  mkdir -p "$ORIGIN"
  local paths
  paths="$(git -C "$REPO_ROOT" ls-tree --name-only "$FIXTURE_SRC" skills steering | tr '\n' ' ')"
  [ "$paths" = "skills steering " ] || { echo "the fixture tree $FIXTURE_SRC lacks skills/ or steering/ (has: $paths)" >&2; exit 2; }
  (set -o pipefail; git -C "$REPO_ROOT" archive "$FIXTURE_SRC" skills steering | tar -x -C "$ORIGIN") || { echo "git archive of $FIXTURE_SRC failed" >&2; exit 2; }
  "${GITC[@]}" -C "$ORIGIN" init -q
  # Older release: two skills missing, like v1.1.0 against main.
  local s
  for s in $TAG_DROPPED_SKILLS; do mv "$ORIGIN/skills/$s" "$WORK/held-$s"; done
  "${GITC[@]}" -C "$ORIGIN" add -A skills steering
  "${GITC[@]}" -C "$ORIGIN" commit -q -m "fixture release $FIXTURE_TAG"
  "${GITC[@]}" -C "$ORIGIN" tag "$FIXTURE_TAG"
  for s in $TAG_DROPPED_SKILLS; do [ "$s" = "$MID_DROPPED_SKILL" ] || mv "$WORK/held-$s" "$ORIGIN/skills/$s"; done
  "${GITC[@]}" -C "$ORIGIN" add -A skills
  "${GITC[@]}" -C "$ORIGIN" commit -q -m "fixture release $MID_TAG"
  "${GITC[@]}" -C "$ORIGIN" tag "$MID_TAG"
  mv "$WORK/held-$MID_DROPPED_SKILL" "$ORIGIN/skills/$MID_DROPPED_SKILL"
  "${GITC[@]}" -C "$ORIGIN" add -A skills
  "${GITC[@]}" -C "$ORIGIN" commit -q -m "fixture release $LATEST_TAG"
  "${GITC[@]}" -C "$ORIGIN" tag -a -m "fixture $LATEST_TAG" "$LATEST_TAG"
  # The v2 line: steering/ deleted (as v2 does) and a v2-only skill.
  "${GITC[@]}" -C "$ORIGIN" checkout -q -b fixture-v2
  "${GITC[@]}" -C "$ORIGIN" rm -q -r steering
  add_fixture_skill "$ORIGIN" "$V2_SKILL" "present only on $V2_TAG"
  "${GITC[@]}" -C "$ORIGIN" add -A skills
  "${GITC[@]}" -C "$ORIGIN" commit -q -m "fixture $V2_TAG"
  "${GITC[@]}" -C "$ORIGIN" tag "$V2_TAG"
  for s in $V2_LOOKALIKES; do "${GITC[@]}" -C "$ORIGIN" tag "$s"; done
  "${GITC[@]}" -C "$ORIGIN" checkout -q main
  # main after the release: an unreleased skill and a pre-release tag.
  add_fixture_skill "$ORIGIN" "$MAIN_SKILL" "present only on main after $LATEST_TAG"
  "${GITC[@]}" -C "$ORIGIN" add -A skills
  "${GITC[@]}" -C "$ORIGIN" commit -q -m "fixture main"
  "${GITC[@]}" -C "$ORIGIN" tag "$RC_TAG"
  "${GITC[@]}" -C "$ORIGIN" checkout -q -b "$FIXTURE_BRANCH"
  add_fixture_skill "$ORIGIN" "$BRANCH_SKILL" "present only on $FIXTURE_BRANCH"
  "${GITC[@]}" -C "$ORIGIN" add -A skills
  "${GITC[@]}" -C "$ORIGIN" commit -q -m "fixture branch"
  "${GITC[@]}" -C "$ORIGIN" checkout -q main
}
build_fixture
export APEX_SKILLS_REPO_URL="file://$ORIGIN"

count_skill_dirs() { # <git ref>
  git -C "$ORIGIN" ls-tree -d --name-only "$1:skills" | /usr/bin/grep -v '^\.' | wc -l | tr -d ' '
}
commit_of() { git -C "$ORIGIN" rev-parse "$1^{commit}"; }
MAIN_COUNT="$(count_skill_dirs main)"
LATEST_COUNT="$(count_skill_dirs "$LATEST_TAG")"
MID_COUNT="$(count_skill_dirs "$MID_TAG")"
TAG_COUNT="$(count_skill_dirs "$FIXTURE_TAG")"
WF_COUNT="$(git -C "$ORIGIN" ls-tree --name-only "$LATEST_TAG:steering/workflows" | /usr/bin/grep -c '\.md$')"
# Sample skills: the first two folders under skills/ that hold a SKILL.md (on this branch skills/apex holds only runbooks/; #283 adds its SKILL.md).
SKILLS_WITH_MD="$(git -C "$ORIGIN" ls-tree -d --name-only "$LATEST_TAG:skills" | /usr/bin/grep -v '^\.' | while read -r d; do if git -C "$ORIGIN" cat-file -e "$LATEST_TAG:skills/$d/SKILL.md" 2>/dev/null; then echo "$d"; fi; done)"
SKILL_A="$(printf '%s\n' "$SKILLS_WITH_MD" | sed -n 1p)"
SKILL_B="$(printf '%s\n' "$SKILLS_WITH_MD" | sed -n 2p)"

# ---------------------------------------------------------------- helpers
PASS=0
FAIL=0
FAILED_CASES=""
CASE=""
CASE_ERRS=""
H=""      # current case HOME
OUT=""    # output file of the last installer run
RC=0      # exit code of the last installer run

new_case() { # <id> <title>
  CASE="$1"; CASE_ERRS=""
  H="$WORK/$1/home"
  mkdir -p "$H"
  echo "=== $1: $2"
}

RUN_SECS=0  # wall time of the last installer run

# A pseudo-terminal driver for run_pty: the installer gets a terminal as
# stdin, stdout and stderr, as a user at a shell does. The closed-stdin and
# piped cases (I1 to I3, Y1, Y2) never reach the terminal code path.
PTY_PYTHON="$(command -v python3 || true)"
PTY_DRIVER="$WORK/pty-driver.py"
cat > "$PTY_DRIVER" <<'EOF'
# usage: python3 pty-driver.py <timeout s> <steps json> -- <command...>
# steps: [[regex, keys], ...]: wait until regex matches the output printed
# since the last step (ANSI codes removed), then type keys. Prints the output;
# exits with the command's exit code, or 142 when it did not exit in time.
import json, os, pty, re, select, signal, sys, time
args = sys.argv[1:]
limit, steps, cmd = float(args[0]), json.loads(args[1]), args[args.index('--') + 1:]
pid, fd = pty.fork()
if pid == 0:
    os.execvp(cmd[0], cmd)
ansi = re.compile(rb'\x1b\[[0-9;?]*[A-Za-z]')
buf, mark, sent, start, status = b'', 0, 0, time.time(), None
def drain(wait):
    global buf
    while True:
        r, _, _ = select.select([fd], [], [], wait)
        if not r:
            return
        try:
            data = os.read(fd, 4096)
        except OSError:
            return
        if not data:
            return
        buf += data
        wait = 0
while status is None:
    if time.time() - start > limit:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        break
    drain(0.1)
    if sent < len(steps) and re.search(steps[sent][0], ansi.sub(b'', buf[mark:]).decode('utf8', 'replace')):
        time.sleep(0.3)
        mark = len(buf)
        os.write(fd, steps[sent][1].encode())
        sent += 1
    done, st = os.waitpid(pid, os.WNOHANG)
    if done:
        status = st
        drain(0.2)
sys.stdout.write(ansi.sub(b'', buf).decode('utf8', 'replace').replace('\r', ''))
sys.stdout.write('\n[pty: %d of %d steps sent%s]\n' % (sent, len(steps), '' if status is not None else ', no exit within %ds' % limit))
if status is None:
    sys.exit(142)
sys.exit(os.WEXITSTATUS(status) if os.WIFEXITED(status) else 128 + os.WTERMSIG(status))
EOF

# Run the installer once on a pseudo-terminal, with run_cli's environment and
# network fence. <steps> is the driver's JSON list of [regex, keys]; in keys,
# \u0003 is Ctrl-C and \u0004 is Ctrl-D. $OUT holds stdout and stderr together
# (one terminal). Knobs: RUN_CWD, RUN_TIMEOUT (default 60).
run_pty() { # <steps> [args...]
  local steps="$1" limit="${RUN_TIMEOUT:-60}" fence=http://127.0.0.1:9
  shift
  OUT="$WORK/$CASE/pty-$(date +%s%N 2>/dev/null || date +%s)-$RANDOM.log"
  (cd "${RUN_CWD:-$H}" && "$PTY_PYTHON" -I "$PTY_DRIVER" "$limit" "$steps" -- \
    env -i "PATH=$PATH" "HOME=$H" "USERPROFILE=$H" LANG=C "TMPDIR=${TMPDIR:-/tmp}" \
    "APEX_SKILLS_REPO_URL=$APEX_SKILLS_REPO_URL" GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_ALLOW_PROTOCOL=file \
    "HTTPS_PROXY=$fence" "HTTP_PROXY=$fence" "ALL_PROXY=$fence" "https_proxy=$fence" "http_proxy=$fence" "all_proxy=$fence" \
    node "${RUN_CLI:-$CLI}" "$@") > "$OUT" 2>&1
  RC=$?
  if [ "$RC" -eq 142 ]; then err "the installer did not exit within ${limit}s on a terminal (log: $OUT)"; fi
}

# Run the installer once. Knobs (set as a prefix on the call):
#   STDIN_TEXT=<text>  pipe this text to stdin     STDIN_EMPTY=1  an empty pipe
#   STDIN_HOLD=1       stdin is a FIFO whose writer never closes it (no EOF)
#   (default stdin is /dev/null)
#   RUN_CWD=<dir>      working directory (default: the case HOME)
#   RUN_ENV="K=V ..."  extra environment, applied last (overrides the defaults)
#   RUN_PATH=<path>    PATH for the installer (default: the harness PATH)
#   RUN_TIMEOUT=<s>    kill the run after this many seconds (default 60)
#   EXPECT_TIMEOUT=1   a timeout is the expected result (harness self-test)
#   PRELOAD=<file>     node --require this file first
#   RUN_CLI=<file>     run this cli.mjs instead of the one under test (an older installer)
run_cli() { # [args...]
  OUT="$WORK/$CASE/out-$(date +%s%N 2>/dev/null || date +%s)-$RANDOM.log"
  OUT_STDOUT="$OUT.stdout"
  OUT_STDERR="$OUT.stderr"
  local preload=() extra=() holder="" fifo="" t0 limit="${RUN_TIMEOUT:-60}"
  if [ -n "${PRELOAD:-}" ]; then preload=(--require "$PRELOAD"); fi
  if [ -n "${RUN_ENV:-}" ]; then read -r -a extra <<< "$RUN_ENV"; fi
  local fence=http://127.0.0.1:9
  local cmd=(perl -e 'alarm shift @ARGV; exec @ARGV or exit 127' "$limit"
    env -i "PATH=${RUN_PATH:-$PATH}" "HOME=$H" "USERPROFILE=$H" NO_COLOR=1 LANG=C "TMPDIR=${TMPDIR:-/tmp}"
    "APEX_SKILLS_REPO_URL=$APEX_SKILLS_REPO_URL" GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_ALLOW_PROTOCOL=file
    "HTTPS_PROXY=$fence" "HTTP_PROXY=$fence" "ALL_PROXY=$fence" "https_proxy=$fence" "http_proxy=$fence" "all_proxy=$fence"
    ${extra[@]+"${extra[@]}"}
    node ${preload[@]+"${preload[@]}"} "${RUN_CLI:-$CLI}" "$@")
  t0="$(date +%s)"
  if [ -n "${STDIN_EMPTY:-}" ]; then
    printf '' | (cd "${RUN_CWD:-$H}" && "${cmd[@]}") > "$OUT_STDOUT" 2> "$OUT_STDERR"
  elif [ -n "${STDIN_TEXT:-}" ]; then
    printf '%s' "$STDIN_TEXT" | (cd "${RUN_CWD:-$H}" && "${cmd[@]}") > "$OUT_STDOUT" 2> "$OUT_STDERR"
  elif [ -n "${STDIN_HOLD:-}" ]; then
    fifo="$OUT.fifo"
    mkfifo "$fifo"
    sleep 3600 > "$fifo" &
    holder=$!
    (cd "${RUN_CWD:-$H}" && "${cmd[@]}") < "$fifo" > "$OUT_STDOUT" 2> "$OUT_STDERR"
  else
    (cd "${RUN_CWD:-$H}" && "${cmd[@]}") < /dev/null > "$OUT_STDOUT" 2> "$OUT_STDERR"
  fi
  RC=$?
  RUN_SECS=$(( $(date +%s) - t0 ))
  if [ -n "$holder" ]; then kill "$holder" 2>/dev/null; wait "$holder" 2>/dev/null; rm -f "$fifo"; fi
  # strip ANSI color codes for readable logs and greps
  local f
  for f in "$OUT_STDOUT" "$OUT_STDERR"; do sed $'s/\x1b\\[[0-9;]*m//g' "$f" > "$f.txt" && mv "$f.txt" "$f"; done
  { echo "\$ HOME=$H cwd=${RUN_CWD:-$H} node ${preload[*]-} cli.mjs $*"; cat "$OUT_STDOUT"; echo "--- stderr"; cat "$OUT_STDERR"; echo "[exit $RC, ${RUN_SECS}s]"; } > "$OUT"
  if [ "$RC" -eq 142 ] && [ -z "${EXPECT_TIMEOUT:-}" ]; then err "the installer did not finish within ${limit}s and was killed (log: $OUT)"; fi
}

err() { CASE_ERRS="${CASE_ERRS}    - $*"$'\n'; }
expect_rc() { [ "$RC" -eq "$1" ] || err "expected exit $1, got $RC (log: $OUT)"; }
expect_out() { /usr/bin/grep -q -- "$1" "$OUT" || err "output lacks '$1'"; }
expect_no_out() { if /usr/bin/grep -q -- "$1" "$OUT"; then err "output contains '$1'"; fi; }
expect_stdout() { /usr/bin/grep -q -- "$1" "$OUT_STDOUT" || err "stdout lacks '$1'"; }
expect_stderr() { /usr/bin/grep -q -- "$1" "$OUT_STDERR" || err "stderr lacks '$1'"; }
expect_no_stdout() { if /usr/bin/grep -q -- "$1" "$OUT_STDOUT"; then err "stdout contains '$1'"; fi; }
expect_no_stderr() { if /usr/bin/grep -q -- "$1" "$OUT_STDERR"; then err "stderr contains '$1'"; fi; }
expect_link() { # <link> <target>: link still exists and still points at target
  if [ ! -L "$1" ]; then err "$1 is no longer a symlink"; elif [ "$(readlink "$1")" != "$2" ]; then err "$1 now points at $(readlink "$1"), not $2"; fi
}

# The trailing slash makes find enter a directory that is itself a symlink.
dangling_links() { # <dir>
  [ -d "$1" ] || return 0
  find "$1/" -mindepth 1 -maxdepth 1 -type l ! -exec test -e {} \; -print
}
count_resolving_links() { # <dir>
  [ -d "$1" ] || { echo 0; return; }
  find "$1/" -mindepth 1 -maxdepth 1 -type l -exec test -e {} \; -print | wc -l | tr -d ' '
}

# Link facts, resolved the way the OS does (relative links from the real
# directory that holds them), so relative and absolute links both count.
LINKINFO="$WORK/linkinfo.cjs"
cat > "$LINKINFO" <<'EOF'
// usage: node linkinfo.cjs <count|absolute> <dir> <root>
// count: symlinks in <dir> whose target is <root> or under it
// absolute: the same, but only those whose link text is an absolute path
const fs = require('fs');
const p = require('path');
const [mode, dir, root] = process.argv.slice(2);
const real = (x) => { try { return fs.realpathSync(x); } catch { return p.resolve(x); } };
let n = 0;
if (fs.existsSync(dir)) {
  const roots = [p.resolve(root), real(root)];
  const rd = real(dir);
  for (const e of fs.readdirSync(dir)) {
    const f = p.join(dir, e);
    let st;
    try { st = fs.lstatSync(f); } catch { continue; }
    if (!st.isSymbolicLink()) continue;
    const text = fs.readlinkSync(f);
    const t = p.resolve(rd, text);
    if (!roots.some((r) => t === r || t.startsWith(r + p.sep))) continue;
    if (mode === 'count' || (mode === 'absolute' && p.isAbsolute(text))) n++;
  }
}
console.log(n);
EOF
links_into_install() { node "$LINKINFO" count "$1" "$H/.apex-skills"; }
absolute_links_into_install() { node "$LINKINFO" absolute "$1" "$H/.apex-skills"; }

# Query the manifest: mfq <file> <js expression over m (the manifest) and b (the base)> [base]
mfq() {
  node -e 'const fs = require("fs"); let m; try { m = JSON.parse(fs.readFileSync(process.argv[1], "utf8")); } catch (e) { console.log("UNREADABLE"); process.exit(0); } const b = process.argv[3]; console.log(String(new Function("m", "b", "return (" + process.argv[2] + ");")(m, b)));' "$1" "$2" "${3:-$H}"
}
manifest_of() { echo "$H/.local/state/apex-skills/manifest.json"; }
# Set an install base's recorded source.ref: mf_set_ref <ref> [base]
mf_set_ref() {
  node -e 'const fs = require("fs"); const [f, ref, b] = process.argv.slice(1); const m = JSON.parse(fs.readFileSync(f, "utf8")); m.bases[b].source.ref = ref; fs.writeFileSync(f, JSON.stringify(m, null, 2));' "$(manifest_of)" "$1" "${2:-$H}"
}
# The file opens with frontmatter (--- on line 1 to a closing ---) that holds
# inclusion: manual. Unclosed, empty and inclusion-less frontmatter fail.
fm_manual() {
  awk 'NR==1 && $0!="---" {exit 1} NR>1 && $0=="---" {closed=1; exit found ? 0 : 1} /^inclusion: manual$/ {found=1} END {if (!closed) exit 1}' "$1"
}
install_head() { git -C "$H/.apex-skills" rev-parse HEAD 2>/dev/null; }
install_branch() { git -C "$H/.apex-skills" symbolic-ref -q --short HEAD 2>/dev/null; }

# Every '~/.claude/apex-steering/<path>' reference in the installed Claude
# commands and SKILL.md files must exist inside this HOME.
check_imports() { # <claude dir>
  local dir="$1" files=() f ref rel n=0 bad=0
  for f in "$dir"/commands/apex/*.md "$dir"/skills/*/SKILL.md; do [ -f "$f" ] && files+=("$f"); done
  if [ "${#files[@]}" -eq 0 ]; then err "no installed command or SKILL.md files found under $dir"; return; fi
  # one entry per (file, reference) pair, so a path cited by two files counts twice
  while IFS= read -r ref; do
    [ -n "$ref" ] || continue
    rel="${ref#*~/.claude/apex-steering/}"
    n=$((n + 1))
    if [ ! -e "$dir/apex-steering/$rel" ]; then bad=$((bad + 1)); err "unresolved import $ref (no $dir/apex-steering/$rel)"; fi
  done < <(/usr/bin/grep -H -o -E '~/\.claude/apex-steering/[A-Za-z0-9._/-]+' "${files[@]}" | sort -u)
  echo "    imports checked: $n, unresolved: $bad"
  [ "$n" -ge 5 ] || err "expected at least 5 apex-steering references (4 shims plus SKILL.md files), found $n"
}

finish_case() {
  if [ -z "$CASE_ERRS" ]; then
    PASS=$((PASS + 1)); echo "CASE $CASE PASS"
  else
    FAIL=$((FAIL + 1)); FAILED_CASES="$FAILED_CASES $CASE"
    echo "CASE $CASE FAIL"
    printf '%s' "$CASE_ERRS"
    if [ -n "$OUT" ] && [ -f "$OUT" ]; then echo "    output tail ($OUT):"; tail -n 12 "$OUT" | sed 's/^/      | /'; fi
  fi
  OUT=""
}

# ---------------------------------------------------------------- cases
new_case R1 "fresh --claude-only install creates ~/.claude/apex-steering; imports resolve"
mkdir -p "$H/.claude"
run_cli --claude-only
expect_rc 0
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT resolving skill links, got $(count_resolving_links "$H/.claude/skills")"
[ -e "$H/.claude/commands/apex/eks.md" ] || err "~/.claude/commands/apex/eks.md does not resolve"
[ -e "$H/.claude/apex-steering/workflows/eks-operation-review.md" ] || err "~/.claude/apex-steering/workflows/eks-operation-review.md does not resolve"
check_imports "$H/.claude"
finish_case

new_case R2 "--version $FIXTURE_TAG after an install leaves no dangling skill links"
mkdir -p "$H/.claude"
run_cli --claude-only
run_cli --version "$FIXTURE_TAG" --claude-only
expect_rc 0
expect_stdout "Removed $(echo $TAG_DROPPED_SKILLS | wc -w | tr -d ' ') links to skills that are not in this version"
d="$(dangling_links "$H/.claude/skills")"; [ -z "$d" ] || err "dangling links: $(echo $d)"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$TAG_COUNT" ] || err "expected $TAG_COUNT skill links, got $(count_resolving_links "$H/.claude/skills")"
[ "$(install_head)" = "$(git -C "$ORIGIN" rev-parse "$FIXTURE_TAG^{commit}")" ] || err "install is not at $FIXTURE_TAG"
finish_case

new_case R3 "--update after a --version pin moves to the latest v1 release, $LATEST_TAG"
mkdir -p "$H/.claude"
run_cli --claude-only
run_cli --version "$FIXTURE_TAG" --claude-only
run_cli --update --claude-only
expect_rc 0
expect_stdout "Updated to the latest v1 release, $LATEST_TAG"
expect_no_stderr "not a v1 release"
[ -z "$(install_branch)" ] || err "install is on branch '$(install_branch)', not detached at $LATEST_TAG"
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "install HEAD is not $LATEST_TAG"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT skill links, got $(count_resolving_links "$H/.claude/skills")"
d="$(dangling_links "$H/.claude/skills")"; [ -z "$d" ] || err "dangling links: $(echo $d)"
finish_case

new_case R3b "fresh --version $FIXTURE_TAG clone, then --update moves to $LATEST_TAG"
mkdir -p "$H/.claude"
run_cli --version "$FIXTURE_TAG" --claude-only
run_cli --update --claude-only
expect_rc 0
[ -z "$(install_branch)" ] || err "install is on branch '$(install_branch)', not detached at $LATEST_TAG"
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "install HEAD is not $LATEST_TAG"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT skill links, got $(count_resolving_links "$H/.claude/skills")"
finish_case

new_case R5 "dangling ~/.claude/skills/eks-recon link, then --update"
mkdir -p "$H/.claude"
run_cli --claude-only
rm -f "$H/.claude/skills/eks-recon"
ln -s "$H/.apex-skills/skills/eks-recon-was-renamed" "$H/.claude/skills/eks-recon"
run_cli --update --claude-only
expect_rc 0
expect_no_out "EEXIST"
[ -e "$H/.claude/skills/eks-recon/SKILL.md" ] || err "eks-recon link was not repaired"
finish_case

new_case R6 "real directory at ~/.claude/skills/eks-recon, then --update"
mkdir -p "$H/.claude"
run_cli --claude-only
rm -f "$H/.claude/skills/eks-recon"
mkdir -p "$H/.claude/skills/eks-recon"
echo "user-owned" > "$H/.claude/skills/eks-recon/USER_FILE"
run_cli --update --claude-only
expect_rc 3
expect_no_out "EISDIR"
expect_out "Skipped 1 path"
expect_out "skills/eks-recon$"
[ -f "$H/.claude/skills/eks-recon/USER_FILE" ] || err "user directory eks-recon was removed or changed"
[ "$(count_resolving_links "$H/.claude/skills")" -eq $((LATEST_COUNT - 1)) ] || err "expected $((LATEST_COUNT - 1)) other skill links, got $(count_resolving_links "$H/.claude/skills")"
finish_case

new_case R4 "--branch $FIXTURE_BRANCH on an existing depth-1 install, then --update follows it"
mkdir -p "$H/.claude"
run_cli --claude-only
run_cli --branch "$FIXTURE_BRANCH" --claude-only
expect_rc 0
[ "$(install_head)" = "$(git -C "$ORIGIN" rev-parse "$FIXTURE_BRANCH")" ] || err "install HEAD is not $FIXTURE_BRANCH"
[ -e "$H/.claude/skills/$BRANCH_SKILL/SKILL.md" ] || err "branch-only skill $BRANCH_SKILL is not linked"
if [ -z "$CASE_ERRS" ]; then
  # advance the branch upstream; --update must fast-forward the branch install
  "${GITC[@]}" -C "$ORIGIN" checkout -q "$FIXTURE_BRANCH"
  echo "advanced" >> "$ORIGIN/skills/$BRANCH_SKILL/SKILL.md"
  "${GITC[@]}" -C "$ORIGIN" commit -q -am "fixture branch advance"
  "${GITC[@]}" -C "$ORIGIN" checkout -q main
  run_cli --update --claude-only
  expect_rc 0
  [ "$(install_head)" = "$(git -C "$ORIGIN" rev-parse "$FIXTURE_BRANCH")" ] || err "--update did not follow $FIXTURE_BRANCH"
fi
finish_case

new_case L1 "the user's own symlinks at every global install path are reported and kept"
mkdir -p "$H/.claude/skills" "$H/.claude/commands" "$H/.kiro/skills" "$H/.kiro/steering" "$H/mine/skill" "$H/mine/commands" "$H/mine/steering"
echo "my skill" > "$H/mine/skill/SKILL.md"
echo "my workflow" > "$H/mine/new-skill.md"
ln -s "$H/mine/skill" "$H/.claude/skills/eks-recon"
ln -s "$H/mine/missing-skill" "$H/.claude/skills/eks-genai"   # the user's own dangling link
ln -s "$H/mine/commands" "$H/.claude/commands/apex"
ln -s "$H/mine/steering" "$H/.claude/apex-steering"
ln -s "$H/mine/skill" "$H/.kiro/skills/eks-recon"
ln -s "$H/mine/new-skill.md" "$H/.kiro/steering/new-skill.md"
for run in install update; do
  if [ "$run" = install ]; then STDIN_TEXT=$'y\n' run_cli; else run_cli --update; fi
  expect_rc 3
  expect_out "Skipped 6 path"
  for p in .claude/skills/eks-recon .claude/skills/eks-genai .claude/commands/apex .claude/apex-steering .kiro/skills/eks-recon .kiro/steering/new-skill.md; do
    expect_out "$H/$p$"
  done
  expect_link "$H/.claude/skills/eks-recon" "$H/mine/skill"
  expect_link "$H/.claude/skills/eks-genai" "$H/mine/missing-skill"
  expect_link "$H/.claude/commands/apex" "$H/mine/commands"
  expect_link "$H/.claude/apex-steering" "$H/mine/steering"
  expect_link "$H/.kiro/skills/eks-recon" "$H/mine/skill"
  expect_link "$H/.kiro/steering/new-skill.md" "$H/mine/new-skill.md"
done
[ "$(cat "$H/mine/new-skill.md")" = "my workflow" ] || err "the user's linked workflow file was changed"
[ "$(links_into_install "$H/.claude/skills")" -eq $((LATEST_COUNT - 2)) ] || err "expected $((LATEST_COUNT - 2)) installer skill links, got $(links_into_install "$H/.claude/skills")"
finish_case

new_case L2 "the user's own symlinks at every --project install path are reported and kept"
P="$H/proj"
mkdir -p "$H/.claude" "$H/.kiro" "$P/.claude/skills" "$P/.claude/commands" "$P/.kiro/skills" "$P/.kiro/steering" "$H/mine/skill" "$H/mine/commands" "$H/mine/steering"
echo "my workflow" > "$H/mine/new-skill.md"
ln -s "$H/mine/skill" "$P/.claude/skills/eks-recon"
ln -s "$H/mine/commands" "$P/.claude/commands/apex"
ln -s "$H/mine/steering" "$P/.claude/apex-steering"
ln -s "$H/mine/skill" "$P/.kiro/skills/eks-recon"
ln -s "$H/mine/new-skill.md" "$P/.kiro/steering/new-skill.md"
STDIN_TEXT=$'y\n' RUN_CWD="$P" run_cli --project
expect_rc 3
expect_out "Skipped 5 path"
expect_link "$P/.claude/skills/eks-recon" "$H/mine/skill"
expect_link "$P/.claude/commands/apex" "$H/mine/commands"
expect_link "$P/.claude/apex-steering" "$H/mine/steering"
expect_link "$P/.kiro/skills/eks-recon" "$H/mine/skill"
expect_link "$P/.kiro/steering/new-skill.md" "$H/mine/new-skill.md"
[ "$(links_into_install "$P/.claude/skills")" -eq $((LATEST_COUNT - 1)) ] || err "expected $((LATEST_COUNT - 1)) installer project skill links, got $(links_into_install "$P/.claude/skills")"
finish_case

new_case K1 "Kiro: workflows installed as copies with inclusion: manual"
mkdir -p "$H/.kiro/steering"
echo "my own steering" > "$H/.kiro/steering/mine.md"
# a v1.2.0-style symlink for one workflow must be replaced by a copy
ln -s "$H/.apex-skills/steering/workflows/new-skill.md" "$H/.kiro/steering/new-skill.md"
run_cli --kiro-only
expect_rc 0
expect_no_out "use /apex commands"
expect_out "Kiro CLI V1/V2 support it only partially"
nwf=0
for src in "$ORIGIN"/steering/workflows/*.md; do
  f="$H/.kiro/steering/$(basename "$src")"
  nwf=$((nwf + 1))
  if [ -L "$f" ] || [ ! -f "$f" ]; then err "$(basename "$f") is not a regular file copy"; continue; fi
  fm_manual "$f" || err "$(basename "$f") frontmatter lacks inclusion: manual"
done
[ "$nwf" -ge 1 ] || err "fixture has no workflows"
[ "$(cat "$H/.kiro/steering/mine.md")" = "my own steering" ] || err "user steering file was changed"
[ "$(count_resolving_links "$H/.kiro/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT Kiro skill links"
finish_case

new_case K2 "Kiro: a renamed marked copy, a note quoting the marker and a user file at a workflow name are kept"
mkdir -p "$H/.kiro/steering"
echo "my own new-skill notes" > "$H/.kiro/steering/new-skill.md"   # user file at a workflow name, no marker
run_cli --kiro-only
expect_rc 3
expect_out "Skipped 1 path"
expect_out "steering/new-skill.md$"
[ "$(cat "$H/.kiro/steering/new-skill.md")" = "my own new-skill notes" ] || err "user file new-skill.md was overwritten"
run_cli --uninstall --kiro-only
expect_rc 0
[ "$(cat "$H/.kiro/steering/new-skill.md")" = "my own new-skill notes" ] || err "--uninstall changed the user file new-skill.md"
# phase 2, a fresh HOME: the installer's own new-skill.md copy
H="$WORK/K2/home2"
mkdir -p "$H/.kiro"
run_cli --kiro-only
expect_rc 0
# the user keeps a customized copy under a new name, marker line and all
cp "$H/.kiro/steering/new-skill.md" "$H/.kiro/steering/my-new-skill.md"
echo "my customization" >> "$H/.kiro/steering/my-new-skill.md"
marker_line="$(sed -n '/^---$/,/^---$/!p' "$H/.kiro/steering/new-skill.md" | head -n 1)"
printf 'note: the installer writes this line:\n%s\n' "$marker_line" > "$H/.kiro/steering/notes.md"
cp "$H/.kiro/steering/my-new-skill.md" "$WORK/K2/my-new-skill.expected"
cp "$H/.kiro/steering/notes.md" "$WORK/K2/notes.expected"
run_cli --update --kiro-only
expect_rc 0   # a kept marked copy alone is not a skipped path (cli.mjs skippedSomething)
expect_out "Kept 1 file"
expect_out "steering/my-new-skill.md$"
cmp -s "$H/.kiro/steering/my-new-skill.md" "$WORK/K2/my-new-skill.expected" || err "--update deleted or changed my-new-skill.md"
cmp -s "$H/.kiro/steering/notes.md" "$WORK/K2/notes.expected" || err "--update deleted or changed notes.md"
run_cli --uninstall --kiro-only
expect_rc 0
expect_out "Kept 1 file"
cmp -s "$H/.kiro/steering/my-new-skill.md" "$WORK/K2/my-new-skill.expected" || err "--uninstall deleted or changed my-new-skill.md"
cmp -s "$H/.kiro/steering/notes.md" "$WORK/K2/notes.expected" || err "--uninstall deleted or changed notes.md"
[ ! -e "$H/.kiro/steering/new-skill.md" ] || err "--uninstall left the installer copy new-skill.md"
finish_case

new_case K3 "Kiro: install, --update and a --version pin keep an edited recorded copy at a workflow name"
mkdir -p "$H/.kiro"
run_cli --kiro-only
expect_rc 0
wf="$H/.kiro/steering/new-skill.md"
echo "my edit" >> "$wf"
cp "$wf" "$WORK/K3/new-skill.expected"
for args in "--kiro-only" "--update --kiro-only" "--version $FIXTURE_TAG --update --kiro-only"; do
  read -r -a argv <<< "$args"
  run_cli "${argv[@]}"
  expect_rc 3
  expect_stderr "changed since"
  expect_stderr "steering/new-skill.md$"
  expect_no_stdout "steering/new-skill.md$"
  cmp -s "$wf" "$WORK/K3/new-skill.expected" || err "'$args' overwrote the edited new-skill.md"
done
run_cli --uninstall --kiro-only
expect_rc 3
expect_stderr "steering/new-skill.md$"
cmp -s "$wf" "$WORK/K3/new-skill.expected" || err "--uninstall deleted or changed the edited new-skill.md"
left="$(cd "$H/.kiro/steering" && ls)"; [ "$left" = "new-skill.md" ] || err "~/.kiro/steering should hold only the edited new-skill.md, has: $(echo $left)"
# once the user removes the edit, the next install writes the workflow again
rm -f "$wf"
run_cli --kiro-only
expect_rc 0
marker_line="$(sed -n '/^---$/,/^---$/!p' "$wf" 2>/dev/null | head -n 1)"
case "$marker_line" in "<!-- apex-skills installer:"*) ;; *) err "new-skill.md was not written again as a marked copy";; esac
finish_case

new_case K4 "Kiro: the prune keeps an edited recorded copy of a workflow that left the repo"
mkdir -p "$H/.kiro"
run_cli --kiro-only
expect_rc 0
MF="$(manifest_of)"
# two copies recorded under workflow names the repo no longer has: zz-gone-a
# stays as written, zz-gone-b is edited after the install
gone_a="$H/.kiro/steering/zz-gone-a.md"; gone_b="$H/.kiro/steering/zz-gone-b.md"
cp "$H/.kiro/steering/new-skill.md" "$gone_a"
cp "$H/.kiro/steering/new-skill.md" "$gone_b"
# shellcheck disable=SC2016  # JavaScript, not shell, expansions
node -e '
  const fs = require("fs"), crypto = require("crypto");
  const [mf, base, ...files] = process.argv.slice(1);
  const m = JSON.parse(fs.readFileSync(mf, "utf8"));
  for (const f of files) m.bases[base].areas["kiro-steering"][f] = { kind: "copy", sha256: crypto.createHash("sha256").update(fs.readFileSync(f)).digest("hex") };
  fs.writeFileSync(mf, JSON.stringify(m, null, 2));
' "$MF" "$H" "$gone_a" "$gone_b"
echo "my edit" >> "$gone_b"
cp "$gone_b" "$WORK/K4/zz-gone-b.expected"
run_cli --update --kiro-only
expect_rc 3
expect_stderr "changed since"
expect_stderr "steering/zz-gone-b.md$"
expect_no_out "not a recorded copy of a current workflow"
[ ! -e "$gone_a" ] || err "the unchanged recorded copy zz-gone-a.md was not pruned"
cmp -s "$gone_b" "$WORK/K4/zz-gone-b.expected" || err "the prune deleted or changed the edited zz-gone-b.md"
# the entry is carried forward, so the next --update and --uninstall keep it too
run_cli --update --kiro-only
expect_rc 3
expect_stderr "steering/zz-gone-b.md$"
cmp -s "$gone_b" "$WORK/K4/zz-gone-b.expected" || err "the second --update deleted or changed zz-gone-b.md"
run_cli --uninstall --kiro-only
expect_rc 3
expect_stderr "changed since"
expect_stderr "steering/zz-gone-b.md$"
cmp -s "$gone_b" "$WORK/K4/zz-gone-b.expected" || err "--uninstall deleted or changed zz-gone-b.md"
finish_case

new_case U1 "--uninstall removes installer entries for Claude and Kiro, keeps user files"
mkdir -p "$H/.claude" "$H/.kiro/steering"
echo "my own steering" > "$H/.kiro/steering/mine.md"
STDIN_TEXT=$'y\n' run_cli
expect_rc 0
[ -e "$H/.claude/apex-steering" ] || err "setup: apex-steering missing after install"
mkdir -p "$H/.claude/skills/my-skill"
run_cli --uninstall
expect_rc 0
for d in "$H/.claude/skills" "$H/.kiro/skills" "$H/.claude/commands" "$H/.claude" "$H/.kiro/steering"; do
  n="$(links_into_install "$d")"; [ "$n" -eq 0 ] || err "$n installer links remain in $d"
done
if [ -e "$H/.claude/apex-steering" ] || [ -L "$H/.claude/apex-steering" ]; then err "~/.claude/apex-steering was not removed"; fi
left="$(cd "$H/.kiro/steering" && ls)"; [ "$left" = "mine.md" ] || err "~/.kiro/steering should hold only mine.md, has: $(echo $left)"
[ -d "$H/.claude/skills/my-skill" ] || err "user skill dir was removed"
finish_case

new_case U2 "--uninstall --project removes the project install, keeps the global one"
mkdir -p "$H/.claude" "$H/proj"
run_cli --claude-only
RUN_CWD="$H/proj" run_cli --project --claude-only
expect_rc 0
[ "$(count_resolving_links "$H/proj/.claude/skills")" -eq "$LATEST_COUNT" ] || err "setup: project install has $(count_resolving_links "$H/proj/.claude/skills") skill links"
RUN_CWD="$H/proj" run_cli --uninstall --project
expect_rc 0
for d in "$H/proj/.claude/skills" "$H/proj/.claude/commands" "$H/proj/.claude"; do
  n="$(links_into_install "$d")"; [ "$n" -eq 0 ] || err "$n installer links remain in $d"
done
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "global install was changed by the project uninstall"
[ -e "$H/.claude/apex-steering" ] || err "global apex-steering was removed by the project uninstall"
finish_case

new_case I1 "closed stdin (</dev/null): defaults are taken and the install finishes"
run_cli
expect_rc 0
expect_out "Done!"
expect_out "default answers are used"
[ "$(/usr/bin/grep -c "default answers are used" "$OUT")" -eq 1 ] || err "the defaults line should print once"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT skill links (default target claude)"
[ -e "$H/.claude/apex-steering/workflows/new-skill.md" ] || err "default steering answer (y) did not install apex-steering"
[ ! -e "$H/.kiro" ] || err "~/.kiro was created although the default target is claude"
finish_case

new_case I2 "empty stdin (an empty pipe), ~/.claude present: steering default is taken"
mkdir -p "$H/.claude"
STDIN_EMPTY=1 run_cli
expect_rc 0
expect_out "Done!"
expect_out "default answers are used"
[ -e "$H/.claude/commands/apex/eks.md" ] || err "default steering answer (y) did not install the commands"
finish_case

new_case I3 "piped answers to two prompts are read in order (kiro, then n)"
STDIN_TEXT=$'kiro\nn\n' run_cli
expect_rc 0
expect_out "Done!"
expect_no_out "default answers are used"
[ "$(count_resolving_links "$H/.kiro/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT Kiro skill links"
[ ! -e "$H/.claude" ] || err "~/.claude was created although the answer was kiro"
[ -z "$(ls -A "$H/.kiro/steering" 2>/dev/null)" ] || err "steering was installed although the answer was n"
finish_case

new_case N1 "--no-steering install, then --update keeps steering off; a run that asks the question adds it"
mkdir -p "$H/.claude" "$H/.kiro"
run_cli --no-steering
expect_rc 0
run_cli --update
expect_rc 0
expect_out "Steering stays off"
if [ -e "$H/.claude/apex-steering" ] || [ -L "$H/.claude/apex-steering" ]; then err "--update added ~/.claude/apex-steering after --no-steering"; fi
[ ! -e "$H/.claude/commands/apex" ] || err "--update added ~/.claude/commands/apex after --no-steering"
[ -z "$(ls -A "$H/.kiro/steering" 2>/dev/null)" ] || err "--update added Kiro steering copies after --no-steering"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "--update did not keep the skill links"
STDIN_TEXT=$'y\n' run_cli
expect_rc 0
[ -e "$H/.claude/apex-steering/workflows/new-skill.md" ] || err "an install that asked the question (answered y) did not add steering back"
run_cli --update
expect_rc 0
expect_no_out "Steering stays off"
[ -e "$H/.kiro/steering/new-skill.md" ] || err "--update after steering was re-added did not keep it"
finish_case

new_case N2 "answering n is kept by --update; the choice is per install base"
mkdir -p "$H/.claude" "$H/proj"
STDIN_TEXT=$'n\n' run_cli
expect_rc 0
RUN_CWD="$H/proj" run_cli --project --claude-only
expect_rc 0
[ -e "$H/proj/.claude/apex-steering" ] || err "setup: project install has no apex-steering"
run_cli --update
expect_rc 0
expect_out "Steering stays off"
[ ! -e "$H/.claude/commands/apex" ] || err "--update added global steering after the n answer"
RUN_CWD="$H/proj" run_cli --update --project
expect_rc 0
expect_no_out "Steering stays off"
[ -e "$H/proj/.claude/commands/apex/eks.md" ] || err "the project --update lost its steering"
finish_case

new_case NK1 "--no-steering, then a --claude-only run keeps steering off, and the next --update adds none"
mkdir -p "$H/.claude" "$H/.kiro"
run_cli -y --no-steering
expect_rc 0
run_cli --claude-only
expect_rc 0
expect_out "Steering stays off"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "--claude-only did not install the Claude Code skill links"
[ ! -e "$H/.claude/commands/apex" ] || err "--claude-only added ~/.claude/commands/apex after --no-steering"
if [ -e "$H/.claude/apex-steering" ] || [ -L "$H/.claude/apex-steering" ]; then err "--claude-only added ~/.claude/apex-steering after --no-steering"; fi
[ "$(mfq "$(manifest_of)" 'm.bases[b].steering')" = "false" ] || err "--claude-only did not keep the saved no-steering choice in the manifest"
run_cli --update
expect_rc 0
expect_out "Steering stays off"
[ -z "$(ls -A "$H/.kiro/steering" 2>/dev/null)" ] || err "--update after --claude-only added the Kiro steering copies the user declined"
[ ! -e "$H/.claude/commands/apex" ] || err "--update after --claude-only added ~/.claude/commands/apex"
finish_case

new_case NK2 "--no-steering, then a --kiro-only run keeps steering off, and the next --update adds none"
mkdir -p "$H/.claude" "$H/.kiro"
run_cli -y --no-steering
expect_rc 0
run_cli --kiro-only
expect_rc 0
expect_out "Steering stays off"
[ "$(count_resolving_links "$H/.kiro/skills")" -eq "$LATEST_COUNT" ] || err "--kiro-only did not install the Kiro skill links"
[ -z "$(ls -A "$H/.kiro/steering" 2>/dev/null)" ] || err "--kiro-only added Kiro steering copies after --no-steering"
[ "$(mfq "$(manifest_of)" 'm.bases[b].steering')" = "false" ] || err "--kiro-only did not keep the saved no-steering choice in the manifest"
run_cli --update
expect_rc 0
expect_out "Steering stays off"
[ ! -e "$H/.claude/commands/apex" ] || err "--update after --kiro-only added the ~/.claude/commands/apex the user declined"
if [ -e "$H/.claude/apex-steering" ] || [ -L "$H/.claude/apex-steering" ]; then err "--update after --kiro-only added ~/.claude/apex-steering"; fi
[ -z "$(ls -A "$H/.kiro/steering" 2>/dev/null)" ] || err "--update after --kiro-only added Kiro steering copies"
finish_case

new_case E1 "--update on a ~/.apex-skills that is not a git clone"
mkdir -p "$H/.claude" "$H/.apex-skills"
run_cli --update --claude-only
expect_rc 1
expect_stderr "is not a git clone"
expect_stderr "mv ~/.apex-skills ~/.apex-skills.old"
expect_no_out "removing"
expect_no_out "detached"
expect_no_out "pinned to a release"
finish_case

new_case E2 "fresh clone of a missing --version names the ref and the ls-remote check"
mkdir -p "$H/.claude"
run_cli --version v9.9.9 --claude-only
expect_rc 1
expect_out "Failed to clone v9.9.9. Check the name (git ls-remote --tags/--heads"
expect_no_out "Check your internet connection"
finish_case

new_case W1 "native Windows (simulated process.platform win32) stops with a clear message"
win32_preload="$WORK/W1/win32-preload.cjs"
printf "Object.defineProperty(process, 'platform', { value: 'win32' });\n" > "$win32_preload"
PRELOAD="$win32_preload" run_cli --claude-only
expect_rc 1
expect_stderr "Native Windows is not supported"
expect_stderr "WSL"
expect_no_stdout "Windows"
[ -z "$(ls -A "$H")" ] || err "the installer wrote to HOME before stopping: $(ls -A "$H")"
finish_case

new_case X1 "a run that skipped paths exits 3; after the conflict is moved it exits 0"
mkdir -p "$H/.claude/skills/eks-recon"
echo "user-owned" > "$H/.claude/skills/eks-recon/USER_FILE"
run_cli --claude-only
expect_rc 3
expect_stderr "Skipped 1 path"
expect_out "exit code 3"
expect_no_out "Done!"
mv "$H/.claude/skills/eks-recon" "$H/moved-eks-recon"
run_cli --update --claude-only
expect_rc 0
expect_out "Done!"
[ -e "$H/.claude/skills/eks-recon/SKILL.md" ] || err "eks-recon was not installed after the conflict was moved"
[ -f "$H/moved-eks-recon/USER_FILE" ] || err "the moved user directory changed"
finish_case

new_case X2 "unknown, contradictory or incomplete flags exit 2 and change nothing"
for args in "--claude-onyl" "--claude-only --kiro-only" "--branch" "--version --claude-only" "install" \
            "--update=yes" "--uninstall --update" "--uninstall --version v1.1.0" "--branch main --version v1.1.0" "--branch ../x" "-x"; do
  read -r -a x2_argv <<< "$args"
  run_cli "${x2_argv[@]}"
  expect_rc 2
  expect_stderr "Nothing was changed"
  expect_no_out "Cloning"
  [ -z "$(ls -A "$H")" ] || err "'$args' wrote to HOME: $(ls -A "$H")"
done
run_cli --claude-onyl
expect_stderr "Unknown flag: --claude-onyl"
run_cli install
expect_stderr "Unexpected argument: install"
run_cli --branch
expect_stderr "--branch needs a value"
run_cli --claude-only --kiro-only
expect_stderr "not both"
finish_case

new_case X3 "--version=<tag> pins like --version <tag>"
mkdir -p "$H/.claude"
run_cli --claude-only "--version=$FIXTURE_TAG"
expect_rc 0
[ "$(install_head)" = "$(git -C "$ORIGIN" rev-parse "$FIXTURE_TAG^{commit}")" ] || err "install is not at $FIXTURE_TAG"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$TAG_COUNT" ] || err "expected $TAG_COUNT skill links"
finish_case

new_case S1 "errors and warnings go to stderr, progress to stdout"
mkdir -p "$H/.claude"
run_cli --version v9.9.9 --claude-only
expect_rc 1
expect_stderr "Failed to clone v9.9.9"
expect_no_stdout "Failed to clone"
expect_stdout "Cloning APEX skills repository"
expect_no_stderr "Cloning APEX skills repository"
mkdir -p "$H/.claude/skills/eks-recon"
run_cli --claude-only
expect_rc 3
expect_stderr "Skipped 1 path"
expect_stderr "skills/eks-recon$"
expect_stderr "Move or rename them"
expect_no_stdout "Skipped"
expect_no_stdout "skills/eks-recon$"
expect_stdout "Installed $((LATEST_COUNT - 1)) skills"
expect_no_out "Installed $LATEST_COUNT skills"
expect_no_stderr "Installed"
finish_case

new_case Y1 "-y takes every default without a prompt, even with answers on stdin"
STDIN_TEXT=$'kiro\nn\n' run_cli -y
expect_rc 0
expect_no_out "Create directory for"
expect_no_out "Install steering"
expect_no_out "default answers are used"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT Claude skill links (default target claude)"
[ -e "$H/.claude/apex-steering/workflows/new-skill.md" ] || err "default steering answer (y) was not taken"
[ ! -e "$H/.kiro" ] || err "~/.kiro was created: stdin was read despite -y"
finish_case

new_case Y2 "--yes finishes while stdin stays open (no EOF)"
mkdir -p "$H/.claude"
STDIN_HOLD=1 RUN_TIMEOUT=20 run_cli --yes
expect_rc 0
[ -e "$H/.claude/commands/apex/eks.md" ] || err "steering (default y) was not installed"
finish_case

new_case G1 "every git call the installer makes has GIT_TERMINAL_PROMPT=0"
mkdir -p "$WORK/G1/bin" "$H/.claude"
real_git="$(command -v git)"
# shellcheck disable=SC2016  # the $ expansions belong to the generated wrapper
printf '#!/bin/sh\nprintf "%%s %%s\\n" "${GIT_TERMINAL_PROMPT-unset}" "$1" >> "%s"\nexec "%s" "$@"\n' "$WORK/G1/git-calls.log" "$real_git" > "$WORK/G1/bin/git"
chmod +x "$WORK/G1/bin/git"
RUN_PATH="$WORK/G1/bin:$PATH" run_cli --claude-only
expect_rc 0
RUN_PATH="$WORK/G1/bin:$PATH" run_cli --version "$FIXTURE_TAG" --claude-only
expect_rc 0
RUN_PATH="$WORK/G1/bin:$PATH" run_cli --update --claude-only
expect_rc 0
calls="$(wc -l < "$WORK/G1/git-calls.log" 2>/dev/null | tr -d ' ')"
bad="$(/usr/bin/grep -vc '^0 ' "$WORK/G1/git-calls.log" 2>/dev/null)"
echo "    git calls logged: ${calls:-0}, without GIT_TERMINAL_PROMPT=0: ${bad:-0}"
[ "${calls:-0}" -ge 8 ] || err "expected at least 8 git calls through the wrapper, got ${calls:-0}"
[ "${bad:-0}" -eq 0 ] || err "git calls without GIT_TERMINAL_PROMPT=0: $(/usr/bin/grep -v '^0 ' "$WORK/G1/git-calls.log" | sort -u | tr '\n' ';')"
finish_case

new_case RL1 "skill and steering links are relative; they still resolve after HOME moves"
mkdir -p "$H/.claude" "$H/.kiro"
STDIN_TEXT=$'y\n' run_cli
expect_rc 0
for d in .claude/skills .kiro/skills .claude/commands .claude; do
  a="$(absolute_links_into_install "$H/$d")"; [ "$a" -eq 0 ] || err "$a absolute installer links in ~/$d"
done
[ "$(links_into_install "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT installer links in ~/.claude/skills"
[ "$(readlink "$H/.claude/apex-steering")" = "../.apex-skills/steering" ] || err "~/.claude/apex-steering is $(readlink "$H/.claude/apex-steering")"
[ "$(readlink "$H/.claude/skills/$SKILL_A")" = "../../.apex-skills/skills/$SKILL_A" ] || err "~/.claude/skills/$SKILL_A is $(readlink "$H/.claude/skills/$SKILL_A")"
mv "$H" "$WORK/RL1/moved-home"
[ "$(count_resolving_links "$WORK/RL1/moved-home/.claude/skills")" -eq "$LATEST_COUNT" ] || err "skill links broke when HOME moved"
[ -e "$WORK/RL1/moved-home/.claude/commands/apex/eks.md" ] || err "the commands link broke when HOME moved"
[ "$(count_resolving_links "$WORK/RL1/moved-home/.kiro/skills")" -eq "$LATEST_COUNT" ] || err "Kiro skill links broke when HOME moved"
mv "$WORK/RL1/moved-home" "$H"
finish_case

new_case RL2 "absolute (v1.2.0) links and links spelled through ./ or .. become relative links"
mkdir -p "$H/.claude"
run_cli --claude-only
expect_rc 0
rm -f "$H/.claude/skills/$SKILL_A" "$H/.claude/skills/$SKILL_B" "$H/.claude/apex-steering"
ln -s "$H/.apex-skills/skills/$SKILL_A" "$H/.claude/skills/$SKILL_A"
ln -s "$H/.apex-skills/./skills/../skills/$SKILL_B" "$H/.claude/skills/$SKILL_B"
ln -s "$H/.apex-skills/steering" "$H/.claude/apex-steering"
run_cli --update --claude-only
expect_rc 0
expect_no_out "Skipped"
for d in .claude/skills .claude; do
  a="$(absolute_links_into_install "$H/$d")"; [ "$a" -eq 0 ] || err "$a absolute installer links left in ~/$d"
done
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT resolving skill links"
[ "$(readlink "$H/.claude/skills/$SKILL_B")" = "../../.apex-skills/skills/$SKILL_B" ] || err "$SKILL_B is $(readlink "$H/.claude/skills/$SKILL_B")"
finish_case

new_case SL1 "~/.claude/skills itself a symlink to another directory"
mkdir -p "$H/.claude" "$H/elsewhere/deeper/skills"
ln -s "$H/elsewhere/deeper/skills" "$H/.claude/skills"
run_cli --claude-only
expect_rc 0
expect_link "$H/.claude/skills" "$H/elsewhere/deeper/skills"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT links resolving through ~/.claude/skills"
[ "$(count_resolving_links "$H/elsewhere/deeper/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT links resolving in the real directory"
a="$(absolute_links_into_install "$H/elsewhere/deeper/skills")"; [ "$a" -eq 0 ] || err "$a absolute links"
run_cli --update --claude-only
expect_rc 0
expect_no_out "Skipped"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "--update broke the links"
run_cli --uninstall --claude-only
expect_rc 0
[ "$(links_into_install "$H/elsewhere/deeper/skills")" -eq 0 ] || err "--uninstall left links in the real directory"
expect_link "$H/.claude/skills" "$H/elsewhere/deeper/skills"
finish_case

new_case SL2 "a dangling ~/.claude/skills symlink is reported and kept; the run finishes"
mkdir -p "$H/.claude"
ln -s "$H/missing-skills-dir" "$H/.claude/skills"
run_cli --claude-only
expect_rc 3
expect_no_out "EEXIST"
expect_stderr "Skipped 1 path"
expect_stderr ".claude/skills$"
expect_link "$H/.claude/skills" "$H/missing-skills-dir"
expect_no_stdout "skills to $H/.claude/skills"
expect_no_stdout "Nothing installed to $H/.claude/skills"
[ ! -e "$H/missing-skills-dir" ] || err "the installer created the dangling link's target"
[ -e "$H/.claude/apex-steering/workflows/new-skill.md" ] || err "steering was not installed"
finish_case

new_case AC1 "every Claude Code skill path holds a directory of the user's: the run says nothing was installed there, not that 0 skills were"
mkdir -p "$H/.claude/skills"
git -C "$ORIGIN" ls-tree -d --name-only "$LATEST_TAG:skills" | /usr/bin/grep -v '^\.' | while read -r s; do mkdir "$H/.claude/skills/$s"; done
run_cli --claude-only -y
expect_rc 3
expect_stderr "Skipped $LATEST_COUNT path"
expect_stdout "Nothing installed to $H/.claude/skills: $LATEST_COUNT paths skipped"
expect_no_stdout "Installed 0 skills"
[ "$(find "$H/.claude/skills" -mindepth 1 -maxdepth 1 -type l | wc -l | tr -d ' ')" -eq 0 ] || err "a link was made over a directory of the user's"
finish_case

new_case SL3 "self-referencing links at install paths and a link loop are reported and kept"
mkdir -p "$H/.claude/skills"
ln -s eks-recon "$H/.claude/skills/eks-recon"
ln -s apex-steering "$H/.claude/apex-steering"
ln -s loop-b "$H/.claude/skills/loop-a"
ln -s loop-a "$H/.claude/skills/loop-b"
run_cli --claude-only
expect_rc 3
expect_no_out "ELOOP"
expect_stderr "Skipped 2 path"
expect_link "$H/.claude/skills/eks-recon" eks-recon
expect_link "$H/.claude/apex-steering" apex-steering
expect_link "$H/.claude/skills/loop-a" loop-b
expect_link "$H/.claude/skills/loop-b" loop-a
run_cli --uninstall --claude-only
expect_rc 0
expect_no_out "ELOOP"
expect_link "$H/.claude/skills/eks-recon" eks-recon
expect_link "$H/.claude/skills/loop-a" loop-b
finish_case

new_case M1 "the install writes a manifest: entries per area, source URL, ref and commit"
mkdir -p "$H/.claude" "$H/.kiro"
STDIN_TEXT=$'y\n' run_cli
expect_rc 0
MF="$(manifest_of)"
if [ ! -f "$MF" ]; then err "no manifest at $MF"; else
  [ "$(mfq "$MF" 'm.version')" = 1 ] || err "manifest version is $(mfq "$MF" 'm.version')"
  [ "$(mfq "$MF" 'Object.keys(m.bases).join(",")')" = "$H" ] || err "manifest bases: $(mfq "$MF" 'Object.keys(m.bases).join(",")')"
  [ "$(mfq "$MF" 'Object.keys(m.bases[b].areas["claude-skills"]).length')" = "$LATEST_COUNT" ] || err "claude-skills entries are not $LATEST_COUNT"
  [ "$(mfq "$MF" 'Object.keys(m.bases[b].areas["kiro-skills"]).length')" = "$LATEST_COUNT" ] || err "kiro-skills entries are not $LATEST_COUNT"
  [ "$(mfq "$MF" 'Object.keys(m.bases[b].areas["claude-steering"]).length')" = 2 ] || err "claude-steering entries are not 2"
  [ "$(mfq "$MF" 'Object.keys(m.bases[b].areas["kiro-steering"]).length')" = "$WF_COUNT" ] || err "kiro-steering entries are not $WF_COUNT"
  [ "$(mfq "$MF" 'm.bases[b].source.commit')" = "$(install_head)" ] || err "source.commit is not the clone HEAD"
  [ "$(mfq "$MF" 'm.bases[b].source.url')" = "file://$ORIGIN" ] || err "source.url is $(mfq "$MF" 'm.bases[b].source.url')"
  [ "$(mfq "$MF" 'm.bases[b].source.ref')" = "$LATEST_TAG" ] || err "source.ref is $(mfq "$MF" 'm.bases[b].source.ref')"
  [ "$(mfq "$MF" 'm.bases[b].steering')" = true ] || err "steering is not true"
  # every recorded copy hash matches the file, every recorded link text matches readlink
  bad="$(mfq "$MF" 'Object.values(m.bases[b].areas).flatMap((a) => Object.entries(a)).filter(([p, e]) => e.kind === "copy" ? require("crypto").createHash("sha256").update(require("fs").readFileSync(p)).digest("hex") !== e.sha256 : require("fs").readlinkSync(p) !== e.target).length')"
  [ "$bad" = 0 ] || err "$bad manifest entries do not match the files on disk"
  left="$(cd "$(dirname "$MF")" && ls -A)"; [ "$left" = "manifest.json" ] || err "state dir holds: $(echo $left)"
fi
run_cli --version "$FIXTURE_TAG" --update
expect_rc 0
[ "$(mfq "$MF" 'm.bases[b].source.ref')" = "$FIXTURE_TAG" ] || err "after the pin source.ref is $(mfq "$MF" 'm.bases[b].source.ref')"
[ "$(mfq "$MF" 'm.bases[b].source.commit')" = "$(git -C "$ORIGIN" rev-parse "$FIXTURE_TAG^{commit}")" ] || err "after the pin source.commit is not the tag commit"
[ "$(mfq "$MF" 'Object.keys(m.bases[b].areas["claude-skills"]).length')" = "$TAG_COUNT" ] || err "after the pin claude-skills entries are not $TAG_COUNT"
d="$(dangling_links "$H/.kiro/skills")"; [ -z "$d" ] || err "dangling Kiro links after the pin: $(echo $d)"
finish_case

new_case M2 "XDG_STATE_HOME (absolute only) moves the manifest"
mkdir -p "$H/.claude"
RUN_ENV="XDG_STATE_HOME=$H/xdg-state" run_cli --claude-only
expect_rc 0
[ -f "$H/xdg-state/apex-skills/manifest.json" ] || err "no manifest under XDG_STATE_HOME"
[ ! -e "$H/.local/state" ] || err "the default state dir was used although XDG_STATE_HOME is set"
RUN_ENV="XDG_STATE_HOME=relative-state" run_cli --update --claude-only
expect_rc 0
[ ! -e "$H/relative-state" ] || err "a relative XDG_STATE_HOME was used"
[ -f "$(manifest_of)" ] || err "a relative XDG_STATE_HOME did not fall back to ~/.local/state"
finish_case

new_case M3 "--uninstall after rm -rf ~/.apex-skills removes the recorded links and Kiro copies"
mkdir -p "$H/.claude" "$H/.kiro/steering"
echo "my own steering" > "$H/.kiro/steering/mine.md"
STDIN_TEXT=$'y\n' run_cli
expect_rc 0
rm -rf "$H/.apex-skills"
run_cli --uninstall
expect_rc 0
left="$(cd "$H/.kiro/steering" && ls)"; [ "$left" = "mine.md" ] || err "~/.kiro/steering should hold only mine.md, has: $(echo $left)"
for d in "$H/.claude/skills" "$H/.kiro/skills" "$H/.claude/commands" "$H/.claude"; do
  n="$(links_into_install "$d")"; [ "$n" -eq 0 ] || err "$n installer links remain in $d"
done
[ "$(mfq "$(manifest_of)" 'm.bases[b] === undefined')" = true ] || err "the manifest still has a record for $H"
finish_case

new_case M4 "--uninstall keeps an edited recorded Kiro copy and a user link into the clone (exit 3)"
mkdir -p "$H/.kiro"
run_cli --kiro-only
expect_rc 0
echo "my edit" >> "$H/.kiro/steering/new-skill.md"
cp "$H/.kiro/steering/new-skill.md" "$WORK/M4/new-skill.expected"
ln -s "$H/.apex-skills/skills/$SKILL_A" "$H/.kiro/skills/my-alias"
run_cli --uninstall --kiro-only
expect_rc 3
expect_stderr "changed since"
expect_stderr "steering/new-skill.md$"
cmp -s "$H/.kiro/steering/new-skill.md" "$WORK/M4/new-skill.expected" || err "--uninstall deleted or changed the edited new-skill.md"
expect_link "$H/.kiro/skills/my-alias" "$H/.apex-skills/skills/$SKILL_A"
[ "$(links_into_install "$H/.kiro/skills")" -eq 1 ] || err "expected only my-alias left in ~/.kiro/skills, found $(links_into_install "$H/.kiro/skills") installer links"
left="$(cd "$H/.kiro/steering" && ls)"; [ "$left" = "new-skill.md" ] || err "~/.kiro/steering should hold only the edited new-skill.md, has: $(echo $left)"
finish_case

new_case M5 "a corrupt or wrong-shape manifest is set aside with a warning; built-in rules apply"
mkdir -p "$H/.claude"
run_cli --claude-only
expect_rc 0
MF="$(manifest_of)"
printf '{"version": 1, "bases": ' > "$MF"
cp "$MF" "$WORK/M5/corrupt.expected"
run_cli --update --claude-only
expect_rc 0
expect_stderr "is not valid"
cmp -s "$MF.corrupt" "$WORK/M5/corrupt.expected" || err "the corrupt manifest was not kept as $MF.corrupt"
[ "$(mfq "$MF" 'Object.keys(m.bases[b].areas["claude-skills"]).length')" = "$LATEST_COUNT" ] || err "the rewritten manifest does not record $LATEST_COUNT skill links"
printf '{"version": 99, "bases": {}}\n' > "$MF"
run_cli --uninstall --claude-only
expect_rc 0
expect_stderr "is not valid"
[ "$(links_into_install "$H/.claude/skills")" -eq 0 ] || err "the fallback uninstall left installer links"
[ ! -e "$H/.claude/apex-steering" ] || err "the fallback uninstall left apex-steering"
finish_case

new_case M6 "a deleted manifest: --update falls back, prunes dangling clone links, writes a new one"
mkdir -p "$H/.claude"
run_cli --claude-only
expect_rc 0
rm -f "$(manifest_of)"
ln -s "$H/.apex-skills/skills/zz-gone-skill" "$H/.claude/skills/zz-gone-skill"
run_cli --update --claude-only
expect_rc 0
if [ -L "$H/.claude/skills/zz-gone-skill" ]; then err "the dangling link into the clone was not pruned"; fi
[ -f "$(manifest_of)" ] || err "no new manifest was written"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT skill links"
finish_case

new_case N3 "the no-steering choice survives rm -rf ~/.apex-skills"
mkdir -p "$H/.claude"
STDIN_TEXT=$'n\n' run_cli
expect_rc 0
rm -rf "$H/.apex-skills"
run_cli --update
expect_rc 0
expect_out "Steering stays off"
[ ! -e "$H/.claude/commands/apex" ] || err "--update added steering after the clone was removed"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT skill links after the re-clone"
finish_case

new_case P1 "--project without a global install still warns about the imports, on stderr"
mkdir -p "$H/.claude" "$H/proj"
RUN_CWD="$H/proj" run_cli --project --claude-only
expect_rc 0
expect_stderr "import @~/.claude/apex-steering"
expect_stderr "run a global install"
run_cli --claude-only
RUN_CWD="$H/proj" run_cli --project --update --claude-only
expect_rc 0
expect_no_out "run a global install"
finish_case

new_case ENV1 "XDG_*, CLAUDE_CONFIG_DIR and GIT_* in the caller's environment do not reach the installer"
poison="$WORK/ENV1/poison"
mkdir -p "$poison" "$H/.claude"
export XDG_STATE_HOME="$poison/state" XDG_CONFIG_HOME="$poison/config" XDG_DATA_HOME="$poison/data" CLAUDE_CONFIG_DIR="$poison/claude" GIT_DIR="$poison/gitdir" GIT_WORK_TREE="$poison/wt" GIT_INDEX_FILE="$poison/index"
run_cli --claude-only
rc_env1=$RC
unset XDG_STATE_HOME XDG_CONFIG_HOME XDG_DATA_HOME CLAUDE_CONFIG_DIR GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
RC=$rc_env1
expect_rc 0
[ -z "$(ls -A "$poison")" ] || err "the installer wrote under the caller's env paths: $(ls -A "$poison")"
[ -f "$(manifest_of)" ] || err "the manifest is not at the default path"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT skill links"
finish_case

new_case NF1 "network fence: an https repo URL is refused at once, nothing is fetched"
mkdir -p "$H/.claude"
RUN_ENV="APEX_SKILLS_REPO_URL=https://github.com/aws-samples/sample-apex-skills.git" RUN_TIMEOUT=30 run_cli --claude-only
expect_rc 1
expect_stderr "Could not read the release tags of https://github.com/aws-samples/sample-apex-skills.git"
expect_stderr "not allowed"
[ ! -e "$H/.apex-skills/skills" ] || err "something was cloned"
[ "$RUN_SECS" -le 10 ] || err "the refused clone took ${RUN_SECS}s"
finish_case

# ---------------------------------------------------------------- release tags
# A copy of the fixture origin with extra tags or none, for the cases below.
origin_copy() { # <dest>: a bare copy of ORIGIN with its branches and tags
  git clone -q --bare "$ORIGIN" "$1"
}
default_skill_checks() { # <skills dir>: the default install is LATEST_TAG's tree
  [ "$(count_resolving_links "$1")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT skill links ($LATEST_TAG), got $(count_resolving_links "$1")"
  if [ -e "$1/$MAIN_SKILL" ]; then err "unreleased main skill $MAIN_SKILL is installed"; fi
  if [ -e "$1/$V2_SKILL" ]; then err "v2 skill $V2_SKILL is installed"; fi
}

new_case V1 "a plain install uses the newest v1 release tag ($LATEST_TAG), not main, a pre-release or v2"
mkdir -p "$H/.claude" "$H/.kiro"
run_cli -y
expect_rc 0
expect_stdout "latest v1 release, $LATEST_TAG"
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "install HEAD is not $LATEST_TAG (main is $(commit_of main), $RC_TAG and $V2_TAG are elsewhere)"
[ -z "$(install_branch)" ] || err "install is on branch '$(install_branch)', not detached at $LATEST_TAG"
default_skill_checks "$H/.claude/skills"
default_skill_checks "$H/.kiro/skills"
[ -e "$H/.claude/apex-steering/workflows" ] || err "steering is not linked"
[ "$(find "$H/.kiro/steering" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')" -eq "$WF_COUNT" ] || err "expected $WF_COUNT Kiro steering copies"
check_imports "$H/.claude"
MF="$(manifest_of)"
[ "$(mfq "$MF" 'm.bases[b].source.ref')" = "$LATEST_TAG" ] || err "manifest source.ref is $(mfq "$MF" 'm.bases[b].source.ref'), not $LATEST_TAG"
[ "$(mfq "$MF" 'm.bases[b].source.commit')" = "$(commit_of "$LATEST_TAG")" ] || err "manifest source.commit is not the $LATEST_TAG commit"
run_cli --update
expect_rc 0
expect_stdout "Already on the latest v1 release, $LATEST_TAG"
expect_no_stderr "not a v1 release"
expect_no_stderr "followed branch"
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "--update moved HEAD off $LATEST_TAG"
run_cli --uninstall
expect_rc 0
[ "$(links_into_install "$H/.claude/skills")" -eq 0 ] || err "--uninstall left skill links"
[ -z "$(find "$H/.kiro/steering" -maxdepth 1 -name '*.md' 2>/dev/null)" ] || err "--uninstall left Kiro copies"
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "--uninstall changed the clone"
finish_case

new_case V2 "release order is numeric (v1.10.9 is newer than v1.10.8 and v1.9.0); an older tag's tree installs cleanly"
SEMVER_ORIGIN="$WORK/V2/origin.git"
origin_copy "$SEMVER_ORIGIN"
# Lexical order would pick v1.9.0; ignoring the patch number would pick v1.10.8.
git -C "$SEMVER_ORIGIN" tag v1.9.0 "$LATEST_TAG^{commit}"
git -C "$SEMVER_ORIGIN" tag v1.10.8 "$LATEST_TAG^{commit}"
git -C "$SEMVER_ORIGIN" tag v1.10.9 "$MID_TAG^{commit}"
mkdir -p "$H/.claude" "$H/.kiro"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$SEMVER_ORIGIN" run_cli -y
expect_rc 0
expect_stdout "latest v1 release, v1.10.9"
[ "$(install_head)" = "$(commit_of "$MID_TAG")" ] || err "install HEAD is not v1.10.9 (the $MID_TAG tree)"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$MID_COUNT" ] || err "expected $MID_COUNT skill links (the $MID_TAG tree), got $(count_resolving_links "$H/.claude/skills")"
if [ -e "$H/.claude/skills/$MID_DROPPED_SKILL" ]; then err "$MID_DROPPED_SKILL is linked, but the v1.10.9 tree lacks it"; fi
d="$(dangling_links "$H/.claude/skills")"; [ -z "$d" ] || err "dangling links: $(echo $d)"
[ "$(find "$H/.kiro/steering" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')" -eq "$WF_COUNT" ] || err "expected $WF_COUNT Kiro steering copies"
check_imports "$H/.claude"
finish_case

new_case V3 "a pre-release or v2 tag only by --version; --update from $RC_TAG moves to $LATEST_TAG with a stderr note, from $V2_TAG to v2.5.0"
mkdir -p "$H/.claude"
run_cli --version "$RC_TAG" --claude-only
expect_rc 0
[ "$(install_head)" = "$(commit_of "$RC_TAG")" ] || err "--version $RC_TAG did not pin the pre-release"
[ -e "$H/.claude/skills/$MAIN_SKILL" ] || err "the $RC_TAG tree's $MAIN_SKILL is not linked"
run_cli --update --claude-only
expect_rc 0
expect_stderr "This install was on $RC_TAG, which is not a v1 release. It now uses the latest v1 release, $LATEST_TAG."
expect_stderr "npx apex-skills --version $RC_TAG"
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "--update from $RC_TAG did not move to $LATEST_TAG"
default_skill_checks "$H/.claude/skills"
run_cli --version "$V2_TAG" --claude-only
expect_rc 0
[ "$(install_head)" = "$(commit_of "$V2_TAG")" ] || err "--version $V2_TAG did not pin the v2 tag"
[ -e "$H/.claude/skills/$V2_SKILL" ] || err "the $V2_TAG tree's $V2_SKILL is not linked"
run_cli --update --claude-only
expect_rc 0
expect_stdout "Updated to the latest v2 release, v2.5.0"
expect_no_stderr "which is not a v"
expect_no_stderr "this install stays on v1"
[ "$(install_head)" = "$(commit_of "$V2_TAG")" ] || err "--update from $V2_TAG left the v2 line"
[ -e "$H/.claude/skills/$V2_SKILL" ] || err "--update from $V2_TAG unlinked $V2_SKILL"
finish_case

new_case V4 "an existing clone on main (an older installer's default) moves to $LATEST_TAG on --update, with a migration note"
mkdir -p "$H/.claude"
run_cli --branch main --claude-only
expect_rc 0
[ -e "$H/.claude/skills/$MAIN_SKILL" ] || err "setup: the main install lacks $MAIN_SKILL"
# An older installer cloned main by default and recorded no branch choice.
git -C "$H/.apex-skills" config --local --unset-all apex-skills.branch 2>/dev/null || true
mf_before="$(mfq "$(manifest_of)" 'Object.keys(m.bases[b].areas["claude-skills"]).length')"
run_cli --update --claude-only
expect_rc 0
expect_stderr "This install followed branch main, which can hold unreleased changes. It now uses the latest v1 release, $LATEST_TAG."
expect_stderr "To keep following main instead, run: npx apex-skills --branch main"
expect_no_stdout "followed branch main"
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "--update left the clone on main"
[ -z "$(install_branch)" ] || err "install is still on branch '$(install_branch)'"
default_skill_checks "$H/.claude/skills"
if [ -L "$H/.claude/skills/$MAIN_SKILL" ]; then err "the link to unreleased $MAIN_SKILL was not pruned"; fi
[ "$mf_before" = "$MAIN_COUNT" ] || err "setup: the main install recorded $mf_before links, not $MAIN_COUNT"
[ "$(mfq "$(manifest_of)" 'm.bases[b].source.ref')" = "$LATEST_TAG" ] || err "manifest source.ref is $(mfq "$(manifest_of)" 'm.bases[b].source.ref')"
run_cli --update --claude-only
expect_rc 0
expect_no_stderr "followed branch"
finish_case

new_case V5 "--branch main (fresh or on an existing clone) is followed by --update, without a migration note"
mkdir -p "$H/.claude"
run_cli --branch main --claude-only
expect_rc 0
run_cli --update --claude-only
expect_rc 0
expect_no_stderr "followed branch"
[ "$(install_branch)" = main ] || err "fresh --branch main: --update left main (on '$(install_branch)')"
[ "$(install_head)" = "$(commit_of main)" ] || err "fresh --branch main: install HEAD is not main"
[ -e "$H/.claude/skills/$MAIN_SKILL" ] || err "fresh --branch main: $MAIN_SKILL is not linked"
rm -rf "$H/.apex-skills"
run_cli --claude-only
expect_rc 0
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "setup: the re-clone is not at $LATEST_TAG"
run_cli --branch main --claude-only
expect_rc 0
run_cli --update --claude-only
expect_rc 0
expect_no_stderr "followed branch"
[ "$(install_branch)" = main ] || err "--branch main on a clone: --update left main (on '$(install_branch)')"
[ -e "$H/.claude/skills/$MAIN_SKILL" ] || err "--branch main on a clone: $MAIN_SKILL is not linked"
run_cli --version "$FIXTURE_TAG" --claude-only
run_cli --update --claude-only
expect_rc 0
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "after --version, --update did not move to $LATEST_TAG"
finish_case

new_case V6 "no v1 release tag reachable (none, only v2 and pre-release tags, or offline): exit 1, nothing changed, no fallback to main"
NOTAG_ORIGIN="$WORK/V6/origin.git"
origin_copy "$NOTAG_ORIGIN"
for t in $(git -C "$NOTAG_ORIGIN" tag -l); do
  case "$t" in "$RC_TAG"|"$V2_TAG") ;; *) git -C "$NOTAG_ORIGIN" tag -d "$t" > /dev/null ;; esac
done
mkdir -p "$H/.claude"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$NOTAG_ORIGIN" run_cli --claude-only
expect_rc 1
expect_stderr "No v1 release tag (v1.x.y) found at file://$NOTAG_ORIGIN"
expect_stderr "Install a branch instead with --branch main"
[ ! -e "$H/.apex-skills" ] || err "a fresh install with no release tag cloned something"
[ ! -e "$(manifest_of)" ] || err "a fresh install with no release tag wrote a manifest"
[ "$(links_into_install "$H/.claude/skills")" -eq 0 ] || err "a fresh install with no release tag made links"
# An existing clone on main (older installer) whose origin has no v1 release tag.
RUN_ENV="APEX_SKILLS_REPO_URL=file://$NOTAG_ORIGIN" run_cli --branch main --claude-only
expect_rc 0
git -C "$H/.apex-skills" config --local --unset-all apex-skills.branch 2>/dev/null || true
head_before="$(install_head)"
links_before="$(links_into_install "$H/.claude/skills")"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$NOTAG_ORIGIN" run_cli --update --claude-only
expect_rc 1
expect_stderr "No v1 release tag (v1.x.y) found at the clone's origin"
[ "$(install_head)" = "$head_before" ] || err "the clone moved although no release tag was found"
[ "$(install_branch)" = main ] || err "the clone left main although no release tag was found"
[ "$(links_into_install "$H/.claude/skills")" = "$links_before" ] || err "links changed although no release tag was found"
# Offline: the clone's origin cannot be reached.
git -C "$H/.apex-skills" remote set-url origin "file://$WORK/V6/no-such-origin.git"
run_cli --update --claude-only
expect_rc 1
expect_stderr "Could not read the release tags of the clone's origin"
[ "$(install_head)" = "$head_before" ] || err "the clone moved although its origin is unreachable"
finish_case

# The real v1.2.0 tree (when this checkout has the tag; a shallow CI checkout
# has no tags, and then this case is skipped, not passed).
if git -C "$REPO_ROOT" rev-parse -q --verify 'refs/tags/v1.2.0^{commit}' > /dev/null 2>&1; then
  new_case V7 "the real v1.2.0 tree installs with this installer (v1.2.0 tagged, main untagged after it)"
  REAL_ORIGIN="$WORK/V7/origin"
  mkdir -p "$REAL_ORIGIN"
  (cd "$REPO_ROOT" && git archive v1.2.0 skills steering) | tar -x -C "$REAL_ORIGIN"
  "${GITC[@]}" -C "$REAL_ORIGIN" init -q
  "${GITC[@]}" -C "$REAL_ORIGIN" add -A skills steering
  "${GITC[@]}" -C "$REAL_ORIGIN" commit -q -m "real v1.2.0 tree"
  "${GITC[@]}" -C "$REAL_ORIGIN" tag v1.2.0
  add_fixture_skill "$REAL_ORIGIN" "$MAIN_SKILL" "present only on main after v1.2.0"
  "${GITC[@]}" -C "$REAL_ORIGIN" add -A skills
  "${GITC[@]}" -C "$REAL_ORIGIN" commit -q -m "main after v1.2.0"
  real_count="$(git -C "$REAL_ORIGIN" ls-tree -d --name-only v1.2.0:skills | /usr/bin/grep -v '^\.' | wc -l | tr -d ' ')"
  real_wf="$(git -C "$REAL_ORIGIN" ls-tree --name-only v1.2.0:steering/workflows | /usr/bin/grep -c '\.md$')"
  mkdir -p "$H/.claude" "$H/.kiro"
  RUN_ENV="APEX_SKILLS_REPO_URL=file://$REAL_ORIGIN" run_cli -y
  expect_rc 0
  [ "$(install_head)" = "$(git -C "$REAL_ORIGIN" rev-parse v1.2.0)" ] || err "install HEAD is not the v1.2.0 tree"
  [ "$(count_resolving_links "$H/.claude/skills")" -eq "$real_count" ] || err "expected $real_count skill links (v1.2.0), got $(count_resolving_links "$H/.claude/skills")"
  [ "$(count_resolving_links "$H/.kiro/skills")" -eq "$real_count" ] || err "expected $real_count Kiro skill links (v1.2.0)"
  [ "$(find "$H/.kiro/steering" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')" -eq "$real_wf" ] || err "expected $real_wf Kiro steering copies (v1.2.0)"
  d="$(dangling_links "$H/.claude/skills")"; [ -z "$d" ] || err "dangling links: $(echo $d)"
  check_imports "$H/.claude"
  finish_case
else
  echo "=== V7: SKIP (this checkout has no v1.2.0 tag; fetch tags to run it)"
fi

# ---------------------------------------------------------------- major lines
V2_NOTE_TAIL='For the v2 installer, see https://github.com/aws-samples/sample-apex-skills/releases'
V1_NOTE_TEXT="is available; this install stays on v1. $V2_NOTE_TAIL"
v1_note() { echo "APEX $1 $V1_NOTE_TEXT"; } # <tag>: the exact note line
branch_note() { echo "APEX $1 is available; this install follows branch $2. $V2_NOTE_TAIL"; } # <tag> <branch>
note_lines() { /usr/bin/grep -c -- "$V2_NOTE_TAIL" "$OUT_STDERR"; }
# A copy of the fixture origin where the v2 line moves on: v2.6.0 adds V2_NEXT_SKILL
# on a new commit after V2_TAG, and the pre-release v2.7.0-rc.1 comes after it.
V2_NEXT_SKILL=zz-v2-next
v2next_origin() { # <dest>
  git clone -q "$ORIGIN" "$1"
  "${GITC[@]}" -C "$1" checkout -q -b fixture-v2 origin/fixture-v2
  add_fixture_skill "$1" "$V2_NEXT_SKILL" "present from v2.6.0"
  "${GITC[@]}" -C "$1" add -A skills
  "${GITC[@]}" -C "$1" commit -q -m "fixture v2.6.0"
  "${GITC[@]}" -C "$1" tag v2.6.0
  add_fixture_skill "$1" zz-v2-rc "present only on v2.7.0-rc.1"
  "${GITC[@]}" -C "$1" add -A skills
  "${GITC[@]}" -C "$1" commit -q -m "fixture v2.7.0-rc.1"
  "${GITC[@]}" -C "$1" tag v2.7.0-rc.1
}
# A bare copy of the fixture origin with no v2 release tag: only the pre-release
# v2.0.0-rc.0 and look-alikes on the v2 commit.
no_v2_release_origin() { # <dest>
  origin_copy "$1"
  local t
  for t in $V2_TAG v2.5.0; do git -C "$1" tag -d "$t" > /dev/null; done
  for t in v2.0.0-rc.0 v3.0.0-beta.1 release-v2.9.0 v2.1 v20.0; do git -C "$1" tag "$t" fixture-v2; done
}

new_case V8 "a clone on v2 stays on v2: --update moves it to the newest v2.x.y, a v2 pre-release pin too; no v1 note"
V8_ORIGIN="$WORK/V8/origin"
v2next_origin "$V8_ORIGIN"
mkdir -p "$H/.claude"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$V8_ORIGIN" run_cli --version "$V2_TAG" --claude-only
expect_rc 0
[ "$(install_head)" = "$(git -C "$V8_ORIGIN" rev-parse "$V2_TAG^{commit}")" ] || err "setup: --version $V2_TAG did not pin it"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$V8_ORIGIN" run_cli --update --claude-only
expect_rc 0
expect_stdout "Updated to the latest v2 release, v2.6.0"
expect_no_stderr "which is not a v"
expect_no_out "this install stays on v1"
expect_no_out "$V2_NOTE_TAIL"
[ "$(install_head)" = "$(git -C "$V8_ORIGIN" rev-parse "v2.6.0^{commit}")" ] || err "--update did not move the $V2_TAG clone to v2.6.0 (HEAD $(install_head))"
[ -e "$H/.claude/skills/$V2_NEXT_SKILL/SKILL.md" ] || err "the v2.6.0 skill $V2_NEXT_SKILL is not linked"
[ -e "$H/.claude/skills/$V2_SKILL/SKILL.md" ] || err "the v2 skill $V2_SKILL is not linked"
if [ -e "$H/.claude/skills/zz-v2-rc" ]; then err "the v2.7.0-rc.1 skill is linked: a pre-release was picked"; fi
if [ -e "$H/.claude/skills/$MAIN_SKILL" ]; then err "a v1 line skill ($MAIN_SKILL) is linked"; fi
[ "$(mfq "$(manifest_of)" 'm.bases[b].source.ref')" = v2.6.0 ] || err "manifest source.ref is $(mfq "$(manifest_of)" 'm.bases[b].source.ref'), not v2.6.0"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$V8_ORIGIN" run_cli --update --claude-only
expect_rc 0
expect_stdout "Already on the latest v2 release, v2.6.0"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$V8_ORIGIN" run_cli --version v2.7.0-rc.1 --claude-only
expect_rc 0
[ -e "$H/.claude/skills/zz-v2-rc/SKILL.md" ] || err "setup: --version v2.7.0-rc.1 did not link zz-v2-rc"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$V8_ORIGIN" run_cli --update --claude-only
expect_rc 0
expect_stderr "This install was on v2.7.0-rc.1, which is not a v2 release. It now uses the latest v2 release, v2.6.0."
expect_stderr "To go back, run: npx apex-skills --version v2.7.0-rc.1"
expect_no_out "this install stays on v1"
[ "$(install_head)" = "$(git -C "$V8_ORIGIN" rev-parse "v2.6.0^{commit}")" ] || err "--update from v2.7.0-rc.1 did not move to v2.6.0"
finish_case

new_case V9 "a clone on v1 stays on v1 while v2 release tags exist; install and --update print the v2 note on stderr"
mkdir -p "$H/.claude"
run_cli -y --claude-only
expect_rc 0
expect_stdout "latest v1 release, $LATEST_TAG"
expect_stderr "$(v1_note v2.5.0)"
[ "$(note_lines)" = 1 ] || err "the install printed the v2 note $(note_lines) times, not once"
expect_no_stdout "$V1_NOTE_TEXT"
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "the install is not on $LATEST_TAG"
default_skill_checks "$H/.claude/skills"
run_cli --update --claude-only
expect_rc 0
expect_stdout "Already on the latest v1 release, $LATEST_TAG"
expect_stderr "$(v1_note v2.5.0)"
[ "$(note_lines)" = 1 ] || err "--update printed the v2 note $(note_lines) times, not once"
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "--update left $LATEST_TAG"
run_cli --version "$RC_TAG" --claude-only
expect_rc 0
expect_stderr "$(v1_note v2.5.0)"
run_cli --update --claude-only
expect_rc 0
expect_stderr "$(v1_note v2.5.0)"
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "--update from the v1 pre-release $RC_TAG did not move to $LATEST_TAG"
default_skill_checks "$H/.claude/skills"
finish_case

new_case V10 "the v2 note needs a v2.0.0 or later release tag; it names the newest one in numeric order"
V10_ORIGIN="$WORK/V10/origin.git"
no_v2_release_origin "$V10_ORIGIN"
mkdir -p "$H/.claude"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$V10_ORIGIN" run_cli -y --claude-only
expect_rc 0
expect_no_out "is available"
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "the install is not on $LATEST_TAG"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$V10_ORIGIN" run_cli --update --claude-only
expect_rc 0
expect_no_out "is available"
git -C "$V10_ORIGIN" tag "$V2_TAG" fixture-v2
RUN_ENV="APEX_SKILLS_REPO_URL=file://$V10_ORIGIN" run_cli --update --claude-only
expect_rc 0
expect_stderr "$(v1_note "$V2_TAG")"
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "--update left $LATEST_TAG once $V2_TAG was tagged"
git -C "$V10_ORIGIN" tag v2.9.0 fixture-v2
git -C "$V10_ORIGIN" tag v2.10.0 fixture-v2
RUN_ENV="APEX_SKILLS_REPO_URL=file://$V10_ORIGIN" run_cli --update --claude-only
expect_rc 0
expect_stderr "$(v1_note v2.10.0)"
finish_case

new_case V11 "the major line comes from the tag at the clone's HEAD, never from an install base's manifest record"
V11_ORIGIN="$WORK/V11/origin"
v2next_origin "$V11_ORIGIN"
v11_run() { RUN_ENV="APEX_SKILLS_REPO_URL=file://$V11_ORIGIN" run_cli "$@"; }
mkdir -p "$H/.claude"
# The clone is on v2.0.0; the manifest record of this base says v1.3.0.
v11_run --version "$V2_TAG" --claude-only
expect_rc 0
mf_set_ref "$LATEST_TAG"
v11_run --update --claude-only
expect_rc 0
expect_stdout "Updated to the latest v2 release, v2.6.0"
[ "$(install_head)" = "$(git -C "$V11_ORIGIN" rev-parse "v2.6.0^{commit}")" ] || err "a v1 manifest record moved the v2 clone off v2"
# The clone is on v1.3.0; the manifest record says v2.0.0.
H="$WORK/V11/home-b"; mkdir -p "$H/.claude"
v11_run -y --claude-only
expect_rc 0
mf_set_ref "$V2_TAG"
v11_run --update --claude-only
expect_rc 0
expect_stdout "Already on the latest v1 release, $LATEST_TAG"
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "a v2 manifest record moved the v1 clone off v1"
# No manifest and no recorded tag: the release tag at HEAD decides (v0.9.0 and
# the v1 look-alikes on the same commit do not).
H="$WORK/V11/home-c"; mkdir -p "$H/.claude"
v11_run --version "$V2_TAG" --claude-only
expect_rc 0
rm -f "$(manifest_of)"
git -C "$H/.apex-skills" config --local --unset-all apex-skills.tag
v11_run --update --claude-only
expect_rc 0
expect_stdout "Updated to the latest v2 release, v2.6.0"
[ "$(install_head)" = "$(git -C "$V11_ORIGIN" rev-parse "v2.6.0^{commit}")" ] || err "with no manifest, the tag at HEAD ($V2_TAG) did not keep the clone on v2"
# Several tags at HEAD: the pinned one decides. v0.9.0 sits on the commit of
# $V2_TAG and v2.5.0 but is on no release line, so --update moves to v1 and
# says the pin was not a v1 release.
H="$WORK/V11/home-d"; mkdir -p "$H/.claude"
v11_run --version v0.9.0 --claude-only
expect_rc 0
v11_run --update --claude-only
expect_rc 0
expect_stderr "This install was on v0.9.0, which is not a v1 release. It now uses the latest v1 release, $LATEST_TAG."
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "the v0.9.0 pin did not move to $LATEST_TAG"
finish_case

new_case MX1 "one clone, two install bases: global v1, then --project --version $V2_TAG; --update from either base stays on v2"
MX1_ORIGIN="$WORK/MX1/origin"
v2next_origin "$MX1_ORIGIN"
mx_run() { RUN_ENV="APEX_SKILLS_REPO_URL=file://$MX1_ORIGIN" run_cli "$@"; }
P="$H/proj"
mkdir -p "$H/.claude" "$P"
mx_dangling() { # no dangling link in either base
  local d dl=""
  for d in "$H/.claude/skills" "$H/.claude" "$H/.claude/commands" "$P/.claude/skills" "$P/.claude" "$P/.claude/commands"; do dl="$dl$(dangling_links "$d")"; done
  [ -z "$dl" ] || err "$1: dangling links: $(echo $dl)"
}
mx_run -y --claude-only
expect_rc 0
RUN_CWD="$P" mx_run --project --version "$V2_TAG" --claude-only
expect_rc 0
[ -e "$P/.claude/skills/$V2_SKILL/SKILL.md" ] || err "setup: the project install lacks $V2_SKILL"
mx_run --update --claude-only
expect_rc 0
expect_stdout "Updated to the latest v2 release, v2.6.0"
[ "$(install_head)" = "$(git -C "$MX1_ORIGIN" rev-parse "v2.6.0^{commit}")" ] || err "the global --update moved the shared v2 clone off v2"
[ -e "$P/.claude/skills/$V2_SKILL/SKILL.md" ] || err "the global --update broke the project's $V2_SKILL link"
mx_dangling "after the global --update"
RUN_CWD="$P" mx_run --update --project --claude-only
expect_rc 0
expect_stdout "Already on the latest v2 release, v2.6.0"
[ -e "$H/.claude/skills/$V2_NEXT_SKILL/SKILL.md" ] || err "the project --update broke the global $V2_NEXT_SKILL link"
mx_dangling "after the project --update"
[ "$(count_resolving_links "$H/.claude/skills")" = "$(count_resolving_links "$P/.claude/skills")" ] || err "the two bases link different skill sets"
finish_case

new_case V12 "a clone on a v2 pre-release with no v2 release tag: --update and a plain run stay on the pin, one note, exit 0"
V12_ORIGIN="$WORK/V12/origin.git"
no_v2_release_origin "$V12_ORIGIN"
v12_run() { RUN_ENV="APEX_SKILLS_REPO_URL=file://$V12_ORIGIN" run_cli "$@"; }
mkdir -p "$H/.claude"
v12_run --version v2.0.0-rc.0 --claude-only
expect_rc 0
head_before="$(install_head)"
links_before="$(links_into_install "$H/.claude/skills")"
for args in "--update --claude-only" "-y --claude-only"; do
  read -r -a argv <<< "$args"
  v12_run "${argv[@]}"
  expect_rc 0
  expect_stderr "No v2 release (v2.x.y) exists yet, so this install stays on v2.0.0-rc.0."
  [ "$(/usr/bin/grep -c 'No v2 release' "$OUT_STDERR")" = 1 ] || err "'$args': the note printed $(/usr/bin/grep -c 'No v2 release' "$OUT_STDERR") times, not once"
  expect_no_out "latest v1 release"
  expect_no_out "$V2_NOTE_TAIL"
  [ "$(install_head)" = "$head_before" ] || err "'$args' moved the clone off the pin"
  [ "$(links_into_install "$H/.claude/skills")" = "$links_before" ] || err "'$args' changed the skill links"
  [ "$(mfq "$(manifest_of)" 'm.bases[b].source.ref')" = v2.0.0-rc.0 ] || err "'$args': manifest source.ref is $(mfq "$(manifest_of)" 'm.bases[b].source.ref')"
done
finish_case

new_case V13 "the v2 note on every run that leaves the clone on v1 or a branch: --branch main, --update of it, --version (fresh and on a clone)"
mkdir -p "$H/.claude"
run_cli --branch main --claude-only
expect_rc 0
expect_stderr "$(branch_note v2.5.0 main)"
[ "$(note_lines)" = 1 ] || err "fresh --branch main printed the note $(note_lines) times"
run_cli --update --claude-only
expect_rc 0
expect_stderr "$(branch_note v2.5.0 main)"
run_cli --version "$MID_TAG" --claude-only
expect_rc 0
expect_stderr "$(v1_note v2.5.0)"
[ "$(note_lines)" = 1 ] || err "--version on a clone printed the note $(note_lines) times"
rm -rf "$H/.apex-skills"
run_cli --version "$MID_TAG" --claude-only
expect_rc 0
expect_stderr "$(v1_note v2.5.0)"
run_cli --version "$V2_TAG" --claude-only
expect_rc 0
expect_no_out "$V2_NOTE_TAIL"
finish_case

new_case V14 "the manifest records v2 and ~/.apex-skills is removed: --update and a plain run clone it again on v2"
V14_ORIGIN="$WORK/V14/origin"
v2next_origin "$V14_ORIGIN"
v14_run() { RUN_ENV="APEX_SKILLS_REPO_URL=file://$V14_ORIGIN" run_cli "$@"; }
mkdir -p "$H/.claude"
v14_run --version "$V2_TAG" --claude-only
expect_rc 0
for args in "--update --claude-only" "-y --claude-only"; do
  rm -rf "$H/.apex-skills"
  read -r -a argv <<< "$args"
  v14_run "${argv[@]}"
  expect_rc 0
  expect_stdout "latest v2 release, v2.6.0"
  expect_no_out "$V2_NOTE_TAIL"
  [ "$(install_head)" = "$(git -C "$V14_ORIGIN" rev-parse "v2.6.0^{commit}")" ] || err "'$args' did not clone the v2 line again"
  [ -e "$H/.claude/skills/$V2_NEXT_SKILL/SKILL.md" ] || err "'$args': $V2_NEXT_SKILL is not linked"
  if [ -e "$H/.claude/skills/$MAIN_SKILL" ]; then err "'$args': a v1 line skill is linked"; fi
  [ "$(mfq "$(manifest_of)" 'm.bases[b].source.ref')" = v2.6.0 ] || err "'$args': manifest source.ref is $(mfq "$(manifest_of)" 'm.bases[b].source.ref')"
done
# With no v2 release yet, the new clone is at the recorded pin.
H="$WORK/V14/home-b"; mkdir -p "$H/.claude"
V14B_ORIGIN="$WORK/V14/origin-b.git"
no_v2_release_origin "$V14B_ORIGIN"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$V14B_ORIGIN" run_cli --version v2.0.0-rc.0 --claude-only
expect_rc 0
rm -rf "$H/.apex-skills"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$V14B_ORIGIN" run_cli --update --claude-only
expect_rc 0
expect_stderr "No v2 release (v2.x.y) exists yet, so this install stays on v2.0.0-rc.0."
[ "$(install_head)" = "$(git -C "$V14B_ORIGIN" rev-parse "v2.0.0-rc.0^{commit}")" ] || err "with no v2 release, the new clone is not at the recorded pin"
finish_case

new_case V15 "a release tag moved upstream: --update follows it and says so"
V15_ORIGIN="$WORK/V15/origin.git"
origin_copy "$V15_ORIGIN"
mkdir -p "$H/.claude"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$V15_ORIGIN" run_cli -y --claude-only
expect_rc 0
git -C "$V15_ORIGIN" tag -f "$LATEST_TAG" "$MID_TAG^{commit}" > /dev/null
RUN_ENV="APEX_SKILLS_REPO_URL=file://$V15_ORIGIN" run_cli --update --claude-only
expect_rc 0
expect_stdout "release $LATEST_TAG was moved to another commit upstream"
expect_no_stdout "Already on the latest"
[ "$(install_head)" = "$(commit_of "$MID_TAG")" ] || err "--update did not follow the moved tag"
d="$(dangling_links "$H/.claude/skills")"; [ -z "$d" ] || err "dangling links: $(echo $d)"
finish_case

# ---------------------------------------------------------------- regressions
new_case UN1 "--uninstall keeps the record of an edited Kiro copy it kept; the next install keeps the edit too"
mkdir -p "$H/.kiro"
run_cli --kiro-only
expect_rc 0
wf="$H/.kiro/steering/new-skill.md"
echo "my edit" >> "$wf"
cp "$wf" "$WORK/UN1/new-skill.expected"
run_cli --uninstall --kiro-only
expect_rc 3
expect_stderr "steering/new-skill.md$"
[ "$(mfq "$(manifest_of)" 'Object.keys(((m.bases[b] || {}).areas || {})["kiro-steering"] || {}).join(",")')" = "$wf" ] || err "--uninstall dropped the record of the kept copy"
run_cli --kiro-only
expect_rc 3
expect_stderr "changed since"
cmp -s "$wf" "$WORK/UN1/new-skill.expected" || err "the install after --uninstall overwrote the edited new-skill.md"
run_cli --uninstall --kiro-only
expect_rc 3
cmp -s "$wf" "$WORK/UN1/new-skill.expected" || err "the second --uninstall deleted or changed the edited new-skill.md"
finish_case

new_case HS1 "one HOME spelled several ways is one install base: an edited Kiro copy is kept"
mkdir -p "$H/.kiro"
RUN_ENV="HOME=$H/" run_cli --kiro-only -y
expect_rc 0
wf="$H/.kiro/steering/new-skill.md"
echo "my edit" >> "$wf"
cp "$wf" "$WORK/HS1/new-skill.expected"
# $H is absolute, so "/$H" starts with //
for home in "$H" "$H/." "/$H"; do
  RUN_ENV="HOME=$home" run_cli --kiro-only -y
  expect_rc 3
  expect_stderr "changed since"
  cmp -s "$wf" "$WORK/HS1/new-skill.expected" || err "HOME=$home overwrote the edited new-skill.md"
done
bases="$(mfq "$(manifest_of)" 'Object.keys(m.bases || {}).join(",")')"
[ "$bases" = "$H" ] || err "expected one install base $H in the manifest, got: $bases"
RUN_ENV="HOME=$H/./" run_cli --uninstall --kiro-only
expect_rc 3
expect_stderr "steering/new-skill.md$"
cmp -s "$wf" "$WORK/HS1/new-skill.expected" || err "--uninstall under another spelling deleted or changed the edited new-skill.md"
left="$(cd "$H/.kiro/steering" && ls)"; [ "$left" = "new-skill.md" ] || err "~/.kiro/steering should hold only the edited new-skill.md, has: $(echo $left)"
finish_case

new_case SH1 "a HOME reached through a symlink is the install base of its real path: an edited Kiro copy is kept from either path and from a --project run in that home"
SH1_REAL="$WORK/SH1/real"
SH1_LINK="$WORK/SH1/link"
mkdir -p "$SH1_REAL/.kiro"
ln -s real "$SH1_LINK"
H="$SH1_REAL"
run_cli --kiro-only -y
expect_rc 0
wf="$SH1_REAL/.kiro/steering/new-skill.md"
echo "my edit" >> "$wf"
cp "$wf" "$WORK/SH1/new-skill.expected"
H="$SH1_LINK"
run_cli --kiro-only -y
expect_rc 3
expect_stderr "changed since"
cmp -s "$wf" "$WORK/SH1/new-skill.expected" || err "a run with HOME reached through a symlink overwrote the edited new-skill.md"
RUN_CWD="$SH1_LINK" run_cli --project --kiro-only -y
expect_rc 3
expect_stderr "changed since"
cmp -s "$wf" "$WORK/SH1/new-skill.expected" || err "a --project run in the home directory reached through a symlink overwrote the edited new-skill.md"
bases="$(mfq "$SH1_REAL/.local/state/apex-skills/manifest.json" 'Object.keys(m.bases || {}).join(",")')"
[ "$bases" = "$SH1_REAL" ] || err "expected one install base $SH1_REAL in the manifest, got: $bases"
# the --project run in HOME writes absolute links, as --project does; the next
# global run makes them relative again
case "$(readlink "$SH1_REAL/.kiro/skills/$SKILL_A")" in /*) ;; *) err "the --project run in HOME left ~/.kiro/skills/$SKILL_A as $(readlink "$SH1_REAL/.kiro/skills/$SKILL_A"), not an absolute link" ;; esac
[ -e "$SH1_REAL/.kiro/skills/$SKILL_A/SKILL.md" ] || err "~/.kiro/skills/$SKILL_A does not resolve after the --project run in HOME"
run_cli --kiro-only -y
expect_rc 3
[ "$(readlink "$SH1_REAL/.kiro/skills/$SKILL_A")" = "../../.apex-skills/skills/$SKILL_A" ] || err "~/.kiro/skills/$SKILL_A is $(readlink "$SH1_REAL/.kiro/skills/$SKILL_A"), not a relative link"
run_cli --uninstall --kiro-only
expect_rc 3
expect_stderr "steering/new-skill.md$"
cmp -s "$wf" "$WORK/SH1/new-skill.expected" || err "--uninstall with HOME reached through a symlink deleted or changed the edited new-skill.md"
[ "$(links_into_install "$SH1_REAL/.kiro/skills")" -eq 0 ] || err "--uninstall left $(links_into_install "$SH1_REAL/.kiro/skills") installer links"
# a HOME that does not exist yet, under a symlinked directory: the base is the
# real path from the first run on
H="$SH1_LINK/new-home"
RUN_CWD="$WORK/SH1" run_cli --claude-only -y
expect_rc 0
RUN_CWD="$WORK/SH1" run_cli --claude-only -y
expect_rc 0
bases="$(mfq "$SH1_REAL/new-home/.local/state/apex-skills/manifest.json" 'Object.keys(m.bases || {}).join(",")')"
[ "$bases" = "$SH1_REAL/new-home" ] || err "expected one install base $SH1_REAL/new-home for a HOME created by the run, got: $bases"
[ "$(readlink "$SH1_REAL/new-home/.claude/skills/$SKILL_A")" = "../../.apex-skills/skills/$SKILL_A" ] || err "~/.claude/skills/$SKILL_A in the new HOME is $(readlink "$SH1_REAL/new-home/.claude/skills/$SKILL_A")"
finish_case

new_case SH2 "--uninstall from a HOME reached through a symlink uses the real path's record: an edited Kiro copy and the user's own link are kept, and no other install is named"
SH2_REAL="$WORK/SH2/real"
SH2_LINK="$WORK/SH2/link"
mkdir -p "$SH2_REAL/.claude" "$SH2_REAL/.kiro"
ln -s real "$SH2_LINK"
H="$SH2_REAL"
run_cli -y
expect_rc 0
wf="$SH2_REAL/.kiro/steering/new-skill.md"
echo "my edit" >> "$wf"
cp "$wf" "$WORK/SH2/new-skill.expected"
ln -s "$SH2_REAL/.apex-skills/skills/$SKILL_A" "$SH2_REAL/.claude/skills/my-alias"
H="$SH2_LINK"
run_cli --uninstall -y
expect_rc 3
expect_stderr "changed since"
expect_stderr "steering/new-skill.md$"
expect_stdout "installed entries from $SH2_REAL$"
expect_no_out "still used by the install"
H="$SH2_REAL"
cmp -s "$wf" "$WORK/SH2/new-skill.expected" || err "--uninstall from the symlinked HOME deleted or changed the edited new-skill.md"
expect_link "$SH2_REAL/.claude/skills/my-alias" "$SH2_REAL/.apex-skills/skills/$SKILL_A"
[ "$(links_into_install "$SH2_REAL/.claude/skills")" -eq 1 ] || err "--uninstall should leave only the user's my-alias link in ~/.claude/skills, left $(links_into_install "$SH2_REAL/.claude/skills")"
[ "$(links_into_install "$SH2_REAL/.kiro/skills")" -eq 0 ] || err "--uninstall left $(links_into_install "$SH2_REAL/.kiro/skills") installer links in ~/.kiro/skills"
[ ! -e "$SH2_REAL/.claude/commands/apex" ] || err "--uninstall left ~/.claude/commands/apex"
bases="$(mfq "$SH2_REAL/.local/state/apex-skills/manifest.json" 'Object.keys(m.bases || {}).join(",")')"
[ "$bases" = "$SH2_REAL" ] || err "expected only the record of $SH2_REAL (it keeps the edited copy), got: $bases"
finish_case

new_case KI1 "a Ctrl-C right after a Kiro copy was updated, before the manifest was saved: the next run takes the copy as the installer's (exit 0) and a later release updates it"
KI1_ORIGIN="$WORK/KI1/origin.git"
origin_copy "$KI1_ORIGIN"
git clone -q "$KI1_ORIGIN" "$WORK/KI1/src"
ki1_release() { # <tag> <line>: a new release on top of LATEST_TAG whose new-skill.md gains <line>
  "${GITC[@]}" -C "$WORK/KI1/src" checkout -q --detach "${KI1_LAST:-$LATEST_TAG}"
  echo "$2" >> "$WORK/KI1/src/steering/workflows/new-skill.md"
  "${GITC[@]}" -C "$WORK/KI1/src" commit -q -am "fixture $1"
  "${GITC[@]}" -C "$WORK/KI1/src" tag "$1"
  git -C "$WORK/KI1/src" push -q origin "refs/tags/$1"
  KI1_LAST="$1"
}
ki1_sha() { node -e 'console.log(require("crypto").createHash("sha256").update(require("fs").readFileSync(process.argv[1])).digest("hex"))' "$1"; }
sigint_preload="$WORK/KI1/sigint.cjs"
cat > "$sigint_preload" <<'JS'
// SIGINT (as a Ctrl-C would send) right after the first write that changes a
// Kiro steering file, so the run stops before it saves the manifest.
const fs = require('fs');
const write = fs.writeFileSync;
fs.writeFileSync = function (p, data, ...rest) {
  let before = null;
  if (typeof p === 'string' && p.includes('/.kiro/steering/')) { try { before = fs.readFileSync(p, 'utf8'); } catch { before = null; } }
  const r = write.call(this, p, data, ...rest);
  if (before !== null && before !== String(data)) process.kill(process.pid, 'SIGINT');
  return r;
};
require('module').syncBuiltinESMExports();
JS
mkdir -p "$H/.kiro"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$KI1_ORIGIN" run_cli --kiro-only -y
expect_rc 0
wf="$H/.kiro/steering/new-skill.md"
ki1_release v1.3.1 "ki1 line one"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$KI1_ORIGIN" PRELOAD="$sigint_preload" run_cli --update
expect_rc 130
/usr/bin/grep -q "ki1 line one" "$wf" || err "the cut-off run did not write the new new-skill.md (the case needs it)"
rec_sha="$(node -e 'const [f, b, p] = process.argv.slice(1); console.log(JSON.parse(require("fs").readFileSync(f, "utf8")).bases[b].areas["kiro-steering"][p].sha256)' "$(manifest_of)" "$H" "$wf")"
if [ -z "$rec_sha" ] || [ "$rec_sha" = "$(ki1_sha "$wf")" ]; then err "the manifest already records the new new-skill.md (the case needs the old record)"; fi
RUN_ENV="APEX_SKILLS_REPO_URL=file://$KI1_ORIGIN" run_cli --update
expect_rc 0
expect_no_stderr "changed since"
/usr/bin/grep -q "ki1 line one" "$wf" || err "the run after the Ctrl-C lost the new new-skill.md text"
ki1_release v1.3.2 "ki1 line two"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$KI1_ORIGIN" run_cli --update
expect_rc 0
expect_no_stderr "changed since"
/usr/bin/grep -q "ki1 line two" "$wf" || err "new-skill.md was not updated to v1.3.2 after the cut-off run"
run_cli --uninstall --kiro-only
expect_rc 0
if [ -e "$wf" ]; then err "--uninstall kept new-skill.md, which holds the installer's text"; fi
finish_case

new_case UE1 "--uninstall on a base with a record removes nothing in an area the record does not hold (Kiro after --claude-only); a base with no record still falls back"
mkdir -p "$H/.claude"
run_cli --claude-only --no-steering -y
expect_rc 0
mkdir -p "$H/.kiro/skills"
ln -s "$H/.apex-skills/skills/$SKILL_A" "$H/.kiro/skills/my-alias"
ln -s "../.apex-skills/steering" "$H/.claude/apex-steering"
run_cli --uninstall
expect_rc 0
expect_link "$H/.kiro/skills/my-alias" "$H/.apex-skills/skills/$SKILL_A"
expect_link "$H/.claude/apex-steering" "../.apex-skills/steering"
[ "$(links_into_install "$H/.claude/skills")" -eq 0 ] || err "--uninstall left $(links_into_install "$H/.claude/skills") recorded skill links"
[ "$(mfq "$(manifest_of)" 'Object.keys(m.bases || {}).length')" = "0" ] || err "--uninstall left a record for the base"
# no record for the base (a 1.2.0 install, or a lost manifest): the 1.2.0 rules
H="$WORK/UE1/home-b"; mkdir -p "$H/.claude"
run_cli --claude-only --no-steering -y
expect_rc 0
rm "$(manifest_of)"
mkdir -p "$H/.kiro/skills"
ln -s "$H/.apex-skills/skills/$SKILL_A" "$H/.kiro/skills/my-alias"
run_cli --uninstall
expect_rc 0
if [ -L "$H/.kiro/skills/my-alias" ]; then err "--uninstall with no record kept the link into the clone in ~/.kiro/skills"; fi
[ "$(links_into_install "$H/.claude/skills")" -eq 0 ] || err "--uninstall with no record left $(links_into_install "$H/.claude/skills") skill links"
finish_case

new_case PL1 "--project links are absolute: they still resolve after the project moves deeper"
mkdir -p "$H/.claude" "$H/proj"
RUN_CWD="$H/proj" run_cli --project --claude-only
expect_rc 0
[ "$(absolute_links_into_install "$H/proj/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT absolute project skill links, got $(absolute_links_into_install "$H/proj/.claude/skills")"
mkdir -p "$H/a/b"
mv "$H/proj" "$H/a/b/proj"
P="$H/a/b/proj"
d="$(dangling_links "$P/.claude/skills") $(dangling_links "$P/.claude") $(dangling_links "$P/.claude/commands")"
[ -z "$(echo $d)" ] || err "links broke when the project moved: $(echo $d)"
[ "$(count_resolving_links "$P/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT resolving skill links in the moved project"
RUN_CWD="$P" run_cli --update --project --claude-only
expect_rc 0
expect_no_out "Skipped"
[ "$(count_resolving_links "$H/.claude/skills")" -eq 0 ] || err "the project install linked into the global ~/.claude/skills"
finish_case

new_case GD1 "GIT_DIR, GIT_WORK_TREE and GIT_INDEX_FILE from the caller never point the installer's git at another repository"
decoy="$WORK/GD1/decoy"
"${GITC[@]}" init -q "$decoy"
"${GITC[@]}" -C "$decoy" commit -q --allow-empty -m decoy
"${GITC[@]}" -C "$decoy" tag v1.0.0
decoy_tag="$(git -C "$decoy" rev-parse v1.0.0)"
cp "$decoy/.git/config" "$WORK/GD1/config.expected"
mkdir -p "$H/.claude"
gd_env="GIT_DIR=$decoy/.git GIT_WORK_TREE=$decoy GIT_INDEX_FILE=$decoy/.git/index"
for args in "--claude-only" "--update --claude-only" "--version $FIXTURE_TAG --claude-only"; do
  read -r -a argv <<< "$args"
  RUN_ENV="$gd_env" run_cli "${argv[@]}"
  expect_rc 0
  [ "$(git -C "$decoy" rev-parse v1.0.0)" = "$decoy_tag" ] || err "'$args' moved the decoy repository's tag v1.0.0"
  cmp -s "$decoy/.git/config" "$WORK/GD1/config.expected" || err "'$args' changed the decoy repository's config"
  [ "$(git -C "$decoy" tag -l | tr '\n' ' ')" = "v1.0.0 " ] || err "'$args' added tags to the decoy: $(git -C "$decoy" tag -l | tr '\n' ' ')"
done
[ "$(install_head)" = "$(commit_of "$FIXTURE_TAG")" ] || err "the install is not at $FIXTURE_TAG"
finish_case

new_case GH1 "a HOME that is a git repository and a ~/.apex-skills that is not a clone: every run stops, HOME's repository is untouched"
# A dotfiles HOME whose origin carries the release tags. git looks for a
# repository upward from its cwd, so from a ~/.apex-skills with no .git of its
# own it would find HOME's repository and fetch, check out and configure there.
"${GITC[@]}" init -q "$H"
echo "my bashrc" > "$H/.bashrc"
"${GITC[@]}" -C "$H" add .bashrc
"${GITC[@]}" -C "$H" commit -q -m dotfiles
git -C "$H" remote add origin "file://$ORIGIN"
mkdir -p "$H/.claude" "$H/.apex-skills"
echo "not a clone" > "$H/.apex-skills/NOTES"
gh_state() { # HEAD, branch, every ref, the config's md5 and the names under .git
  echo "head=$(git -C "$H" rev-parse HEAD) branch=$(git -C "$H" symbolic-ref -q HEAD)"
  git -C "$H" for-each-ref
  md5sum < "$H/.git/config"
  ls -A "$H/.git"
}
gh_state > "$WORK/GH1/state.expected"
for args in "--update --claude-only" "--claude-only" "--version $FIXTURE_TAG --claude-only" "--branch $FIXTURE_BRANCH --claude-only"; do
  read -r -a argv <<< "$args"
  run_cli "${argv[@]}"
  expect_rc 1
  expect_stderr "is not a git clone"
  gh_state > "$WORK/GH1/state.now"
  cmp -s "$WORK/GH1/state.now" "$WORK/GH1/state.expected" || err "'$args' changed HOME's repository: $(diff "$WORK/GH1/state.expected" "$WORK/GH1/state.now" | /usr/bin/grep '^[<>]' | tr '\n' ' ')"
  [ "$(cat "$H/.bashrc" 2>/dev/null)" = "my bashrc" ] || err "'$args' removed or changed ~/.bashrc"
  [ "$(cat "$H/.apex-skills/NOTES" 2>/dev/null)" = "not a clone" ] || err "'$args' changed ~/.apex-skills/NOTES"
done
finish_case

new_case DC1 "a changed file in the clone (an edited v1.2.0 Kiro link target): --update names it, keeps it, never advises removing the clone"
DC_ORIGIN="$WORK/DC1/origin"
git clone -q "$ORIGIN" "$DC_ORIGIN"
"${GITC[@]}" -C "$DC_ORIGIN" checkout -q -b rel "$LATEST_TAG"
echo "upstream change" >> "$DC_ORIGIN/steering/workflows/new-skill.md"
echo "a new upstream file" > "$DC_ORIGIN/steering/workflows/zz-new.md"
"${GITC[@]}" -C "$DC_ORIGIN" add -A steering
"${GITC[@]}" -C "$DC_ORIGIN" commit -q -m "fixture v1.3.1"
"${GITC[@]}" -C "$DC_ORIGIN" tag v1.3.1
dc_run() { RUN_ENV="APEX_SKILLS_REPO_URL=file://$DC_ORIGIN" run_cli "$@"; }
mkdir -p "$H/.kiro"
dc_run --version "$LATEST_TAG" --kiro-only
expect_rc 0
# v1.2.0 linked Kiro workflows into the clone, so an edit there edits the clone
rm -f "$H/.kiro/steering/new-skill.md"
ln -s "$H/.apex-skills/steering/workflows/new-skill.md" "$H/.kiro/steering/new-skill.md"
echo "my edit" >> "$H/.kiro/steering/new-skill.md"
cp "$H/.apex-skills/steering/workflows/new-skill.md" "$WORK/DC1/new-skill.expected"
head_before="$(install_head)"
dc_run --update --kiro-only
expect_rc 1
expect_stderr "$H/.apex-skills/steering/workflows/new-skill.md"
expect_stderr "Copy them out of ~/.apex-skills"
expect_no_out "removing"
cmp -s "$H/.apex-skills/steering/workflows/new-skill.md" "$WORK/DC1/new-skill.expected" || err "--update lost the edit in the clone"
[ "$(install_head)" = "$head_before" ] || err "--update moved the clone although it holds a changed file"
# A file added in the clone where the new release has one: the checkout fails,
# and the advice names the file instead of suggesting removing the clone.
H="$WORK/DC1/home-b"; mkdir -p "$H/.kiro"
dc_run --version "$LATEST_TAG" --kiro-only
expect_rc 0
echo "my own file" > "$H/.apex-skills/steering/workflows/zz-new.md"
dc_run --update --kiro-only
expect_rc 1
expect_stderr "$H/.apex-skills/steering/workflows/zz-new.md"
expect_stderr "1 file(s) you changed or added"
expect_stderr "mv ~/.apex-skills ~/.apex-skills.old"
expect_no_out "removing"
[ "$(cat "$H/.apex-skills/steering/workflows/zz-new.md")" = "my own file" ] || err "--update lost the user's file in the clone"
finish_case

new_case HN1 "the steering-off hint names the clone's ref, so following it keeps a --version pin (and a --branch)"
mkdir -p "$H/.claude"
run_cli --no-steering --version "$MID_TAG" --claude-only
expect_rc 0
run_cli --version "$MID_TAG" --update --claude-only
expect_rc 0
expect_stdout "to add it, run npx apex-skills --version $MID_TAG (without --update, --claude-only or --kiro-only; this run installs for every detected tool)"
run_cli --version "$MID_TAG"
expect_rc 0
[ "$(install_head)" = "$(commit_of "$MID_TAG")" ] || err "following the hint moved the clone off $MID_TAG"
[ -e "$H/.claude/apex-steering/workflows/new-skill.md" ] || err "following the hint did not add steering"
H="$WORK/HN1/home-b"; mkdir -p "$H/.claude"
run_cli --no-steering --branch main --claude-only
expect_rc 0
run_cli --update --claude-only
expect_rc 0
expect_stdout "to add it, run npx apex-skills --branch main (without --update, --claude-only or --kiro-only; this run installs for every detected tool)"
finish_case

new_case NT1 "a run that stops before the clone (no v1 release tag) creates no ~/.claude or ~/.kiro"
NT_ORIGIN="$WORK/NT1/origin.git"
origin_copy "$NT_ORIGIN"
for t in $(git -C "$NT_ORIGIN" tag -l); do git -C "$NT_ORIGIN" tag -d "$t" > /dev/null; done
for args in "-y" "--claude-only" "--kiro-only"; do
  RUN_ENV="APEX_SKILLS_REPO_URL=file://$NT_ORIGIN" run_cli $args
  expect_rc 1
  expect_stderr "No v1 release tag"
  [ -z "$(ls -A "$H")" ] || err "'$args' stopped at the clone but wrote to HOME: $(ls -A "$H")"
done
finish_case

new_case UP1 "--update with neither ~/.claude nor ~/.kiro asks nothing: it takes the default target while stdin stays open"
run_cli -y
expect_rc 0
rm -rf "$H/.claude"
STDIN_HOLD=1 RUN_TIMEOUT=20 run_cli --update
expect_rc 0
expect_no_out "Create directory for"
expect_stdout "Taking the default answer: claude"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT skill links after --update"
finish_case

new_case SK1 "a release with no skills/: --update stops (exit 1); the clone, links and manifest stay as they were"
SK_ORIGIN="$WORK/SK1/origin"
git clone -q "$ORIGIN" "$SK_ORIGIN"
"${GITC[@]}" -C "$SK_ORIGIN" checkout -q -b broken "$LATEST_TAG"
"${GITC[@]}" -C "$SK_ORIGIN" rm -q -r skills
"${GITC[@]}" -C "$SK_ORIGIN" commit -q -m "fixture v1.9.0 without skills/"
"${GITC[@]}" -C "$SK_ORIGIN" tag v1.9.0
mkdir -p "$H/.claude"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$SK_ORIGIN" run_cli --version "$LATEST_TAG" --claude-only
expect_rc 0
head_before="$(install_head)"
mf_before="$(cat "$(manifest_of)")"
RUN_ENV="APEX_SKILLS_REPO_URL=file://$SK_ORIGIN" run_cli --update --claude-only
expect_rc 1
expect_stderr "v1.9.0 has no skills/ directory"
[ "$(install_head)" = "$head_before" ] || err "the clone moved to a release with no skills/"
d="$(dangling_links "$H/.claude/skills")"; [ -z "$d" ] || err "dangling links: $(echo $d)"
[ "$(cat "$(manifest_of)")" = "$mf_before" ] || err "the manifest changed"
finish_case

new_case CR1 "a run that stops part way keeps the record of the links it did not reach; --uninstall removes them all"
crash_preload="$WORK/CR1/crash.cjs"
cat > "$crash_preload" <<'JS'
// The first symlinkSync call fails as an I/O error would, so the run stops part way.
const fs = require('fs');
fs.symlinkSync = () => { const e = new Error('simulated I/O error'); e.code = 'EIO'; throw e; };
require('module').syncBuiltinESMExports();
JS
mkdir -p "$H/.claude"
run_cli --version "$FIXTURE_TAG" --claude-only
expect_rc 0
PRELOAD="$crash_preload" run_cli --update --claude-only
expect_rc 1
expect_stderr "simulated I/O error"
# every installer link on disk is recorded, compared by name (a count can match with a name missing)
cr1_disk="$(find "$H/.claude/skills/" -mindepth 1 -maxdepth 1 -type l -printf '%f\n' | LC_ALL=C sort)"
cr1_rec="$(mfq "$(manifest_of)" 'Object.keys(m.bases[b].areas["claude-skills"]).map((p) => p.split("/").pop()).join("\n")' | LC_ALL=C sort)"
cr1_missing="$(LC_ALL=C comm -23 <(printf '%s\n' "$cr1_disk") <(printf '%s\n' "$cr1_rec") | tr '\n' ' ')"
[ -n "$cr1_disk" ] || err "no skill links on disk after the stopped run"
[ -z "${cr1_missing// /}" ] || err "the stopped run's record lacks these links on disk: $cr1_missing"
run_cli --uninstall --claude-only
expect_rc 0
[ "$(links_into_install "$H/.claude/skills")" -eq 0 ] || err "--uninstall left $(links_into_install "$H/.claude/skills") installer links"
# a dangling installer link the record lacks is removed by --uninstall too
run_cli --claude-only
expect_rc 0
ln -s ../../.apex-skills/skills/zz-sb "$H/.claude/skills/zz-sb"
run_cli --uninstall --claude-only
expect_rc 0
if [ -L "$H/.claude/skills/zz-sb" ]; then err "--uninstall left the dangling installer link zz-sb"; fi
finish_case

new_case NC1 "--uninstall with no clone and no manifest keeps marked Kiro copies and says why"
mkdir -p "$H/.kiro"
run_cli --kiro-only
expect_rc 0
rm -rf "$H/.apex-skills" "$(manifest_of)"
run_cli --uninstall --kiro-only
expect_rc 0
expect_stderr "cannot tell its copies from yours"
expect_no_out "not a recorded copy of a current workflow"
[ "$(find "$H/.kiro/steering" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')" -eq "$WF_COUNT" ] || err "expected the $WF_COUNT marked copies to be kept"
finish_case

new_case MS1 "an install manifest that cannot be saved: exit 3, and the warning says what later runs lose"
mkdir -p "$H/.claude" "$H/.local/state/apex-skills"
chmod 555 "$H/.local/state/apex-skills"
run_cli --claude-only
expect_rc 3
expect_stderr "Could not save the install manifest"
expect_stderr "forgets a --no-steering choice"
expect_stderr "use the last saved record (with none, the built-in ownership rules)"
expect_stdout "Done, but the install manifest could not be saved (see above); exit code 3."
expect_no_out "Done, with skipped paths"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT skill links"
chmod 755 "$H/.local/state/apex-skills"
finish_case

new_case MR1 "an install manifest that cannot be read (not ENOENT): every run stops (exit 1); no record, link or edited Kiro copy is lost"
mkdir -p "$H/.kiro" "$H/proj"
run_cli --kiro-only
expect_rc 0
RUN_CWD="$H/proj" run_cli --project --kiro-only
expect_rc 0
wf="$H/.kiro/steering/new-skill.md"
echo "my edit" >> "$wf"
cp "$wf" "$WORK/MR1/new-skill.expected"
MF="$(manifest_of)"
cp "$MF" "$WORK/MR1/manifest.expected"
[ "$(mfq "$MF" 'Object.keys(m.bases).length')" = 2 ] || err "setup: expected 2 install bases in the manifest"
mr_links="$(links_into_install "$H/.kiro/skills") $(links_into_install "$H/proj/.kiro/skills")"
mr_head="$(install_head)"
mr_check() { # <what ran>: nothing the manifest protects changed
  cmp -s "$wf" "$WORK/MR1/new-skill.expected" || err "$1 deleted or changed the edited new-skill.md"
  [ "$(links_into_install "$H/.kiro/skills") $(links_into_install "$H/proj/.kiro/skills")" = "$mr_links" ] || err "$1 changed the skill links (global, project: $mr_links before)"
  [ "$(install_head)" = "$mr_head" ] || err "$1 moved the clone"
  [ ! -e "$MF.corrupt" ] || err "$1 renamed the manifest to manifest.json.corrupt"
}
mr_runs=("--update --kiro-only" "--kiro-only" "--uninstall --kiro-only" "--uninstall")
if [ "$(id -u)" -ne 0 ]; then
  chmod 000 "$MF"
  for args in "${mr_runs[@]}"; do
    read -r -a argv <<< "$args"
    run_cli "${argv[@]}"
    expect_rc 1
    expect_stderr "Could not read the install manifest"
    chmod 600 "$MF"
    cmp -s "$MF" "$WORK/MR1/manifest.expected" || err "'$args' (chmod 000) replaced or changed the manifest"
    chmod 000 "$MF"
    mr_check "'$args' (chmod 000)"
  done
  chmod 600 "$MF"
else
  echo "    running as root, which reads a chmod 000 file: only the directory variant runs"
fi
# A directory in the manifest's place (EISDIR), which root cannot read either.
mv "$MF" "$WORK/MR1/manifest.saved"
mkdir "$MF"
for args in "${mr_runs[@]}"; do
  read -r -a argv <<< "$args"
  run_cli "${argv[@]}"
  expect_rc 1
  expect_stderr "Could not read the install manifest"
  { [ -d "$MF" ] && [ -z "$(ls -A "$MF")" ]; } || err "'$args' (a directory in its place) changed $MF"
  mr_check "'$args' (a directory in its place)"
done
rmdir "$MF"
mv "$WORK/MR1/manifest.saved" "$MF"
# Readable again: both records are intact, and --uninstall keeps the edited copy.
[ "$(mfq "$MF" 'Object.keys(m.bases).length')" = 2 ] || err "a record was lost"
run_cli --uninstall --kiro-only
expect_rc 3
cmp -s "$wf" "$WORK/MR1/new-skill.expected" || err "--uninstall after the manifest was readable again deleted the edited new-skill.md"
[ "$(count_resolving_links "$H/proj/.kiro/skills")" -eq "$LATEST_COUNT" ] || err "the project install lost skill links"
finish_case

new_case RO1 "a read-only ~/.claude/skills: those links are listed (exit 3); the Kiro and steering halves still install"
mkdir -p "$H/.claude/skills" "$H/.kiro"
chmod 555 "$H/.claude/skills"
STDIN_TEXT=$'y\n' run_cli
expect_rc 3
expect_stderr "permission denied"
expect_no_out "EACCES"
[ "$(count_resolving_links "$H/.kiro/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT Kiro skill links"
[ "$(find "$H/.kiro/steering" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')" -eq "$WF_COUNT" ] || err "expected $WF_COUNT Kiro steering copies"
[ -e "$H/.claude/apex-steering/workflows/new-skill.md" ] || err "Claude steering was not installed"
chmod 755 "$H/.claude/skills"
run_cli --update
expect_rc 0
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT Claude skill links once the directory is writable"
# a read-only ~/.kiro/steering: the copies are listed, the skill links install
H="$WORK/RO1/home-b"; mkdir -p "$H/.kiro/steering"
chmod 555 "$H/.kiro/steering"
run_cli --kiro-only
expect_rc 3
expect_stderr "permission denied"
expect_stderr "steering/new-skill.md$"
[ "$(count_resolving_links "$H/.kiro/skills")" -eq "$LATEST_COUNT" ] || err "expected $LATEST_COUNT Kiro skill links with a read-only steering dir"
chmod 755 "$H/.kiro/steering"
finish_case

new_case HM1 "HOME empty or relative: exit 1 before anything is written"
mkdir -p "$WORK/HM1/cwd"
for home in "" relhome; do
  RUN_ENV="HOME=$home" RUN_CWD="$WORK/HM1/cwd" run_cli -y
  expect_rc 1
  expect_stderr "so there is no safe place to install"
  [ -z "$(ls -A "$WORK/HM1/cwd")" ] || err "HOME='$home' wrote into the working directory: $(ls -A "$WORK/HM1/cwd")"
done
finish_case

new_case H1 "--help lists every flag and the exit codes on stdout"
run_cli --help
expect_rc 0
# each flag at the start of its own help row, so a flag named only in another
# row's text (--uninstall in the --no-steering row) does not count
for f in --claude-only --kiro-only --project --no-steering --update "--version <tag>" "--branch <name>" --uninstall "-y, --yes" "-h, --help"; do
  expect_stdout "^  $f "
done
expect_stdout "Exit codes:"
expect_stdout "3  done"
expect_stdout "run it again to finish before --uninstall: links a stopped"
[ ! -s "$OUT_STDERR" ] || err "--help wrote to stderr"
finish_case

new_case NG1 "no git in PATH: exit 1, the message on stderr, nothing written"
mkdir -p "$WORK/NG1/bin"
ln -s "$(command -v node)" "$WORK/NG1/bin/node"
RUN_PATH="$WORK/NG1/bin" run_cli -y
expect_rc 1
expect_stderr "git is required but not found in PATH"
expect_no_stdout "git is required"
[ -z "$(ls -A "$H")" ] || err "the installer wrote to HOME without git: $(ls -A "$H")"
finish_case

new_case NG2 "--uninstall with no git in PATH: says ~/.apex-skills was not checked, not that it is not a git clone"
mkdir -p "$H/.claude" "$WORK/NG2/bin"
run_cli --claude-only
expect_rc 0
ln -s "$(command -v node)" "$WORK/NG2/bin/node"
RUN_PATH="$WORK/NG2/bin" run_cli --uninstall
expect_rc 0
expect_stdout "git is not in PATH, so $H/.apex-skills was not checked and is left alone"
expect_no_out "not a git clone"
expect_no_out "rm -rf"
[ -d "$H/.apex-skills/.git" ] || err "--uninstall without git changed ~/.apex-skills"
finish_case

new_case MC1 "a manifest entry outside the base's .claude and .kiro, or spelled with .., is not trusted: --uninstall leaves that path alone"
mkdir -p "$H/.claude"
# One crafted entry per run, so each check stands on its own: an absolute path
# outside the base, a path that starts inside .claude but leaves it by .., and
# a sibling directory whose name starts with .claude (entry|path it names).
for pair in "$H/victim|$H/victim" "$H/.claude/../victim-dotdot|$H/victim-dotdot" "$H/.claude-x/victim-sibling|$H/.claude-x/victim-sibling"; do
  entry="${pair%%|*}"
  victim="${pair#*|}"
  mkdir -p "$(dirname "$victim")"
  run_cli --claude-only
  expect_rc 0
  ln -s "$H/.apex-skills/skills/$SKILL_A" "$victim"
  # shellcheck disable=SC2016  # JavaScript, not shell, expansions
  node -e '
    const fs = require("fs");
    const [mf, base, entry, victim] = process.argv.slice(1);
    const m = JSON.parse(fs.readFileSync(mf, "utf8"));
    m.bases[base].areas["claude-skills"][entry] = { kind: "link", target: fs.readlinkSync(victim) };
    fs.writeFileSync(mf, JSON.stringify(m, null, 2));
  ' "$(manifest_of)" "$H" "$entry" "$victim"
  run_cli --uninstall --claude-only
  [ -L "$victim" ] || err "--uninstall deleted $victim through the manifest entry $entry"
  expect_stderr "is not valid"
  [ "$(links_into_install "$H/.claude/skills")" -eq 0 ] || err "the fallback uninstall left installer links"
  rm -f "$victim" "$(manifest_of).corrupt"
done
finish_case

new_case US1 "a scoped --uninstall with both tools installed removes only that tool's entries"
mkdir -p "$H/.claude" "$H/.kiro"
STDIN_TEXT=$'y\n' run_cli
expect_rc 0
run_cli --uninstall --claude-only
expect_rc 0
[ "$(links_into_install "$H/.claude/skills")" -eq 0 ] || err "--uninstall --claude-only left $(links_into_install "$H/.claude/skills") Claude skill links"
if [ -L "$H/.claude/apex-steering" ] || [ -L "$H/.claude/commands/apex" ]; then err "--uninstall --claude-only left the Claude steering links"; fi
[ "$(count_resolving_links "$H/.kiro/skills")" -eq "$LATEST_COUNT" ] || err "--uninstall --claude-only removed Kiro skill links ($(count_resolving_links "$H/.kiro/skills") of $LATEST_COUNT left)"
[ "$(find "$H/.kiro/steering" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')" -eq "$WF_COUNT" ] || err "--uninstall --claude-only removed Kiro steering copies"
us_areas="$(mfq "$(manifest_of)" 'Object.keys(((m.bases[b] || {}).areas) || {}).sort().join(",")')"
[ "$us_areas" = "kiro-skills,kiro-steering" ] || err "the record should keep only the Kiro areas, has: $us_areas"
# the other way round, in a second HOME
H="$WORK/US1/home-b"; mkdir -p "$H/.claude" "$H/.kiro"
STDIN_TEXT=$'y\n' run_cli
expect_rc 0
run_cli --uninstall --kiro-only
expect_rc 0
[ "$(links_into_install "$H/.kiro/skills")" -eq 0 ] || err "--uninstall --kiro-only left $(links_into_install "$H/.kiro/skills") Kiro skill links"
[ "$(find "$H/.kiro/steering" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')" -eq 0 ] || err "--uninstall --kiro-only left Kiro steering copies"
[ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "--uninstall --kiro-only removed Claude skill links ($(count_resolving_links "$H/.claude/skills") of $LATEST_COUNT left)"
[ -e "$H/.claude/apex-steering/workflows/new-skill.md" ] || err "--uninstall --kiro-only removed ~/.claude/apex-steering"
[ -e "$H/.claude/commands/apex/eks.md" ] || err "--uninstall --kiro-only removed ~/.claude/commands/apex"
us_areas="$(mfq "$(manifest_of)" 'Object.keys(((m.bases[b] || {}).areas) || {}).sort().join(",")')"
[ "$us_areas" = "claude-skills,claude-steering" ] || err "the record should keep only the Claude areas, has: $us_areas"
finish_case

new_case UL1 "a recorded link the user replaced with a symlink of their own is kept by --uninstall (exit 3)"
mkdir -p "$H/.claude" "$H/my-skills/$SKILL_A"
run_cli --claude-only
expect_rc 0
rm "$H/.claude/skills/$SKILL_A"
ln -s "$H/my-skills/$SKILL_A" "$H/.claude/skills/$SKILL_A"
run_cli --uninstall --claude-only
expect_rc 3
expect_stderr "changed since"
expect_stderr "skills/$SKILL_A$"
expect_link "$H/.claude/skills/$SKILL_A" "$H/my-skills/$SKILL_A"
[ "$(links_into_install "$H/.claude/skills")" -eq 0 ] || err "--uninstall left $(links_into_install "$H/.claude/skills") installer links"
finish_case

new_case UA1 "a user alias link into the clone survives --update; only dangling installer links are pruned"
mkdir -p "$H/.claude"
run_cli --claude-only
expect_rc 0
ln -s "$H/.apex-skills/skills/$SKILL_A" "$H/.claude/skills/my-alias"
ln -s "../../.apex-skills/skills/$SKILL_B" "$H/.claude/skills/my-alias-rel"
ln -s "../../.apex-skills/skills/zz-gone-skill" "$H/.claude/skills/zz-gone-skill"
run_cli --update --claude-only
expect_rc 0
expect_link "$H/.claude/skills/my-alias" "$H/.apex-skills/skills/$SKILL_A"
expect_link "$H/.claude/skills/my-alias-rel" "../../.apex-skills/skills/$SKILL_B"
if [ -L "$H/.claude/skills/zz-gone-skill" ]; then err "--update left the dangling installer link zz-gone-skill"; fi
finish_case

new_case RU1 "an APEX_SKILLS_REPO_URL that starts with - is refused before git sees it"
marker="$WORK/RU1/upload-pack-ran"
evil="$WORK/RU1/evil.sh"
printf '#!/bin/sh\ntouch "%s"\nexit 1\n' "$marker" > "$evil"
chmod +x "$evil"
# a repository cwd with an origin: git ls-remote with no repository argument uses it
git clone -q "$ORIGIN" "$WORK/RU1/repo"
mkdir -p "$H/.claude"
RUN_ENV="APEX_SKILLS_REPO_URL=--upload-pack=$evil" RUN_CWD="$WORK/RU1/repo" run_cli --claude-only
expect_rc 1
expect_stderr 'starts with "-"'
[ ! -e "$marker" ] || err "the URL reached git as an option and ran $evil"
[ ! -e "$H/.apex-skills" ] || err "something was cloned"
finish_case

# An upgrade from the real installer on main before this branch (6103231): it
# cloned main and linked Kiro workflows. Only its repository URL is changed,
# because it always cloned from GitHub. Skipped when the commit is not here.
OLD_REV=6103231
if git -C "$REPO_ROOT" cat-file -e "$OLD_REV:misc/installer/bin/cli.mjs" 2>/dev/null; then
  new_case OLD1 "upgrade from an install made by the real installer at $OLD_REV: --update moves to $LATEST_TAG, keeps user files, no dangling links"
  old="$WORK/OLD1/old-installer"
  mkdir -p "$old/bin"
  git -C "$REPO_ROOT" show "$OLD_REV:misc/installer/package.json" > "$old/package.json"
  git -C "$REPO_ROOT" show "$OLD_REV:misc/installer/bin/cli.mjs" | sed 's|^const REPO_URL = .*|const REPO_URL = process.env.APEX_SKILLS_REPO_URL;|' > "$old/bin/cli.mjs"
  [ "$(/usr/bin/grep -c '^const REPO_URL = process.env.APEX_SKILLS_REPO_URL;$' "$old/bin/cli.mjs")" = 1 ] || err "setup: could not point the old installer at the fixture"
  mkdir -p "$H/.claude/skills/my-skill" "$H/.kiro/steering"
  echo "my own steering" > "$H/.kiro/steering/mine.md"
  RUN_CLI="$old/bin/cli.mjs" run_cli --claude-only
  expect_rc 0
  RUN_CLI="$old/bin/cli.mjs" run_cli --kiro-only
  expect_rc 0
  [ "$(install_branch)" = main ] || err "setup: the old installer's clone is not on main"
  [ -L "$H/.kiro/steering/new-skill.md" ] || err "setup: the old installer did not link the Kiro workflows"
  [ -e "$H/.claude/skills/$MAIN_SKILL" ] || err "setup: the old install lacks the main-only $MAIN_SKILL"
  run_cli --update
  expect_rc 0
  expect_stderr "This install followed branch main"
  [ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "--update did not move the old install to $LATEST_TAG"
  default_skill_checks "$H/.claude/skills"
  default_skill_checks "$H/.kiro/skills"
  d="$(dangling_links "$H/.claude/skills") $(dangling_links "$H/.kiro/skills") $(dangling_links "$H/.claude/commands") $(dangling_links "$H/.kiro/steering")"
  [ -z "$(echo $d)" ] || err "dangling links after the upgrade: $(echo $d)"
  if [ -L "$H/.kiro/steering/new-skill.md" ] || ! fm_manual "$H/.kiro/steering/new-skill.md"; then err "the Kiro workflow link was not replaced by a manual copy"; fi
  [ "$(cat "$H/.kiro/steering/mine.md")" = "my own steering" ] || err "the user's steering file changed"
  [ -d "$H/.claude/skills/my-skill" ] || err "the user's skill dir was removed"
  [ -f "$(manifest_of)" ] || err "the upgrade wrote no manifest"
  check_imports "$H/.claude"
  run_cli --uninstall
  expect_rc 0
  [ "$(links_into_install "$H/.claude/skills")" -eq 0 ] || err "--uninstall left installer links"
  [ "$(cat "$H/.kiro/steering/mine.md")" = "my own steering" ] || err "--uninstall changed the user's steering file"
  finish_case
else
  echo "=== OLD1: SKIP (this checkout lacks $OLD_REV; fetch the full history to run it)"
fi

new_case TT1 "at a terminal, Ctrl-C or Ctrl-D at the steering question cancels (exit 130) and writes nothing; a typed answer still installs"
if [ -z "$PTY_PYTHON" ]; then
  echo "    SKIP: no python3 for the pseudo-terminal"
else
  mkdir -p "$H/.claude"
  tt_state() { find "$H" | sort; }
  tt_state > "$WORK/TT1/state.expected"
  for key in '\u0003' '\u0004'; do
    RUN_TIMEOUT=30 run_pty '[["Install steering", "'"$key"'"]]'
    expect_rc 130
    expect_out "Cancelled at a question; nothing was changed"
    expect_no_out "default answers are used"
    tt_state > "$WORK/TT1/state.now"
    cmp -s "$WORK/TT1/state.now" "$WORK/TT1/state.expected" || err "a cancelled run ($key) wrote to HOME: $(diff "$WORK/TT1/state.expected" "$WORK/TT1/state.now" | /usr/bin/grep '^>' | head -n 3 | tr '\n' ' ')"
  done
  RUN_TIMEOUT=30 run_pty '[["Install steering", "n\r"]]'
  expect_rc 0
  expect_out "Done!"
  [ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "the typed answer did not install $LATEST_COUNT skill links"
  [ ! -e "$H/.claude/commands/apex" ] || err "steering was installed although the typed answer was n"
fi
finish_case

new_case TT2 "at a terminal with neither ~/.claude nor ~/.kiro (two questions): Ctrl-C at either cancels, writes nothing and the process exits"
if [ -z "$PTY_PYTHON" ]; then
  echo "    SKIP: no python3 for the pseudo-terminal"
else
  for steps in '[["Create directory", "\u0003"]]' '[["Create directory", "claude\r"], ["Install steering", "\u0003"]]'; do
    RUN_TIMEOUT=30 run_pty "$steps"
    expect_rc 130
    expect_out "Cancelled at a question; nothing was changed"
    [ -z "$(ls -A "$H")" ] || err "a cancelled run ($steps) wrote to HOME: $(find "$H" -mindepth 1 -maxdepth 1 | tr '\n' ' ')"
  done
  RUN_TIMEOUT=30 run_pty '[["Create directory", "kiro\r"], ["Install steering", "y\r"]]'
  expect_rc 0
  expect_out "Done!"
  [ "$(count_resolving_links "$H/.kiro/skills")" -eq "$LATEST_COUNT" ] || err "the typed answers did not install $LATEST_COUNT Kiro skill links"
  [ ! -e "$H/.claude" ] || err "~/.claude was created although the typed answer was kiro"
fi
finish_case

new_case CL1 "a commit made on a pinned (detached) clone: --update, a plain run, --version and --branch stop (exit 1) and keep it; on a branch, --update moves on"
mkdir -p "$H/.claude"
run_cli --version "$MID_TAG" --claude-only
expect_rc 0
echo "my work" > "$H/.apex-skills/MINE.md"
"${GITC[@]}" -C "$H/.apex-skills" add MINE.md
"${GITC[@]}" -C "$H/.apex-skills" commit -q -m "my local commit"
mine="$(install_head)"
for args in "--update --claude-only" "--claude-only" "--version $LATEST_TAG --claude-only" "--branch $FIXTURE_BRANCH --claude-only"; do
  read -r -a argv <<< "$args"
  run_cli "${argv[@]}"
  expect_rc 1
  expect_stderr "1 commit(s) that no branch or tag holds"
  expect_stderr "my local commit"
  [ "$(install_head)" = "$mine" ] || err "'$args' moved the clone off the local commit"
  [ "$(cat "$H/.apex-skills/MINE.md" 2>/dev/null)" = "my work" ] || err "'$args' removed MINE.md from the clone"
done
git -C "$H/.apex-skills" branch my-work
run_cli --update --claude-only
expect_rc 0
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "with the commit on a branch, --update did not move to $LATEST_TAG"
[ "$(git -C "$H/.apex-skills" rev-parse my-work)" = "$mine" ] || err "the branch my-work lost the local commit"
finish_case

new_case IW1 "a path in the way of a managed directory (a file or a dangling symlink at ~/.claude, a file at <project>/.claude) or an unreadable one: listed (exit 3), never a crash"
echo "my file" > "$H/.claude"
for args in "--claude-only" "--claude-only --no-steering"; do
  read -r -a argv <<< "$args"
  run_cli "${argv[@]}"
  expect_rc 3
  expect_stderr "Skipped 1 path(s) that already exist"
  expect_stderr "$H/.claude$"
  expect_no_out "ENOTDIR"
  expect_no_out "permission denied"
  [ "$(cat "$H/.claude")" = "my file" ] || err "'$args' changed the file at ~/.claude"
done
H="$WORK/IW1/home-b"; mkdir -p "$H"
ln -s "$H/nowhere" "$H/.claude"
run_cli --claude-only
expect_rc 3
expect_stderr "$H/.claude$"
expect_no_out "ENOENT"
expect_link "$H/.claude" "$H/nowhere"
H="$WORK/IW1/home-c"; mkdir -p "$H/.claude" "$H/proj"
echo "my project file" > "$H/proj/.claude"
RUN_CWD="$H/proj" run_cli --project --claude-only
expect_rc 3
expect_stderr "$H/proj/.claude$"
expect_no_out "ENOTDIR"
[ "$(cat "$H/proj/.claude")" = "my project file" ] || err "--project changed the file at <project>/.claude"
if [ "$(id -u)" -ne 0 ]; then
  H="$WORK/IW1/home-d"; mkdir -p "$H/.claude" "$H/.kiro"
  run_cli -y
  expect_rc 0
  chmod 000 "$H/.claude/skills"
  run_cli --update
  expect_rc 3
  expect_stderr "permission denied"
  expect_stderr "$H/.claude/skills$"
  expect_no_out "EACCES"
  run_cli --uninstall
  expect_rc 3
  expect_no_out "EACCES"
  chmod 755 "$H/.claude/skills"
  [ "$(count_resolving_links "$H/.kiro/skills")" -eq 0 ] || err "--uninstall stopped before the Kiro skill links"
  [ "$(count_resolving_links "$H/.claude/skills")" -eq "$LATEST_COUNT" ] || err "the links in the unreadable directory changed"
  [ "$(mfq "$(manifest_of)" 'Object.keys((m.bases[b] && m.bases[b].areas["claude-skills"]) || {}).length')" -eq "$LATEST_COUNT" ] || err "the records of the links in the unreadable directory were dropped"
  run_cli --uninstall
  expect_rc 0
  [ "$(count_resolving_links "$H/.claude/skills")" -eq 0 ] || err "--uninstall, once the directory was readable, left the Claude skill links"
else
  echo "    (unreadable directory part skipped: running as root, which ignores chmod)"
fi
finish_case

new_case AD1 "no advice says to remove ~/.apex-skills: a directory that is not a clone, an unreadable clone, a failed update with only ignored files"
mkdir -p "$H/.claude" "$H/.apex-skills/skills/mine"
echo "my skill" > "$H/.apex-skills/skills/mine/SKILL.md"
for args in "-y --claude-only" "--update --claude-only"; do
  read -r -a argv <<< "$args"
  run_cli "${argv[@]}"
  expect_rc 1
  expect_stderr "not a git clone or cannot be read"
  expect_stderr "mv ~/.apex-skills ~/.apex-skills.old"
  expect_no_out "removing"
  [ "$(cat "$H/.apex-skills/skills/mine/SKILL.md")" = "my skill" ] || err "'$args' changed the user's file"
done
H="$WORK/AD1/home-b"; mkdir -p "$H/.claude"
run_cli --branch "$FIXTURE_BRANCH" --claude-only
expect_rc 0
# a report the user saved in the clone, which git ignores, and an origin that fails
mkdir -p "$H/.apex-skills/reports"
echo "my report" > "$H/.apex-skills/reports/EKS-Upgrade-Assessment-prod.md"
echo "reports/" >> "$H/.apex-skills/.git/info/exclude"
git -C "$H/.apex-skills" remote set-url origin "file://$WORK/AD1/no-such-origin"
run_cli --update --claude-only
expect_rc 1
expect_stderr "mv ~/.apex-skills ~/.apex-skills.old"
expect_no_out "removing"
[ "$(cat "$H/.apex-skills/reports/EKS-Upgrade-Assessment-prod.md")" = "my report" ] || err "--update changed the ignored report"
if [ "$(id -u)" -ne 0 ]; then
  H="$WORK/AD1/home-c"; mkdir -p "$H/.claude"
  run_cli --claude-only
  expect_rc 0
  chmod 000 "$H/.apex-skills"
  run_cli --update --claude-only
  chmod 755 "$H/.apex-skills"
  expect_rc 1
  expect_stderr "mv ~/.apex-skills ~/.apex-skills.old"
  expect_no_out "removing"
fi
finish_case

new_case PN1 "a --version pin: a later plain run or --update moves it to the latest release; passing --version again keeps it"
mkdir -p "$H/.kiro"
run_cli --version "$FIXTURE_TAG" --kiro-only
expect_rc 0
run_cli --version "$FIXTURE_TAG" --kiro-only -y
expect_rc 0
[ "$(install_head)" = "$(commit_of "$FIXTURE_TAG")" ] || err "passing --version $FIXTURE_TAG again did not keep the pin"
run_cli --kiro-only -y
expect_rc 0
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "a plain run did not move the pin to $LATEST_TAG"
expect_stdout "Updated to the latest v1 release, $LATEST_TAG"
finish_case

new_case NS1 "steering installed, then --no-steering, then --update: the line counts the steering entries still recorded as installed; nothing is removed"
mkdir -p "$H/.claude" "$H/.kiro"
STDIN_TEXT=$'y\n' run_cli
expect_rc 0
ns_before="$(cd "$H" && find .claude .kiro | LC_ALL=C sort)"
run_cli --no-steering
expect_rc 0
run_cli --update
expect_rc 0
expect_stdout "Steering is off, as chosen at install (--no-steering or n): the Kiro copies are not updated and the Claude Code links follow the clone; $((2 + WF_COUNT)) steering entries from an earlier install are still recorded as installed (to remove them: --uninstall, then install with --no-steering)"
expect_no_out "Steering stays off"
[ "$(cd "$H" && find .claude .kiro | LC_ALL=C sort)" = "$ns_before" ] || err "--no-steering or --update added or removed paths: $(diff <(echo "$ns_before") <(cd "$H" && find .claude .kiro | LC_ALL=C sort) | head -n 5 | tr '\n' ' ')"
[ -e "$H/.claude/apex-steering/workflows/new-skill.md" ] || err "~/.claude/apex-steering was removed"
[ "$(find "$H/.kiro/steering" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')" -eq "$WF_COUNT" ] || err "Kiro steering copies were removed"
finish_case

new_case BF1 "--branch of a local branch that cannot fast-forward: the message says the clone is now on that branch and how to go back"
mkdir -p "$H/.claude"
run_cli --claude-only
expect_rc 0
# a local branch of that name with a commit of its own, made from the release,
# so it and origin's branch each have commits the other lacks
"${GITC[@]}" -C "$H/.apex-skills" checkout -q -b "$FIXTURE_BRANCH"
echo "my work" > "$H/.apex-skills/MINE.md"
"${GITC[@]}" -C "$H/.apex-skills" add MINE.md
"${GITC[@]}" -C "$H/.apex-skills" commit -q -m "my local commit"
"${GITC[@]}" -C "$H/.apex-skills" checkout -q --detach "$LATEST_TAG"
run_cli --branch "$FIXTURE_BRANCH" --claude-only
expect_rc 1
expect_stderr "The local branch $FIXTURE_BRANCH in ~/.apex-skills cannot fast-forward to origin/$FIXTURE_BRANCH"
expect_stderr "~/.apex-skills is now on the local branch $FIXTURE_BRANCH, so the installed skills come from it"
expect_stderr "To go back, run: npx apex-skills --version $LATEST_TAG"
expect_no_out "Failed to check out branch"
[ "$(install_branch)" = "$FIXTURE_BRANCH" ] || err "the clone is on '$(install_branch)', not the local branch $FIXTURE_BRANCH the message names"
run_cli --version "$LATEST_TAG" --claude-only
expect_rc 0
[ "$(install_head)" = "$(commit_of "$LATEST_TAG")" ] || err "the go-back command did not return the clone to $LATEST_TAG"
# the clone already on that local branch (no detach): HEAD does not move, so
# there is no "is now on the local branch" line
H="$WORK/BF1/home-b"; mkdir -p "$H/.claude"
run_cli --claude-only
expect_rc 0
"${GITC[@]}" -C "$H/.apex-skills" checkout -q -b "$FIXTURE_BRANCH"
echo "my work" > "$H/.apex-skills/MINE.md"
"${GITC[@]}" -C "$H/.apex-skills" add MINE.md
"${GITC[@]}" -C "$H/.apex-skills" commit -q -m "my local commit"
bf_mine="$(install_head)"
run_cli --branch "$FIXTURE_BRANCH" --claude-only
expect_rc 1
expect_stderr "Not possible to fast-forward"
expect_no_out "is now on the local branch"
expect_no_out "To go back, run"
[ "$(install_branch)" = "$FIXTURE_BRANCH" ] || err "the clone left the local branch $FIXTURE_BRANCH: on '$(install_branch)'"
[ "$(install_head)" = "$bf_mine" ] || err "HEAD moved off the local commit"
finish_case

new_case NS2 "edited Kiro copies are the only steering entries left after --no-steering and --uninstall: --update names them for removal by hand; one unedited entry reads in the singular"
mkdir -p "$H/.claude" "$H/.kiro"
run_cli -y
expect_rc 0
ns2_f="$(find "$H/.kiro/steering" -maxdepth 1 -name '*.md' | LC_ALL=C sort | sed -n 1p)"
cp "$ns2_f" "$WORK/NS2/orig.md"
echo "my edit" >> "$ns2_f"
run_cli --no-steering
expect_rc 0
run_cli --uninstall
expect_rc 3
[ -f "$ns2_f" ] || err "--uninstall removed the edited copy $ns2_f"
run_cli --update
expect_rc 0
expect_stdout "Steering is off, as chosen at install (--no-steering or n): the Kiro copies are not updated and the Claude Code links follow the clone; 1 steering entry from an earlier install was changed since it was installed, so --uninstall keeps it; to remove it, delete it by hand (the next --uninstall then clears its record):"
expect_stdout "^    $ns2_f$"
expect_no_out "to remove them: --uninstall"
expect_no_out "1 steering entries"
# the copy unedited again: --uninstall can remove it, and the line says so, in the singular
cp "$WORK/NS2/orig.md" "$ns2_f"
run_cli --update
expect_rc 0
expect_stdout "Steering is off, as chosen at install (--no-steering or n): the Kiro copies are not updated and the Claude Code links follow the clone; 1 steering entry from an earlier install is still recorded as installed (to remove it: --uninstall, then install with --no-steering)"
expect_no_out "delete it by hand"
run_cli --uninstall
expect_rc 0
[ ! -e "$ns2_f" ] || err "--uninstall did not remove the unedited copy $ns2_f"
finish_case

new_case UK1 "--uninstall names rm -rf ~/.apex-skills only when no other install base uses the clone"
mkdir -p "$H/.claude" "$H/proj"
run_cli --claude-only
RUN_CWD="$H/proj" run_cli --project --claude-only
expect_rc 0
RUN_CWD="$H/proj" run_cli --uninstall --project
expect_rc 0
expect_no_out "rm -rf"
expect_stdout "~/.apex-skills is still used by the install in $H; keep it"
run_cli --uninstall
expect_rc 0
expect_stdout "To remove it too, once nothing else uses it (this run sees only the installs the manifest records; installs made before 1.3.0 are not recorded): rm -rf ~/.apex-skills"
expect_no_out "still used by"
# the other way round: the global uninstall names the project install
H="$WORK/UK1/home-b"; mkdir -p "$H/.claude" "$H/proj"
run_cli --claude-only
RUN_CWD="$H/proj" run_cli --project --claude-only
run_cli --uninstall
expect_rc 0
expect_no_out "rm -rf"
expect_stdout "~/.apex-skills is still used by the install in $H/proj; keep it"
# a single install, then --uninstall
H="$WORK/UK1/home-c"; mkdir -p "$H/.claude"
run_cli --claude-only
run_cli --uninstall
expect_rc 0
expect_stdout "To remove it too, once nothing else uses it (this run sees only the installs the manifest records; installs made before 1.3.0 are not recorded): rm -rf ~/.apex-skills"
expect_no_out "still used by"
finish_case

new_case UK2 "--uninstall --claude-only after a Claude and Kiro install: no rm -rf line while the base still records the Kiro entries"
mkdir -p "$H/.claude" "$H/.kiro"
run_cli -y
expect_rc 0
run_cli --uninstall --claude-only
expect_rc 0
expect_no_out "rm -rf"
expect_no_out "still used by"
[ "$(count_resolving_links "$H/.kiro/skills")" -eq "$LATEST_COUNT" ] || err "the Kiro skill links do not all resolve after --uninstall --claude-only"
[ "$(find "$H/.kiro/steering" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')" -eq "$WF_COUNT" ] || err "Kiro steering copies were removed by --uninstall --claude-only"
run_cli --uninstall --kiro-only
expect_rc 0
expect_stdout "To remove it too, once nothing else uses it (this run sees only the installs the manifest records; installs made before 1.3.0 are not recorded): rm -rf ~/.apex-skills"
finish_case

new_case UK3 "a partial --uninstall (a read-only ~/.claude/skills, with and without a manifest): no rm -rf line while anything was kept"
for mode in record no-manifest; do
  H="$WORK/UK3/home-$mode"; mkdir -p "$H/.claude"
  run_cli --claude-only -y
  expect_rc 0
  if [ "$mode" = no-manifest ]; then rm -f "$(manifest_of)"; fi
  chmod 555 "$H/.claude/skills"
  run_cli --uninstall
  expect_rc 3
  expect_stderr "permission denied"
  expect_no_out "rm -rf"
  chmod 755 "$H/.claude/skills"
  run_cli --uninstall
  expect_rc 0
  expect_stdout "To remove it too, once nothing else uses it (this run sees only the installs the manifest records; installs made before 1.3.0 are not recorded): rm -rf ~/.apex-skills"
done
finish_case

# A listing (path, type, link text, size, mode) and the content of every file.
tree_sum() { # <dir>
  (cd "$1" && find . -printf '%p %y %l %s %m\n' | LC_ALL=C sort && find . -type f -exec md5sum {} + | LC_ALL=C sort) | md5sum
}
new_case SC1 "--claude-only -y and --kiro-only -y with both ~/.claude and ~/.kiro present leave the other tree byte-identical"
for scope in claude kiro; do
  H="$WORK/SC1/home-$scope"
  mkdir -p "$H/.claude/skills/my-skill" "$H/.claude/commands" "$H/.kiro/skills/my-skill" "$H/.kiro/steering"
  echo "mine" > "$H/.claude/skills/my-skill/SKILL.md"
  echo "mine" > "$H/.kiro/skills/my-skill/SKILL.md"
  echo "my steering" > "$H/.kiro/steering/mine.md"
  if [ "$scope" = claude ]; then other=.kiro; else other=.claude; fi
  sc_before="$(tree_sum "$H/$other")"
  run_cli "--$scope-only" -y
  expect_rc 0
  [ "$(tree_sum "$H/$other")" = "$sc_before" ] || err "--$scope-only -y changed ~/$other: $(cd "$H/$other" && find . -newer "$H/$other/skills/my-skill/SKILL.md" | head -n 5 | tr '\n' ' ')"
  [ "$(count_resolving_links "$H/.$scope/skills")" -eq "$LATEST_COUNT" ] || err "--$scope-only -y did not install $LATEST_COUNT skill links in ~/.$scope/skills"
done
finish_case

new_case RW1 "a read-only directory over recorded entries (a stale skill link, Kiro copies the prune removes): with write access back, --uninstall leaves no installer entry"
mkdir -p "$H/.claude"
run_cli --claude-only
expect_rc 0
# an absolute link into the clone: a stale spelling the next run replaces
ln -sfn "$H/.apex-skills/skills/$SKILL_A" "$H/.claude/skills/$SKILL_A"
chmod 555 "$H/.claude/skills"
run_cli --update --claude-only
expect_rc 3
expect_stderr "permission denied"
expect_stderr "$H/.claude/skills/$SKILL_A$"
chmod 755 "$H/.claude/skills"
run_cli --uninstall --claude-only
expect_rc 0
for d in "$H/.claude/skills" "$H/.claude/commands" "$H/.claude"; do
  n="$(links_into_install "$d")"; [ "$n" -eq 0 ] || err "$n installer links remain in $d after --uninstall"
done
# Kiro copies the prune cannot remove (no steering/ in $V2_TAG)
H="$WORK/RW1/home-b"; mkdir -p "$H/.kiro"
run_cli --kiro-only -y
expect_rc 0
chmod 555 "$H/.kiro/steering"
run_cli --version "$V2_TAG" --kiro-only
expect_rc 3
expect_stderr "permission denied"
chmod 755 "$H/.kiro/steering"
run_cli --uninstall --kiro-only
expect_rc 0
n="$(find "$H/.kiro/steering" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')"; [ "$n" -eq 0 ] || err "$n Kiro steering copies remain after --uninstall"
n="$(links_into_install "$H/.kiro/skills")"; [ "$n" -eq 0 ] || err "$n installer links remain in ~/.kiro/skills after --uninstall"
finish_case

new_case KD1 "a Kiro copy whose write fails with a disk error (not a refused write): exit 1 with that error, not listed as a path in the way"
mkdir -p "$H/.kiro"
run_cli --kiro-only
expect_rc 0
kd1_preload="$WORK/KD1/nospace.cjs"
cat > "$kd1_preload" <<'JS'
// The write of one Kiro copy fails as a full disk would, after cutting the file short.
const fs = require('fs');
const write = fs.writeFileSync;
fs.writeFileSync = (p, data, ...rest) => {
  if (String(p).endsWith('/.kiro/steering/new-skill.md')) {
    write(p, String(data).slice(0, 10));
    const e = new Error('simulated ENOSPC: no space left on device'); e.code = 'ENOSPC'; throw e;
  }
  return write(p, data, ...rest);
};
require('module').syncBuiltinESMExports();
JS
# An up-to-date copy is not written again, so remove it: the update writes it.
rm "$H/.kiro/steering/new-skill.md"
PRELOAD="$kd1_preload" run_cli --update --kiro-only
expect_rc 1
expect_stderr "simulated ENOSPC"
expect_no_out "already exist and were not created by this installer"
finish_case

new_case UB1 "--uninstall under a read-only ~/.kiro/steering lists the copies it could not remove once, not also as marked files that are not a recorded copy"
mkdir -p "$H/.kiro"
run_cli --kiro-only
expect_rc 0
chmod 555 "$H/.kiro/steering"
run_cli --uninstall --kiro-only
expect_rc 3
expect_stderr "Could not write or read $WF_COUNT path(s)"
expect_stderr "steering/new-skill.md$"
expect_no_out "not a recorded copy of a current workflow"
chmod 755 "$H/.kiro/steering"
finish_case

new_case NS3 "steering off with some, not all, leftover steering entries edited: the line counts the edited ones and says --uninstall keeps them"
mkdir -p "$H/.claude" "$H/.kiro"
run_cli -y
expect_rc 0
ns3_f="$(find "$H/.kiro/steering" -maxdepth 1 -name '*.md' | LC_ALL=C sort | sed -n 1p)"
echo "my edit" >> "$ns3_f"
run_cli --no-steering
expect_rc 0
run_cli --update
expect_rc 0
expect_stdout "$((2 + WF_COUNT)) steering entries from an earlier install are still recorded as installed (to remove them: --uninstall, then install with --no-steering) (1 of them changed since; --uninstall keeps and lists those)"
finish_case

new_case UR1 "--uninstall after a --claude-only install names the Kiro paths the record lacks and leaves what is there"
mkdir -p "$H/.claude"
run_cli --claude-only
expect_rc 0
mkdir -p "$H/.kiro/skills"
ln -s "../../.apex-skills/skills/$SKILL_A" "$H/.kiro/skills/$SKILL_A"
run_cli --uninstall
expect_rc 0
expect_stdout "Nothing recorded for $H/.kiro/skills in this install's record; anything there is left as it is."
expect_stdout "Nothing recorded for $H/.kiro/steering in this install's record; anything there is left as it is."
expect_no_out "Nothing recorded for $H/.claude"
[ -L "$H/.kiro/skills/$SKILL_A" ] || err "--uninstall removed a link in ~/.kiro/skills that the record lacks"
finish_case

new_case UF1 "--uninstall with a plain file at ~/.apex-skills: says it is not a git clone, no rm -rf line"
mkdir -p "$H/.claude"
run_cli --claude-only
expect_rc 0
run_cli --uninstall
expect_rc 0
rm -rf "$H/.apex-skills"
echo "my file" > "$H/.apex-skills"
run_cli --uninstall
expect_rc 0
expect_stdout "$H/.apex-skills is not a git clone or cannot be read, so the installer leaves it alone"
expect_no_out "Repository still at"
expect_no_out "rm -rf"
[ "$(cat "$H/.apex-skills")" = "my file" ] || err "--uninstall changed the file at ~/.apex-skills"
finish_case

new_case KR1 "a read-only Kiro copy that already holds this release's text, as recorded: not written again, exit 0"
mkdir -p "$H/.kiro"
run_cli --kiro-only
expect_rc 0
kr1_f="$H/.kiro/steering/new-skill.md"
chmod 444 "$kr1_f"
run_cli --update --kiro-only
expect_rc 0
expect_no_out "Could not write"
[ "$(mfq "$(manifest_of)" "Boolean(b && m.bases[b].areas['kiro-steering']['$kr1_f'])")" = true ] || err "the record lost the up-to-date copy $kr1_f"
chmod 644 "$kr1_f"
finish_case

new_case KM1 "recorded Kiro copies that lost their marker (one emptied, one replaced): listed once, as changed since, and kept"
mkdir -p "$H/.kiro"
run_cli --kiro-only
expect_rc 0
km1_a="$H/.kiro/steering/new-skill.md"
: > "$km1_a"
run_cli --update --kiro-only
expect_rc 3
expect_stderr "Kept 1 path(s) the installer created that were changed since"
expect_no_out "not created by this installer"
[ ! -s "$km1_a" ] || err "the emptied copy was written again"
# phase 2, a fresh HOME: the same copy replaced instead of emptied
H="$WORK/KM1/home2"
mkdir -p "$H/.kiro"
run_cli --kiro-only
expect_rc 0
km1_b="$H/.kiro/steering/new-skill.md"
echo "my own notes" > "$km1_b"
run_cli --update --kiro-only
expect_rc 3
expect_stderr "Kept 1 path(s) the installer created that were changed since"
expect_no_out "not created by this installer"
[ "$(cat "$km1_b")" = "my own notes" ] || err "the replaced copy was written again"
finish_case

new_case T1 "harness self-test: an installer that never exits is killed at RUN_TIMEOUT"
hang_preload="$WORK/T1/hang.cjs"
printf 'Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 600000);\n' > "$hang_preload"
EXPECT_TIMEOUT=1 RUN_TIMEOUT=3 PRELOAD="$hang_preload" run_cli --help
[ "$RC" -eq 142 ] || err "expected the timeout exit 142, got $RC"
[ "$RUN_SECS" -le 10 ] || err "the timeout took ${RUN_SECS}s"
finish_case

new_case T2 "harness self-test: the frontmatter check rejects unclosed, empty and inclusion-less frontmatter"
mkdir -p "$WORK/T2"
printf -- '---\ninclusion: manual\n---\nbody\n' > "$WORK/T2/good.md"
printf -- '---\ninclusion: manual\nbody, no closing line\n' > "$WORK/T2/unclosed.md"
printf -- '---\ninclusion: manual\n' > "$WORK/T2/unclosed-eof.md"
printf '' > "$WORK/T2/empty-file.md"
printf -- '---\n---\nbody\n' > "$WORK/T2/empty-frontmatter.md"
printf -- '---\nname: x\n---\ninclusion: manual\n' > "$WORK/T2/no-inclusion.md"
fm_manual "$WORK/T2/good.md" || err "good.md was rejected"
for f in unclosed unclosed-eof empty-file empty-frontmatter no-inclusion; do
  if fm_manual "$WORK/T2/$f.md"; then err "$f.md passed the frontmatter check"; fi
done
finish_case

echo
echo "SUMMARY: $PASS passed, $FAIL failed${FAILED_CASES:+ (failed:$FAILED_CASES)}"
[ "$FAIL" -eq 0 ]
