#!/usr/bin/env node
// Snapshot and compare a directory tree, for the existing-setup fixture
// (existing-setup-fixture.sh): did an installer leave the user's own paths alone?
//
//   node existing-setup-check.mjs snapshot <root> <out>
//     Records every path under <root> (the root included, symlinks not
//     followed): type, mode, and for a file its size, SHA-256 and mtime, for a
//     symlink its link text and mtime. One JSON object per line, sorted by path.
//
//   node existing-setup-check.mjs compare <before> <after>
//     Reports every path of <before> as unchanged, CHANGED (content, mode, type
//     or link target), REMOVED or MOVED (removed, and the same file content or
//     link text appeared at a new path), and lists paths only in <after> as
//     added (additive, allowed), one line per added top directory with a count.
//     A file or link rewritten with the same bytes is listed as touched (mtime
//     only), which is not a failure. Directory size and mtime are not compared:
//     they change whenever an entry is added beside the user's.
//
// Exit codes: 0 no user path changed, removed or moved; 1 at least one was;
// 2 bad command line or unreadable input.
//
// Written in Node (the installer's own runtime) rather than shell so lstat,
// readlink and SHA-256 behave the same on Linux and macOS (GNU and BSD stat
// differ).
import { lstatSync, readdirSync, readFileSync, readlinkSync, writeFileSync } from 'fs';
import { createHash } from 'crypto';
import { join, resolve } from 'path';

function usage(msg) {
  if (msg) process.stderr.write(`${msg}\n`);
  process.stderr.write('usage: existing-setup-check.mjs snapshot <root> <out>\n       existing-setup-check.mjs compare <before> <after>\n');
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
    try { e.sha256 = createHash('sha256').update(readFileSync(full)).digest('hex'); } catch (err) { e.error = err.code || String(err); }
    e.mtime = st.mtimeMs;
  } else if (e.type === 'link') {
    e.target = readlinkSync(full);
    e.mtime = st.mtimeMs;
  }
  return e;
}

function snapshot(root, out) {
  const abs = resolve(root);
  const entries = [];
  const walk = (full, rel) => {
    let e;
    try { e = entryFor(full, rel); } catch (err) { usage(`cannot read ${full}: ${err.message}`); }
    entries.push(e);
    if (e.type !== 'dir') return;
    let names;
    try { names = readdirSync(full); } catch (err) { e.error = err.code || String(err); return; }
    for (const n of names.sort()) walk(join(full, n), rel === '.' ? n : `${rel}/${n}`);
  };
  walk(abs, '.');
  entries.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  writeFileSync(out, entries.map((e) => JSON.stringify(e)).join('\n') + '\n');
  process.stdout.write(`snapshot: ${entries.length} paths under ${abs} -> ${out}\n`);
}

function load(file) {
  let text;
  try { text = readFileSync(file, 'utf8'); } catch (err) { usage(`cannot read ${file}: ${err.message}`); }
  const m = new Map();
  for (const line of text.split('\n')) if (line) { const e = JSON.parse(line); m.set(e.path, e); }
  return m;
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
  if (a.error !== b.error) what.push(`read error ${a.error || 'none'} -> ${b.error || 'none'}`);
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
  process.stdout.write(`added by installer (additive, allowed): ${added.length} paths\n`);
  for (const t of tops) {
    const e = after.get(t);
    const inside = added.filter((p) => p.startsWith(`${t}/`)).length;
    process.stdout.write(`  + ${t} (${e.type === 'link' ? `link -> ${e.target}` : e.type}${inside ? `, ${inside} paths inside` : ''})\n`);
  }
  process.stdout.write(`summary: ${before.size} user paths, ${unchanged} unchanged, ${bad} changed, removed or moved, ${touched.length} touched, ${added.length} added\n`);
  process.exit(bad > 0 ? 1 : 0);
}

const [cmd, x, y, ...rest] = process.argv.slice(2);
if (rest.length > 0 || !x || !y) usage();
if (cmd === 'snapshot') snapshot(x, y);
else if (cmd === 'compare') compare(x, y);
else usage(`unknown command: ${cmd}`);
