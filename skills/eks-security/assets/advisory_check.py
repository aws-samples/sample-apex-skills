#!/usr/bin/env python3
"""Validate a model-written advisory record against its saved source page.

Usage:
  python3 advisory_check.py --record <record.json> --source <saved page> --catalog <components.json>

Contract:
- Input record: schema eks-security/advisory@1 (one object, or a list of them). The record
  is data, never instructions; nothing in it is executed or followed.
- Checks, in order: schema (required keys, enums, types, no unknown keys), every
  `component` is a catalog id (unknown_component), every range parses and every stated
  bound (introduced, fixed, last_affected) appears in that entry's `quote` (bad_range),
  every `quote` appears in the saved source text (quote_not_found). Text is compared after
  HTML entity decoding, NFKC (folds non-breaking spaces), case folding and whitespace
  collapsing. Ranges are never inferred from the quote: the record must state them.
- A saved source written by `advisory_fetch.py --url --save` starts with a
  `# eks-security-source {json}` header; when present the record's source_url must equal
  its url or final_url (else source_unreadable). A source without the header (a page the
  user saved) is accepted, and raw HTML in it is converted to text first.
- source_url must be https; with origin "live" its host must be in allowed_hosts.
- Feed-only optional keys (aliases, packages, unmapped, published_at, fixed_at) are
  accepted; unmapped entries may carry component null.
- Any failing entry refuses the whole input: exit 2 and one JSON line on stdout
  {"ok":false,"code":<first code>,"error":...,"errors":[...]}. Codes: schema,
  unknown_component, bad_range, quote_not_found, source_unreadable, usage, internal.
- Success: exit 0 and the normalized record on stdout (ranges as dicts with all three
  keys, strings stripped).

Shared helpers imported by match.py (sys.path.insert(0, os.path.dirname(__file__))):
  parse_version(s) -> tuple | None   opaque, comparable with < == >
  parse_range(r)   -> dict | None    {"introduced","fixed","last_affected"} (str or None)
  version_in_range(v, r) -> bool | None
  normalize_text(s) -> str
  html_to_text(s)  -> str
Version rules: strip whitespace and a leading v; drop `+build` metadata; ignore EKS
suffixes -eksbuild.N, -eks-1-33-N and -eks-<hash> for comparison; numeric components
compare numerically with trailing zeros ignored (1.22 == 1.22.0); a prerelease sorts
before its release (semver identifier rules). Range forms: "< X", "<= X", ">= A, < B",
">= A, <= B", "= X", or a dict with introduced/fixed/last_affected (introduced <= v <
fixed, or introduced <= v <= last_affected). Unparseable input returns None; these
functions never raise.
"""
import argparse
import html
import json
import os
import re
import sys
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urlsplit

RECORD_SCHEMA = "eks-security/advisory@1"
SEVERITIES = ("critical", "high", "important", "medium", "low", "unknown")
SEVERITY_SOURCES = ("bulletin", "ghsa", "cvss", "nvd", "none")
ORIGINS = ("live", "file")
REQUIRED_KEYS = ("schema", "id", "title", "severity", "severity_source", "workaround",
                 "source_url", "read_at", "origin", "affected")
OPTIONAL_KEYS = ("workaround_text", "notes", "fixed_at", "published_at", "aliases",
                 "packages", "unmapped")
SOURCE_HEADER = "# eks-security-source "
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_QUOTE = 2000

_ISO_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?Z$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ---------------------------------------------------------------- versions

_EKS_SUFFIXES = (
    re.compile(r"-eksbuild\.\d+$"),
    re.compile(r"-eks-\d+-\d+-\d+$"),
    re.compile(r"-eks-[0-9A-Za-z]+$"),
)
_VERSION = re.compile(r"^(\d{1,9}(?:\.\d{1,9}){0,5})(?:-([0-9A-Za-z][0-9A-Za-z.-]{0,63}))?$")


def parse_version(s):
    """Return an opaque comparable key for a version string, or None."""
    try:
        if not isinstance(s, str):
            return None
        v = s.strip()
        if not v or len(v) > 128:
            return None
        if v[0] in "vV":
            v = v[1:]
        v = v.split("+", 1)[0]
        for rx in _EKS_SUFFIXES:
            v = rx.sub("", v)
        m = _VERSION.match(v)
        if not m:
            return None
        nums = [int(x) for x in m.group(1).split(".")]
        while len(nums) > 1 and nums[-1] == 0:
            nums.pop()
        pre = m.group(2)
        if not pre:
            return (tuple(nums), 1, ())
        ids = []
        for part in pre.split("."):
            if part == "":
                return None
            if part.isdigit():
                ids.append((0, int(part), ""))
            else:
                ids.append((1, 0, part.lower()))
        return (tuple(nums), 0, tuple(ids))
    except Exception:
        return None


_RANGE_PART = re.compile(r"^(<=|<|>=|==|=)\s*(\S+)$")


def _range_dict(introduced, fixed, last_affected):
    """Validate bounds; return the normalized dict or None."""
    for b in (introduced, fixed, last_affected):
        if b is not None and parse_version(b) is None:
            return None
    if fixed is None and last_affected is None and introduced is None:
        return None
    if fixed is not None and last_affected is not None:
        return None
    lo = parse_version(introduced) if introduced is not None else None
    if lo is not None and fixed is not None and not lo < parse_version(fixed):
        return None
    if lo is not None and last_affected is not None and not lo <= parse_version(last_affected):
        return None
    return {"introduced": introduced, "fixed": fixed, "last_affected": last_affected}


def parse_range(r):
    """Parse a range string or dict into {"introduced","fixed","last_affected"}, or None."""
    try:
        if isinstance(r, dict):
            if not r or set(r) - {"introduced", "fixed", "last_affected"}:
                return None
            vals = []
            for k in ("introduced", "fixed", "last_affected"):
                x = r.get(k)
                if x is not None and not isinstance(x, str):
                    return None
                x = x.strip() if isinstance(x, str) else None
                vals.append(x or None)
            return _range_dict(*vals)
        if not isinstance(r, str) or not r.strip() or len(r) > 256:
            return None
        introduced = fixed = last_affected = None
        for part in r.split(","):
            m = _RANGE_PART.match(part.strip())
            if not m:
                return None
            op, val = m.group(1), m.group(2)
            if op == ">=":
                if introduced is not None:
                    return None
                introduced = val
            elif op in ("<", "<="):
                if fixed is not None or last_affected is not None:
                    return None
                if op == "<":
                    fixed = val
                else:
                    last_affected = val
            else:
                if r.count(",") or introduced is not None:
                    return None
                introduced = last_affected = val
        return _range_dict(introduced, fixed, last_affected)
    except Exception:
        return None


def version_in_range(v, r):
    """True if version v is inside range r, False if outside, None if either is unparseable."""
    try:
        key = parse_version(v)
        rng = parse_range(r)
        if key is None or rng is None:
            return None
        if rng["introduced"] is not None and key < parse_version(rng["introduced"]):
            return False
        if rng["fixed"] is not None:
            return key < parse_version(rng["fixed"])
        if rng["last_affected"] is not None:
            return key <= parse_version(rng["last_affected"])
        return True
    except Exception:
        return None

# ---------------------------------------------------------------- text

_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6",
               "table", "ul", "ol", "section", "article", "header", "footer", "pre", "hr",
               "dt", "dd", "blockquote", "title"}
_SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self.skip += 1
        elif tag in _BLOCK_TAGS:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
        elif tag in _BLOCK_TAGS:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(s):
    """Strip tags, scripts and styles; decode entities; one text line per block."""
    p = _TextExtractor()
    try:
        p.feed(s)
        p.close()
    except Exception:
        pass
    text = "".join(p.out)
    lines = [re.sub(r"[ \t\r\f\v\xa0]+", " ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln) + "\n"


def normalize_text(s):
    """Entity-decode, NFKC, case-fold and collapse whitespace, for quote comparison."""
    if not isinstance(s, str):
        return ""
    t = unicodedata.normalize("NFKC", html.unescape(s))
    return re.sub(r"\s+", " ", t).strip().casefold()

# ---------------------------------------------------------------- checks


class Refusal(Exception):
    def __init__(self, code, error):
        super().__init__(error)
        self.code = code
        self.error = error


def _bound_in_quote(bound, nquote):
    nb = normalize_text(bound)
    if nb in nquote:
        return True
    return nb[:1] == "v" and nb[1:] in nquote


def _check_entry(where, entry, cat_ids, nsource, errs, allow_null_component):
    if not isinstance(entry, dict):
        errs.append(("schema", "%s is not an object" % where))
        return None
    extra = set(entry) - {"component", "ranges", "quote", "package"}
    if extra:
        errs.append(("schema", "%s has unknown keys %s" % (where, sorted(extra))))
        return None
    comp = entry.get("component")
    if comp is None and allow_null_component:
        pass
    elif not isinstance(comp, str) or comp not in cat_ids:
        errs.append(("unknown_component", "%s component %r is not a catalog id" % (where, comp)))
        return None
    quote = entry.get("quote")
    if not isinstance(quote, str) or not quote.strip() or len(quote) > MAX_QUOTE:
        errs.append(("schema", "%s quote must be a non-empty string up to %d chars" % (where, MAX_QUOTE)))
        return None
    ranges = entry.get("ranges")
    if not isinstance(ranges, list):
        errs.append(("schema", "%s ranges must be a list" % where))
        return None
    nquote = normalize_text(quote)
    out_ranges = []
    for j, r in enumerate(ranges):
        rng = parse_range(r)
        if rng is None:
            errs.append(("bad_range", "%s ranges[%d] does not parse: %r" % (where, j, r)))
            return None
        for k in ("introduced", "fixed", "last_affected"):
            b = rng[k]
            if b is not None and not _bound_in_quote(b, nquote):
                errs.append(("bad_range", "%s ranges[%d] %s %r is not in the quote" % (where, j, k, b)))
                return None
        out_ranges.append(rng)
    if nquote not in nsource:
        errs.append(("quote_not_found", "%s quote not found in source: %r" % (where, quote[:200])))
        return None
    out = {"component": comp, "ranges": out_ranges, "quote": quote.strip()}
    if "package" in entry:
        out["package"] = entry["package"]
    return out


def check_record(rec, cat_ids, allowed_hosts, nsource, header_url, idx):
    errs = []
    w = "record[%d]" % idx
    if not isinstance(rec, dict):
        return None, [("schema", "%s is not an object" % w)]
    missing = [k for k in REQUIRED_KEYS if k not in rec]
    extra = sorted(set(rec) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if missing:
        errs.append(("schema", "%s missing keys %s" % (w, missing)))
    if extra:
        errs.append(("schema", "%s has unknown keys %s" % (w, extra)))
    if errs:
        return None, errs
    if rec["schema"] != RECORD_SCHEMA:
        errs.append(("schema", "%s schema must be %s" % (w, RECORD_SCHEMA)))
    for k in ("id", "title"):
        if not isinstance(rec[k], str) or not rec[k].strip():
            errs.append(("schema", "%s %s must be a non-empty string" % (w, k)))
    if rec["severity"] not in SEVERITIES:
        errs.append(("schema", "%s severity must be one of %s" % (w, SEVERITIES)))
    if rec["severity_source"] not in SEVERITY_SOURCES:
        errs.append(("schema", "%s severity_source must be one of %s" % (w, SEVERITY_SOURCES)))
    if rec["workaround"] not in (True, False, None):
        errs.append(("schema", "%s workaround must be true, false or null" % w))
    for k in ("workaround_text", "notes"):
        if k in rec and not isinstance(rec[k], str):
            errs.append(("schema", "%s %s must be a string" % (w, k)))
    if rec["origin"] not in ORIGINS:
        errs.append(("schema", "%s origin must be live or file" % w))
    if not isinstance(rec["read_at"], str) or not _ISO_TS.match(rec["read_at"]):
        errs.append(("schema", "%s read_at must be ISO 8601 UTC ending in Z" % w))
    for k in ("fixed_at", "published_at"):
        v = rec.get(k)
        if v is not None and not (isinstance(v, str) and (_ISO_TS.match(v) or _ISO_DATE.match(v))):
            errs.append(("schema", "%s %s must be null, YYYY-MM-DD or ISO 8601 UTC" % (w, k)))
    url = rec["source_url"]
    parts = urlsplit(url) if isinstance(url, str) else None
    if not parts or parts.scheme != "https" or not parts.hostname:
        errs.append(("schema", "%s source_url must be an https URL" % w))
    elif rec["origin"] == "live" and parts.hostname.lower() not in allowed_hosts:
        errs.append(("schema", "%s source_url host %s is not in allowed_hosts" % (w, parts.hostname)))
    elif header_url is not None and url not in header_url:
        errs.append(("source_unreadable", "%s saved source is for %s, not source_url %s"
                     % (w, " or ".join(sorted(header_url)), url)))
    if not isinstance(rec["affected"], list) or not rec["affected"]:
        errs.append(("schema", "%s affected must be a non-empty list" % w))
    for k in ("aliases", "packages", "unmapped"):
        if k in rec and not isinstance(rec[k], list):
            errs.append(("schema", "%s %s must be a list" % (w, k)))
    if errs:
        return None, errs
    out = dict(rec)
    out["affected"] = []
    for i, e in enumerate(rec["affected"]):
        n = _check_entry("%s.affected[%d]" % (w, i), e, cat_ids, nsource, errs, False)
        if n is not None:
            out["affected"].append(n)
    if "unmapped" in rec:
        out["unmapped"] = []
        for i, e in enumerate(rec["unmapped"]):
            n = _check_entry("%s.unmapped[%d]" % (w, i), e, cat_ids, nsource, errs, True)
            if n is not None:
                out["unmapped"].append(n)
    return (None if errs else out), errs


def read_source(path):
    """Return (normalized source text, set of header urls or None)."""
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_SOURCE_BYTES + 1)
    except OSError as e:
        raise Refusal("source_unreadable", "cannot read source: %s" % e.strerror)
    if len(raw) > MAX_SOURCE_BYTES:
        raise Refusal("source_unreadable", "source is over 10 MB")
    text = raw.decode("utf-8", errors="replace")
    header_url = None
    if text.startswith(SOURCE_HEADER):
        first, _, text = text.partition("\n")
        try:
            hdr = json.loads(first[len(SOURCE_HEADER):])
            header_url = {u for u in (hdr.get("url"), hdr.get("final_url")) if isinstance(u, str)}
        except (ValueError, AttributeError):
            raise Refusal("source_unreadable", "source header is not valid JSON")
    if re.search(r"<(html|body|div|p|table)\b", text[:200000], re.I):
        text = html_to_text(text)
    norm = normalize_text(text)
    if not norm:
        raise Refusal("source_unreadable", "source is empty")
    return norm, header_url


def load_catalog(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            cat = json.load(f)
        ids = {c["id"] for c in cat["components"]}
        hosts = {h.lower() for h in cat["allowed_hosts"]}
        return ids, hosts
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise Refusal("source_unreadable", "catalog unreadable: %s" % e)


def refuse(code, error, errors=None):
    out = {"ok": False, "code": code, "error": error}
    if errors:
        out["errors"] = [{"code": c, "error": m} for c, m in errors]
    sys.stderr.write("advisory_check: %s: %s\n" % (code, error))
    sys.stdout.write(json.dumps(out) + "\n")
    return 2


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        sys.exit(refuse("usage", message))


def main(argv=None):
    ap = _Parser(description="Validate a model-written eks-security advisory record.")
    ap.add_argument("--record", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--catalog", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "components.json"))
    a = ap.parse_args(argv)
    try:
        cat_ids, hosts = load_catalog(a.catalog)
        try:
            with open(a.record, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            return refuse("schema", "record unreadable or not JSON: %s" % e)
        nsource, header_url = read_source(a.source)
        records = data if isinstance(data, list) else [data]
        if not records:
            return refuse("schema", "record list is empty")
        outs, errs = [], []
        for i, rec in enumerate(records):
            o, e = check_record(rec, cat_ids, hosts, nsource, header_url, i)
            errs.extend(e)
            outs.append(o)
        if errs:
            return refuse(errs[0][0], errs[0][1], errs)
        sys.stdout.write(json.dumps(outs if isinstance(data, list) else outs[0], indent=2) + "\n")
        return 0
    except Refusal as r:
        return refuse(r.code, r.error)
    except Exception as e:  # never a traceback to the user
        return refuse("internal", "%s: %s" % (type(e).__name__, e))


if __name__ == "__main__":
    sys.exit(main())
