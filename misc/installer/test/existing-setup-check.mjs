#!/usr/bin/env node
// Snapshot and compare a directory tree, for the existing-setup fixture
// (existing-setup-fixture.sh): did an installer leave the user's own paths alone?
//
//   node existing-setup-check.mjs snapshot <root> <out>
//     Records every path under <root> (the root included, symlinks not
//     followed): type, mode, and for a file its size, SHA-256 and mtime, for a
//     symlink its link text and mtime. One JSON object per line, sorted by path.
//     Written to <out>.tmp, then renamed to <out>, so a cut-short write never
//     leaves a short <out>.
//
//   node existing-setup-check.mjs rebase <baseline> <root> <out>
//     Re-reads, under <root>, only the paths <baseline> holds and writes them to
//     <out> as a new baseline: for a user edit made between installer steps.
//     A path the user adds between steps is not in it; one that is gone is left
//     out.
//
//   node existing-setup-check.mjs compare <before> <after>
//     Reports every path of <before> as unchanged, CHANGED (content, mode, type
//     or link target), REMOVED or MOVED (removed, and the same file content or
//     link text appeared at a new path; first match in sort order), and lists paths only in <after> as
//     added, one line per added top directory with a count. Added paths are
//     allowed by this checker wherever they land, inside a user directory (a
//     dotfiles tree linked in, a backup file beside a user's file) included;
//     whether an add inside a user directory counts as "beside" the user's
//     setup is an open question for the user. A file or link rewritten with
//     the same bytes is listed as touched (mtime only), which is not a failure
//     (this checker's reading of "overwrite": a change of content, mode, type
//     or link target; whether a same-bytes rewrite counts is also an open
//     question for the user). Directory size and mtime are not compared: they
//     change whenever an entry is added beside the user's. Inode and link
//     count are not recorded either.
//
// Read errors: any path under <root> that cannot be read (lstat, readdir,
// readlink or the file's bytes) stops the snapshot with exit 2, so a snapshot
// never holds a path it could not check. A snapshot or baseline that is
// empty, has no root entry (".") or holds a line that is not a snapshot entry
// is refused with exit 2.
//
// Exit codes: 0 no user path changed, removed or moved; 1 at least one was;
// 2 bad command line, unreadable or invalid input, or an output that could not
// be written (the message is on stderr).
//
// Written in Node (the installer's own runtime) rather than shell so lstat,
// readlink and SHA-256 behave the same on Linux and macOS (GNU and BSD stat
// differ).
import { lstatSync, readdirSync, readFileSync, readlinkSync, renameSync, writeFileSync } from 'fs';
import { createHash } from 'crypto';
import { join, resolve } from 'path';

function usage(msg) {
  if (msg) process.stderr.write(`${msg}\n`);
  process.stderr.write('usage: existing-setup-check.mjs snapshot <root> <out>\n       existing-setup-check.mjs rebase <baseline> <root> <out>\n       existing-setup-check.mjs compare <before> <after>\n');
  process.exit(2);
}

function typeOf(st) {
  if (st.isSymbolicLink()) return 'link';
  if (st.isFile()) return 'file';
  if (st.isDirectory()) return 'dir';
  if (st.isFIFO()) return 'fifo';
  if (st.isSocket()) return 'socket';
  return 'other';
}

function entryFor(full, rel) {
  const st = lstatSync(full);
  const e = { path: rel, type: typeOf(st), mode: (st.mode & 0o7777).toString(8).padStart(4, '0') };
  if (e.type === 'file') {
    e.size = st.size;
    e.sha256 = createHash('sha256').update(readFileSync(full)).digest('hex');
    e.mtime = st.mtimeMs;
  } else if (e.type === 'link') {
    e.target = readlinkSync(full);
    e.mtime = st.mtimeMs;
  }
  return e;
}

function readEntry(full, rel) {
  try { return entryFor(full, rel); } catch (err) { return usage(`cannot read ${full}: ${err.message}`); }
}

function write(out, entries, what) {
  entries.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  try {
    writeFileSync(`${out}.tmp`, entries.map((e) => JSON.stringify(e)).join('\n') + '\n');
    renameSync(`${out}.tmp`, out);
  } catch (err) { usage(`cannot write ${out}: ${err.message}`); }
  process.stdout.write(`${what}: ${entries.length} paths -> ${out}\n`);
}

function snapshot(root, out) {
  const abs = resolve(root);
  const entries = [];
  const walk = (full, rel) => {
    const e = readEntry(full, rel);
    entries.push(e);
    if (e.type !== 'dir') return;
    let names;
    try { names = readdirSync(full); } catch (err) { usage(`cannot read ${full}: ${err.message}`); }
    for (const n of names.sort()) walk(join(full, n), rel === '.' ? n : `${rel}/${n}`);
  };
  walk(abs, '.');
  write(out, entries, `snapshot of ${abs}`);
}

function load(file) {
  let text;
  try { text = readFileSync(file, 'utf8'); } catch (err) { usage(`cannot read ${file}: ${err.message}`); }
  const m = new Map();
  let n = 0;
  for (const line of text.split('\n')) {
    n++;
    if (!line) continue;
    let e;
    try { e = JSON.parse(line); } catch (err) { usage(`${file}:${n}: not a snapshot entry (${err.message})`); }
    if (!e || typeof e.path !== 'string' || typeof e.type !== 'string') usage(`${file}:${n}: not a snapshot entry`);
    m.set(e.path, e);
  }
  if (!m.has('.')) usage(`${file}: empty, or no root entry ".": not a valid snapshot`);
  return m;
}

function rebase(baseFile, root, out) {
  const abs = resolve(root);
  const entries = [];
  for (const p of load(baseFile).keys()) {
    const full = p === '.' ? abs : join(abs, p);
    let st = null;
    try { st = lstatSync(full); } catch (err) { if (err.code !== 'ENOENT') usage(`cannot read ${full}: ${err.message}`); }
    if (st) entries.push(readEntry(full, p));
  }
  write(out, entries, `baseline from ${baseFile} re-read under ${abs}`);
}

function describe(e) {
  if (e.type === 'file') return `file ${e.mode} ${e.size} bytes sha256 ${e.sha256}`;
  if (e.type === 'link') return `link ${e.mode} -> ${e.target}`;
  return `${e.type} ${e.mode}`;
}

function differences(a, b) {
  const what = [];
  if (a.type !== b.type) what.push(`type ${a.type} -> ${b.type}`);
  if (a.mode !== b.mode) what.push(`mode ${a.mode} -> ${b.mode}`);
  if (a.type === 'file' && b.type === 'file' && (a.sha256 !== b.sha256 || a.size !== b.size)) what.push(`content (${a.size} bytes sha256 ${a.sha256} -> ${b.size} bytes sha256 ${b.sha256})`);
  if (a.type === 'link' && b.type === 'link' && a.target !== b.target) what.push(`target ${a.target} -> ${b.target}`);
  return what;
}

function compare(beforeFile, afterFile) {
  const before = load(beforeFile);
  const after = load(afterFile);
  const added = [...after.keys()].filter((p) => !before.has(p));
  const lines = [];
  const touched = [];
  let unchanged = 0;
  let bad = 0;
  for (const [p, a] of before) {
    const b = after.get(p);
    if (!b) {
      const dest = added.find((q) => {
        const n = after.get(q);
        return n.type === a.type && ((a.type === 'file' && n.sha256 === a.sha256) || (a.type === 'link' && n.target === a.target));
      });
      lines.push(dest ? `MOVED     ${p} -> ${dest}` : `REMOVED   ${p} (was ${describe(a)})`);
      bad++;
      continue;
    }
    const what = differences(a, b);
    if (what.length > 0) { lines.push(`CHANGED   ${p}: ${what.join('; ')}`); bad++; continue; }
    if (a.mtime !== undefined && a.mtime !== b.mtime) touched.push(p);
    lines.push(`unchanged ${p}`);
    unchanged++;
  }
  for (const l of lines) process.stdout.write(`${l}\n`);
  for (const p of touched) process.stdout.write(`touched   ${p}: same content and mode, mtime changed (rewritten in place; not a failure)\n`);
  // Added paths, folded under their topmost added ancestor.
  const tops = added.filter((p) => !added.some((q) => q !== p && p.startsWith(`${q}/`)));
  process.stdout.write(`added by installer (allowed by this checker): ${added.length} paths\n`);
  for (const t of tops) {
    const e = after.get(t);
    const inside = added.filter((p) => p.startsWith(`${t}/`)).length;
    process.stdout.write(`  + ${t} (${e.type === 'link' ? `link -> ${e.target}` : e.type}${inside ? `, ${inside} paths inside` : ''})\n`);
  }
  process.stdout.write(`summary: ${before.size} user paths, ${unchanged} unchanged, ${bad} changed, removed or moved, ${touched.length} touched, ${added.length} added\n`);
  process.exit(bad > 0 ? 1 : 0);
}

const [cmd, ...args] = process.argv.slice(2);
const need = { snapshot: 2, rebase: 3, compare: 2 }[cmd];
if (need === undefined) usage(cmd ? `unknown command: ${cmd}` : undefined);
if (args.length !== need || args.some((a) => !a)) usage();
if (cmd === 'snapshot') snapshot(...args);
else if (cmd === 'rebase') rebase(...args);
else compare(...args);
