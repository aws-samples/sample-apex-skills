#!/usr/bin/env python3
"""Read advisory feeds into eks-security/advisory@1 records, or save a bulletin page as text.

Usage (one source per run):
  advisory_fetch.py --ghsa <owner>/<repo>/<GHSA-id>   [--input <file>] [--out <file>]
  advisory_fetch.py --k8s                [--since YYYY-MM-DD] [--input <file>] [--out <file>]
  advisory_fetch.py --alas al2|al2023    [--since YYYY-MM-DD] [--input <file>] [--out <file>]
  advisory_fetch.py --bottlerocket       [--since YYYY-MM-DD] [--input <file>] [--out <file>]
  advisory_fetch.py --url <bulletin url> --save <file> [--input <saved html>]
  common: [--catalog components.json] (default: beside this script)

Contract:
- Network: HTTPS GET only, host must be in the catalog's allowed_hosts, redirects followed
  by hand (at most 5) and only to https allow-listed hosts, 20 s timeout, 10 MB cap per
  response (gzip feeds also capped at 100 MB decompressed), User-Agent "eks-security-skill".
  XML with a DOCTYPE or ENTITY declaration is refused. Feed text is data: nothing in it is
  executed or followed.
- --input reads a saved response instead of fetching (offline mode and tests); records then
  carry origin "file" and read_at = the file's mtime.
- Structured feeds produce a JSON list of records on stdout (or --out, mode 0600). Package
  and product names map to catalog ids through the aliases, case-insensitively; a package
  with no match goes to the record's `unmapped` list with component null, never into
  `affected`. GHSA ranges are parsed with advisory_check.parse_range and each affected
  entry's quote is the feed's own range string (entries for one component are merged, their
  quotes joined with "; "). Kubernetes feed, ALAS and Bottlerocket records carry no
  comparable ranges (empty `ranges`, match.py treats them as review items) with the reason
  in `notes`; ALAS and Bottlerocket list their packages in `packages`.
- --since filters k8s, ALAS and Bottlerocket by publish date; default is 30 days before now.
  Items with no date are kept.
- `workaround` is null in feed records: the feeds do not state it.
- Severity as published: GHSA `severity` ("moderate" read as medium); ALAS and Bottlerocket
  severity (severity_source "bulletin"); Kubernetes feed: the label on the "CVSS Rating"
  text, else the CVSS 3.x base score computed from the published vector (FIRST formula),
  else unknown.
- ALAS: --alas al2023 keeps ALAS2023* ids (incl. LIVEPATCH, NVIDIA), --alas al2 keeps the
  other ALAS2* ids; anything else is skipped with a count on stderr.
- --url --save writes the page as normalized text with a first line
  `# eks-security-source {"url","final_url","read_at","origin","sha256"}` (sha256 of the
  response body), then prints a one-line JSON summary. The model extracts a record from the
  text and advisory_check.py validates it against this file.
- Exit 0 ok; 2 on any error with one JSON line {"ok":false,"code","error"} on stdout and the
  message on stderr. Codes: usage, host_not_allowed, redirect_off_list, http_error,
  timeout, too_large, not_found, parse_error, internal.
"""
import argparse
import datetime as dt
import email.utils
import gzip
import hashlib
import io
import json
import os
import re
import socket
import ssl
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from advisory_check import RECORD_SCHEMA, html_to_text, parse_range  # noqa: E402

USER_AGENT = "eks-security-skill"
TIMEOUT = 20
MAX_BYTES = 10 * 1024 * 1024
MAX_GUNZIP = 100 * 1024 * 1024
MAX_REDIRECTS = 5
SEVERITY_MAP = {"critical": "critical", "high": "high", "important": "important",
                "medium": "medium", "moderate": "medium", "low": "low"}
_GHSA_ID = re.compile(r"^GHSA(-[23456789cfghjmpqrvwx]{4}){3}$", re.I)
_REPO_PART = re.compile(r"^(?!\.{1,2}$)[A-Za-z0-9_.-]{1,100}$")
_ALAS_TITLE = re.compile(r"^(ALAS[0-9A-Z._-]*?-\d{4}-\d+)\s*\(([a-z]+)\)\s*:\s*(.+)$", re.I)


class FetchError(Exception):
    def __init__(self, code, error):
        super().__init__(error)
        self.code = code
        self.error = error


def now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso(d):
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---------------------------------------------------------------- catalog


def load_catalog(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            cat = json.load(f)
        aliases = {}
        for c in cat["components"]:
            for name in [c["id"]] + list(c.get("aliases", [])):
                aliases[name.strip().casefold()] = c["id"]
        feeds = {f["id"]: f["url"] for f in cat["feeds"]}
        hosts = {h.lower() for h in cat["allowed_hosts"]}
        return aliases, feeds, hosts
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise FetchError("usage", "catalog unreadable: %s" % e)


def map_alias(aliases, name):
    if not isinstance(name, str):
        return None
    return aliases.get(name.strip().casefold())

# ---------------------------------------------------------------- network


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _check_url(url, hosts):
    p = urlsplit(url)
    if p.scheme != "https" or not p.hostname:
        raise FetchError("host_not_allowed", "only https URLs are fetched: %s" % url)
    if p.hostname.lower() not in hosts:
        raise FetchError("host_not_allowed", "host %s is not in allowed_hosts" % p.hostname)
    if p.username or p.password or (p.port not in (None, 443)):
        raise FetchError("host_not_allowed", "URL credentials or a non-443 port are refused")


def fetch(url, hosts, accept="*/*"):
    """GET url; return (body bytes, final url). Follows allow-listed redirects by hand."""
    opener = urllib.request.build_opener(_NoRedirect,
                                         urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    cur = url
    for _ in range(MAX_REDIRECTS + 1):
        try:
            _check_url(cur, hosts)
        except FetchError as e:
            if cur != url:
                raise FetchError("redirect_off_list", "redirect to %s refused: %s" % (cur, e.error))
            raise
        req = urllib.request.Request(cur, method="GET", headers={"User-Agent": USER_AGENT, "Accept": accept})
        try:
            resp = opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                loc = e.headers.get("Location")
                e.close()
                if not loc:
                    raise FetchError("http_error", "redirect with no Location from %s" % cur)
                cur = urljoin(cur, loc)
                continue
            if e.code == 404:
                raise FetchError("not_found", "HTTP 404 for %s" % cur)
            raise FetchError("http_error", "HTTP %d for %s" % (e.code, cur))
        except (socket.timeout, TimeoutError):
            raise FetchError("timeout", "no response from %s within %d s" % (cur, TIMEOUT))
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise FetchError("timeout", "no response from %s within %d s" % (cur, TIMEOUT))
            raise FetchError("http_error", "cannot reach %s: %s" % (cur, e.reason))
        with resp:
            body = resp.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise FetchError("too_large", "response from %s is over 10 MB" % cur)
        return body, cur
    raise FetchError("redirect_off_list", "more than %d redirects from %s" % (MAX_REDIRECTS, url))


def read_input(path):
    try:
        with open(path, "rb") as f:
            body = f.read(MAX_BYTES + 1)
        mtime = dt.datetime.fromtimestamp(os.stat(path).st_mtime, dt.timezone.utc)
    except OSError as e:
        raise FetchError("usage", "cannot read --input: %s" % e.strerror)
    if len(body) > MAX_BYTES:
        raise FetchError("too_large", "--input is over 10 MB")
    return body, iso(mtime)


def get(args, url, hosts, accept="*/*"):
    """Return (body, final_url, read_at, origin)."""
    if args.input:
        body, read_at = read_input(args.input)
        return body, url, read_at, "file"
    body, final = fetch(url, hosts, accept)
    return body, final, now_iso(), "live"

# ---------------------------------------------------------------- parsing helpers


def parse_json(body):
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise FetchError("parse_error", "response is not JSON: %s" % e)


def parse_xml(body):
    if body[:2] == b"\x1f\x8b":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as g:
                body = g.read(MAX_GUNZIP + 1)
        except (OSError, EOFError) as e:
            raise FetchError("parse_error", "bad gzip data: %s" % e)
        if len(body) > MAX_GUNZIP:
            raise FetchError("too_large", "decompressed feed is over 100 MB")
    head = body[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in body.upper():
        raise FetchError("parse_error", "XML with DOCTYPE or ENTITY declarations is refused")
    try:
        return ET.fromstring(body)
    except ET.ParseError as e:
        raise FetchError("parse_error", "response is not XML: %s" % e)


def parse_since(s):
    if s is None:
        return dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        raise FetchError("usage", "--since must be YYYY-MM-DD")


def parse_iso(s):
    if not isinstance(s, str):
        return None
    try:
        d = dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def severity(raw, source):
    s = SEVERITY_MAP.get(str(raw or "").strip().lower())
    return (s, source) if s else ("unknown", "none")


def base_record(rid, title, sev, sev_src, source_url, read_at, origin):
    return {"schema": RECORD_SCHEMA, "id": rid, "title": title, "severity": sev,
            "severity_source": sev_src, "workaround": None, "workaround_text": "",
            "source_url": source_url, "read_at": read_at, "origin": origin,
            "affected": [], "unmapped": [], "notes": ""}


def _text(el, tag):
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""

# ---------------------------------------------------------------- GHSA


def ghsa_records(data, aliases, read_at, origin, fallback_url):
    if isinstance(data, dict) and str(data.get("status")) == "404" or (
            isinstance(data, dict) and data.get("message") == "Not Found"):
        raise FetchError("not_found", "advisory not found")
    items = data if isinstance(data, list) else [data]
    out = []
    for adv in items:
        if not isinstance(adv, dict) or not isinstance(adv.get("vulnerabilities"), list):
            raise FetchError("parse_error", "not a GitHub security advisory object")
        ghsa = adv.get("ghsa_id") or ""
        cve = adv.get("cve_id") or ""
        sev, src = severity(adv.get("severity"), "ghsa")
        url = adv.get("html_url") or adv.get("url") or fallback_url
        rec = base_record(cve or ghsa, adv.get("summary") or "", sev, src, url, read_at, origin)
        rec["aliases"] = sorted({i.get("value") for i in adv.get("identifiers") or []
                                 if isinstance(i, dict) and i.get("value") and i.get("value") != rec["id"]}
                                | ({ghsa} if ghsa and ghsa != rec["id"] else set()))
        rec["published_at"] = adv.get("published_at")
        notes = []
        if adv.get("withdrawn_at"):
            notes.append("withdrawn at %s" % adv["withdrawn_at"])
        merged = {}
        for v in adv["vulnerabilities"]:
            if not isinstance(v, dict):
                continue
            pkg = (v.get("package") or {}).get("name") if isinstance(v.get("package"), dict) else None
            rstr = v.get("vulnerable_version_range") or ""
            rng = parse_range(rstr) if rstr else None
            patched = v.get("patched_versions") or v.get("first_patched_version")
            if isinstance(patched, dict):
                patched = patched.get("identifier")
            if rstr and rng is None:
                notes.append("unparsed range for %s: %s" % (pkg, rstr))
            if not rstr:
                notes.append("no vulnerable range for %s (patched: %s)" % (pkg, patched))
            comp = map_alias(aliases, pkg)
            if comp is None:
                rec["unmapped"].append({"component": None, "package": pkg,
                                        "ranges": [rng] if rng else [], "quote": rstr})
                continue
            e = merged.setdefault(comp, {"component": comp, "ranges": [], "quote": []})
            if rng or rstr:
                e["ranges"].append(rng or rstr)  # an unparsed range stays, so match.py gives bad_range
            if rstr:
                e["quote"].append(rstr)
        for e in merged.values():
            e["quote"] = "; ".join(e["quote"])
            rec["affected"].append(e)
        if adv.get("withdrawn_at"):
            rec["unmapped"].extend(dict(e, component=None) for e in rec["affected"])
            rec["affected"] = []
        rec["notes"] = "; ".join(notes)
        out.append(rec)
    return out

# ---------------------------------------------------------------- Kubernetes CVE feed

_CVSS_LINE = re.compile(r"CVSS Rating[:*\s]*(\S.{0,400}?)(?:\n\s*\n|\Z)", re.I | re.S)
_CVSS_LABEL = re.compile(r"\b(Critical|High|Medium|Low)\b", re.I)
_MD_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")
_CVSS_VEC = re.compile(r"CVSS:3\.[01]/((?:[A-Z]{1,2}:[A-Z]/?){8})")
_AFFECTED = re.compile(r"#+\s*Affected Versions\s*(.+?)(?:\n#+\s|\Z)", re.I | re.S)
_W = {"AV": {"N": .85, "A": .62, "L": .55, "P": .2}, "AC": {"L": .77, "H": .44},
      "UI": {"N": .85, "R": .62}, "CIA": {"H": .56, "L": .22, "N": 0.0}}


def _roundup(x):
    i = int(round(x * 100000))
    return i / 100000.0 if i % 10000 == 0 else (i // 10000 + 1) / 10.0


def cvss3_severity(vector):
    """CVSS v3.x base severity from a vector string (FIRST CVSS 3.1 spec), or None."""
    try:
        m = dict(p.split(":") for p in vector.strip("/").split("/"))
        scope_changed = m["S"] == "C"
        pr = {"N": .85, "L": .68 if scope_changed else .62, "H": .5 if scope_changed else .27}[m["PR"]]
        iss = 1 - (1 - _W["CIA"][m["C"]]) * (1 - _W["CIA"][m["I"]]) * (1 - _W["CIA"][m["A"]])
        impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if scope_changed else 6.42 * iss
        expl = 8.22 * _W["AV"][m["AV"]] * _W["AC"][m["AC"]] * pr * _W["UI"][m["UI"]]
        if impact <= 0:
            return None
        score = _roundup(min((1.08 if scope_changed else 1.0) * (impact + expl), 10))
    except (KeyError, ValueError):
        return None
    return "critical" if score >= 9 else "high" if score >= 7 else "medium" if score >= 4 else "low"


def k8s_severity(text):
    """Published label on the CVSS Rating line first, else the score of its CVSS 3.x vector."""
    head = text.replace("\r\n", "\n")[:2000]
    m = _CVSS_LINE.search(head)
    block = m.group(1) if m else head[:400]
    lab = _CVSS_LABEL.search(_MD_LINK.sub(" ", block)) if m else None
    if lab:
        return lab.group(1).lower(), "cvss"
    vec = _CVSS_VEC.search(block)
    sev = cvss3_severity(vec.group(1)) if vec else None
    return (sev, "cvss") if sev else ("unknown", "none")


def k8s_records(data, read_at, origin, since):
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise FetchError("parse_error", "not the Kubernetes official CVE JSON feed")
    out = []
    for it in data["items"]:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        pub = parse_iso(it.get("date_published"))
        if pub is not None and pub < since:
            continue
        text = it.get("content_text") or ""
        sev, src = k8s_severity(text)
        url = it.get("url") or it.get("external_url") or ""
        rec = base_record(it["id"], it.get("summary") or "", sev, src, url, read_at, origin)
        rec["published_at"] = iso(pub) if pub else None
        av = _AFFECTED.search(text)
        published = re.sub(r"\s+", " ", av.group(1)).strip()[:600] if av else ""
        rec["notes"] = ("Kubernetes CVE feed carries no structured ranges: review the advisory"
                        + (". Affected versions as published: %s" % published if published else "."))
        out.append(rec)
    return out

# ---------------------------------------------------------------- ALAS RSS


def alas_records(root, flavor, read_at, origin, since):
    comp = "node-os:%s" % flavor
    out, skipped = [], 0
    for item in root.iter("item"):
        title = _text(item, "title")
        m = _ALAS_TITLE.match(title)
        if not m:
            skipped += 1
            continue
        rid, sev_raw, pkg = m.group(1), m.group(2), m.group(3).strip()
        # AL2023 ids: ALAS2023-, ALAS2023LIVEPATCH-, ALAS2023NVIDIA-; AL2 ids: ALAS2-, ALAS2KERNEL-...
        is_2023 = rid.upper().startswith("ALAS2023")
        if (flavor == "al2023") != is_2023 or (flavor == "al2" and not rid.upper().startswith("ALAS2")):
            skipped += 1
            continue
        pub = None
        try:
            pd = _text(item, "pubDate")
            pub = email.utils.parsedate_to_datetime(pd) if pd else None
        except (TypeError, ValueError):
            pub = None
        if pub is not None and pub < since:
            continue
        sev, src = severity(sev_raw, "bulletin")
        link = _text(item, "link")
        rec = base_record(rid, title, sev, src, link, read_at, origin)
        rec["aliases"] = re.findall(r"CVE-\d{4}-\d+", _text(item, "description"))
        rec["published_at"] = iso(pub) if pub else None
        rec["packages"] = [{"name": pkg}]
        rec["affected"] = [{"component": comp, "ranges": [], "quote": title}]
        rec["notes"] = "package-level: check node AMI release"
        out.append(rec)
    if skipped:
        sys.stderr.write("advisory_fetch: skipped %d ALAS items not matching %s\n" % (skipped, flavor))
    return out

# ---------------------------------------------------------------- Bottlerocket updateinfo


def bottlerocket_records(root, read_at, origin, since, feed_url):
    out = []
    for u in root.iter("update"):
        uid = _text(u, "id")
        if not uid:
            continue
        issued = u.find("issued")
        pub = parse_iso(issued.get("date")) if issued is not None else None
        if pub is not None and pub < since:
            continue
        title = _text(u, "title")
        sev, src = severity(_text(u, "severity"), "bulletin")
        refs = [r for r in u.iter("reference")]
        url = feed_url
        for r in refs:
            href = r.get("href") or ""
            if r.get("type") in ("ghsa", "brsa") and href.startswith("https://"):
                url = href
                break
        rec = base_record(uid, title, sev, src, url, read_at, origin)
        rec["aliases"] = sorted({r.get("id") for r in refs if r.get("type") == "cve" and r.get("id")})
        rec["published_at"] = iso(pub) if pub else None
        pkgs, seen = [], set()
        for p in u.iter("package"):
            key = (p.get("name"), p.get("version"), p.get("release"))
            if key in seen or not key[0]:
                continue
            seen.add(key)
            fixed = p.get("version") or ""
            if p.get("release"):
                fixed += "-" + p.get("release")
            pkgs.append({"name": key[0], "fixed": fixed})
        rec["packages"] = pkgs
        rec["affected"] = [{"component": "node-os:bottlerocket", "ranges": [], "quote": title}]
        rec["notes"] = ("package-level: fixed package versions are listed in packages; "
                        "check the node's Bottlerocket release")
        out.append(rec)
    return out

# ---------------------------------------------------------------- save page


def save_page(args, hosts):
    _check_url(args.url, hosts)
    body, final, read_at, origin = get(args, args.url, hosts, "text/html,application/xhtml+xml,*/*")
    text = body.decode("utf-8", errors="replace")
    if not text.lstrip().startswith(("{", "[")):
        text = html_to_text(text)
    header = {"url": args.url, "final_url": final, "read_at": read_at, "origin": origin,
              "sha256": hashlib.sha256(body).hexdigest()}
    write_private(args.save, "# eks-security-source " + json.dumps(header) + "\n" + text)
    sys.stdout.write(json.dumps(dict(header, ok=True, saved=args.save, chars=len(text))) + "\n")
    return 0


def write_private(path, text):
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as e:
        raise FetchError("usage", "cannot write %s: %s" % (path, e.strerror))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(text)

# ---------------------------------------------------------------- main


def refuse(code, error):
    sys.stderr.write("advisory_fetch: %s: %s\n" % (code, error))
    sys.stdout.write(json.dumps({"ok": False, "code": code, "error": error}) + "\n")
    return 2


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        sys.exit(refuse("usage", message))


def main(argv=None):
    ap = _Parser(description="Read EKS advisory feeds into eks-security/advisory@1 records.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--ghsa", metavar="OWNER/REPO/GHSA-ID")
    src.add_argument("--k8s", action="store_true")
    src.add_argument("--alas", choices=("al2", "al2023"))
    src.add_argument("--bottlerocket", action="store_true")
    src.add_argument("--url")
    ap.add_argument("--save")
    ap.add_argument("--since")
    ap.add_argument("--input")
    ap.add_argument("--out")
    ap.add_argument("--catalog", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "components.json"))
    a = ap.parse_args(argv)
    try:
        aliases, feeds, hosts = load_catalog(a.catalog)
        if a.url:
            if not a.save:
                return refuse("usage", "--url needs --save <file>")
            return save_page(a, hosts)
        if a.save:
            return refuse("usage", "--save is only used with --url")
        since = parse_since(a.since)
        if a.ghsa:
            parts = a.ghsa.split("/")
            if len(parts) != 3 or not all(_REPO_PART.match(p) for p in parts[:2]) or not _GHSA_ID.match(parts[2]):
                return refuse("usage", "--ghsa must be <owner>/<repo>/GHSA-xxxx-xxxx-xxxx")
            url = feeds["github-repo-advisory"].format(owner=parts[0], repo=parts[1], ghsa=parts[2])
            body, final, read_at, origin = get(a, url, hosts, "application/vnd.github+json")
            recs = ghsa_records(parse_json(body), aliases, read_at, origin, url)
        elif a.k8s:
            url = feeds["k8s-cve"]
            body, final, read_at, origin = get(a, url, hosts, "application/json")
            recs = k8s_records(parse_json(body), read_at, origin, since)
        elif a.alas:
            url = feeds["alas-%s" % a.alas]
            body, final, read_at, origin = get(a, url, hosts, "application/rss+xml,application/xml")
            recs = alas_records(parse_xml(body), a.alas, read_at, origin, since)
        else:
            url = feeds["bottlerocket"]
            body, final, read_at, origin = get(a, url, hosts)
            recs = bottlerocket_records(parse_xml(body), read_at, origin, since, url)
        text = json.dumps(recs, indent=2) + "\n"
        if a.out:
            write_private(a.out, text)
            sys.stdout.write(json.dumps({"ok": True, "records": len(recs), "out": a.out}) + "\n")
        else:
            sys.stdout.write(text)
        return 0
    except FetchError as e:
        return refuse(e.code, e.error)
    except KeyError as e:
        return refuse("usage", "catalog has no feed %s" % e)
    except Exception as e:  # never a traceback to the user
        return refuse("internal", "%s: %s" % (type(e).__name__, e))


if __name__ == "__main__":
    sys.exit(main())
