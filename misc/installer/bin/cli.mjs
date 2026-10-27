#!/usr/bin/env node
import { existsSync, mkdirSync, readdirSync, symlinkSync, readlinkSync, unlinkSync, lstatSync, statSync, readFileSync, writeFileSync, renameSync, realpathSync } from 'fs';
import { join, resolve, dirname, basename, sep, relative, isAbsolute } from 'path';
import { homedir, platform } from 'os';
import { execFileSync } from 'child_process';
import { createInterface } from 'readline';
import { createHash } from 'crypto';

import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { version: VERSION } = require('../package.json');
// APEX_SKILLS_REPO_URL lets CI install from a local checkout (misc/installer/test/install-paths.sh).
// A value that starts with "-" is refused in main(), and every git call puts
// "--" before it, so it can never be read as a git option.
const REPO_URL = process.env.APEX_SKILLS_REPO_URL || 'https://github.com/aws-samples/sample-apex-skills.git';
// Where a v1 install points for the v2 installer (the v2 note).
const V2_INFO_URL = 'https://github.com/aws-samples/sample-apex-skills/releases';
// os.homedir() returns an empty string when HOME is set but empty; main()
// stops before writing anything unless HOME is an absolute path. An absolute
// HOME is normalised (no trailing slash, /./ or //). resolve('') would be the cwd,
// so an empty or relative HOME is kept as given for that check.
const HOME = isAbsolute(homedir()) ? resolve(homedir()) : homedir();
const INSTALL_DIR = join(HOME, '.apex-skills');
// The install base of a global install: HOME's real path (symlinks resolved,
// as process.cwd() is for --project), so one directory reached by any spelling
// or symlink is one install base in the manifest.
const HOME_BASE = isAbsolute(HOME) ? realPath(HOME) : HOME;

// Exit codes: 0 installed (or removed) everything; 1 error; 2 bad command line
// (unknown, contradictory or incomplete flags; nothing was changed); 3 finished,
// but some paths were skipped because they were not created by this installer
// (or changed since it created them, or could not be written), or the install
// manifest could not be saved; 130 cancelled at a question (Ctrl-C or Ctrl-D at
// a terminal), nothing was changed.
const EXIT_OK = 0;
const EXIT_ERROR = 1;
const EXIT_USAGE = 2;
const EXIT_SKIPPED = 3;
const EXIT_CANCELLED = 130;

// ANSI colors
const c = {
  reset: '\x1b[0m',
  bold: '\x1b[1m',
  dim: '\x1b[2m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  red: '\x1b[31m',
  cyan: '\x1b[36m',
};

// Progress goes to stdout; warnings and errors go to stderr.
const log = (msg) => console.log(msg);
const logErr = (msg) => console.error(msg);
const info = (msg) => log(`${c.blue}i${c.reset} ${msg}`);
const success = (msg) => log(`${c.green}✓${c.reset} ${msg}`);
const warn = (msg) => logErr(`${c.yellow}!${c.reset} ${msg}`);
const error = (msg) => logErr(`${c.red}✗${c.reset} ${msg}`);

function banner() {
  log(`\n${c.bold}${c.cyan}  APEX Skills Installer${c.reset} ${c.dim}v${VERSION}${c.reset}`);
  log(`${c.dim}  Platform engineering skills for AI agents${c.reset}\n`);
}

// ---------------------------------------------------------------- arguments
class UsageError extends Error {}

const BOOL_FLAGS = {
  '--claude-only': 'claudeOnly',
  '--kiro-only': 'kiroOnly',
  '--project': 'project',
  '--no-steering': 'noSteering',
  '--update': 'update',
  '--uninstall': 'uninstall',
  '--yes': 'yes',
  '-y': 'yes',
  '--help': 'help',
  '-h': 'help',
};
const VALUE_FLAGS = { '--branch': 'branch', '--version': 'version', '-v': 'version' };
const SAFE_REF = /^[a-zA-Z0-9][a-zA-Z0-9._\-/]*$/;

function parseArgs(argv) {
  const flags = { branch: null, version: null };
  for (const key of Object.values(BOOL_FLAGS)) flags[key] = false;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const eq = arg.startsWith('--') ? arg.indexOf('=') : -1;
    const name = eq > 0 ? arg.slice(0, eq) : arg;
    if (VALUE_FLAGS[name]) {
      const val = eq > 0 ? arg.slice(eq + 1) : argv[++i];
      if (val === undefined || val === '' || val.startsWith('-')) {
        throw new UsageError(`${name} needs a value, for example ${name === '--branch' ? '--branch main' : `${name} v1.2.0`}`);
      }
      flags[VALUE_FLAGS[name]] = val;
    } else if (BOOL_FLAGS[name]) {
      if (eq > 0) throw new UsageError(`${name} does not take a value`);
      flags[BOOL_FLAGS[name]] = true;
    } else {
      throw new UsageError(arg.startsWith('-') ? `Unknown flag: ${arg}` : `Unexpected argument: ${arg}`);
    }
  }
  if (flags.claudeOnly && flags.kiroOnly) {
    throw new UsageError('Use --claude-only or --kiro-only, not both (with neither, every detected tool is installed).');
  }
  if (flags.branch && flags.version) throw new UsageError('Cannot use --branch and --version together. Pick one.');
  if (flags.uninstall && (flags.update || flags.branch || flags.version)) {
    throw new UsageError('--uninstall cannot be combined with --update, --branch or --version.');
  }
  const ref = flags.version || flags.branch;
  if (ref && !SAFE_REF.test(ref)) {
    throw new UsageError(`Invalid ref: "${ref}". Only alphanumeric, dots, hyphens, slashes, and underscores are allowed.`);
  }
  return flags;
}

// ---------------------------------------------------------------- prompts
// One readline interface for the whole run, so piped answers are read in
// order. When stdin is closed or empty (for example `npx apex-skills </dev/null`
// in a script), every prompt takes its default and the install finishes. With
// -y/--yes no prompt is shown and stdin is never read. At a terminal, input
// that ends before an answer (Ctrl-C, or Ctrl-D, which closes it) cancels the
// run instead: every question is asked before anything is written, so a
// cancelled run has changed nothing (exit code 130).
class CancelError extends Error {}
let assumeYes = false;
let rl = null;
let inputClosed = false;
let waiting = null;
let defaultsNoted = false;
const pendingLines = [];

function openInput() {
  if (rl) return;
  rl = createInterface({ input: process.stdin, output: process.stdout });
  rl.on('line', (line) => {
    if (waiting) { const w = waiting; waiting = null; w(line); } else pendingLines.push(line);
  });
  // Ctrl-C at a terminal: end the input, as Ctrl-D does; ask() then cancels.
  rl.on('SIGINT', () => rl.close());
  rl.on('close', () => {
    inputClosed = true;
    if (waiting) { const w = waiting; waiting = null; w(null); }
  });
}

function closeInput() {
  if (rl) rl.close();
}

function ask(question, defaultVal = '') {
  if (assumeYes) return Promise.resolve(defaultVal);
  openInput();
  const suffix = defaultVal ? ` [${defaultVal}]` : '';
  const text = `${c.cyan}?${c.reset} ${question}${suffix}: `;
  // A closed interface is never prompted again: prompting it resumes stdin.
  // At a terminal that keeps the process alive after the run ends, but a
  // terminal whose input ended cancels at that question, so no later question
  // is asked; with stdin at end of file (a pipe, /dev/null) the process exits
  // either way (seen on Node 18.20.8 and 22.14.0). So no run today behaves
  // differently without this guard.
  if (inputClosed) process.stdout.write(text);
  else { rl.setPrompt(text); rl.prompt(); }
  return new Promise((res, rej) => {
    const answered = (line) => {
      if (line === null && process.stdin.isTTY) { // a terminal ended the input: cancel
        log('');
        rej(new CancelError('Cancelled at a question; nothing was changed.'));
        return;
      }
      if (line === null) { // stdin closed before an answer
        log('');
        if (!defaultsNoted) { info('No input on stdin, so the default answers are used'); defaultsNoted = true; }
        res(defaultVal);
        return;
      }
      res(line.trim() || defaultVal);
    };
    if (pendingLines.length > 0) answered(pendingLines.shift());
    else if (inputClosed) answered(null);
    else waiting = answered;
  });
}

// ---------------------------------------------------------------- git
// Every git call runs without a shell, with stdin closed and with terminal
// prompts off, so an HTTPS URL that needs credentials fails instead of waiting
// for a password nobody will type. The variables that point git at another
// repository (a git hook exports GIT_DIR and GIT_WORK_TREE, for example) are
// removed. git also looks for a repository upward from its cwd, so a
// ~/.apex-skills that is not a clone, inside a HOME that is a git repository
// (dotfiles), would make git act on HOME's repository: GIT_CEILING_DIRECTORIES
// stops that search at ~/.apex-skills itself, and isOwnClone() checks, before
// any other git call on an existing ~/.apex-skills, that it is the top of its
// own work tree.
const GIT_ENV = { ...process.env, GIT_TERMINAL_PROMPT: '0', GIT_CEILING_DIRECTORIES: dirname(INSTALL_DIR) };
for (const key of ['GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_COMMON_DIR', 'GIT_NAMESPACE', 'GIT_PREFIX']) delete GIT_ENV[key];
const GIT_OPTS = { stdio: ['ignore', 'pipe', 'pipe'], encoding: 'utf8', env: GIT_ENV };

function hasGit() {
  try {
    execFileSync('git', ['--version'], GIT_OPTS);
    return true;
  } catch { return false; }
}

function git(args) {
  return execFileSync('git', args, { ...GIT_OPTS, cwd: INSTALL_DIR });
}
function gitOk(args) {
  try { git(args); return true; } catch { return false; }
}

// True only when ~/.apex-skills is itself the top of a git work tree (its own
// clone), not a directory that git would place inside another repository.
function isOwnClone() {
  try { return git(['rev-parse', '--show-toplevel']).trim() === realpathSync(INSTALL_DIR); } catch { return false; }
}
// The advice never says to remove ~/.apex-skills: what is in it was never
// inspected (it can be the user's own files, an unreadable clone, or a clone
// with changes git ignores). Moving it aside loses nothing.
const MOVE_ASIDE = 'move it aside (mv ~/.apex-skills ~/.apex-skills.old) and re-run; that keeps everything in it';
function notAClone() {
  warn(`~/.apex-skills is not a git clone or cannot be read, so the installer leaves it alone; ${MOVE_ASIDE}`);
  return new Error(`${INSTALL_DIR} is not a git clone or cannot be read`);
}

// An error whose message was already printed; the caller adds no advice.
class CloneError extends Error {}

function headCommit() {
  try { return git(['rev-parse', 'HEAD']).trim(); } catch { return null; }
}

// Files in the clone that differ from its commit: tracked changes only, or
// untracked files too. A v1.2.0 Kiro steering file was a symlink into the
// clone, so a user who edited it edited a file here.
function localChanges(withUntracked) {
  try {
    return git(['status', '--porcelain', `--untracked-files=${withUntracked ? 'all' : 'no'}`])
      .split('\n').filter(Boolean).map((l) => l.slice(3));
  } catch { return []; }
}

// Commits at HEAD that no branch, tag or remote-tracking ref holds: a commit
// made on the detached clone of a --version pin or a release. Moving HEAD
// would leave them in the reflog only, which git expires. Read before the
// fetch, which can move a tag off HEAD; a git error stops the run.
function unsavedCommits() {
  return git(['log', '--format=%h %s', 'HEAD', '--not', '--branches', '--tags', '--remotes']).split('\n').filter(Boolean);
}

// Before HEAD moves to ref (fetched already): the target must hold skills/,
// and the clone must have no commits that only HEAD holds (unsaved, read
// before the fetch) and no changed tracked files, which a checkout would
// refuse to overwrite or a removed clone would lose. Either way nothing moves.
// The fetch before the check can be a --depth 1 fetch, which makes a full
// clone (the user's own, for example) shallow. Nothing is lost; the refusals
// below say how to get the history back.
const SHALLOW_NOTE = '  If ~/.apex-skills was a full clone, the fetch before this check (with --depth 1) can have made it shallow; git -C ~/.apex-skills fetch --unshallow origin restores its history.';
function checkTarget(ref, unsaved) {
  const target = git(['rev-parse', '--verify', '-q', `${ref}^{commit}`]).trim();
  const name = ref.replace(/^refs\/(tags|remotes\/origin)\//, '');
  if (!gitOk(['cat-file', '-e', `${target}:skills`])) {
    error(`${name} has no skills/ directory, so it cannot be installed; the files and HEAD of ~/.apex-skills were not changed.`);
    logErr(SHALLOW_NOTE);
    throw new CloneError('no skills/ in the target');
  }
  if (target === headCommit()) return;
  if (unsaved.length > 0) {
    error(`~/.apex-skills has ${unsaved.length} commit(s) that no branch or tag holds; moving to ${name} would leave them behind:`);
    for (const l of unsaved) logErr(`    ${l}`);
    logErr('  Keep them on a branch (git -C ~/.apex-skills branch my-work), then re-run. ~/.apex-skills was not moved.');
    logErr(SHALLOW_NOTE);
    throw new CloneError('commits only HEAD holds');
  }
  const files = localChanges(false);
  if (files.length === 0) return;
  error(`~/.apex-skills has ${files.length} changed file(s) that moving to ${name} would overwrite:`);
  for (const f of files) logErr(`    ${join(INSTALL_DIR, f)}`);
  logErr('  Copy them out of ~/.apex-skills to keep them, then run git -C ~/.apex-skills checkout -- . and re-run. The files and HEAD of ~/.apex-skills were not changed. If the re-run lists a commit that no branch or tag holds, the fetch moved the tag the clone is on: keep that commit with git -C ~/.apex-skills branch <name>, then re-run.');
  logErr(SHALLOW_NOTE);
  throw new CloneError('changed files in the clone');
}

// The advice after a failed update: move the clone aside, never remove it, and
// name the files the user changed or added there that git reports (files git
// ignores, such as reports, and local commits are not in that list).
function updateFailedAdvice() {
  const files = localChanges(true);
  warn(`Update failed (git's reason is below). Fix the cause and run again: for a network or access failure, check your connection; for a branch that origin does not have, move to a release with --version <tag> or to --branch main. If the clone itself is broken, or holds a local commit on that branch, ${MOVE_ASIDE}.`);
  if (files.length === 0) return;
  logErr(`  ~/.apex-skills holds ${files.length} file(s) you changed or added (files git ignores are not listed):`);
  for (const f of files) logErr(`    ${join(INSTALL_DIR, f)}`);
}

// The clone is depth-1 and single-branch, so a plain `git checkout <ref>` or
// `git pull` cannot see other branches or recover from a detached HEAD. Each
// ref is fetched by an explicit refspec instead.
function syncBranch(branch) {
  const unsaved = unsavedCommits();
  const haveLocal = gitOk(['rev-parse', '--verify', '-q', `refs/heads/${branch}`]);
  const depth = haveLocal ? [] : ['--depth', '1'];
  git(['fetch', ...depth, 'origin', `+refs/heads/${branch}:refs/remotes/origin/${branch}`]);
  checkTarget(`refs/remotes/origin/${branch}`, unsaved);
  if (haveLocal) {
    // Read only, for the message below: whether this checkout moves HEAD onto
    // the branch, and the tag recorded before it.
    const moves = !gitOk(['symbolic-ref', '-q', 'HEAD']) || git(['symbolic-ref', '--short', '-q', 'HEAD']).trim() !== branch;
    const tag = configValue(TAG_KEY);
    git(['checkout', '-q', branch]);
    try {
      git(['merge', '--ff-only', '-q', `refs/remotes/origin/${branch}`]);
    } catch (e) {
      // The checkout above moved HEAD and only the fast-forward failed: say
      // where the clone is now, not "failed to check out".
      if (!moves) throw e;
      error(`The local branch ${branch} in ~/.apex-skills cannot fast-forward to origin/${branch} (git's reason is below). ~/.apex-skills is now on the local branch ${branch}, so the installed skills come from it.`);
      // Only when a tag was recorded: a clone that was on a branch has none.
      if (tag) logErr(`  To go back, run: npx apex-skills --version ${tag}`);
      throw new CloneError(e.message);
    }
  } else {
    git(['checkout', '-q', '-b', branch, `refs/remotes/origin/${branch}`]);
  }
}

function syncTag(tag) {
  const unsaved = unsavedCommits();
  git(['fetch', '--depth', '1', '--force', 'origin', `+refs/tags/${tag}:refs/tags/${tag}`]);
  checkTarget(`refs/tags/${tag}`, unsaved);
  git(['checkout', '-q', '--detach', `refs/tags/${tag}`]);
}

// Releases. A plain install uses the newest v1.x.y release tag, in numeric
// order (v1.10.0 is newer than v1.9.0), not the tip of main, which can hold
// unreleased changes. --update keeps a clone on its major line: a clone on a
// v1 tag moves to the newest v1.x.y, a clone on a v2 tag to the newest v2.x.y.
// Pre-release tags (v1.3.0-rc.0) are never picked on their own, and a fresh
// install picks another major line (v2.0.0) only when the install manifest
// records it for the base; --version picks any tag.
// The tags are read with git ls-remote, so nothing is fetched to choose one.
const RELEASE_TAG = /^v(\d+)\.(\d+)\.(\d+)$/;
// A release or pre-release tag, to read the major line of a clone's tag.
const VERSION_TAG = /^v(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z.-]+)?$/;
const DEFAULT_MAJOR = 1;

// The major line of a tag (v2.0.0-rc.0 is on line 2), or null for a tag that
// is not a version, or is on line 0.
function majorOf(tag) {
  const m = typeof tag === 'string' ? VERSION_TAG.exec(tag) : null;
  const n = m ? Number(m[1]) : 0;
  return n >= 1 ? n : null;
}
function isRelease(tag, major) {
  const m = RELEASE_TAG.exec(tag || '');
  return m !== null && Number(m[1]) === major;
}

// The newest release of one major line, by minor, then patch.
function newestRelease(names, major) {
  let best = null;
  for (const name of names) {
    const m = RELEASE_TAG.exec(name);
    if (!m || Number(m[1]) !== major) continue;
    const v = [Number(m[2]), Number(m[3])];
    if (!best || v[0] > best.v[0] || (v[0] === best.v[0] && v[1] > best.v[1])) best = { name, v };
  }
  return best ? best.name : null;
}

// The newest release on line 2 or later (v2.0.0 and up, no pre-releases), for
// the note a v1 install prints.
function newestLaterRelease(names) {
  let best = null;
  for (const name of names) {
    const m = RELEASE_TAG.exec(name);
    if (!m || Number(m[1]) < 2) continue;
    const v = [Number(m[1]), Number(m[2]), Number(m[3])];
    const i = best ? v.findIndex((x, k) => x !== best.v[k]) : -1;
    if (!best || (i > -1 && v[i] > best.v[i])) best = { name, v };
  }
  return best ? best.name : null;
}

// The tag names of a remote: a URL (fresh clone) or 'origin' (run inside the clone).
function remoteTags(remote, inClone) {
  const out = execFileSync('git', ['ls-remote', '--tags', '--refs', '--', remote], inClone ? { ...GIT_OPTS, cwd: INSTALL_DIR } : GIT_OPTS);
  return out.split('\n').map((l) => l.split('\t')[1] || '').filter((r) => r.startsWith('refs/tags/')).map((r) => r.slice('refs/tags/'.length));
}

// One line on stderr when the run leaves the clone on v1 (a v1 tag, a tag on
// no major line, or a branch) and a v2.0.0 or later release exists. The tags
// are read again when the run did not read them (--version, --branch); when
// they cannot be read, no note. The exit code does not change.
function noteLaterRelease(outcome) {
  if (!outcome || outcome.stayed) return;
  if (!outcome.branch && (majorOf(outcome.ref) || DEFAULT_MAJOR) !== DEFAULT_MAJOR) return;
  let names = outcome.names;
  if (!names) {
    try { names = remoteTags(existsSync(INSTALL_DIR) ? 'origin' : REPO_URL, existsSync(INSTALL_DIR)); } catch { return; }
  }
  const later = newestLaterRelease(names);
  if (!later) return;
  const where = outcome.branch ? `this install follows branch ${outcome.ref}` : `this install stays on ${majorOf(outcome.ref) || !outcome.ref ? 'v1' : outcome.ref}`;
  warn(`APEX ${later} is available; ${where}. For the v2 installer, see ${V2_INFO_URL}`);
}

// Returns the newest release of the major line and the tag names read. Fails
// closed: with no reachable release tag of that line it throws and the caller
// changes nothing, unless allowNone is set; then tag is null.
function latestRelease(remote, inClone, major, allowNone = false) {
  let names;
  try {
    names = remoteTags(remote, inClone);
  } catch (e) {
    error(`Could not read the release tags of ${inClone ? 'the clone\'s origin' : REPO_URL}. Check your connection and git access.`);
    throw e;
  }
  const tag = newestRelease(names, major);
  if (!tag && !allowNone) {
    error(`No v${major} release tag (v${major}.x.y) found at ${inClone ? 'the clone\'s origin' : REPO_URL}, so there is no release to install.`);
    logErr(`  Install a branch instead with --branch main, or a tag with --version <tag> (list them: git ls-remote --tags ${REPO_URL}).`);
    throw new Error(`No v${major} release tag found; nothing was installed or changed.`);
  }
  return { tag, names };
}

// The note when a clone (or the recorded install) is on a pin of line 2 or
// later and that line has no release yet: the install stays on the pin.
function noteNoRelease(major, pin) {
  warn(`No v${major} release (v${major}.x.y) exists yet, so this install stays on ${pin}.`);
}

// The ref the clone was set to is kept in its git config: a branch chosen with
// --branch, so --update keeps following it (main included), or the tag it was
// checked out at. A clone on main without that record was made by an older
// installer's default, and --update moves it to the release.
const BRANCH_KEY = 'apex-skills.branch';
const TAG_KEY = 'apex-skills.tag';
function configValue(key) {
  try { return git(['config', '--local', '--get', key]).trim() || null; } catch { return null; }
}
function recordRef(kind, name) {
  gitOk(['config', '--local', '--unset-all', BRANCH_KEY]);
  gitOk(['config', '--local', '--unset-all', TAG_KEY]);
  git(['config', '--local', kind === 'branch' ? BRANCH_KEY : TAG_KEY, name]);
}

// What HEAD is: a branch name, or the tag at HEAD (the recorded tag, else a
// release tag, else a pre-release tag, else any), or null when it is not a git
// clone. Tags on line 0 (v0.9.0) do not count as releases here.
function describeHead() {
  if (!isOwnClone()) return null;
  if (gitOk(['symbolic-ref', '-q', 'HEAD'])) return { branch: git(['symbolic-ref', '--short', '-q', 'HEAD']).trim() };
  let tags = [];
  try { tags = git(['tag', '--points-at', 'HEAD']).split('\n').map((t) => t.trim()).filter(Boolean); } catch { tags = []; }
  const recorded = configValue(TAG_KEY);
  return { tag: (recorded && tags.includes(recorded) ? recorded : null) || tags.find((t) => RELEASE_TAG.test(t) && majorOf(t)) || tags.find((t) => majorOf(t)) || tags[0] || null };
}

// Returns the outcome: ref, the branch or tag the clone is on afterwards (for
// the manifest); branch, whether ref is a branch; names, the remote's tag names
// when the run read them; stayed, whether a pin was kept because its line has
// no release yet (no v2 note then).
function cloneOrUpdate(flags) {
  const ref = flags.version || flags.branch;
  if (existsSync(INSTALL_DIR)) {
    // Before any other git call: git must act on this clone and nothing else.
    if (!isOwnClone()) throw notAClone();
    if (ref) {
      info(`Switching to ${flags.version ? `version ${ref}` : `branch ${ref}`}...`);
      try {
        if (flags.version) syncTag(ref); else syncBranch(ref);
        recordRef(flags.version ? 'tag' : 'branch', ref);
        success(`Now on ${ref}`);
      } catch (e) {
        if (!(e instanceof CloneError)) {
          error(flags.version
            ? `Failed to check out version ${ref}. List releases with: git ls-remote --tags ${REPO_URL}`
            : `Failed to check out branch ${ref}. List branches with: git ls-remote --heads ${REPO_URL}`);
        }
        throw e;
      }
      return { ref, branch: Boolean(flags.branch), names: null };
    }
    info('Updating existing installation...');
    const head = describeHead();
    if (head && head.branch && (head.branch !== 'main' || configValue(BRANCH_KEY) === head.branch)) {
      try {
        syncBranch(head.branch);
      } catch (e) {
        if (!(e instanceof CloneError)) updateFailedAdvice();
        throw e;
      }
      success(`Updated to the latest commit of branch ${head.branch}, the branch the clone follows`);
      return { ref: head.branch, branch: true, names: null };
    }
    if (!head) throw notAClone();
    // The major line to stay on comes from the clone itself, never from an
    // install base's record: the clone is shared by every base, so a v2 clone
    // stays on v2 and a v1 clone on v1 whichever base runs --update. A clone on
    // a branch (an older installer's main) moves to v1; a clone on a tag keeps
    // the line of the tag at HEAD, else v1.
    const major = head.branch ? DEFAULT_MAJOR : (majorOf(head.tag) || DEFAULT_MAJOR);
    const onPin = !head.branch && head.tag && major !== DEFAULT_MAJOR;
    const { tag, names } = latestRelease('origin', true, major, onPin);
    if (!tag) {
      noteNoRelease(major, head.tag);
      return { ref: head.tag, branch: false, names, stayed: true };
    }
    const before = headCommit();
    try {
      syncTag(tag);
      recordRef('tag', tag);
    } catch (e) {
      if (!(e instanceof CloneError)) updateFailedAdvice();
      throw e;
    }
    const from = head.branch ? `branch ${head.branch}` : head.tag;
    if (head.branch) {
      warn(`This install followed branch ${head.branch}, which can hold unreleased changes. It now uses the latest v${major} release, ${tag}.`);
      warn(`To keep following ${head.branch} instead, run: npx apex-skills --branch ${head.branch}`);
    } else if (!isRelease(from, major)) {
      warn(`This install was on ${from || 'a commit with no release tag'}, which is not a v${major} release. It now uses the latest v${major} release, ${tag}.`);
      if (from) warn(`To go back, run: npx apex-skills --version ${from}`);
    }
    if (from !== tag) success(`Updated to the latest v${major} release, ${tag}`);
    else if (headCommit() !== before) success(`Updated: release ${tag} was moved to another commit upstream, and the clone now uses that commit`);
    else success(`Already on the latest v${major} release, ${tag}`);
    return { ref: tag, branch: false, names };
  }
  // A fresh install (no clone) uses the newest release of the major line the
  // install manifest recorded for this install base (a v2 install whose clone
  // was removed is cloned again on v2; with no v2 release yet, at its recorded
  // pin), else of v1.
  let target = ref;
  let names = null;
  let label = ref;
  let stayed = false;
  if (!ref) {
    const recorded = recordedRef(flags.project ? process.cwd() : HOME_BASE);
    const major = majorOf(recorded) || DEFAULT_MAJOR;
    ({ tag: target, names } = latestRelease(REPO_URL, false, major, major !== DEFAULT_MAJOR));
    label = `latest v${major} release, ${target}`;
    if (major !== DEFAULT_MAJOR) {
      info(`The install manifest records ${recorded} for this install base, so the new clone stays on the v${major} line`);
      if (!target) { noteNoRelease(major, recorded); target = recorded; label = recorded; stayed = true; }
    }
  }
  info(`Cloning APEX skills repository (${label})...`);
  try {
    execFileSync('git', ['clone', '--depth', '1', '--branch', target, '--', REPO_URL, INSTALL_DIR], GIT_OPTS);
    recordRef(flags.branch ? 'branch' : 'tag', target);
    success(`Repository cloned (${target})`);
  } catch (e) {
    error(ref
      ? `Failed to clone ${ref}. Check the name (git ls-remote --tags/--heads ${REPO_URL}), your connection and git access.`
      : `Failed to clone repository at ${target} (git's reason is below). Check your internet connection and git access, and that nothing is at ~/.apex-skills (a symlink to a path that does not exist counts).`);
    throw e;
  }
  return { ref: target, branch: Boolean(flags.branch), names, stayed };
}

// What the clone now holds, for the manifest: ref is the branch or tag it was
// set to (the resolved release tag for a plain install or --update).
function cloneSource(ref) {
  const commit = (() => { try { return git(['rev-parse', 'HEAD']).trim(); } catch { return null; } })();
  return { url: REPO_URL, ref: ref || null, commit };
}

function getSkills() {
  const skillsDir = join(INSTALL_DIR, 'skills');
  if (!existsSync(skillsDir)) return [];
  return readdirSync(skillsDir).filter((name) => {
    if (name === 'README.md' || name.startsWith('.')) return false;
    const full = join(skillsDir, name);
    try { return statSync(full).isDirectory(); } catch { return false; }
  });
}

// ---------------------------------------------------------------- paths
// lstat, not existsSync: existsSync is false for a dangling symlink.
function lstatOrNull(p) {
  try { return lstatSync(p); } catch { return null; }
}

// The real path of p, or of its deepest existing ancestor with the rest
// appended. A relative link is resolved by the OS from the real directory that
// holds it, so ~/.claude/skills being itself a symlink must not break the links.
function realPath(p) {
  const abs = resolve(p);
  try { return realpathSync(abs); } catch { /* missing, dangling or looping */ }
  const parent = dirname(abs);
  return parent === abs ? abs : join(realPath(parent), basename(abs));
}

function linkTarget(p) {
  return resolve(realPath(dirname(p)), readlinkSync(p));
}

// The link text from linkPath to target: relative for a global install, so the
// links survive a moved home directory; absolute for --project, whose links
// cross from the project into ~/.apex-skills, so they survive a moved project.
let absoluteLinks = false;
function linkText(target, linkPath) {
  if (absoluteLinks) return resolve(target);
  return relative(realPath(dirname(linkPath)), realPath(target));
}

// A link whose target is inside the clone: relative links (this version) and
// absolute links (v1.2.0 and earlier) both count.
function isInstallerLink(p) {
  const st = lstatOrNull(p);
  if (!st || !st.isSymbolicLink()) return false;
  let target;
  try { target = linkTarget(p); } catch { return false; }
  return [resolve(INSTALL_DIR), realPath(INSTALL_DIR)].some((root) => target === root || target.startsWith(root + sep));
}

const conflicts = [];  // paths the installer did not create; reported and left alone
const keptCopies = []; // marked Kiro files that are not a recorded copy of a current workflow
const keptUnknown = []; // marked Kiro files kept because there is no clone and no record
const changed = [];    // manifest entries changed since the installer wrote them; kept
const blocked = [];    // paths that could not be written (permission denied); left as they were
let manifestLost = false; // the install manifest could not be saved

// A write the file system refused (a read-only directory, for example): the
// path is listed and the run goes on with the rest (exit code 3).
function writeBlocked(e) {
  return Boolean(e) && ['EACCES', 'EPERM', 'EROFS'].includes(e.code);
}

// The path at or above p that stands where a directory must be: the nearest
// one that exists, when it is not a directory (a file, a dangling symlink, a
// link to a file at ~/.claude, for example). null when that one is a
// directory, or cannot be checked.
function inTheWay(p) {
  for (let q = resolve(p); ; q = dirname(q)) {
    let st = null;
    try { st = lstatSync(q); } catch (e) { if (e.code !== 'ENOENT' && e.code !== 'ENOTDIR') return null; }
    if (st) {
      let isDir = false;
      try { isDir = statSync(q).isDirectory(); } catch { isDir = false; }
      return isDir ? null : q;
    }
    if (dirname(q) === q) return null;
  }
}

// A write at p that failed: refused (listed as not written), or a path in the
// way (listed once with the paths the installer did not create); either way
// the run goes on (exit code 3). Any other error stops the run.
function cannotWrite(p, e) {
  if (writeBlocked(e)) { if (!blocked.includes(p)) blocked.push(p); return; }
  const w = inTheWay(p);
  if (!w) throw e;
  if (!conflicts.includes(w)) conflicts.push(w);
}

// The entries of a directory the installer manages; none when it is missing
// or not a directory. One it cannot read is listed with the paths that could
// not be written, and nothing in it is removed.
function listDir(dir) {
  try { return readdirSync(dir); } catch (e) {
    if (e.code === 'ENOENT' || e.code === 'ENOTDIR') return [];
    if (!writeBlocked(e)) throw e;
    if (!blocked.includes(dir)) blocked.push(dir);
    return [];
  }
}

// True when p cannot be checked (its directory cannot be read), as opposed to
// missing: a record for it is kept, since nobody can tell whether it changed.
function unreadable(p) {
  try { lstatSync(p); return false; } catch (e) { return e.code !== 'ENOENT' && e.code !== 'ENOTDIR'; }
}
function keepUnreadable(p) {
  if (!unreadable(p)) return false;
  if (!blocked.includes(dirname(p))) blocked.push(dirname(p));
  return true;
}
// unlinkSync that lists a refused path instead of stopping the run; true when removed.
function tryUnlink(p) {
  try { unlinkSync(p); return true; } catch (e) {
    if (!writeBlocked(e)) throw e;
    if (!blocked.includes(p)) blocked.push(p);
    return false;
  }
}

// A directory the installer links into. Anything else at that path (a file, a
// dangling symlink, a link to a file) is a conflict, and that target is skipped.
function prepareDir(dir) {
  const st = lstatOrNull(dir);
  if (st) {
    let isDir = false;
    try { isDir = statSync(dir).isDirectory(); } catch { isDir = false; }
    if (isDir) return true;
    conflicts.push(dir);
    return false;
  }
  try {
    mkdirSync(dir, { recursive: true });
    return true;
  } catch (e) {
    const w = writeBlocked(e) ? null : inTheWay(dir);
    if (w) { if (!conflicts.includes(w)) conflicts.push(w); } else if (!blocked.includes(dir)) blocked.push(dir);
    return false;
  }
}

// ---------------------------------------------------------------- manifest
// The manifest records, per install base (HOME or a --project directory), every
// path the installer created: links with their link text and Kiro copies with a
// SHA-256 of the content written, grouped by area, plus the source (URL, ref,
// commit) and the steering choice. It lives outside the clone, so removing
// ~/.apex-skills does not lose it. --uninstall and the prune after an update use
// it: an entry is removed only while it still matches what was recorded. A base
// with no record (an install made by v1.2.0 or earlier, or a missing or corrupt
// manifest) falls back to the rules by link target and Kiro marker; --uninstall
// removes nothing in an area a base's record does not hold.
const STATE_DIR = (() => {
  const xdg = process.env.XDG_STATE_HOME;
  return xdg && isAbsolute(xdg) ? join(xdg, 'apex-skills') : join(HOME, '.local', 'state', 'apex-skills');
})();
const MANIFEST_FILE = join(STATE_DIR, 'manifest.json');
const MANIFEST_VERSION = 1;
const AREAS = ['claude-skills', 'claude-steering', 'kiro-skills', 'kiro-steering'];

function sha256(text) {
  return createHash('sha256').update(text).digest('hex');
}

function validEntry(e) {
  if (!e || typeof e !== 'object') return false;
  if (e.kind === 'link') return typeof e.target === 'string';
  if (e.kind === 'copy') return typeof e.sha256 === 'string';
  return false;
}

// Every recorded path must sit under its base's .claude or .kiro directory
// (spelled without . or .. parts). This is checked on the path text only: a
// symlinked parent directory is followed, so a crafted entry under one can
// make --uninstall or the prune delete a file outside these directories.
function insideBase(base, p) {
  if (!isAbsolute(p) || resolve(p) !== p) return false;
  return [join(base, '.claude'), join(base, '.kiro')].some((root) => p.startsWith(root + sep));
}

function validManifest(m) {
  if (!m || typeof m !== 'object' || m.version !== MANIFEST_VERSION) return false;
  if (!m.bases || typeof m.bases !== 'object' || Array.isArray(m.bases)) return false;
  for (const [base, rec] of Object.entries(m.bases)) {
    if (!isAbsolute(base) || !rec || typeof rec !== 'object' || !rec.areas || typeof rec.areas !== 'object') return false;
    for (const [area, entries] of Object.entries(rec.areas)) {
      if (!AREAS.includes(area) || !entries || typeof entries !== 'object') return false;
      for (const [p, e] of Object.entries(entries)) if (!insideBase(base, p) || !validEntry(e)) return false;
    }
  }
  return true;
}

// The manifest's text, or null when there is none (ENOENT). A manifest that
// exists but cannot be read (permission denied, a directory in its place) stops
// the run before it changes anything: read as empty, it would let the run
// overwrite or delete what its records protect (an edited Kiro copy, the
// records of other install bases) and then save over it.
function readManifestText() {
  try { return readFileSync(MANIFEST_FILE, 'utf8'); } catch (e) {
    if (e.code === 'ENOENT') return null;
    throw new Error(`Could not read the install manifest ${MANIFEST_FILE} (${e.code || e.message}). It records what the installer created, so nothing was changed; make it readable, then re-run.`);
  }
}

// The ref the manifest recorded for an install base (source.ref), read without
// changing anything; null when there is no valid record.
function recordedRef(base) {
  const text = readManifestText();
  if (text === null) return null;
  try {
    const m = JSON.parse(text);
    const rec = validManifest(m) ? m.bases[base] : null;
    return rec && rec.source && typeof rec.source.ref === 'string' ? rec.source.ref : null;
  } catch { return null; }
}

function loadManifest() {
  const text = readManifestText();
  if (text === null) return { version: MANIFEST_VERSION, bases: {} };
  let m = null;
  try { m = JSON.parse(text); } catch { m = null; }
  if (validManifest(m)) return m;
  const kept = `${MANIFEST_FILE}.corrupt`;
  let moved = false;
  try { renameSync(MANIFEST_FILE, kept); moved = true; } catch { /* reported below */ }
  warn(`The install manifest ${MANIFEST_FILE} is not valid; ${moved ? `it was moved to ${kept} and ` : ''}this run uses the built-in ownership rules`);
  return { version: MANIFEST_VERSION, bases: {} };
}

// Written to a temporary file and renamed, so a crash never leaves half a manifest.
function saveManifest(m) {
  const tmp = `${MANIFEST_FILE}.tmp-${process.pid}`;
  try {
    mkdirSync(STATE_DIR, { recursive: true });
    writeFileSync(tmp, `${JSON.stringify(m, null, 2)}\n`);
    renameSync(tmp, MANIFEST_FILE);
  } catch (e) {
    try { unlinkSync(tmp); } catch { /* nothing to clean */ }
    manifestLost = true;
    warn(`Could not save the install manifest ${MANIFEST_FILE} (${e.code || e.message}). Later runs will not know what this run did:`);
    logErr('  --uninstall and the prune use the last saved record (with none, the built-in ownership rules), so they miss what this run added, and --update, --claude-only or --kiro-only forgets a --no-steering choice made in this run.');
  }
}

function entryMatches(p, e) {
  const st = lstatOrNull(p);
  if (!st) return false;
  if (e.kind === 'link') {
    try { return st.isSymbolicLink() && readlinkSync(p) === e.target; } catch { return false; }
  }
  if (e.kind === 'copy') {
    try { return st.isFile() && sha256(readFileSync(p)) === e.sha256; } catch { return false; }
  }
  return false;
}

// The current run: entries written per area, merged into the manifest at the end.
const run = { manifest: null, base: null, prev: null, areas: {}, source: null, steering: undefined, touched: false };

function record(area, p, entry) {
  if (!run.areas[area]) run.areas[area] = {};
  run.areas[area][p] = entry;
  run.touched = true;
}
function startArea(area) {
  if (!run.areas[area]) run.areas[area] = {};
  run.touched = true;
}
function prevArea(area) {
  return run.prev && run.prev.areas[area] ? run.prev.areas[area] : null;
}

// After a run that stopped part way (crashed), an area's record is merged per
// entry: the entries the run did not reach are kept, so a later prune or
// --uninstall still finds them. A finished run replaces each area it wrote.
function saveRun(crashed = false) {
  if (!run.manifest || !run.touched) return;
  const prev = run.prev || { areas: {} };
  const areas = { ...prev.areas };
  for (const [area, entries] of Object.entries(run.areas)) areas[area] = crashed ? { ...(prev.areas[area] || {}), ...entries } : entries;
  const rec = { ...prev, areas, updatedAt: new Date().toISOString() };
  if (run.source) rec.source = run.source;
  if (run.steering !== undefined) rec.steering = run.steering;
  run.manifest.bases[run.base] = rec;
  saveManifest(run.manifest);
  run.touched = false;
}

// A recorded Kiro copy whose content no longer matches the recorded SHA-256 was
// edited (the test --uninstall uses: entryMatches). Install, --update and the
// prune keep it, list it under "changed since" (exit 3) and carry its entry
// into this run's record, so later runs and --uninstall still keep it.
function keepIfEdited(area, p, e) {
  if (!e || e.kind !== 'copy' || !lstatOrNull(p) || entryMatches(p, e)) return false;
  if (!changed.includes(p)) changed.push(p);
  record(area, p, e);
  return true;
}

// Remove the previous run's entries in an area that this run did not write
// again, while they still match what was recorded (for example skills absent
// from a pinned older release). With no record for the area, remove dangling
// links into the clone, as v1.2.0 did.
// With a record, dangling links into the clone that the record lacks (left by
// a run that stopped part way) are removed too.
function pruneArea(area, dir) {
  const prev = prevArea(area);
  const now = run.areas[area] || {};
  let pruned = 0;
  if (prev) {
    for (const [p, e] of Object.entries(prev)) {
      if (now[p]) continue;
      if (!entryMatches(p, e)) { if (!keepIfEdited(area, p, e) && keepUnreadable(p)) record(area, p, e); continue; }
      if (tryUnlink(p)) pruned++; else record(area, p, e);
    }
  }
  if (dir && existsSync(dir)) {
    for (const entry of listDir(dir)) {
      const full = join(dir, entry);
      if (!now[full] && isInstallerLink(full) && !existsSync(full) && tryUnlink(full)) pruned++;
    }
  }
  return pruned;
}

// ---------------------------------------------------------------- install
// Returns 'skip' (already correct), 'created', or 'conflict' (a file,
// directory or symlink the installer did not create sits at linkPath; only a
// link into the installer's clone is ever replaced, anything else is left alone).
function safeSymlink(area, target, linkPath) {
  const want = linkText(target, linkPath);
  const st = lstatOrNull(linkPath);
  if (st) {
    if (!isInstallerLink(linkPath)) {
      conflicts.push(linkPath);
      return 'conflict';
    }
    if (readlinkSync(linkPath) === want && existsSync(linkPath)) {
      record(area, linkPath, { kind: 'link', target: want });
      return 'skip';
    }
    // a stale, dangling or differently spelled link into the clone; when it
    // cannot be removed it stays recorded, so a later run still finds it
    if (!tryUnlink(linkPath)) { record(area, linkPath, { kind: 'link', target: readlinkSync(linkPath) }); return 'conflict'; }
  }
  try {
    symlinkSync(want, linkPath);
  } catch (e) {
    cannotWrite(linkPath, e);
    return 'conflict';
  }
  record(area, linkPath, { kind: 'link', target: want });
  return 'created';
}

function symlinkSkills(area, targetDir, skills) {
  if (!prepareDir(targetDir)) return null;
  startArea(area);
  let count = 0;
  let linked = 0;
  for (const name of skills) {
    const result = safeSymlink(area, join(INSTALL_DIR, 'skills', name), join(targetDir, name));
    if (result === 'created') count++;
    if (result !== 'conflict') linked++;
  }
  const pruned = pruneArea(area, targetDir);
  if (pruned > 0) info(`Removed ${pruned} links to skills that are not in this version`);
  // The line names the links in place (new or already there), not the skills
  // found, so a run that skipped every path does not read as installed.
  if (linked === 0) info(`Nothing installed to ${c.dim}${targetDir}${c.reset}: ${skills.length} paths skipped (listed below)`);
  else success(`Installed ${linked} skills to ${c.dim}${targetDir}${c.reset}${count > 0 ? ` (${count} new)` : ''}`);
  return count;
}

function symlinkSteeringClaude(claudeBase) {
  const area = 'claude-steering';
  const commandsSource = join(INSTALL_DIR, 'steering', 'commands', 'apex');
  startArea(area);
  // A tree with no steering/ (the v2 layout): the recorded links into it
  // would dangle, so they are pruned.
  if (!existsSync(commandsSource)) { warn('No steering commands found in repo'); pruneArea(area, null); return; }
  const commandsDir = join(claudeBase, 'commands');
  if (prepareDir(commandsDir)) {
    const link = join(commandsDir, 'apex');
    if (safeSymlink(area, commandsSource, link) !== 'conflict') {
      success(`Steering commands linked to ${c.dim}${link}${c.reset}`);
    }
  }
  // The /apex:* commands import @~/.claude/apex-steering/...; the eks-operation-review skill tells Claude to read a file there.
  const steeringLink = join(claudeBase, 'apex-steering');
  if (safeSymlink(area, join(INSTALL_DIR, 'steering'), steeringLink) !== 'conflict') {
    success(`Steering workflows linked to ${c.dim}${steeringLink}${c.reset}`);
  }
  pruneArea(area, null);
}

// Kiro loads steering files without an inclusion key into every interaction,
// so the workflows are installed as copies marked `inclusion: manual` (they
// then appear as slash commands; Kiro CLI V1/V2 support inclusion modes only
// partially). The marker, on the first line after the frontmatter, identifies
// the copies. Only a marked file under a current workflow name is overwritten,
// and not when the manifest records it with another hash and it does not hold
// this release's text (an edited copy is kept, as --uninstall keeps it); a
// marked file under any other name (a renamed copy) is reported and kept,
// unless the manifest shows the installer wrote it and it is unchanged.
const KIRO_MARKER = '<!-- apex-skills installer: generated copy of steering/workflows; installer 1.3.0 install, --update and --uninstall keep this file once you edit it and list it (exit code 3), but replace or delete it when there is no install record for this home or project directory (no manifest, or the directory was moved or renamed since); a 1.2.0 install or --update replaces it (a plain npx apex-skills runs the version that npm view apex-skills version prints); to be safe, save your own version under another name -->';

function isKiroCopy(p) {
  const st = lstatOrNull(p);
  if (!st || !st.isFile()) return false;
  try {
    const m = readFileSync(p, 'utf8').match(/^---\r?\n[\s\S]*?\r?\n---\r?\n(.*)/);
    return m !== null && m[1].replace(/\r$/, '') === KIRO_MARKER;
  } catch { return false; }
}

function kiroWorkflowNames() {
  const source = join(INSTALL_DIR, 'steering', 'workflows');
  try { return readdirSync(source).filter((f) => f.endsWith('.md')); } catch { return []; }
}

function withManualInclusion(text) {
  const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/);
  if (!m) return `---\ninclusion: manual\n---\n${KIRO_MARKER}\n${text}`;
  const fm = m[1].split(/\r?\n/).filter((l) => !/^inclusion\s*:/.test(l));
  fm.push('inclusion: manual');
  return `---\n${fm.join('\n')}\n---\n${KIRO_MARKER}\n${text.slice(m[0].length)}`;
}

function installSteeringKiro(steeringDir) {
  const area = 'kiro-steering';
  const source = join(INSTALL_DIR, 'steering', 'workflows');
  // A tree with no steering/ (the v2 layout): unchanged recorded copies are
  // pruned, as for workflows that left the repo; edited ones are kept.
  if (!existsSync(source)) { warn('No steering workflows found in repo'); startArea(area); pruneArea(area, null); return; }
  if (!prepareDir(steeringDir)) return;
  startArea(area);
  const files = kiroWorkflowNames();
  const prev = prevArea(area);
  let written = 0;
  for (const file of files) {
    const dest = join(steeringDir, file);
    const st = lstatOrNull(dest);
    const text = withManualInclusion(readFileSync(join(source, file), 'utf8'));
    // A copy that already holds this release's text is the installer's (a run
    // cut off after writing it, before the manifest was saved), not an edit.
    const current = { kind: 'copy', sha256: sha256(text) };
    if (st && isInstallerLink(dest)) { if (!tryUnlink(dest)) continue; } // links from installer v1.2.0 and earlier
    // A recorded copy that lost its marker (emptied, or replaced) is listed
    // once, as changed since, not also as a path the installer did not create.
    else if (st && !isKiroCopy(dest)) { if (!keepIfEdited(area, dest, prev && prev[dest])) conflicts.push(dest); continue; }
    else if (st && !entryMatches(dest, current) && keepIfEdited(area, dest, prev && prev[dest])) continue;
    // Already this release's text, as recorded: not written again, as an
    // up-to-date link is not, so a read-only copy that is current is no error.
    else if (st && prev && prev[dest] && prev[dest].sha256 === current.sha256 && entryMatches(dest, current)) { record(area, dest, current); written++; continue; }
    try {
      writeFileSync(dest, text);
    } catch (e) {
      // Only a refused write is listed; any other error (a full disk, an I/O
      // error) can leave half a copy, so it stops the run with that error.
      if (!writeBlocked(e)) throw e;
      cannotWrite(dest, e);
      if (prev && prev[dest] && lstatOrNull(dest)) record(area, dest, prev[dest]);
      continue;
    }
    record(area, dest, { kind: 'copy', sha256: sha256(text) });
    written++;
  }
  // Copies of workflows that no longer exist: removed when the manifest shows
  // they are the installer's and unchanged; with no record, only dangling
  // installer links are dropped. Edited recorded copies are listed as changed;
  // other marked copies are reported and kept.
  pruneArea(area, null);
  for (const entry of listDir(steeringDir)) {
    const full = join(steeringDir, entry);
    if (files.includes(entry) || changed.includes(full)) continue;
    if (!prev && isInstallerLink(full) && !existsSync(full)) tryUnlink(full);
    else if (isKiroCopy(full)) keptCopies.push(full);
  }
  success(`Steering workflows copied to ${c.dim}${steeringDir}${c.reset} as manual steering (${written} files)`);
}

function reportConflicts() {
  if (conflicts.length > 0) {
    warn(`Skipped ${conflicts.length} path(s) that already exist and were not created by this installer:`);
    for (const p of conflicts) logErr(`    ${p}`);
    warn('Move or rename them, then re-run to install those items.');
  }
  if (changed.length > 0) {
    warn(`Kept ${changed.length} path(s) the installer created that were changed since:`);
    for (const p of changed) logErr(`    ${p}`);
  }
  if (keptCopies.length > 0) {
    warn(`Kept ${keptCopies.length} file(s) that carry the installer's marker but are not a recorded copy of a current workflow:`);
    for (const p of keptCopies) logErr(`    ${p}`);
  }
  if (keptUnknown.length > 0) {
    warn(`Kept ${keptUnknown.length} file(s) that carry the installer's marker: with no ~/.apex-skills and no install manifest record, the installer cannot tell its copies from yours (delete them by hand if they are not yours):`);
    for (const p of keptUnknown) logErr(`    ${p}`);
  }
  if (blocked.length > 0) {
    warn(`Could not write or read ${blocked.length} path(s) (permission denied); fix the permissions, then re-run:`);
    for (const p of blocked) logErr(`    ${p}`);
  }
}

function skippedSomething() {
  return conflicts.length > 0 || changed.length > 0 || blocked.length > 0 || manifestLost;
}

// ---------------------------------------------------------------- uninstall
function uninstall(flags) {
  banner();
  info('Uninstalling APEX skills...');
  // --project removes the install made in the current directory, not the global one.
  const base = flags.project ? process.cwd() : HOME_BASE;
  const claudeBase = join(base, '.claude');
  const kiroBase = join(base, '.kiro');
  const manifest = loadManifest();
  const rec = manifest.bases[base] || null;

  let removed = 0;
  const workflowNames = kiroWorkflowNames();
  const noClone = !existsSync(join(INSTALL_DIR, 'steering', 'workflows'));
  const removeIfInstalled = (p, kiroSteering = false) => {
    if (isInstallerLink(p)) { if (tryUnlink(p)) removed++; return; }
    if (kiroSteering && isKiroCopy(p)) {
      if (workflowNames.includes(basename(p))) { if (tryUnlink(p)) removed++; } else (noClone ? keptUnknown : keptCopies).push(p);
    }
  };
  // Dangling links into the clone that a record lacks (left by a run that
  // stopped part way) are removed with the recorded entries.
  const sweepDangling = (dir) => {
    if (!existsSync(dir)) return;
    for (const entry of listDir(dir)) {
      const full = join(dir, entry);
      if (isInstallerLink(full) && !existsSync(full) && tryUnlink(full)) removed++;
    }
  };
  const areaDir = {
    'claude-skills': join(claudeBase, 'skills'),
    'kiro-skills': join(kiroBase, 'skills'),
  };
  const sweep = (dir, kiroSteering = false) => {
    if (!existsSync(dir)) return;
    for (const entry of listDir(dir)) removeIfInstalled(join(dir, entry), kiroSteering);
  };
  // With a record for the area: remove exactly its entries that still match.
  // With a record for the base but not the area (Kiro after a --claude-only
  // install): nothing is removed there, so a link of the user's is kept.
  // With no record for the base: the v1.2.0 rules (links into the clone,
  // marked Kiro copies).
  const fallback = {
    'claude-skills': () => sweep(join(claudeBase, 'skills')),
    'claude-steering': () => { removeIfInstalled(join(claudeBase, 'commands', 'apex')); removeIfInstalled(join(claudeBase, 'apex-steering')); },
    'kiro-skills': () => sweep(join(kiroBase, 'skills')),
    'kiro-steering': () => sweep(join(kiroBase, 'steering'), true),
  };
  const areaPaths = {
    'claude-skills': join(claudeBase, 'skills'),
    'claude-steering': `${join(claudeBase, 'commands', 'apex')} and ${join(claudeBase, 'apex-steering')}`,
    'kiro-skills': join(kiroBase, 'skills'),
    'kiro-steering': join(kiroBase, 'steering'),
  };
  const areas = AREAS.filter((a) => (a.startsWith('claude') ? !flags.kiroOnly : !flags.claudeOnly));
  for (const area of areas) {
    const entries = rec && rec.areas[area];
    if (!entries) {
      if (!rec) fallback[area]();
      else info(`Nothing recorded for ${areaPaths[area]} in this install's record; anything there is left as it is.`);
      continue;
    }
    // Kept entries (changed since, or not removable) stay recorded, so a later
    // install still keeps them; removed and missing ones leave the record.
    const keep = {};
    for (const [p, e] of Object.entries(entries)) {
      if (entryMatches(p, e)) { if (tryUnlink(p)) removed++; else keep[p] = e; } else if (lstatOrNull(p)) { changed.push(p); keep[p] = e; } else if (keepUnreadable(p)) keep[p] = e;
    }
    if (areaDir[area]) sweepDangling(areaDir[area]);
    if (Object.keys(keep).length > 0) rec.areas[area] = keep; else delete rec.areas[area];
    if (area === 'kiro-steering') {
      const dir = join(kiroBase, 'steering');
      if (existsSync(dir)) for (const entry of listDir(dir)) { const full = join(dir, entry); if (isKiroCopy(full) && !changed.includes(full) && !blocked.includes(full)) keptCopies.push(full); }
    }
  }
  if (rec) {
    if (Object.keys(rec.areas).length === 0) delete manifest.bases[base];
    saveManifest(manifest);
  }

  success(`Removed ${removed} installed entries from ${c.dim}${base}${c.reset}`);
  reportConflicts();

  // A file or a directory that is not a clone is not the installer's: no rm -rf advice.
  if (existsSync(INSTALL_DIR) && !hasGit()) info(`git is not in PATH, so ${INSTALL_DIR} was not checked and is left alone`);
  else if (existsSync(INSTALL_DIR) && !isOwnClone()) info(`${INSTALL_DIR} is not a git clone or cannot be read, so the installer leaves it alone`);
  else if (existsSync(INSTALL_DIR)) {
    info(`Repository still at ${INSTALL_DIR}`);
    // The clone is shared: while the manifest records another install base,
    // removing it would break that install. The hint is left out too while
    // this base still records entries (a scoped --uninstall, or entries kept)
    // and when this run kept anything (listed above).
    const others = Object.keys(manifest.bases).filter((b) => b !== base);
    const keptSome = conflicts.length + changed.length + blocked.length + keptCopies.length + keptUnknown.length > 0;
    if (others.length > 0) info(`~/.apex-skills is still used by the install${others.length > 1 ? 's' : ''} in ${others.join(', ')}; keep it`);
    else if (!manifest.bases[base] && !keptSome) info('To remove it too, once nothing else uses it (this run sees only the installs the manifest records; installs made before 1.3.0 are not recorded): rm -rf ~/.apex-skills (this also deletes anything you changed or added in it)');
  }
  log('');
  return skippedSomething() ? EXIT_SKIPPED : EXIT_OK;
}

function showHelp() {
  banner();
  log(`${c.bold}Usage:${c.reset}  npx apex-skills [flags]\n`);
  log(`${c.bold}Flags:${c.reset}`);
  log(`  --claude-only        Install for Claude Code only; asks no steering question: steering is installed`);
  log(`                       unless --no-steering or a saved no-steering choice`);
  log(`  --kiro-only          Install for Kiro CLI only; asks no steering question: steering is installed`);
  log(`                       unless --no-steering or a saved no-steering choice`);
  log(`  --project            Install to current project instead of global`);
  log(`  --no-steering        Skip steering/commands setup. Steering an earlier run installed is not removed:`);
  log(`                       the Kiro copies stay and are not updated (they go stale), while the Claude Code`);
  log(`                       links stay and follow the clone. To remove it, run --uninstall, then install`);
  log(`                       with --no-steering`);
  log(`  --update             Move to the latest release of the clone's major line (v1 or v2) and reinstall`);
  log(`                       links and steering copies (non-interactive; a branch chosen with --branch is`);
  log(`                       followed). It keeps a saved no-steering choice (--no-steering or n), as`);
  log(`                       --claude-only and --kiro-only do; a run that asks the steering question`);
  log(`                       records the answer again, and -y or closed stdin answers y`);
  log(`  --version <tag>      Pin to a specific tag, pre-releases included (e.g. v1.1.0); a later install`);
  log(`                       or --update without --version or --branch moves to the latest release (see`);
  log(`                       Source below)`);
  log(`  --branch <name>      Follow a branch (e.g. main) instead of the latest v1 release`);
  log(`  --uninstall          Remove installed links and steering copies (keeps cloned repo); honours`);
  log(`                       --project, --claude-only and --kiro-only`);
  log(`  -y, --yes            Take the default answer to every question (no prompts)`);
  log(`  -h, --help           Show this help\n`);
  log(`${c.bold}Exit codes:${c.reset}`);
  log(`  0  done   1  error (for example no v1 release tag found)   2  bad flags (nothing changed)`);
  log(`  3  done, but some paths were skipped or could not be written, or the install manifest was not saved (listed on stderr)`);
  log(`  130  cancelled by Ctrl-C or Ctrl-D at a terminal: at a question, nothing was changed; a Ctrl-C`);
  log(`       later stops the run part way: run it again to finish before --uninstall: links a stopped`);
  log(`       run made are not recorded, so --uninstall can keep them and rm -rf ~/.apex-skills would`);
  log(`       leave them dangling\n`);
  log(`${c.bold}Source:${c.reset} without --version or --branch, a fresh install uses the newest v1.x.y release tag`);
  log(`(numeric order), or of v2 when the install manifest records a v2 tag for this install base.`);
  log(`--update stays on the clone's major line: a v1 clone moves to the newest v1.x.y, a v2 clone to the`);
  log(`newest v2.x.y. Pre-release tags such as v1.3.0-rc.0 are used only when named with --version, and`);
  log(`so is v2.0.0 for a fresh install with no v2 record. When a v2.0.0 or later release exists, a run`);
  log(`that leaves the clone on v1, on a tag of no major line (the line names the tag) or on a branch,`);
  log(`and can read the remote's tags, prints one line on stderr about it. A plain run on an existing`);
  log(`clone updates it as --update does.\n`);
  log(`${c.bold}Examples:${c.reset}`);
  log(`  npx apex-skills                        Interactive install`);
  log(`  npx apex-skills -y                     Install with the default answers`);
  log(`  npx apex-skills --update               Update to the latest release of the clone's major line`);
  log(`  npx apex-skills --branch main          Follow main (unreleased changes) instead`);
  log(`  npx apex-skills --version v1.1.0       Pin to release v1.1.0`);
  log(`  npx apex-skills --branch feat/new-eks  Install from a branch`);
  log(`  npx apex-skills --claude-only          Install for Claude Code only`);
  log(`  npx apex-skills --project              Install into current project\n`);
}

// ---------------------------------------------------------------- main
async function main() {
  let flags;
  try {
    flags = parseArgs(process.argv.slice(2));
  } catch (e) {
    if (!(e instanceof UsageError)) throw e;
    error(e.message);
    logErr('Run npx apex-skills --help for the list of flags. Nothing was changed.');
    return EXIT_USAGE;
  }
  // --update asks nothing: with neither ~/.claude nor ~/.kiro it takes the
  // default target, as -y does.
  assumeYes = flags.yes || flags.update;

  if (flags.help) { showHelp(); return EXIT_OK; }

  if (!isAbsolute(HOME)) {
    error(`HOME is ${HOME ? `"${HOME}", not an absolute path` : 'empty'}, so there is no safe place to install. Set HOME and re-run. Nothing was changed.`);
    return EXIT_ERROR;
  }
  if (REPO_URL.startsWith('-')) {
    error(`APEX_SKILLS_REPO_URL ("${REPO_URL}") starts with "-", which git would read as an option. Nothing was changed.`);
    return EXIT_ERROR;
  }

  if (platform() === 'win32') {
    error('Native Windows is not supported (the installer relies on symlinks). Nothing was installed.');
    error('Use WSL (Windows Subsystem for Linux): open a WSL shell and run npx apex-skills there.');
    return EXIT_ERROR;
  }

  if (flags.uninstall) return uninstall(flags);

  banner();

  if (!hasGit()) {
    error('git is required but not found in PATH.');
    return EXIT_ERROR;
  }
  // An unreadable install manifest stops the run here, before the clone moves.
  readManifestText();

  // Detect targets. A missing ~/.claude or ~/.kiro is created only once the
  // clone is in place, so a run that stops at the clone creates nothing.
  const claudeDir = join(HOME, '.claude');
  const kiroDir = join(HOME, '.kiro');
  let installClaude = !flags.kiroOnly && existsSync(claudeDir);
  let installKiro = !flags.claudeOnly && existsSync(kiroDir);
  const createDirs = [];

  if (!installClaude && !installKiro && !flags.claudeOnly && !flags.kiroOnly) {
    warn('Neither ~/.claude nor ~/.kiro found.');
    const choice = await ask('Create directory for (claude/kiro/both)', 'claude');
    if (assumeYes) info(`Taking the default answer: ${choice}`);
    if (choice === 'claude' || choice === 'both') { createDirs.push(claudeDir); installClaude = true; }
    if (choice === 'kiro' || choice === 'both') { createDirs.push(kiroDir); installKiro = true; }
    if (!installClaude && !installKiro) { error('No target selected.'); return EXIT_ERROR; }
  }

  if (flags.claudeOnly && !existsSync(claudeDir)) { createDirs.push(claudeDir); installClaude = true; }
  if (flags.kiroOnly && !existsSync(kiroDir)) { createDirs.push(kiroDir); installKiro = true; }

  // The steering question is asked here, before the clone or any link, so a
  // run cancelled at any question has written nothing. --update asks nothing.
  let steeringAnswer = null;
  if (!flags.noSteering && !flags.update && !flags.claudeOnly && !flags.kiroOnly) {
    const answer = (await ask('Install steering workflows/commands? (y/n)', 'y')).toLowerCase();
    steeringAnswer = answer === 'y' || answer === 'yes';
  }
  closeInput();

  // Clone or update
  const outcome = cloneOrUpdate(flags);
  const sourceRef = outcome.ref;
  noteLaterRelease(outcome);
  // A path in the way of one (a file or a dangling symlink at ~/.claude) is
  // listed, and that tool's paths are skipped (exit code 3).
  for (const dir of createDirs) {
    try { mkdirSync(dir, { recursive: true }); } catch (e) { cannotWrite(dir, e); }
  }

  const skills = getSkills();
  if (skills.length === 0) { error('No skills found in repository.'); return EXIT_ERROR; }

  info(`Found ${skills.length} skills`);

  const installBase = flags.project ? process.cwd() : HOME_BASE;
  absoluteLinks = flags.project;
  run.manifest = loadManifest();
  run.base = installBase;
  run.prev = run.manifest.bases[installBase] || null;
  run.source = cloneSource(sourceRef);

  // Determine skill target directories
  const claudeSkillsDir = join(installBase, '.claude', 'skills');
  const kiroSkillsDir = join(installBase, '.kiro', 'skills');

  // Install skills
  if (installClaude) symlinkSkills('claude-skills', claudeSkillsDir, skills);
  if (installKiro) symlinkSkills('kiro-skills', kiroSkillsDir, skills);

  // Steering. A no-steering choice (--no-steering or answering n) is remembered
  // per install base in the manifest. --update, --claude-only and --kiro-only
  // ask no steering question, so they keep it; any other run records its
  // choice again (-y and closed stdin answer y). (v1.2.0 and earlier did not
  // remember it.)
  const keepsChoice = flags.update || flags.claudeOnly || flags.kiroOnly;
  const steeringOff = Boolean(run.prev && run.prev.steering === false);
  let doSteering = !flags.noSteering;
  if (doSteering && keepsChoice && steeringOff) {
    doSteering = false;
    // The hint names the ref the clone is on now, so following it adds
    // steering without moving a --version pin or leaving a --branch. It is
    // printed only when the record holds no steering from an earlier run.
    const keepRef = `${outcome.branch ? '--branch' : '--version'} ${sourceRef}`;
    // Steering an earlier run installed is not removed by turning it off, so
    // the record can still hold it; the line then says so instead. It counts
    // the recorded entries, so one deleted by hand since is still counted.
    // When every one of them was changed since (an edited Kiro copy, kept by
    // --uninstall too), the line names them for removal by hand instead.
    const leftOver = ['claude-steering', 'kiro-steering'].flatMap((area) => Object.entries(prevArea(area) || {}));
    const n = leftOver.length;
    const edited = leftOver.filter(([p, e]) => lstatOrNull(p) && !entryMatches(p, e)).map(([p]) => p);
    if (n > 0 && edited.length === n) {
      info(`Steering is off, as chosen at install (--no-steering or n): the Kiro copies are not updated and the Claude Code links follow the clone; ${n === 1 ? '1 steering entry from an earlier install was changed since it was installed, so --uninstall keeps it; to remove it, delete it by hand (the next --uninstall then clears its record):' : `${n} steering entries from an earlier install were changed since they were installed, so --uninstall keeps them; to remove them, delete them by hand (the next --uninstall then clears their record):`}`);
      for (const p of edited) log(`    ${p}`);
    } else if (n > 0) info(`Steering is off, as chosen at install (--no-steering or n): the Kiro copies are not updated and the Claude Code links follow the clone; ${n === 1 ? '1 steering entry from an earlier install is still recorded as installed (to remove it' : `${n} steering entries from an earlier install are still recorded as installed (to remove them`}: --uninstall, then install with --no-steering)${edited.length > 0 ? ` (${edited.length} of them changed since; --uninstall keeps and lists those)` : ''}`);
    else info(`Steering stays off, as chosen at install (--no-steering or n); to add it, run npx apex-skills ${keepRef} (without --update, --claude-only or --kiro-only; this run installs for every detected tool)`);
  } else if (steeringAnswer !== null) {
    doSteering = steeringAnswer;
  }
  run.steering = (!flags.update || flags.noSteering) ? doSteering : !steeringOff;
  run.touched = true;

  if (doSteering) {
    if (installClaude) {
      symlinkSteeringClaude(join(installBase, '.claude'));
      if (flags.project && !existsSync(join(claudeDir, 'apex-steering'))) {
        warn('The /apex:* commands import @~/.claude/apex-steering (your home directory);');
        warn('run a global install (npx apex-skills --claude-only) so those imports resolve.');
      }
    }
    if (installKiro) {
      installSteeringKiro(join(installBase, '.kiro', 'steering'));
    }
  }
  saveRun();
  reportConflicts();

  // Summary
  log('');
  // When the failed manifest save is the only cause of exit code 3, the line names it.
  const onlyManifest = manifestLost && conflicts.length + changed.length + blocked.length === 0;
  log(onlyManifest
    ? `${c.bold}${c.yellow}Done, but the install manifest could not be saved (see above); exit code ${EXIT_SKIPPED}.${c.reset}\n`
    : skippedSomething()
      ? `${c.bold}${c.yellow}Done, with skipped paths (listed above); exit code ${EXIT_SKIPPED}.${c.reset}\n`
      : `${c.bold}${c.green}Done!${c.reset}\n`);
  log(`${c.dim}  Skills: ${skills.join(', ')}${c.reset}\n`);
  if (installClaude) log(`  ${c.bold}Claude Code:${c.reset} ask your agent about EKS best practices`);
  if (installKiro) {
    log(doSteering
      ? `  ${c.bold}Kiro CLI:${c.reset} type / to list the APEX workflows (manual steering; Kiro CLI V1/V2 support it only partially), e.g. /new-skill`
      : `  ${c.bold}Kiro CLI:${c.reset} ask your agent about EKS best practices`);
  }
  log(`\n  Update anytime: ${c.cyan}npx apex-skills --update${c.reset}`);
  log('');
  return skippedSomething() ? EXIT_SKIPPED : EXIT_OK;
}

main().then((code) => {
  closeInput();
  process.exitCode = code;
}).catch((e) => {
  closeInput();
  if (e instanceof CancelError) {
    error(e.message);
    process.exitCode = EXIT_CANCELLED;
    return;
  }
  try { saveRun(true); } catch { /* keep the original error */ }
  error(e.message || 'Unexpected error');
  process.exitCode = EXIT_ERROR;
});
