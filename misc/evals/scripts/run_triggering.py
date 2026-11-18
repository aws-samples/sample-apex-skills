#!/usr/bin/env python3
"""Triggering-axis runner for misc/evals/ (PLAN §1.5 re-scope).

Replaces skill-creator/scripts/run_eval.py for this repo's triggering evals.
The upstream detector keyed off an ephemeral command-file with a uuid-suffixed
name, which doesn't match how current Claude Code loads skills — real trigger
events carry the canonical skill name with no uuid, so the substring match
always returns False. See misc/evals/PLAN.md §1.0.5 and §1.5.0 for the full
postmortem of the reverted wrapper attempt.

Design (PLAN §1.5.2):

  stage_skill_sandbox(skill_name, repo_skill_dir) yields a (sandbox, home)
  pair. `sandbox/.claude/skills/<skill_name>/` symlinks at the repo skill
  dir and nothing else. HOME holds no ~/.aws: the subprocess gets AWS
  access only from the eval-role credentials below. No state on disk outside
  these two mktemp dirs; both are removed in the `finally:` block.

  mint_eval_role_credentials() assumes role apex-eval-bedrock-invoke in the
  account named by ~/.apex-eval/expected-account, through profile
  apex-eval-admin of ~/.apex-eval/aws-config, then checks the new session
  with sts get-caller-identity. The runner refuses to start when any step
  fails; there is no fallback credential. Only those role credentials and
  the profile's region reach `claude -p`; every AWS_* variable of the parent
  is dropped.

  run_single_query(...) launches `claude -p` with `cwd=sandbox`, `HOME=home`,
  `CLAUDECODE` stripped, streams stream-json, and watches for a Skill
  tool_use whose input names the canonical skill. Kills the subprocess on
  first match so negatives don't burn the full response-generation budget.

  main() mirrors run_eval.py's CLI and output schema so misc/evals/
  run_all_evals.py keeps parsing the stdout JSON blob without changes.

Both helpers are importable — Phase 2's task-axis runner reuses
`stage_skill_sandbox` (+ a no-skill variant for the `without_skill` config)
so there's one sandbox primitive across both axes.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime
import json
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

try:  # PyYAML is present in this eval env (siblings import it unconditionally),
    import yaml  # but keep the stdlib-only regex fallback below so this runner
except ImportError:  # still works in a bare interpreter.
    yaml = None


# Claude Code ships these skills in v2.1.121; system/init.skills lists them
# before any project-level or plugin skills. Update if a CLI bump changes
# the built-in set. An unexpected entry in the subject subprocess's init
# event means a plugin-registered skill leaked past the HOME isolation;
# we mark the run invalid rather than silently pass.
BUILTIN_SKILLS = frozenset({
    "update-config",
    "debug",
    "simplify",
    "batch",
    "fewer-permission-prompts",
    "loop",
    "claude-api",
})


# ---------- sandbox primitive -------------------------------------------------


@contextlib.contextmanager
def stage_skill_sandbox(skill_name: str, repo_skill_dir: Path):
    """Yield (sandbox, home) with exactly one skill staged and a clean HOME.

    sandbox/.claude/skills/<skill_name>/   symlink -> repo_skill_dir

    HOME is empty: no link to the host's ~/.aws.

    Both dirs are mktemp'd; both are removed when the block exits, including
    on exception. Safe against Ctrl-C during the run. Callers may also use
    this from Phase 2's task runner — `with_skill` config points here;
    `without_skill` config should use stage_empty_sandbox() below.
    """
    sandbox = Path(tempfile.mkdtemp(prefix="evals-sandbox-"))
    clean_home = Path(tempfile.mkdtemp(prefix="evals-home-"))
    try:
        skills_dir = sandbox / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / skill_name).symlink_to(repo_skill_dir.resolve())
        yield sandbox, clean_home
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
        shutil.rmtree(clean_home, ignore_errors=True)


@contextlib.contextmanager
def stage_empty_sandbox():
    """Yield (sandbox, home) with no skills staged — the `without_skill`
    config for Phase 2's task-axis runner. Same HOME isolation as
    stage_skill_sandbox (an empty clean HOME, no ~/.aws), but no
    `.claude/` dir at all so the subject subprocess sees zero skills.
    """
    sandbox = Path(tempfile.mkdtemp(prefix="evals-sandbox-"))
    clean_home = Path(tempfile.mkdtemp(prefix="evals-home-"))
    try:
        yield sandbox, clean_home
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
        shutil.rmtree(clean_home, ignore_errors=True)


def build_subprocess_env(
    home: Path,
    extra: dict[str, str] | None = None,
    *,
    aws_env: dict[str, str],
) -> dict[str, str]:
    """Build the env dict for a `claude -p` subprocess. Strips CLAUDECODE so
    a session-local parent doesn't confuse the child, drops every AWS_*
    variable of the parent (keys, AWS_PROFILE, config paths, Bedrock API
    keys), sets HOME to the clean temp dir, merges caller-supplied overrides
    (KUBECONFIG, etc.) and then `aws_env`, the eval-role credentials from
    EvalCredentials.env. `extra` may not carry AWS_* names."""
    bad = sorted(k for k in (extra or {}) if k.startswith("AWS_"))
    if bad:
        raise ValueError(f"AWS variables reach the subject only as eval-role credentials: {bad}")
    env = {
        k: v for k, v in os.environ.items()
        if k != "CLAUDECODE" and not k.startswith("AWS_")
    }
    env["HOME"] = str(home)
    if extra:
        env.update(extra)
    env.update(aws_env)
    return env


# ---------- eval-role credentials ---------------------------------------------


EVAL_ROLE_NAME = "apex-eval-bedrock-invoke"
EVAL_ADMIN_PROFILE = "apex-eval-admin"
# The admin profile is itself an assumed role, so this assume-role is role
# chaining, which AWS caps at one hour (a longer DurationSeconds fails).
EVAL_SESSION_SECONDS = 3600
# Spare seconds a session must have left past a subprocess's timeout.
EVAL_SESSION_MARGIN = 120


class EvalCredentialError(RuntimeError):
    """The eval-role credentials could not be obtained or did not check out."""


def eval_config_dir() -> Path:
    """~/.apex-eval: aws-config (profile apex-eval-admin) and expected-account."""
    return Path.home() / ".apex-eval"


def _read_expected_account(cfg: Path) -> str:
    path = cfg / "expected-account"
    try:
        account = path.read_text().strip()
    except OSError as e:
        raise EvalCredentialError(
            f"cannot read {path} ({e.strerror}); it must hold the eval account id"
        ) from e
    if not re.fullmatch(r"\d{12}", account):
        raise EvalCredentialError(f"{path} must hold one 12-digit account id")
    return account


def _read_profile_region(cfg: Path) -> str:
    import configparser

    path = cfg / "aws-config"
    parser = configparser.ConfigParser(interpolation=None)
    try:
        read = parser.read(path)
    except configparser.Error as e:
        raise EvalCredentialError(f"cannot parse {path}: {e}") from e
    section = f"profile {EVAL_ADMIN_PROFILE}"
    if not read or not parser.has_section(section):
        raise EvalCredentialError(f"{path} has no [{section}] section")
    region = parser.get(section, "region", fallback="").strip()
    if not region:
        raise EvalCredentialError(f"[{section}] in {path} sets no region")
    return region


def _aws_call_env(**overrides: str) -> dict[str, str]:
    """Env for the runner's own `aws` calls: the parent's env minus every
    AWS_* variable, with no shared credentials file and no instance-metadata
    lookup, so only the credentials named in `overrides` can be used."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("AWS_")}
    env["AWS_SHARED_CREDENTIALS_FILE"] = os.devnull
    env["AWS_EC2_METADATA_DISABLED"] = "true"
    env.update(overrides)
    return env


def _last_line(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "no error text"


@dataclasses.dataclass(frozen=True)
class EvalCredentials:
    """One eval-role session: `env` is what the subject gets, `expires_at`
    the session's end as epoch seconds. Held in memory only."""

    env: dict[str, str]
    expires_at: float

    def __repr__(self) -> str:  # keep keys out of tracebacks and logs
        return f"EvalCredentials(expires_at={self.expires_at:.0f})"

    def fresh(self, min_seconds: int) -> "EvalCredentials":
        """Self when at least `min_seconds` remain, else a new session."""
        if time.time() + min_seconds < self.expires_at:
            return self
        return mint_eval_role_credentials(min_seconds=min_seconds)


def mint_eval_role_credentials(min_seconds: int = 0) -> EvalCredentials:
    """Assume the eval role and prove the session's account before use.

    Raises EvalCredentialError, with what to fix, when the config files are
    missing or wrong, the admin profile's sign-in fails, the
    assume-role fails, or get-caller-identity names another account or role.
    """
    if min_seconds + EVAL_SESSION_MARGIN > EVAL_SESSION_SECONDS:
        raise EvalCredentialError(
            f"a {min_seconds}s subprocess does not fit in a {EVAL_SESSION_SECONDS}s "
            "eval-role session; lower the timeout"
        )
    cfg = eval_config_dir()
    account = _read_expected_account(cfg)
    region = _read_profile_region(cfg)
    role_arn = f"arn:aws:iam::{account}:role/{EVAL_ROLE_NAME}"

    r = subprocess.run(
        [
            "aws", "sts", "assume-role",
            "--profile", EVAL_ADMIN_PROFILE,
            "--role-arn", role_arn,
            "--role-session-name", f"apex-eval-{os.getpid()}",
            "--duration-seconds", str(EVAL_SESSION_SECONDS),
            "--region", region,
            "--output", "json",
        ],
        capture_output=True, text=True, timeout=180,
        env=_aws_call_env(AWS_CONFIG_FILE=str(cfg / "aws-config")),
    )
    if r.returncode != 0:
        raise EvalCredentialError(
            f"could not assume {EVAL_ROLE_NAME} through profile {EVAL_ADMIN_PROFILE} "
            f"of {cfg / 'aws-config'}. If this is a sign-in error, sign in again "
            f"for that profile and retry. aws said: {_last_line(r.stderr)}"
        )
    try:
        creds = json.loads(r.stdout)["Credentials"]
        role_env = {
            "AWS_ACCESS_KEY_ID": creds["AccessKeyId"],
            "AWS_SECRET_ACCESS_KEY": creds["SecretAccessKey"],
            "AWS_SESSION_TOKEN": creds["SessionToken"],
        }
        expires_at = datetime.datetime.fromisoformat(
            creds["Expiration"].replace("Z", "+00:00")
        ).timestamp()
    except (ValueError, KeyError, TypeError) as e:
        raise EvalCredentialError(f"assume-role returned no usable credentials ({e!r})") from e
    region_env = {"AWS_REGION": region, "AWS_DEFAULT_REGION": region}

    r = subprocess.run(
        ["aws", "sts", "get-caller-identity", "--output", "json"],
        capture_output=True, text=True, timeout=60,
        env=_aws_call_env(AWS_CONFIG_FILE=os.devnull, **role_env, **region_env),
    )
    if r.returncode != 0:
        raise EvalCredentialError(
            f"get-caller-identity failed with the eval-role session: {_last_line(r.stderr)}"
        )
    try:
        ident = json.loads(r.stdout)
    except ValueError as e:
        raise EvalCredentialError("get-caller-identity returned no JSON") from e
    arn = str(ident.get("Arn", ""))
    if ident.get("Account") != account or f":assumed-role/{EVAL_ROLE_NAME}/" not in arn:
        raise EvalCredentialError(
            f"the eval-role session is {arn or 'unknown'}, not role {EVAL_ROLE_NAME} "
            f"in the account in {cfg / 'expected-account'}; refusing to run"
        )
    if time.time() + min_seconds >= expires_at:
        raise EvalCredentialError("the new eval-role session expires too soon")
    return EvalCredentials(
        env={**role_env, **region_env, "AWS_EC2_METADATA_DISABLED": "true"},
        expires_at=expires_at,
    )


_eval_credentials: EvalCredentials | None = None


def set_eval_credentials(creds: EvalCredentials) -> None:
    """Hold `creds` for this process unless a later session is already held."""
    global _eval_credentials
    if _eval_credentials is None or creds.expires_at > _eval_credentials.expires_at:
        _eval_credentials = creds


def eval_aws_env(timeout: int) -> dict[str, str]:
    """The subject's AWS env for a subprocess that may run `timeout` seconds,
    refreshing the held session when it would expire first."""
    global _eval_credentials
    if _eval_credentials is None:
        raise EvalCredentialError("no eval-role session; the runner mints one before any run")
    _eval_credentials = _eval_credentials.fresh(timeout + EVAL_SESSION_MARGIN)
    return dict(_eval_credentials.env)


# ---------- stream parser -----------------------------------------------------


def _match_skill_in_input(raw_json: str, skill_name: str) -> bool:
    """True when accumulated input JSON names the canonical skill.

    Stream events deliver the tool_use input as `input_json_delta` chunks;
    we can't parse until the block is complete, so we substring-match on the
    canonical name. That's tight enough because the skill name is kebab-case
    and unique across the staged sandbox (only one skill is visible to the
    subprocess at all).
    """
    compact = raw_json.replace(" ", "")
    return (
        f'"skill":"{skill_name}"' in compact
        or f'"name":"{skill_name}"' in compact
    )


def parse_stream_for_trigger(
    process: subprocess.Popen,
    skill_name: str,
    timeout: float,
) -> dict:
    """Consume the subprocess's stream-json stdout and return a result dict:

        {
          "triggered": bool,
          "invalid": bool,
          "invalid_reason": str | None,
          "init_skills": list[str] | None,
        }

    Returns as soon as the Skill tool_use is observed (kills the process),
    or when the subprocess exits / timeout is hit.
    """
    out = {
        "triggered": False,
        "invalid": False,
        "invalid_reason": None,
        "init_skills": None,
    }
    buffer = ""
    pending_block: dict | None = None  # {"type": "tool_use", "name": "...", "input_json": "..."}
    start = time.time()

    def _emit_invalid(reason: str) -> None:
        out["invalid"] = True
        out["invalid_reason"] = reason

    def _check_init(init_skills: list[str]) -> None:
        out["init_skills"] = init_skills
        unexpected = [s for s in init_skills if s not in BUILTIN_SKILLS and s != skill_name]
        if unexpected:
            _emit_invalid(f"unexpected skills in system/init: {unexpected}")

    try:
        while True:
            if time.time() - start > timeout:
                break
            if process.poll() is not None:
                # Drain remaining output.
                rest = process.stdout.read() if process.stdout else b""
                if rest:
                    buffer += rest.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    _handle_line(line, skill_name, out, _check_init, _emit_invalid, pending_block)
                    if out["triggered"]:
                        return out
                break

            ready, _, _ = select.select([process.stdout], [], [], 1.0)
            if not ready:
                continue
            chunk = os.read(process.stdout.fileno(), 8192)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="replace")

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                pending_block = _handle_line(
                    line, skill_name, out, _check_init, _emit_invalid, pending_block
                )
                if out["triggered"]:
                    return out
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    return out


def _handle_line(
    raw_line: str,
    skill_name: str,
    out: dict,
    check_init,
    emit_invalid,
    pending_block: dict | None,
) -> dict | None:
    """Process one stream-json line; updates `out` in place. Returns the
    current pending_block so the caller can thread state across lines.

    Two detection paths, matching what the live stream actually emits:

      (a) stream_event / content_block_start + content_block_delta (input
          JSON deltas) + content_block_stop — the partial-messages view.
      (b) assistant message whose content includes a Skill tool_use with
          input.skill set — the fallback view if deltas are missed.
    """
    line = raw_line.strip()
    if not line:
        return pending_block
    try:
        evt = json.loads(line)
    except json.JSONDecodeError:
        return pending_block
    if not isinstance(evt, dict):
        return pending_block

    etype = evt.get("type")

    if etype == "system" and evt.get("subtype") == "init":
        skills = evt.get("skills") or []
        check_init(list(skills))
        return pending_block

    if etype == "stream_event":
        se = evt.get("event") or {}
        se_type = se.get("type", "")

        if se_type == "content_block_start":
            cb = se.get("content_block") or {}
            if cb.get("type") == "tool_use":
                name = cb.get("name", "")
                # input may already be populated; check immediately.
                initial = json.dumps(cb.get("input") or {}, separators=(",", ":"))
                if name == "Skill" and _match_skill_in_input(initial, skill_name):
                    out["triggered"] = True
                    return None
                return {"name": name, "input_json": initial}
            return None

        if se_type == "content_block_delta" and pending_block:
            delta = se.get("delta") or {}
            if delta.get("type") == "input_json_delta":
                pending_block["input_json"] += delta.get("partial_json", "")
                if pending_block["name"] == "Skill" and _match_skill_in_input(
                    pending_block["input_json"], skill_name
                ):
                    out["triggered"] = True
                    return None
            return pending_block

        if se_type in ("content_block_stop", "message_stop"):
            if pending_block and pending_block["name"] == "Skill":
                if _match_skill_in_input(pending_block["input_json"], skill_name):
                    out["triggered"] = True
                    return None
            return None

        return pending_block

    if etype == "assistant":
        msg = evt.get("message") or {}
        for c in msg.get("content", []) or []:
            if c.get("type") != "tool_use":
                continue
            if c.get("name") != "Skill":
                continue
            # Accept either `input.skill` or `input.name` — current Claude Code
            # emits `skill`, but the field has moved before and a rename would
            # silently zero TPR on this fallback path. The delta path above
            # substring-matches the raw JSON and is unaffected.
            inp = c.get("input") or {}
            if inp.get("skill") == skill_name or inp.get("name") == skill_name:
                out["triggered"] = True
                return None
        return pending_block

    if etype == "result":
        return pending_block

    return pending_block


# ---------- single query ------------------------------------------------------


def run_single_query(
    query: str,
    skill_name: str,
    repo_skill_dir: Path,
    model: str | None,
    timeout: int,
) -> dict:
    """Run one `claude -p` invocation in a fresh sandbox. Returns the result
    dict from parse_stream_for_trigger (triggered / invalid / init_skills).
    Caller maps `triggered` to a pass/fail count.
    """
    with stage_skill_sandbox(skill_name, repo_skill_dir) as (sandbox, home):
        env = build_subprocess_env(home, aws_env=eval_aws_env(timeout))

        cmd = [
            "claude",
            "-p", query,
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--permission-mode", "bypassPermissions",
        ]
        if model:
            cmd.extend(["--model", model])

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=str(sandbox),
            env=env,
        )
        return parse_stream_for_trigger(process, skill_name, timeout=timeout)


# ---------- top-level aggregation ---------------------------------------------


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def read_skill_meta(skill_dir: Path) -> tuple[str, str]:
    """Parse SKILL.md frontmatter for (name, description).

    Uses yaml.safe_load when PyYAML is importable (matching the docs
    pipeline's parsing contract); falls back to the original stdlib-only
    regex scraper otherwise. Raises RuntimeError on missing frontmatter,
    missing `name`, or (yaml path only) invalid YAML.
    """
    text = (skill_dir / "SKILL.md").read_text()
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise RuntimeError(f"SKILL.md has no YAML frontmatter: {skill_dir}")
    fm = m.group(1)
    if len(fm.encode("utf-8")) > 256 * 1024:
        raise RuntimeError(f"SKILL.md frontmatter exceeds maximum allowed size: {skill_dir}")

    if yaml is not None:
        try:
            data = yaml.safe_load(fm)
        except yaml.YAMLError as e:
            raise RuntimeError(
                f"SKILL.md frontmatter is not valid YAML: {skill_dir}: {e}"
            ) from e
        if not isinstance(data, dict) or not data.get("name"):
            raise RuntimeError(f"SKILL.md frontmatter missing `name`: {skill_dir}")
        name = str(data["name"]).strip()
        description = str(data.get("description") or "").strip()
        return name, description

    return _read_skill_meta_regex(fm, skill_dir)


def _read_skill_meta_regex(fm: str, skill_dir: Path) -> tuple[str, str]:
    """Stdlib-only fallback frontmatter scraper (pre-PyYAML behavior).
    Only understands top-level `name:` and `description:` (plain or block
    scalar) — kept for environments without PyYAML installed.
    Known divergence from the YAML path: quoted values keep their
    surrounding quotes (cosmetic; description is output-metadata only).
    """
    name = None
    description_lines: list[str] = []
    in_description = False
    description_indent: int | None = None

    for line in fm.splitlines():
        if in_description:
            if line.startswith(" " * (description_indent or 1)) or not line.strip():
                description_lines.append(line)
                continue
            in_description = False

        key_match = re.match(r"^(\w+):\s*(.*)$", line)
        if not key_match:
            continue
        key, value = key_match.group(1), key_match.group(2)
        if key == "name":
            name = value.strip().strip("'\"")
        elif key == "description":
            if value.strip() in ("|", ">", "|-", ">-"):
                in_description = True
                description_indent = 2
                description_lines = []
            else:
                description_lines = [value]

    if not name:
        raise RuntimeError(f"SKILL.md frontmatter missing `name`: {skill_dir}")
    description = "\n".join(description_lines).strip()
    return name, description


def _worker(args: tuple) -> tuple[str, dict]:
    query, skill_name, repo_skill_dir, model, timeout, creds = args
    set_eval_credentials(creds)
    try:
        result = run_single_query(query, skill_name, Path(repo_skill_dir), model, timeout)
    except Exception as e:  # noqa: BLE001
        result = {
            "triggered": False,
            "invalid": True,
            "invalid_reason": f"worker exception: {e!r}",
            "init_skills": None,
        }
    return query, result


def run_eval(
    eval_set: list[dict],
    skill_name: str,
    description: str,
    repo_skill_dir: Path,
    num_workers: int,
    timeout: int,
    runs_per_query: int,
    trigger_threshold: float,
    model: str | None,
    creds: EvalCredentials,
) -> dict:
    """Execute every (query × run_idx) pair; aggregate into run_eval.py's
    output schema so downstream parsers don't need to change. Each worker
    starts from `creds` and refreshes it when a query would outlive it.
    """
    jobs = []
    for item in eval_set:
        for _ in range(runs_per_query):
            jobs.append((item["query"], skill_name, str(repo_skill_dir), model, timeout, creds))

    triggers_by_query: dict[str, list[bool]] = {}
    invalids_by_query: dict[str, list[dict]] = {}

    with ProcessPoolExecutor(max_workers=num_workers) as ex:
        futures = [ex.submit(_worker, j) for j in jobs]
        for fut in as_completed(futures):
            query, result = fut.result()
            triggers_by_query.setdefault(query, []).append(bool(result["triggered"]))
            if result.get("invalid"):
                invalids_by_query.setdefault(query, []).append(
                    {
                        "reason": result.get("invalid_reason"),
                        "init_skills": result.get("init_skills"),
                    }
                )

    results: list[dict] = []
    item_by_query = {item["query"]: item for item in eval_set}
    for query in (item["query"] for item in eval_set):
        triggers = triggers_by_query.get(query, [])
        item = item_by_query[query]
        runs = len(triggers)
        trigger_count = sum(triggers)
        rate = (trigger_count / runs) if runs else 0.0
        should = bool(item["should_trigger"])
        if should:
            did_pass = rate >= trigger_threshold
        else:
            did_pass = rate < trigger_threshold
        row = {
            "query": query,
            "should_trigger": should,
            "trigger_rate": rate,
            "triggers": trigger_count,
            "runs": runs,
            "pass": did_pass,
        }
        if query in invalids_by_query:
            row["invalid_runs"] = invalids_by_query[query]
        results.append(row)

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    return {
        "skill_name": skill_name,
        "description": description,
        "results": results,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
        },
    }


# ---------- CLI ---------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--eval-set", required=True, help="Path to triggering.json")
    parser.add_argument("--skill-path", required=True, help="Path to skills/<name>/")
    parser.add_argument("--num-workers", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=90, help="Per-query wallclock seconds")
    parser.add_argument("--runs-per-query", type=int, default=3)
    parser.add_argument("--trigger-threshold", type=float, default=0.5)
    parser.add_argument("--model", default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    eval_set = json.loads(Path(args.eval_set).read_text())
    skill_dir = Path(args.skill_path).resolve()
    if not (skill_dir / "SKILL.md").exists():
        print(f"error: no SKILL.md at {skill_dir}", file=sys.stderr)
        return 1

    name, description = read_skill_meta(skill_dir)

    try:
        creds = mint_eval_role_credentials(min_seconds=args.timeout + EVAL_SESSION_MARGIN)
    except EvalCredentialError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"[run_triggering] skill={name} prompts={len(eval_set)} "
              f"runs={args.runs_per_query} workers={args.num_workers} model={args.model}",
              file=sys.stderr)

    output = run_eval(
        eval_set=eval_set,
        skill_name=name,
        description=description,
        repo_skill_dir=skill_dir,
        num_workers=args.num_workers,
        timeout=args.timeout,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        model=args.model,
        creds=creds,
    )

    if args.verbose:
        s = output["summary"]
        print(f"[run_triggering] {s['passed']}/{s['total']} passed", file=sys.stderr)
        for r in output["results"]:
            tag = "PASS" if r["pass"] else "FAIL"
            rate = f"{r['triggers']}/{r['runs']}"
            print(f"  [{tag}] rate={rate} expected={r['should_trigger']}: {r['query'][:70]}",
                  file=sys.stderr)

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
