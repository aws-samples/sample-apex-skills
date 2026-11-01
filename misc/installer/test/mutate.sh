#!/usr/bin/env bash
# Mutation gate for the installer harness (misc/installer/test/install-paths.sh).
#
# Each mutant is a copy of bin/cli.mjs with one deliberate defect. The harness
# runs against every mutant and must fail; a mutant that passes ("survived")
# means a behavior the harness claims to cover is not really tested. A green
# run shows only that the listed mutants are killed, not that every behavior
# of the installer is tested. A kill means only that the harness ran and
# reported at least one failed case (its SUMMARY line); a harness that stops
# with no such line (a crash before the cases, a signal, or a hang killed at
# the limit below) is reported as "HARNESS DID NOT RUN" and fails the gate.
# Each harness run, the baseline included, is killed after
# MUTATE_HARNESS_TIMEOUT seconds (default 1200, about nine times the slowest
# pass measured below; set it to a whole number of seconds, 1 or more: 0, a
# fraction below 1 or a value that is not a number turns the limit off, and a
# negative value stops the harness from running, so the run ends at BASELINE
# FAIL, exit 1); inside the harness, the --help start check and each
# installer run have their own 60 s limit. Without these limits a hang would
# be caught only by the CI job's timeout. No mutant names the cases that
# should fail. Read each "killed by:" list: one that only a timeout or load
# explains is not a kill; rerun that mutant with --only. Run it
# before each review of an installer change; CI also runs it every week
# (.github/workflows/installer-mutation.yml). It runs the whole harness once
# per mutant. One pass took 99 to 135 s with 113 cases (119 at this head) on
# one 16-CPU Linux machine on 2026-10-20 (the harness runs its cases one at a
# time; a pass takes longer when a mutant makes an installer run hang until
# its 60 s limit). With 115 mutants and the baseline, the 116 passes take
# about 191 to 261 minutes there, so the weekly job may stop at its
# 240-minute cap (timeout-minutes in installer-mutation.yml) on a
# GitHub-hosted runner, where a pass has not been timed. A job stopped at the
# cap is a timeout, not a surviving mutant: rerun each mutant it did not
# reach with --only <ID> (one ID per run).
#
# Usage: misc/installer/test/mutate.sh [--only <ID>]
# Exit: 0 every mutant killed; 1 a mutant survived, did not apply, or the
# harness did not run for it, or the unmutated baseline failed; 2 a bad
# argument, or --only names no mutant.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/../bin/cli.mjs"
PKG="$SCRIPT_DIR/../package.json"
HARNESS="$SCRIPT_DIR/install-paths.sh"
ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --only) ONLY="$2"; shift 2 ;;
    -h|--help) sed -n '2,/^set -u$/p' "$0" | sed '$d'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

WORK="$(mktemp -d "${TMPDIR:-/tmp}/apex-mutate.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
LIMIT="${MUTATE_HARNESS_TIMEOUT:-1200}"
# Run the harness under the time limit; perl's alarm works where timeout(1) is
# missing (macOS), and a run it kills exits 142.
harness() { # <cli.mjs> <scratch dir>
  perl -e 'alarm shift @ARGV; exec @ARGV or exit 127' "$LIMIT" bash "$HARNESS" --cli "$1" --work "$2"
}

# [id, the defect, exact text in cli.mjs (must occur once), replacement]
cat > "$WORK/mutants.cjs" <<'EOF'
module.exports = [
  ['git-prompt', 'git may prompt for credentials',
    "GIT_TERMINAL_PROMPT: '0'", "GIT_TERMINAL_PROMPT: process.env.GIT_TERMINAL_PROMPT || ''"],
  ['git-env-leak', 'GIT_DIR and friends from the caller reach git',
    'delete GIT_ENV[key];', 'void key;'],
  ['absolute-links', 'links are absolute again',
    'symlinkSync(want, linkPath);', 'symlinkSync(resolve(target), linkPath);'],
  ['logical-relative', 'relative link text computed from the logical, not the real, directory',
    'return relative(realPath(dirname(linkPath)), realPath(target));', 'return relative(dirname(linkPath), target);'],
  ['project-relative', '--project links are relative, so a moved project breaks them',
    'if (absoluteLinks) return resolve(target);', ''],
  ['skip-exit-0', 'skipped paths exit 0',
    'const EXIT_SKIPPED = 3;', 'const EXIT_SKIPPED = 0;'],
  ['usage-exit-1', 'bad flags exit 1',
    'const EXIT_USAGE = 2;', 'const EXIT_USAGE = 1;'],
  ['unknown-flag-ignored', 'unknown flags are ignored',
    "throw new UsageError(arg.startsWith('-') ?", "if (false) throw new UsageError(arg.startsWith('-') ?"],
  ['contradiction-allowed', '--claude-only with --kiro-only is accepted',
    'if (flags.claudeOnly && flags.kiroOnly) {', 'if (false) {'],
  ['stderr-to-stdout', 'warnings and errors go to stdout',
    'const logErr = (msg) => console.error(msg);', 'const logErr = (msg) => console.log(msg);'],
  ['yes-ignored', '-y does not skip the prompts',
    'assumeYes = flags.yes || flags.update;', 'assumeYes = flags.update;'],
  ['update-prompts', '--update asks for a target when neither ~/.claude nor ~/.kiro exists',
    'assumeYes = flags.yes || flags.update;', 'assumeYes = flags.yes;'],
  ['manifest-not-saved', 'the install manifest is never written',
    'saveManifest(run.manifest);', 'void run.manifest;'],
  ['manifest-loss-exit-0', 'a manifest that cannot be saved exits 0',
    '|| blocked.length > 0 || manifestLost;', '|| blocked.length > 0;'],
  ['copy-hash-ignored', 'an edited Kiro copy counts as unchanged',
    'return st.isFile() && sha256(readFileSync(p)) === e.sha256;', 'return st.isFile();'],
  ['uninstall-unchecked', '--uninstall removes recorded paths without checking them',
    'if (entryMatches(p, e)) { if (tryUnlink(p)) removed++; else keep[p] = e; } else if (lstatOrNull(p)) { changed.push(p); keep[p] = e; }', 'if (lstatOrNull(p)) { if (tryUnlink(p)) removed++; }'],
  ['uninstall-drops-kept', '--uninstall drops the record of a path it kept',
    'if (Object.keys(keep).length > 0) rec.areas[area] = keep; else delete rec.areas[area];', 'delete rec.areas[area];'],
  ['no-dangling-sweep', '--uninstall with a record leaves dangling installer links the record lacks',
    'if (areaDir[area]) sweepDangling(areaDir[area]);', ''],
  ['no-prune', 'recorded links of skills missing from a pinned release are kept',
    'if (tryUnlink(p)) pruned++; else record(area, p, e);', 'void e;'],
  ['crash-replaces', 'a run that stops part way replaces an area record with its partial set',
    'crashed ? { ...(prev.areas[area] || {}), ...entries } : entries', 'entries'],
  ['install-overwrites-edit', 'install and --update overwrite an edited recorded Kiro copy',
    'else if (st && !entryMatches(dest, current) && keepIfEdited(area, dest, prev && prev[dest])) continue;', ''],
  ['prune-edit-silent', 'the prune keeps an edited recorded Kiro copy without listing it',
    'if (!entryMatches(p, e)) { if (!keepIfEdited(area, p, e) && keepUnreadable(p)) record(area, p, e); continue; }', 'if (!entryMatches(p, e)) continue;'],
  ['edit-not-carried', 'a kept edited Kiro copy drops out of the manifest',
    '  record(area, p, e);\n  return true;', '  return true;'],
  ['any-link-is-ours', 'every link at an install path is replaced',
    'return [resolve(INSTALL_DIR), realPath(INSTALL_DIR)].some(', 'return true || [resolve(INSTALL_DIR), realPath(INSTALL_DIR)].some('],
  ['dangling-dir-ok', 'a dangling skills-dir symlink is treated as a directory',
    'if (isDir) return true;', 'if (isDir || st) return true;'],
  ['eacces-crash', 'a read-only skills directory stops the run',
    '    cannotWrite(linkPath, e);', '    throw e;'],
  ['kiro-eacces-crash', 'a read-only Kiro steering directory stops the run',
    '      cannotWrite(dest, e);', '      throw e;'],
  ['corrupt-not-kept', 'a corrupt manifest is not set aside',
    'try { renameSync(MANIFEST_FILE, kept); moved = true; }', 'try { moved = false; }'],
  ['manifest-outside-base', 'a manifest entry outside the base is trusted',
    'if (!insideBase(base, p) || !validEntry(e)) return false;', 'if (!isAbsolute(p) || !validEntry(e)) return false;'],
  ['dotdot-entry', 'a manifest entry spelled with .. is trusted',
    'if (!isAbsolute(p) || resolve(p) !== p) return false;', 'if (!isAbsolute(p)) return false;'],
  ['relative-xdg', 'a relative XDG_STATE_HOME is used',
    'return xdg && isAbsolute(xdg) ?', 'return xdg ?'],
  ['update-forgets-steering', '--update forgets the no-steering choice',
    'if (doSteering && keepsChoice && steeringOff) {', 'if (false) {'],
  ['hint-no-ref', 'the steering-off hint does not name the clone\'s ref',
    'to add it, run npx apex-skills ${keepRef} (without --update', 'to add it, run npx apex-skills (without --update'],
  ['edited-steering-uninstall-advice', 'with only edited steering entries left, the steering-off line still says --uninstall removes them',
    'if (n > 0 && edited.length === n) {', 'if (false) {'],
  ['steering-plural-one', 'one steering entry left reads in the plural',
    "${n === 1 ? '1 steering entry from an earlier install is still recorded as installed (to remove it' :", "${n === 1 ? '1 steering entries from an earlier install are still recorded as installed (to remove them' :"],
  ['uninstall-hint-ignores-record', '--uninstall names rm -rf ~/.apex-skills while this base still records entries',
    'else if (!manifest.bases[base] && !keptSome) info(', 'else if (!keptSome) info('],
  ['uninstall-hint-ignores-kept', '--uninstall names rm -rf ~/.apex-skills when it kept paths',
    'else if (!manifest.bases[base] && !keptSome) info(', 'else if (!manifest.bases[base]) info('],
  ['branch-moves-always', 'a --branch that cannot fast-forward says HEAD moved when it was already on that branch',
    "const moves = !gitOk(['symbolic-ref', '-q', 'HEAD']) || git(['symbolic-ref', '--short', '-q', 'HEAD']).trim() !== branch;", 'const moves = true;'],
  ['closed-stdin-hangs', 'closed stdin no longer takes the defaults',
    "if (!defaultsNoted) { info('No input on stdin, so the default answers are used'); defaultsNoted = true; }\n        res(defaultVal);", "return;"],
  ['home-unchecked', 'an empty or relative HOME is used',
    'if (!isAbsolute(HOME)) {', 'if (false) {'],
  ['dash-url', 'a repository URL starting with - is accepted',
    "if (REPO_URL.startsWith('-')) {", 'if (false) {'],
  ['mkdir-early', '~/.claude is created before the clone succeeds',
    'const createDirs = [];', 'const createDirs = []; const pushDir = createDirs.push.bind(createDirs); createDirs.push = (d) => { mkdirSync(d, { recursive: true }); return pushDir(d); };'],
  ['no-git-ok', 'no git in PATH exits 0',
    "error('git is required but not found in PATH.');\n    return EXIT_ERROR;", "error('git is required but not found in PATH.');\n    return EXIT_OK;"],
  ['windows-stdout', 'the Windows stop goes to stdout',
    "error('Native Windows is not supported", "log('Native Windows is not supported"],
  ['help-missing-flag', '--help leaves out --uninstall',
    '  log(`  --uninstall          Remove installed links and steering copies (keeps cloned repo); honours`);\n  log(`                       --project, --claude-only and --kiro-only`);\n', ''],
  ['prune-silent', 'the prune of skills that left the release is not reported',
    'if (pruned > 0) info(`Removed ${pruned} links', 'if (false) info(`Removed ${pruned} links'],
  ['not-clone-typeerror', 'a ~/.apex-skills that is not a clone ends in a TypeError',
    "warn(`~/.apex-skills is not a git clone or cannot be read, so the installer leaves it alone; ${MOVE_ASIDE}`);\n  return new Error(`${INSTALL_DIR} is not a git clone or cannot be read`);", 'null.x;'],
  ['not-clone-silent', 'a ~/.apex-skills that is not a clone gets no advice',
    "  warn(`~/.apex-skills is not a git clone or cannot be read, so the installer leaves it alone; ${MOVE_ASIDE}`);\n", ''],
  ['manifest-unreadable-empty', 'a manifest that cannot be read is taken as empty and saved over',
    "if (e.code === 'ENOENT') return null;", 'return null;'],
  ['dirty-not-checked', 'changed files in the clone are not checked before HEAD moves',
    'const files = localChanges(false);', 'const files = [];'],
  ['advice-ignores-changes', 'a failed update advises removing a clone that holds the user\'s files',
    'const files = localChanges(true);', 'const files = [];'],
  ['tty-close-defaults', 'Ctrl-C or Ctrl-D at a terminal question takes the defaults and installs',
    'if (line === null && process.stdin.isTTY) {', 'if (line === null && false) {'],
  ['cancel-exit-1', 'a cancelled run exits 1, not 130',
    'const EXIT_CANCELLED = 130;', 'const EXIT_CANCELLED = 1;'],
  ['claude-only-writes-kiro', '--claude-only also installs into an existing ~/.kiro',
    'let installKiro = !flags.claudeOnly && existsSync(kiroDir);', 'let installKiro = existsSync(kiroDir);'],
  ['stale-link-record-lost', 'a stale installer link that cannot be removed drops out of the manifest',
    "if (!tryUnlink(linkPath)) { record(area, linkPath, { kind: 'link', target: readlinkSync(linkPath) }); return 'conflict'; }", "if (!tryUnlink(linkPath)) { return 'conflict'; }"],
  ['prune-record-lost', 'a recorded entry the prune cannot remove drops out of the manifest',
    'if (tryUnlink(p)) pruned++; else record(area, p, e);', 'if (tryUnlink(p)) pruned++;'],
  ['unsaved-not-checked', 'commits only HEAD holds are left behind when HEAD moves',
    '  if (unsaved.length > 0) {', '  if (false) {'],
  ['unsaved-after-fetch', 'commits only HEAD holds are read after the fetch, which can move a tag off HEAD',
    'checkTarget(`refs/tags/${tag}`, unsaved);', 'checkTarget(`refs/tags/${tag}`, unsavedCommits());'],
  ['in-the-way-crash', 'a file or dangling symlink in the way of a managed directory stops the run',
    '  const w = inTheWay(p);\n  if (!w) throw e;', '  throw e;'],
  ['in-the-way-misnamed', 'a path in the way of a managed directory is reported as permission denied',
    'const w = writeBlocked(e) ? null : inTheWay(dir);', 'const w = null;'],
  ['create-dir-crash', 'creating ~/.claude or ~/.kiro over a dangling symlink stops the run',
    '    try { mkdirSync(dir, { recursive: true }); } catch (e) { cannotWrite(dir, e); }', '    mkdirSync(dir, { recursive: true });'],
  ['unreadable-dir-crash', 'an unreadable managed directory stops the run',
    '    if (!writeBlocked(e)) throw e;\n    if (!blocked.includes(dir)) blocked.push(dir);\n    return [];', '    throw e;'],
  ['unreadable-uninstall-forgets', '--uninstall drops the records of entries it cannot check',
    ' else if (keepUnreadable(p)) keep[p] = e;', ''],
  ['unreadable-prune-forgets', 'the prune drops the records of entries it cannot check',
    'if (!keepIfEdited(area, p, e) && keepUnreadable(p)) record(area, p, e);', 'keepIfEdited(area, p, e);'],
  ['advice-remove', 'the advice says to remove ~/.apex-skills',
    "const MOVE_ASIDE = 'move it aside (mv ~/.apex-skills ~/.apex-skills.old) and re-run; that keeps everything in it';", "const MOVE_ASIDE = 'try removing ~/.apex-skills and re-running';"],
  ['update-failed-silent', 'a failed update gives no advice',
    "  warn(`Update failed (git's reason is below). Fix the cause and run again: for a network or access failure, check your connection; for a branch that origin does not have, move to a release with --version <tag> or to --branch main. If the clone itself is broken, or holds a local commit on that branch, ${MOVE_ASIDE}.`);\n", ''],
  ['no-skills-check', 'a release with no skills/ is checked out',
    "if (!gitOk(['cat-file', '-e', `${target}:skills`])) {", 'if (false) {'],
  ['update-silent-retag', 'a moved release tag reads as already up to date',
    'else if (headCommit() !== before) success(', 'else if (false) success('],
  ['no-clone-reason', 'kept marked copies with no clone get the wrong reason',
    '(noClone ? keptUnknown : keptCopies).push(p)', 'keptCopies.push(p)'],
  ['default-main', 'a plain install clones main, not the latest v1 release',
    '({ tag: target, names } = latestRelease(REPO_URL, false, major, major !== DEFAULT_MAJOR));', "({ tag: target, names } = { tag: 'main', names: [] });"],
  ['update-follows-main', '--update keeps an older default clone on main',
    "(head.branch !== 'main' || configValue(BRANCH_KEY) === head.branch)", '(true)'],
  ['lexical-order', 'release tags are ordered as strings',
    'if (!best || v[0] > best.v[0] || (v[0] === best.v[0] && v[1] > best.v[1])) best = { name, v };', 'if (!best || name > best.name) best = { name, v };'],
  ['patch-ignored', 'the patch number is ignored when ordering releases',
    '(v[0] === best.v[0] && v[1] > best.v[1])', 'false'],
  ['prerelease-picked', 'pre-release and suffixed tags count as releases',
    'const RELEASE_TAG = /^v(\\d+)\\.(\\d+)\\.(\\d+)$/;', 'const RELEASE_TAG = /^v(\\d+)\\.(\\d+)\\.(\\d+)/;'],
  ['any-major', 'any major line counts as a release of the clone\'s line',
    'if (!m || Number(m[1]) !== major) continue;', 'if (!m) continue;'],
  ['prefixed-tag', 'a tag that ends in vN.x.y counts as a release',
    'const RELEASE_TAG = /^v(\\d+)\\.(\\d+)\\.(\\d+)$/;', 'const RELEASE_TAG = /v(\\d+)\\.(\\d+)\\.(\\d+)$/;'],
  ['no-tag-main', 'with no v1 release tag the install falls back to main',
    '  if (!tag && !allowNone) {\n    error(', "  if (!tag && !allowNone) return { tag: 'main', names };\n  if (!tag && !allowNone) {\n    error("],
  ['branch-not-recorded', '--branch on an existing clone is not remembered',
    "recordRef(flags.version ? 'tag' : 'branch', ref);", "recordRef('tag', ref);"],
  ['fresh-branch-not-recorded', '--branch on a fresh clone is not remembered',
    "recordRef(flags.branch ? 'branch' : 'tag', target);", "recordRef('tag', target);"],
  ['no-migration-note', 'moving a main clone to the release prints no note',
    '      warn(`This install followed branch ${head.branch}, which can hold unreleased changes. It now uses the latest v${major} release, ${tag}.`);\n', ''],
  ['non-release-silent', 'leaving a pre-release pin prints no note',
    '    } else if (!isRelease(from, major)) {', '    } else if (false) {'],
  ['cross-major-quiet', 'leaving a release of another major line prints no note',
    '    } else if (!isRelease(from, major)) {', "    } else if (!RELEASE_TAG.test(from || '')) {"],
  ['recorded-tag-ignored', 'the note names some tag at HEAD, not the pinned one',
    '(recorded && tags.includes(recorded) ? recorded : null) || ', ''],
  ['manifest-ref-dropped', 'the manifest does not record the resolved ref',
    'return { url: REPO_URL, ref: ref || null, commit };', 'return { url: REPO_URL, ref: null, commit };'],
  ['update-stays-v1', '--update moves every tag clone to v1, a v2 clone included',
    'const major = head.branch ? DEFAULT_MAJOR :', 'const major = true ? DEFAULT_MAJOR :'],
  ['manifest-major-used', 'the major line comes from the base\'s manifest record before the clone\'s tag',
    'const major = head.branch ? DEFAULT_MAJOR : (majorOf(head.tag) || DEFAULT_MAJOR);', 'const major = head.branch ? DEFAULT_MAJOR : (majorOf(recordedRef(flags.project ? process.cwd() : HOME)) || majorOf(head.tag) || DEFAULT_MAJOR);'],
  ['head-major-ignored', 'the tag at HEAD does not set the major line',
    '(majorOf(head.tag) || DEFAULT_MAJOR);', 'DEFAULT_MAJOR;'],
  ['prerelease-major-ignored', 'a pre-release pin has no major line',
    "const m = typeof tag === 'string' ? VERSION_TAG.exec(tag) : null;", "const m = typeof tag === 'string' ? RELEASE_TAG.exec(tag) : null;"],
  ['line0-release', 'v0.9.0 at HEAD counts as the clone\'s release tag',
    'tags.find((t) => RELEASE_TAG.test(t) && majorOf(t))', 'tags.find((t) => RELEASE_TAG.test(t))'],
  ['major-fallback-v1', 'with no release of the clone\'s line, --update falls back to v1',
    'const tag = newestRelease(names, major);', 'const tag = newestRelease(names, major) || newestRelease(names, 1);'],
  ['v2-pin-fails', 'a v2 pre-release pin with no v2 release stops with exit 1',
    'const onPin = !head.branch && head.tag && major !== DEFAULT_MAJOR;', 'const onPin = false;'],
  ['fresh-ignores-record', 'a fresh clone ignores the major line the manifest recorded',
    'const major = majorOf(recorded) || DEFAULT_MAJOR;', 'const major = DEFAULT_MAJOR;'],
  ['steering-gone-kept', 'links into a removed steering/ are not pruned',
    "if (!existsSync(commandsSource)) { warn('No steering commands found in repo'); pruneArea(area, null); return; }", "if (!existsSync(commandsSource)) { warn('No steering commands found in repo'); return; }"],
  ['note-missing', 'the v2 note is never printed',
    '  if (!later) return;\n', '  return;\n'],
  ['note-stdout', 'the v2 note goes to stdout',
    '  warn(`APEX ${later} is available', '  info(`APEX ${later} is available'],
  ['note-call-missing', 'no run prints the v2 note',
    '  noteLaterRelease(outcome);\n', ''],
  ['note-only-read-tags', 'runs that did not read the tags (--version, --branch) print no v2 note',
    "  if (!names) {\n    try { names = remoteTags(existsSync(INSTALL_DIR) ? 'origin' : REPO_URL, existsSync(INSTALL_DIR)); } catch { return; }\n  }", '  if (!names) return;'],
  ['note-branch-silent', 'a branch clone prints no v2 note',
    'if (!outcome.branch && (majorOf(outcome.ref) || DEFAULT_MAJOR) !== DEFAULT_MAJOR) return;', 'if (outcome.branch || (majorOf(outcome.ref) || DEFAULT_MAJOR) !== DEFAULT_MAJOR) return;'],
  ['note-on-v2-clone', 'a v2 clone prints the v1 note too',
    '  if (!outcome.branch && (majorOf(outcome.ref) || DEFAULT_MAJOR) !== DEFAULT_MAJOR) return;\n', ''],
  ['note-prerelease', 'a v2 pre-release tag triggers the v2 note',
    'const m = RELEASE_TAG.exec(name);\n    if (!m || Number(m[1]) < 2) continue;', 'const m = VERSION_TAG.exec(name);\n    if (!m || Number(m[1]) < 2) continue;'],
  ['note-lexical', 'the v2 note names a later release in string order',
    'if (!best || (i > -1 && v[i] > best.v[i])) best = { name, v };', 'if (!best || name > best.name) best = { name, v };'],
  ['home-spelling', 'one HOME spelled two ways (a trailing slash) is two install bases',
    'const HOME_BASE = isAbsolute(HOME) ? realPath(HOME) : HOME;', 'const HOME_BASE = homedir();'],
  ['home-symlink', 'a HOME reached through a symlink is another install base than its real path',
    'const HOME_BASE = isAbsolute(HOME) ? realPath(HOME) : HOME;', 'const HOME_BASE = HOME;'],
  ['kiro-same-text-edited', 'a Kiro copy that holds the new release\'s text, under an older record, counts as edited',
    'else if (st && !entryMatches(dest, current) && keepIfEdited(', 'else if (st && keepIfEdited('],
  ['uninstall-area-fallback', '--uninstall falls back to the 1.2.0 rules in an area a base\'s record does not hold',
    '      if (!rec) fallback[area]();\n', '      if (true) fallback[area]();\n'],
  ['claude-only-forgets-steering', 'a --claude-only run forgets the saved no-steering choice',
    'const keepsChoice = flags.update || flags.claudeOnly || flags.kiroOnly;', 'const keepsChoice = flags.update || flags.kiroOnly;'],
  ['kiro-only-forgets-steering', 'a --kiro-only run forgets the saved no-steering choice',
    'const keepsChoice = flags.update || flags.claudeOnly || flags.kiroOnly;', 'const keepsChoice = flags.update || flags.claudeOnly;'],
  ['nothing-installed-silent', 'a run that skipped every skill path reads as "Installed 0 skills"',
    'if (linked === 0) info(', 'if (false) info('],
  ['kiro-disk-error-listed', 'a Kiro copy write that fails with a disk error is listed as a path in the way, not stopped',
    'so it stops the run with that error.\n      if (!writeBlocked(e)) throw e;\n', 'so it stops the run with that error.\n'],
  ['uninstall-blocked-also-kept', '--uninstall lists a Kiro copy it could not remove under the kept marked files too',
    '!changed.includes(full) && !blocked.includes(full)) keptCopies.push(full);', '!changed.includes(full)) keptCopies.push(full);'],
  ['uninstall-no-clone-check', '--uninstall with a file at ~/.apex-skills calls it the repository and advises rm -rf',
    'if (existsSync(INSTALL_DIR) && !isOwnClone()) info(', 'if (false) info('],
  ['uninstall-unrecorded-area-silent', '--uninstall says nothing about an area the record lacks',
    "      else info(`Nothing recorded for ${areaPaths[area]}", "      else if (false) info(`Nothing recorded for ${areaPaths[area]}"],
  ['steering-off-edited-count-missing', 'with steering off and some leftovers edited, the line does not count the edited ones',
    "${edited.length > 0 ? ` (${edited.length} of them changed since", "${false ? ` (${edited.length} of them changed since"],
  ['kiro-current-rewritten', 'a Kiro copy that already holds the recorded release text is written again, so a read-only one fails',
    'else if (st && prev && prev[dest] && prev[dest].sha256 === current.sha256 && entryMatches(dest, current)) {', 'else if (false) {'],
  ['kiro-unmarked-recorded-conflict', 'a recorded Kiro copy that lost its marker is also listed as not created by the installer',
    '{ if (!keepIfEdited(area, dest, prev && prev[dest])) conflicts.push(dest); continue; }', '{ conflicts.push(dest); continue; }'],
];
EOF

apply() { # <index> <out file>; prints the mutant id
  # shellcheck disable=SC2016  # JavaScript, not shell, expansions
  node -e '
    const fs = require("fs");
    const [file, idx, src, out] = process.argv.slice(1);
    const [id, , from, to] = require(file)[Number(idx)];
    const text = fs.readFileSync(src, "utf8");
    const n = text.split(from).length - 1;
    console.log(id);
    if (n !== 1) { console.error(`mutant ${id}: expected the text once, found it ${n} times`); process.exit(1); }
    fs.writeFileSync(out, text.replace(from, () => to));
  ' "$WORK/mutants.cjs" "$1" "$SRC" "$2"
}

# --only must name a mutant, or the run would report "0 killed" and pass.
if [ -n "$ONLY" ] && ! node -e 'process.exit(require(process.argv[1]).some((m) => m[0] === process.argv[2]) ? 0 : 1)' "$WORK/mutants.cjs" "$ONLY"; then
  echo "no mutant has the id '$ONLY' (see the list in $0)" >&2
  exit 2
fi

# Baseline: the unmutated installer must pass, or every "kill" means nothing.
mkdir -p "$WORK/base/bin"
cp "$PKG" "$WORK/base/package.json"
cp "$SRC" "$WORK/base/bin/cli.mjs"
if ! harness "$WORK/base/bin/cli.mjs" "$WORK/base/work" > "$WORK/base/log" 2>&1; then
  echo "BASELINE FAIL: the harness fails on the unmutated installer:"
  tail -n 5 "$WORK/base/log"
  exit 1
fi
echo "BASELINE PASS: $(/usr/bin/grep '^SUMMARY' "$WORK/base/log")"

count="$(node -e 'console.log(require(process.argv[1]).length)' "$WORK/mutants.cjs")"
killed=0; survived=0; broken=0
for i in $(seq 0 $((count - 1))); do
  d="$WORK/m$i"
  mkdir -p "$d/bin"
  cp "$PKG" "$d/package.json"
  if ! id="$(apply "$i" "$d/bin/cli.mjs" 2> "$d/apply.err")"; then
    echo "MUTANT ${id:-#$i} DID NOT APPLY: $(cat "$d/apply.err")"; broken=$((broken + 1)); continue
  fi
  if [ -n "$ONLY" ] && [ "$id" != "$ONLY" ]; then continue; fi
  harness "$d/bin/cli.mjs" "$d/work" > "$d/log" 2>&1
  rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "MUTANT $id SURVIVED"; survived=$((survived + 1))
  elif /usr/bin/grep -qE '^SUMMARY: .* [1-9][0-9]* failed' "$d/log"; then
    echo "MUTANT $id killed by:$(/usr/bin/grep '^SUMMARY' "$d/log" | sed -n 's/.*(failed:\(.*\))/\1/p')"; killed=$((killed + 1))
  else
    if [ "$rc" -eq 142 ]; then why="killed at the ${LIMIT}s limit"; else why="exit $rc"; fi
    echo "MUTANT $id HARNESS DID NOT RUN ($why, no SUMMARY line with a failed case): $(tail -n 3 "$d/log" | tr '\n' ' ')"; broken=$((broken + 1))
  fi
done
echo "MUTATION SUMMARY: $killed killed, $survived survived, $broken did not apply or did not run"
[ "$survived" -eq 0 ] && [ "$broken" -eq 0 ]
