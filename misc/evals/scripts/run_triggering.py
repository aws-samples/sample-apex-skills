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
  dir and nothing else. HOME holds no ~/.aws: the host's AWS keys are no
  longer handed to the subprocess in its environment or HOME; it gets the
  eval-role credentials below. The subprocess runs inside wall_off_host;
  what the wall hides and what stays open is in misc/evals/README.md,
  "Eval-role setup (`~/.apex-eval`)". No state on disk outside
  these two mktemp dirs; both are removed in the `finally:` block.

  mint_eval_role_credentials() assumes role apex-eval-bedrock-invoke in the
  account named by ~/.apex-eval/expected-account, through profile
  apex-eval-admin of ~/.apex-eval/aws-config, then checks the new session
  with sts get-caller-identity. The runner refuses to start when any step
  fails; there is no fallback credential. Only those role credentials and
  the profile's region reach `claude -p`; every AWS_* variable of the parent
  is dropped. The runner also refuses to start unless
  CLAUDE_CODE_USE_BEDROCK=1, and drops SUBJECT_DROPPED_VARS from the subject's
  env, so the model call goes through Bedrock on that session.

  run_single_query(...) runs one query on the `--harness` adapter (claude,
  kiro or codex; one function each: run_claude, run_kiro, run_codex) with
  `cwd=sandbox`, `HOME=home` and the eval-role env (harness_env), and
  watches its JSON Lines output for the skill load: for claude a
  Skill tool_use naming the canonical skill, for kiro and codex a tool call
  that reads the staged SKILL.md. Kills the subprocess on first match so
  negatives don't burn the full response-generation budget. A run is
  invalid when it shows no start event, or, without a seen trigger, times
  out, closes stdout without exiting, exits non-zero or shows no end event;
  also when the harness reports an error (claude result is_error, kiro
  runError, codex turn.failed or error), claude's system/init lists an
  unexpected skill, a kiro or codex run shows no tool view (no ACP update,
  no item event), or the worker raised. Invalid runs count in neither the
  trigger count nor the run count; a case with no valid run fails, and so
  does a class's shared should-not case with any invalid run.

  main() mirrors run_eval.py's CLI and output schema so misc/evals/
  run_all_evals.py keeps parsing the stdout JSON blob; the fields it adds
  are listed at score_case and run_eval. `--class` merges a class's shared
  trigger cases with the skill's own (targets: CLASS_TARGETS).
  It exits 2 when the eval-role session is refused at start or a refresh
  fails mid-run.

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

from parse_trajectory import (
    END_EVENTS,
    HARNESSES,
    START_EVENTS,
    acp_update,
    codex_usage,
    kiro_usage,
)

import yaml  # also needed by the class-membership read (run_checks, below)


# Claude Code ships these skills (the v2.1.121 set plus those 2.1.328 lists,
# below); system/init.skills lists them
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
    # listed in system/init by Claude Code 2.1.328
    "deep-research",
    "dataviz",
    "verify",
    "code-review",
    "doctor",
    "workflow-authoring",
    "run",
    "run-skill-generator",
    "plugin-authoring",
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


# Container engine sockets: a subject in the docker group could start a
# container that mounts any host path (~/.aws included), so each one that
# exists reads as /dev/null inside the wall: default docker, containerd and
# rootless-docker sockets only.
ENGINE_SOCKETS = ("/run/docker.sock", "/run/containerd/containerd.sock",
                  "/run/user/{uid}/docker.sock")


def _home_or_above(d: Path) -> bool:
    """True for HOME, ~/.local and every folder above either: the wall never
    binds one of these back, since each holds other tools' sign-in files."""
    home = Path.home().resolve()
    return any(d == x or d in x.parents for x in (home, home / ".local"))


def _package_root(exe: Path) -> Path | None:
    """The npm package folder `exe` sits in: the folder after its first
    node_modules (two for an @scope; the exe itself when it sits directly
    there), or None outside node_modules."""
    parts = exe.parts
    if "node_modules" not in parts:
        return None
    i = parts.index("node_modules")
    n = i + 3 if i + 1 < len(parts) and parts[i + 1].startswith("@") else i + 2
    return Path(*parts[:n])


def _cli_binds(prog: str) -> list[tuple[Path, Path]]:
    """(source, mount point) pairs that keep the harness CLI `prog` runnable
    inside the wall: the file PATH finds and the file it links to, and for a
    script (a `#!` line) its interpreter file and the file that links to.
    An npm script also gets its package folder (_package_root; an npm
    package carries its own dependencies), never the npm prefix it shares
    with node. Any other script gets the folder it shares with its
    interpreter, unless that folder is HOME, ~/.local or
    above (_home_or_above): then only the two files are bound."""
    found = shutil.which(prog)
    if found is None:
        return []  # the subject fails to start: an invalid run
    exe = Path(found).resolve()
    binds = [(exe, exe), (exe, Path(found).absolute())]
    try:
        with open(exe, "rb") as fh:
            first = fh.readline(512).decode("utf-8", "replace")
    except OSError:
        first = ""
    if first.startswith("#!"):
        words = [w for w in first[2:].split() if not w.startswith("-")]
        name = words[1] if len(words) > 1 and Path(words[0]).name == "env" else (words or [""])[0]
        interp = shutil.which(name) if name else None
        if interp:
            real = Path(interp).resolve()
            binds += [(real, real), (real, Path(interp).absolute())]
            shared = _package_root(exe) or Path(os.path.commonpath([exe, real]))
            if len(shared.parts) > 2 and not _home_or_above(shared):
                binds.append((shared, shared))
    return binds


def kiro_data_dir(env: dict[str, str]) -> Path:
    """The kiro-cli data folder (its sign-in and chat history) a kiro
    subject with `env` uses: $XDG_DATA_HOME/kiro-cli (harness_env sets
    XDG_DATA_HOME), else ~/.local/share/kiro-cli. That kiro-cli keeps its
    sign-in there is assumed; no kiro run has signed in under the wall yet."""
    return Path(env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "kiro-cli"


def wall_off_host(cmd: list[str], sandbox: Path, home: Path,
                  skill_dir: Path | None = None, ro_dirs: tuple[Path, ...] = (),
                  rw_dirs: tuple[Path, ...] = ()) -> list[str]:
    """`cmd` under bubblewrap, so a subject does not read the host's skill
    copies (a C1 run read one from another worktree) or the host's keys by
    path.
    The runner's HOME, the repo, its temp dir (tempfile.gettempdir()), /tmp
    and the user runtime dir (/run/user/<uid> and XDG_RUNTIME_DIR, which
    hold the user session bus, so systemd-run --user cannot reach it) each
    read as an empty tmpfs; the run's sandbox and clean HOME are bound back
    read-write, and the staged skill folder (`skill_dir`, none for
    without_skill), the run's own harness CLI (`cmd[0]`, _cli_binds: its
    files, and its npm package folder, never HOME or ~/.local) and each of
    `ro_dirs` (a caller-added PATH dir, such as the C1 driver's T7 aws shim
    dir) read-only, a link as a link. A dir of `ro_dirs` that is an
    outermost walled folder (HOME, /tmp, the runtime dir; the repo or temp
    dir only when outside those) or a folder above one, or HOME, ~/.local
    or above, is not bound; any other is bound as given, so a caller passes
    only a private dir it created. Each of `rw_dirs` (a kiro subject's
    kiro_data_dir, so it signs in as the operator) that exists is bound back
    read-write, unless it is HOME, ~/.local, ~/.local/share, a walled
    folder or one above it.
    The container engine sockets read as /dev/null, and
    --new-session stops the subject pushing input into the runner's terminal
    itself. The rest of the host filesystem and the network are unchanged
    (a session bus outside the runtime dir, such as an abstract socket,
    stays reachable). --unshare-pid and a fresh /proc give the subject its
    own process table, so it cannot list or signal host processes.
    Raises RuntimeError when bwrap is not installed, before any subject
    starts."""
    if shutil.which("bwrap") is None:
        raise RuntimeError("bwrap is not installed: the subject sandbox needs it to wall off "
                           "the host's skill copies (dnf install bubblewrap)")
    walls: list[Path] = []
    hidden = {Path.home().resolve(), REPO_ROOT.resolve(), Path(tempfile.gettempdir()).resolve(),
              Path("/tmp").resolve(), Path(f"/run/user/{os.getuid()}")}
    if os.path.isabs(os.environ.get("XDG_RUNTIME_DIR", "")):
        hidden.add(Path(os.environ["XDG_RUNTIME_DIR"]).resolve())
    for p in sorted(hidden, key=lambda p: len(p.parts)):
        if len(p.parts) > 1 and p.is_dir() and not any(p == w or w in p.parents for w in walls):
            walls.append(p)
    args = ["bwrap", "--dev-bind", "/", "/", "--unshare-pid", "--proc", "/proc",
            "--die-with-parent", "--new-session"]
    for w in walls:
        args += ["--tmpfs", str(w)]
    for sock in ENGINE_SOCKETS:
        sock_path = Path(sock.format(uid=os.getuid()))
        if os.path.exists(sock_path):  # False when it cannot be read
            args += ["--ro-bind", "/dev/null", str(sock_path.resolve())]
    walled = lambda d: any(d == w or w in d.parents for w in walls)  # noqa: E731
    binds = [b for b in _cli_binds(cmd[0]) if walled(b[1])]
    if skill_dir:
        binds.append((Path(skill_dir).resolve(),) * 2)
    refused = lambda d: _home_or_above(d) or any(d == w or d in w.parents for w in walls)  # noqa: E731
    for d in map(lambda d: Path(d).resolve(), ro_dirs):
        if not refused(d):
            binds.append((d, d))
    share = Path.home().resolve() / ".local" / "share"
    rw = [d for d in map(lambda d: Path(d).resolve(), rw_dirs)
          if d.is_dir() and not refused(d) and d != share]
    seen: set[Path] = set()
    for src, dest in binds:
        if dest not in seen and src.exists():
            seen.add(dest)
            # a link stays a link (an npm bin finds its package by the path it links to)
            args += ["--symlink", str(src), str(dest)] if dest != src and dest.is_symlink() \
                else ["--ro-bind", str(src), str(dest)]
    for p in (*rw, sandbox, home):
        args += ["--bind", str(Path(p).resolve()), str(Path(p).resolve())]
    return args + ["--chdir", str(Path(sandbox).resolve()), "--", *cmd]


def build_subprocess_env(
    home: Path,
    extra: dict[str, str] | None = None,
    *,
    aws_env: dict[str, str],
) -> dict[str, str]:
    """Build the env dict for a `claude -p` subprocess. Strips CLAUDECODE so
    a session-local parent doesn't confuse the child, drops every AWS_*
    variable of the parent (keys, AWS_PROFILE, config paths, Bedrock API
    keys), every APEX_EVAL_* variable (the CI secrets the eval-role config
    is written from) and SUBJECT_DROPPED_VARS, sets HOME to the clean temp
    dir, merges caller-supplied overrides (KUBECONFIG, etc.) and then
    `aws_env`, the eval-role credentials from EvalCredentials.env. `extra`
    may not carry AWS_* names. harness_env adds what a kiro or codex
    subject needs on top."""
    bad = sorted(k for k in (extra or {}) if k.startswith("AWS_"))
    if bad:
        raise ValueError(f"AWS variables reach the subject only as eval-role credentials: {bad}")
    env = {
        k: v for k, v in os.environ.items()
        if k != "CLAUDECODE" and not k.startswith(("AWS_", "APEX_EVAL_"))
        and k not in SUBJECT_DROPPED_VARS
    }
    env["HOME"] = str(home)
    if extra:
        env.update(extra)
    env.update(aws_env)
    return env


# ---------- eval-role credentials ---------------------------------------------


EVAL_ROLE_NAME = "apex-eval-bedrock-invoke"
EVAL_ADMIN_PROFILE = "apex-eval-admin"
SETUP_HINT = 'see "Eval-role setup (`~/.apex-eval`)" in misc/evals/README.md'
# The admin profile is expected to be an assumed role, so this assume-role is
# role chaining, which AWS caps at one hour (a longer DurationSeconds fails).
EVAL_SESSION_SECONDS = 3600
# Spare seconds a session must have left past a subprocess's timeout.
EVAL_SESSION_MARGIN = 120
# Never passed to the subject: each could send its model calls somewhere
# other than Bedrock on the eval-role session. KIRO_API_KEY goes back only
# to a kiro subject (harness_env).
SUBJECT_DROPPED_VARS = frozenset({
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
    "ANTHROPIC_BEDROCK_BASE_URL", "CLAUDE_CODE_SKIP_BEDROCK_AUTH", "CLAUDE_CONFIG_DIR",
    "KIRO_API_KEY",
})


class EvalCredentialError(RuntimeError):
    """The eval-role credentials could not be obtained or did not check out."""


def eval_config_dir() -> Path:
    """~/.apex-eval: aws-config (profile apex-eval-admin) and expected-account."""
    return Path.home() / ".apex-eval"


def _read_expected_account(cfg: Path) -> str:
    path = cfg / "expected-account"
    try:
        account = path.read_text().strip()
    except (OSError, UnicodeDecodeError) as e:
        why = e.strerror if isinstance(e, OSError) else "not UTF-8"
        raise EvalCredentialError(
            f"cannot read {path} ({why}); it must hold the eval account id; {SETUP_HINT}"
        ) from e
    if not re.fullmatch(r"[0-9]{12}", account):
        raise EvalCredentialError(f"{path} must hold one 12-digit account id; {SETUP_HINT}")
    return account


def _read_profile_region(cfg: Path) -> str:
    import configparser

    path = cfg / "aws-config"
    parser = configparser.ConfigParser(interpolation=None)
    try:
        read = parser.read(path)
    except (configparser.Error, UnicodeDecodeError) as e:
        raise EvalCredentialError(f"cannot parse {path}: {e}; {SETUP_HINT}") from e
    if not read:
        raise EvalCredentialError(f"cannot read {path}; {SETUP_HINT}")
    section = f"profile {EVAL_ADMIN_PROFILE}"
    if not parser.has_section(section):
        raise EvalCredentialError(f"{path} has no [{section}] section; {SETUP_HINT}")
    region = parser.get(section, "region", fallback="").strip()
    if not region:
        raise EvalCredentialError(f"[{section}] in {path} sets no region; {SETUP_HINT}")
    return region


def _aws_call_env(**overrides: str) -> dict[str, str]:
    """Env for the runner's own `aws` calls: the parent's env minus every
    AWS_* variable, with no shared credentials file and no instance-metadata
    lookup. The CLI's other credential providers (such as ~/.boto and the
    container provider) stay; the get-caller-identity check bounds them."""
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

    def fresh(self, timeout: int) -> "EvalCredentials":
        """Self when it outlasts a `timeout`-second subprocess by
        EVAL_SESSION_MARGIN, else a new session."""
        if time.time() + timeout + EVAL_SESSION_MARGIN < self.expires_at:
            return self
        return mint_eval_role_credentials(timeout=timeout)


def _run_aws(argv: list[str], timeout: int, env: dict[str, str]) -> subprocess.CompletedProcess:
    """Run one `aws` call; a missing `aws` or a timeout is an
    EvalCredentialError whose text holds no argv (it names the role ARN)."""
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise EvalCredentialError(f"aws {argv[1]} {argv[2]} timed out after {timeout}s") from None
    except OSError as e:
        raise EvalCredentialError(f"cannot run aws ({e.strerror})") from None
    except UnicodeDecodeError:
        raise EvalCredentialError(f"aws {argv[1]} {argv[2]} printed output that is not UTF-8") from None


def mint_eval_role_credentials(
    timeout: int = 0, source: str = "the subprocess timeout"
) -> EvalCredentials:
    """Assume the eval role and prove the session's account before use.
    The session must outlast a `timeout`-second subprocess by
    EVAL_SESSION_MARGIN; `source` names where that timeout was set.

    Raises EvalCredentialError, with what to fix, when the model would not
    go through Bedrock, the config files are missing or wrong, the admin
    profile's sign-in fails, the assume-role fails, or get-caller-identity
    names another account or role.
    """
    if os.environ.get("CLAUDE_CODE_USE_BEDROCK") != "1":
        raise EvalCredentialError(
            "CLAUDE_CODE_USE_BEDROCK=1 is not set, so `claude -p` would not send its "
            "model calls through Bedrock on the eval-role session; refusing to run"
        )
    other = sorted(k for k in os.environ
                   if k.startswith("CLAUDE_CODE_USE_") and k != "CLAUDE_CODE_USE_BEDROCK")
    if other:
        raise EvalCredentialError(
            f"{', '.join(other)} set beside CLAUDE_CODE_USE_BEDROCK, so the model route is "
            "not proven to be Bedrock; unset it and retry"
        )
    # Same `>=` as the check on the new session below, so a timeout that
    # passes here cannot fail there only by the cap.
    if timeout + EVAL_SESSION_MARGIN >= EVAL_SESSION_SECONDS:
        raise EvalCredentialError(
            f"{source} is {timeout}s; with {EVAL_SESSION_MARGIN}s spare it must stay under the "
            f"{EVAL_SESSION_SECONDS}s eval-role session (AWS caps a role-chained session "
            f"at one hour); lower {source}"
        )
    cfg = eval_config_dir()
    account = _read_expected_account(cfg)
    region = _read_profile_region(cfg)
    role_arn = f"arn:aws:iam::{account}:role/{EVAL_ROLE_NAME}"

    r = _run_aws(
        [
            "aws", "sts", "assume-role",
            "--profile", EVAL_ADMIN_PROFILE,
            "--role-arn", role_arn,
            "--role-session-name", f"apex-eval-{os.getpid()}",
            "--duration-seconds", str(EVAL_SESSION_SECONDS),
            "--region", region,
            "--output", "json",
        ],
        180, _aws_call_env(AWS_CONFIG_FILE=str(cfg / "aws-config")),
    )
    if r.returncode != 0:
        raise EvalCredentialError(
            f"could not assume {EVAL_ROLE_NAME} through profile {EVAL_ADMIN_PROFILE} "
            f"of {cfg / 'aws-config'}. If this is a sign-in error, sign in again "
            f"for that profile and retry. aws exited {r.returncode}: {_last_line(r.stderr)}"
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
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise EvalCredentialError(f"assume-role returned no usable credentials ({e!r})") from e
    region_env = {"AWS_REGION": region, "AWS_DEFAULT_REGION": region}

    r = _run_aws(
        ["aws", "sts", "get-caller-identity", "--output", "json"],
        60, _aws_call_env(AWS_CONFIG_FILE=os.devnull, **role_env, **region_env),
    )
    if r.returncode != 0:
        raise EvalCredentialError(
            f"get-caller-identity failed with the eval-role session (aws exited "
            f"{r.returncode}): {_last_line(r.stderr)}"
        )
    try:
        ident = json.loads(r.stdout)
        arn, got_account = str(ident.get("Arn", "")), ident.get("Account")
    except (ValueError, AttributeError) as e:
        raise EvalCredentialError("get-caller-identity returned no JSON object") from e
    if got_account != account or f":assumed-role/{EVAL_ROLE_NAME}/" not in arn:
        raise EvalCredentialError(
            f"the eval-role session is {arn or 'unknown'}, not role {EVAL_ROLE_NAME} "
            f"in the account in {cfg / 'expected-account'}; refusing to run"
        )
    if time.time() + timeout + EVAL_SESSION_MARGIN >= expires_at:
        raise EvalCredentialError(
            f"the new eval-role session expires too soon for {source} ({timeout}s)"
        )
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
    _eval_credentials = _eval_credentials.fresh(timeout)
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


def new_run_record(harness: str) -> dict:
    """The per-run record every harness adapter returns.

    triggered       True only on a valid run whose output showed the skill load
    trigger_seen    the output showed the skill load (kept on an invalid run)
    invalid         the run cannot count: invalid_reason says why
    init_seen       the harness's start event was read (claude system/init,
                    kiro runStarted, codex thread.started)
    end_seen        the harness's end event was read (claude result, kiro
                    runFinished, codex turn.completed)
    returncode      the harness's exit code (negative: killed by a signal,
                    such as the kill on a seen trigger)
    timed_out       the run hit --timeout
    tokens          token counts when the output carries them, else None
                    (claude: the result's usage keys; kiro and codex:
                    parse_trajectory's USAGE_TOKEN_KEYS names)
    """
    return {
        "harness": harness,
        "triggered": False,
        "trigger_seen": False,
        "invalid": False,
        "invalid_reason": None,
        "init_skills": None,
        "init_seen": False,
        "end_seen": False,
        "returncode": None,
        "timed_out": False,
        "tokens": None,
    }


def _mark_invalid(out: dict, reason: str) -> None:
    """First reason wins."""
    if not out["invalid"]:
        out["invalid"] = True
        out["invalid_reason"] = reason


def read_stream_lines(process: subprocess.Popen, timeout: float, on_line) -> str:
    """Feed each stdout line to on_line(line) until on_line returns True or
    the stream ends. Returns "stopped" (on_line asked to stop), "exited" (the
    process exited), "eof" (stdout closed and the process did not exit
    within the time left) or "timeout". Never kills the process."""
    buffer = ""
    start = time.time()

    def feed(text: str) -> bool:
        nonlocal buffer
        buffer += text
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if on_line(line):
                return True
        return False

    while True:
        remaining = timeout - (time.time() - start)
        if remaining <= 0:
            return "timeout"
        if process.poll() is not None:
            rest = process.stdout.read() if process.stdout else b""
            # The trailing "\n" flushes a last line printed with no newline.
            return "stopped" if feed((rest or b"").decode("utf-8", errors="replace") + "\n") else "exited"
        ready, _, _ = select.select([process.stdout], [], [], min(1.0, remaining))
        if not ready:
            continue
        chunk = os.read(process.stdout.fileno(), 8192)
        if not chunk:
            try:
                process.wait(timeout=max(0.1, min(10.0, timeout - (time.time() - start))))
            except subprocess.TimeoutExpired:
                return "eof"
            return "stopped" if feed("\n") else "exited"
        if feed(chunk.decode("utf-8", errors="replace")):
            return "stopped"


def finish_run(out: dict, process: subprocess.Popen, how: str, timeout: float,
               init_name: str, end_name: str) -> dict:
    """Kill the process if it still runs, record its exit code, and mark the
    run invalid when it cannot count: no start event, a timeout, a
    non-zero exit or no end event, unless the skill load was seen after a
    start event (the runner kills the process on a seen trigger, so its exit
    code is then a signal). An invalid run never reads triggered True."""
    if process.poll() is None:
        process.kill()
        process.wait()
    out["returncode"] = process.returncode
    out["timed_out"] = how == "timeout"
    if not out["init_seen"]:
        _mark_invalid(out, f"no {init_name} event")
    elif out["trigger_seen"]:
        pass
    elif how == "timeout":
        _mark_invalid(out, f"timed out after {timeout}s before the run ended")
    elif how == "eof":
        _mark_invalid(out, "stdout closed but the process did not exit")
    elif process.returncode != 0:
        _mark_invalid(out, f"exited {process.returncode}")
    elif not out["end_seen"]:
        _mark_invalid(out, f"no {end_name} event")
    out["triggered"] = bool(out["trigger_seen"]) and not out["invalid"]
    return out


def _json_object(raw_line: str) -> dict | None:
    line = raw_line.strip()
    if not line:
        return None
    try:
        evt = json.loads(line)
    except json.JSONDecodeError:
        return None
    return evt if isinstance(evt, dict) else None


def _int_fields(d: dict, keys) -> dict:
    return {k: d[k] for k in keys if isinstance(d.get(k), int) and not isinstance(d.get(k), bool)}


def _names_skill_file(obj, skill_name: str, skill_dir: Path) -> bool:
    """True when a tool call's input names the staged skill's SKILL.md: by
    the staged path (.../skills/<name>/SKILL.md) or the repo folder the
    staged link resolves to."""
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return (f"skills/{skill_name}/SKILL.md" in text
            or f"{Path(skill_dir).resolve()}/SKILL.md" in text)


# ---------- claude adapter ----------------------------------------------------


CLAUDE_TOKEN_KEYS = ("input_tokens", "output_tokens",
                     "cache_read_input_tokens", "cache_creation_input_tokens")


def parse_stream_for_trigger(
    process: subprocess.Popen,
    skill_name: str,
    timeout: float,
) -> dict:
    """Consume `claude -p` stream-json stdout and return new_run_record's
    dict for harness claude. Stops as soon as the Skill tool_use is seen
    (finish_run kills the process), or when the process exits or the
    timeout is hit."""
    out = new_run_record("claude")
    pending = [None]

    def _check_init(init_skills: list[str]) -> None:
        out["init_seen"] = True
        out["init_skills"] = init_skills
        unexpected = [s for s in init_skills if s not in BUILTIN_SKILLS and s != skill_name]
        if unexpected:
            _mark_invalid(out, f"unexpected skills in system/init: {unexpected}")

    def on_line(line: str) -> bool:
        pending[0] = _handle_line(line, skill_name, out, _check_init,
                                  lambda reason: _mark_invalid(out, reason), pending[0])
        if out["triggered"]:
            out["trigger_seen"] = True
            return True
        return False

    how = read_stream_lines(process, timeout, on_line)
    return finish_run(out, process, how, timeout, "system/init", "result")


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
        out["end_seen"] = True
        usage = evt.get("usage")
        if isinstance(usage, dict):
            tokens = _int_fields(usage, CLAUDE_TOKEN_KEYS)
            if tokens:
                tokens["total_tokens"] = sum(tokens.values())
                out["tokens"] = tokens
        if evt.get("is_error") is True:
            emit_invalid("result event reports is_error")
        return pending_block

    return pending_block


# ---------- single query ------------------------------------------------------


def run_claude(query: str, skill_name: str, skill_dir: Path, model: str | None,
               timeout: int, sandbox: Path, home: Path, env: dict[str, str]) -> dict:
    """Claude Code adapter: `claude -p` stream-json; the skill is staged at
    sandbox/.claude/skills/<name>/ by stage_skill_sandbox, and a trigger is
    a Skill tool_use naming it."""
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
        wall_off_host(cmd, sandbox, home, skill_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=str(sandbox),
        env=env,
    )
    return parse_stream_for_trigger(process, skill_name, timeout=timeout)


# ---------- kiro adapter ------------------------------------------------------
#
# Kiro CLI 3.5.0, `kiro-cli chat --help`: `--output-format stream-json` prints
# "The run's ACP events as JSON Lines on stdout, one self-describing event per
# line" and implies --no-interactive. A headless run signs in with the
# KIRO_API_KEY environment variable when it is set (kiro.dev/docs/cli/headless,
# read 2026-11-19); else the runner relies on the operator's existing kiro-cli
# sign-in, which kiro-cli keeps in its data dir under XDG_DATA_HOME
# (harness_env passes the parent's). `kiro-cli whoami` was checked on that
# sign-in; a `chat` run on it is first seen in the live runs. Either way Kiro's model calls go to Kiro's service, not to
# Bedrock on the eval-role session; the eval-role env still reaches the subprocess for
# its AWS tool calls. Kiro reads global skills from ~/.kiro/skills/
# (kiro.dev/docs/skills). A trigger is read as a file-read tool call on
# .../skills/<name>/SKILL.md: assumed, not seen in a recorded stream (that
# page names no activation mechanism). The record types read here
# (runStarted, sessionUpdate, runFinished) are the names in the 3.4.0
# and 3.5.0 binaries; the runError record is documented for Kiro CLI 3.5.0 or later
# (kiro.dev/docs/cli/headless, read 2026-11-19). Events, tool calls and
# tokens are read with parse_trajectory's helpers, the task runner's rules.


def parse_kiro_stream(process: subprocess.Popen, skill_name: str, skill_dir: Path,
                      timeout: float) -> dict:
    out = new_run_record("kiro")
    updates = [0]

    def on_line(line: str) -> bool:
        evt = _json_object(line)
        if evt is None:
            return False
        etype = evt.get("type")
        if etype == START_EVENTS["kiro"]:
            out["init_seen"] = True
            return False
        if etype == END_EVENTS["kiro"]:
            out["end_seen"] = True
            tokens = kiro_usage(evt)
            if tokens:
                tokens["total_tokens"] = tokens["input_tokens"] + tokens["output_tokens"]
                out["tokens"] = tokens
            return False
        if etype == "runError":
            _mark_invalid(out, "runError record")
            return False
        call = acp_update(evt)
        if call is None:
            return False
        updates[0] += 1
        if call.get("sessionUpdate") in ("tool_call", "tool_call_update"):
            probe = {k: call.get(k) for k in ("rawInput", "locations", "title")}
            if _names_skill_file(probe, skill_name, skill_dir):
                out["trigger_seen"] = True
                return True
        return False

    how = read_stream_lines(process, timeout, on_line)
    finish_run(out, process, how, timeout, START_EVENTS["kiro"], END_EVENTS["kiro"])
    if not out["invalid"] and not out["trigger_seen"] and updates[0] == 0:
        _mark_invalid(out, "no sessionUpdate event, so the output cannot show whether the skill loaded")
    return out


def run_kiro(query: str, skill_name: str, skill_dir: Path, model: str | None,
             timeout: int, sandbox: Path, home: Path, env: dict[str, str]) -> dict:
    """Kiro CLI adapter: the skill is linked at <clean HOME>/.kiro/skills/<name>."""
    skills = home / ".kiro" / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    (skills / skill_name).symlink_to(Path(skill_dir).resolve())
    cmd = [
        "kiro-cli", "chat",
        "--agent-engine", "v3",
        "--no-interactive",
        "--output-format", "stream-json",
        "--trust-all-tools",
        "--trust-workspace",
    ]
    if model:
        cmd.extend(["--model", model])
    cmd.append(query)
    process = subprocess.Popen(wall_off_host(cmd, sandbox, home, skill_dir, rw_dirs=(kiro_data_dir(env),)),
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, cwd=str(sandbox), env=env)
    return parse_kiro_stream(process, skill_name, skill_dir, timeout)


# ---------- codex adapter -----------------------------------------------------
#
# Codex CLI 0.163.0, `codex exec --help`: `--json` "Print events to stdout as
# JSONL". The event and item types are openai/codex
# codex-rs/exec/src/exec_events.rs (read at f8c6026c, 2026-11-19):
# thread.started, turn.started, turn.completed {usage}, turn.failed, error,
# item.started / item.updated / item.completed, item types agent_message,
# reasoning, command_execution {command}, file_change, mcp_tool_call
# {arguments}, web_search, todo_list, error. Codex reads skills from
# $HOME/.agents/skills and, once it picks a skill, "reads the full SKILL.md"
# (learn.chatgpt.com/docs/build-skills, read 2026-11-19); that read is a
# command_execution whose command names the file. The model goes to Bedrock
# through the built-in amazon-bedrock-runtime provider, which signs with
# AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY from the env
# (codex-rs/model-provider/src/amazon_bedrock/auth.rs), here the eval role's.


CODEX_BEDROCK_PROVIDER = "amazon-bedrock-runtime"
# Never passed to a Codex subject: each could route its model calls off the
# eval-role session or load a config other than the clean HOME's.
CODEX_DROPPED_VARS = frozenset({"CODEX_HOME", "CODEX_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL"})


def harness_env(env: dict[str, str], home: Path, harness: str) -> dict[str, str]:
    """A copy of build_subprocess_env's `env` for a `harness` subject, used
    by both runners: codex loses CODEX_DROPPED_VARS and gets CODEX_HOME in
    the clean HOME; kiro keeps the parent's XDG_DATA_HOME, else gets the
    parent's ~/.local/share, so a kiro subject reads and writes the
    operator's kiro-cli data (its sign-in and chat history) and runs as the
    operator's Kiro identity; kiro also gets the parent's KIRO_API_KEY when
    it is set, which every other subject and the grader never see. Inside
    the wall a subject sees only its own CLI of HOME's tools, apart from a
    caller-added PATH dir and, for kiro, the kiro-cli data folder
    (kiro_data_dir), so no other subject reads Kiro's sign-in files when
    XDG_DATA_HOME is inside a wall; the grader runs outside the wall and
    can."""
    env = dict(env)
    if harness == "codex":
        for k in CODEX_DROPPED_VARS:
            env.pop(k, None)
        (home / ".codex").mkdir(exist_ok=True)
        env["CODEX_HOME"] = str(home / ".codex")
    elif harness == "kiro":
        if not env.get("XDG_DATA_HOME"):
            env["XDG_DATA_HOME"] = str(Path.home() / ".local" / "share")
        if os.environ.get("KIRO_API_KEY"):
            env["KIRO_API_KEY"] = os.environ["KIRO_API_KEY"]
    return env


def parse_codex_stream(process: subprocess.Popen, skill_name: str, skill_dir: Path,
                       timeout: float) -> dict:
    out = new_run_record("codex")
    items = [0]

    def on_line(line: str) -> bool:
        evt = _json_object(line)
        if evt is None:
            return False
        etype = evt.get("type")
        if etype == START_EVENTS["codex"]:
            out["init_seen"] = True
        elif etype == END_EVENTS["codex"]:
            out["end_seen"] = True
            got = codex_usage(evt)
            if got:
                tokens = out["tokens"] or dict.fromkeys(got, 0)
                for k, v in got.items():
                    tokens[k] += v
                # cached counts are part of input
                tokens["total_tokens"] = tokens["input_tokens"] + tokens["output_tokens"]
                out["tokens"] = tokens
        elif etype == "turn.failed":
            _mark_invalid(out, "turn.failed event")
        elif etype == "error":
            _mark_invalid(out, "error event")
        elif etype in ("item.started", "item.updated", "item.completed"):
            items[0] += 1
            item = evt.get("item")
            if not isinstance(item, dict):
                return False
            probe = None
            if item.get("type") == "command_execution":
                probe = item.get("command")
            elif item.get("type") == "mcp_tool_call":
                probe = item.get("arguments")
            if probe is not None and _names_skill_file(probe, skill_name, skill_dir):
                out["trigger_seen"] = True
                return True
        return False

    how = read_stream_lines(process, timeout, on_line)
    finish_run(out, process, how, timeout, START_EVENTS["codex"], END_EVENTS["codex"])
    if not out["invalid"] and not out["trigger_seen"] and items[0] == 0:
        _mark_invalid(out, "no item event, so the output cannot show whether the skill loaded")
    return out


def run_codex(query: str, skill_name: str, skill_dir: Path, model: str | None,
              timeout: int, sandbox: Path, home: Path, env: dict[str, str]) -> dict:
    """Codex CLI adapter: the skill is linked at <clean HOME>/.agents/skills/<name>,
    CODEX_HOME is the clean HOME's .codex (harness_env), and the model
    provider is Bedrock in the eval role's region."""
    skills = home / ".agents" / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    (skills / skill_name).symlink_to(Path(skill_dir).resolve())
    region = env.get("AWS_REGION", "")
    cmd = [
        "codex", "exec",
        "--json",
        "--skip-git-repo-check",
        "--ephemeral",
        "--sandbox", "read-only",
        "-C", str(sandbox),
        "-c", f'model_provider="{CODEX_BEDROCK_PROVIDER}"',
        "-c", f'model_providers.{CODEX_BEDROCK_PROVIDER}.aws.region="{region}"',
    ]
    if model:
        cmd.extend(["--model", model])
    cmd.append(query)
    process = subprocess.Popen(wall_off_host(cmd, sandbox, home, skill_dir), stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=str(sandbox),
                               env=env)
    return parse_codex_stream(process, skill_name, skill_dir, timeout)


HARNESS_ADAPTERS = {"claude": run_claude, "kiro": run_kiro, "codex": run_codex}
# The subject model on kiro and codex when --subject-model is not given
# (claude's is --model, a Bedrock id). codex: the amazon-bedrock-runtime
# provider's Terra id (openai/codex rust-v0.163.0,
# codex-rs/model-provider-info/src/lib.rs:93-94; that provider's catalog
# holds OpenAI models only). kiro: a Kiro catalog id
# (kiro.dev/docs/cli/chat/model-selection). Both read 2026-11-19.
HARNESS_SUBJECT_MODELS = {"codex": "global.openai.gpt-5.6-terra", "kiro": "claude-opus-4.8"}


def subject_model(harness: str, model: str | None, override: str | None) -> str | None:
    """The subject's model: `override` (--subject-model) when given, else
    `model` on claude and HARNESS_SUBJECT_MODELS on kiro and codex."""
    if override:
        return override
    return model if harness == "claude" else HARNESS_SUBJECT_MODELS[harness]


# The CLI and version each adapter was written against; .github/workflows/
# evals.yml installs the same claude and codex pins (kiro is not in CI).
HARNESS_CLI_VERSIONS = {"claude": ("claude", "2.1.328"), "codex": ("codex", "0.163.0"),
                        "kiro": ("kiro-cli", "3.5.0")}


def check_cli_versions(harnesses) -> str | None:
    """None when each harness's `<cli> --version` names its
    HARNESS_CLI_VERSIONS version, else the error to print. A version read is
    not a model call; both runners call this before any run."""
    for harness in dict.fromkeys(harnesses):
        cli, want = HARNESS_CLI_VERSIONS[harness]
        try:
            out = subprocess.run([cli, "--version"], capture_output=True, text=True,
                                 timeout=30).stdout
        except (OSError, subprocess.TimeoutExpired) as e:
            return f"cannot read `{cli} --version` ({e}); the {harness} adapter needs {cli} {want}"
        got = re.search(r"\d+\.\d+\.\d+", out)
        if not got or got.group(0) != want:
            found = got.group(0) if got else repr(out.strip())
            return (f"{cli} {found} is installed, but the {harness} adapter was written "
                    f"against {cli} {want}: install {want} or update the adapter")
    return None


def run_single_query(
    query: str,
    skill_name: str,
    repo_skill_dir: Path,
    model: str | None,
    timeout: int,
    *,
    harness: str = "claude",
) -> dict:
    """Run one query on one harness in a fresh sandbox and clean HOME, with
    the eval-role env (harness_env). Returns the adapter's new_run_record
    dict; the caller counts only valid runs."""
    adapter = HARNESS_ADAPTERS[harness]
    with stage_skill_sandbox(skill_name, repo_skill_dir) as (sandbox, home):
        env = harness_env(build_subprocess_env(home, aws_env=eval_aws_env(timeout)),
                          home, harness)
        return adapter(query, skill_name, Path(repo_skill_dir), model, timeout, sandbox, home, env)


# ---------- top-level aggregation ---------------------------------------------


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def read_skill_meta(skill_dir: Path) -> tuple[str, str]:
    """Parse SKILL.md frontmatter for (name, description) with
    yaml.safe_load (the docs pipeline's parsing contract). Raises
    RuntimeError on missing frontmatter, missing `name` or invalid YAML.
    """
    text = (skill_dir / "SKILL.md").read_text()
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise RuntimeError(f"SKILL.md has no YAML frontmatter: {skill_dir}")
    fm = m.group(1)
    if len(fm.encode("utf-8")) > 256 * 1024:
        raise RuntimeError(f"SKILL.md frontmatter exceeds maximum allowed size: {skill_dir}")
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


def _worker(args: tuple) -> tuple[int, dict]:
    case_idx, query, skill_name, repo_skill_dir, model, timeout, creds, harness = args
    set_eval_credentials(creds)
    try:
        result = run_single_query(query, skill_name, Path(repo_skill_dir), model, timeout,
                                  harness=harness)
    except EvalCredentialError:
        raise  # a failed refresh stops the run; it is never an invalid run that can pass
    except Exception as e:  # noqa: BLE001
        result = new_run_record(harness)
        result["invalid"] = True
        result["invalid_reason"] = f"worker exception: {e!r}"
    return case_idx, result


def score_case(item: dict, records: list[dict], trigger_threshold: float) -> dict:
    """One results[] row. Only valid runs count, in both the trigger count
    and the run count behind the rate; a case with no valid run fails on
    either side, and a class's shared negative with any invalid run fails."""
    valid = [r for r in records if not r.get("invalid")]
    invalid = [r for r in records if r.get("invalid")]
    runs = len(valid)
    trigger_count = sum(1 for r in valid if r.get("triggered"))
    rate = (trigger_count / runs) if runs else 0.0
    should = bool(item["should_trigger"])
    source = item.get("source", "member")
    if not runs:
        fail_reason = "no valid run"
    elif not should and invalid and source != "member":
        fail_reason = "shared negative with invalid runs"
    elif should:
        fail_reason = None if rate >= trigger_threshold else "trigger rate below threshold"
    else:
        fail_reason = None if rate < trigger_threshold else "trigger rate at or above threshold"
    row = {
        "query": item["query"],
        "should_trigger": should,
        "trigger_rate": rate,
        "triggers": trigger_count,
        "runs": runs,
        "pass": fail_reason is None,
        "source": source,
        "attempted_runs": len(records),
        "invalid_count": len(invalid),
        "fail_reason": fail_reason,
        "run_records": records,
    }
    if "id" in item:
        row["id"] = item["id"]
    if invalid:
        row["invalid_runs"] = [
            {"reason": r.get("invalid_reason"), "init_skills": r.get("init_skills")}
            for r in invalid
        ]
    return row


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
    *,
    harness: str = "claude",
) -> dict:
    """Execute every (case x run) pair; aggregate into run_eval.py's output
    schema plus the fields score_case adds. Cases are keyed by their index,
    so a shared case whose query matches a member's is its own row. Each
    worker starts from `creds` and refreshes it when a query would outlive it.
    """
    jobs = []
    for idx, item in enumerate(eval_set):
        for _ in range(runs_per_query):
            jobs.append((idx, item["query"], skill_name, str(repo_skill_dir), model, timeout,
                         creds, harness))

    records_by_case: dict[int, list[dict]] = {}

    with ProcessPoolExecutor(max_workers=num_workers) as ex:
        futures = [ex.submit(_worker, j) for j in jobs]
        for fut in as_completed(futures):
            try:
                idx, result = fut.result()
            except EvalCredentialError:
                for f in futures:
                    f.cancel()
                raise
            records_by_case.setdefault(idx, []).append(result)

    results = [score_case(item, records_by_case.get(idx, []), trigger_threshold)
               for idx, item in enumerate(eval_set)]

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    all_runs = [rec for r in results for rec in r["run_records"]]
    totals = [rec["tokens"]["total_tokens"] for rec in all_runs
              if not rec.get("invalid") and isinstance(rec.get("tokens"), dict)
              and isinstance(rec["tokens"].get("total_tokens"), int)]
    return {
        "skill_name": skill_name,
        "description": description,
        "harness": harness,
        "runs_per_query": runs_per_query,
        "trigger_threshold": trigger_threshold,
        "results": results,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "invalid_runs": sum(r["invalid_count"] for r in results),
            "runs_with_tokens": len(totals),
            "tokens_per_run": (sum(totals) / len(totals)) if totals else None,
        },
    }


# ---------- class shared trigger evals ----------------------------------------
#
# A class's shared trigger cases live at classes/<class>/evals/trigger/
# triggering.json. They run against each target of the
# class, merged with the target's own cases, a class's parents' cases first.
# A class's targets (CLASS_TARGETS, built by class_targets below) are every
# skill whose SKILL.md frontmatter names the class, or a child of it, in
# metadata.apex-classes (each a blocking target), plus the explicit list
# here; run_task_evals.py builds its target list from it too.
# The explicit list is report-only: a failed shared case does not fail the
# key by itself (a task case's grader score still counts in the key's pooled
# delta). It holds the 22 planned skills and the 4 skills their owners hold.
# dotnet-aws-ecs is not a target until its own rebuild. No devops-agent copy
# is a target, listed or by membership; the copies are to be tested inside a
# DevOps Agent environment instead.

REPO_ROOT = Path(__file__).resolve().parents[3]

_APEX_BASE_REPORT_ONLY = (
    "skills/apex", "skills/apex-new-skill", "skills/ecs-architect", "skills/ecs-build",
    "skills/ecs-devops", "skills/ecs-genai", "skills/ecs-modernize", "skills/ecs-observability",
    "skills/ecs-operation-review", "skills/ecs-recon", "skills/ecs-security",
    "skills/eks-best-practices", "skills/eks-build", "skills/eks-cost-intelligence",
    "skills/eks-design", "skills/eks-genai", "skills/eks-mcp-server",
    "skills/eks-platform-engineering", "skills/eks-recon", "skills/eks-security",
    "skills/graviton-migration", "skills/update-docs",
    "skills/eks-upgrade-check", "skills/eks-operation-review",
    "skills/eks-well-architected-review", "skills/eks-ingress-migration",
)
EXPLICIT_CLASS_TARGETS: dict[str, dict[str, bool]] = {
    "apex-base": {p: False for p in _APEX_BASE_REPORT_ONLY},
}
sys.path.insert(0, str(REPO_ROOT / "classes" / "steward" / "scripts"))
import run_checks  # noqa: E402  (class membership, as the admission runner reads it)


class EvalSetError(ValueError):
    """An eval set, class or target that cannot be run as asked."""


def run_key_for(skill_dir: Path) -> str:
    """The key a run's output and history use: the folder name for
    skills/<name>, <parent>-<name> for any other folder (a hand run with
    --skill-path devops-agent/<name>/ shares its twin's `name:`)."""
    skill_dir = Path(skill_dir).resolve()
    if skill_dir.parent.name == "skills":
        return skill_dir.name
    return f"{skill_dir.parent.name}-{skill_dir.name}"


def target_path(skill_dir: Path) -> str | None:
    """skill_dir relative to the repo root, or None outside it."""
    try:
        return Path(skill_dir).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return None


def class_parents(name: str, classes_root: Path) -> list[str]:
    path = classes_root / name / "class.yaml"
    try:
        text = path.read_text()
    except OSError as e:
        raise EvalSetError(f"no class {name!r}: cannot read {path}") from e
    data = yaml.safe_load(text) or {}
    parents = data.get("parents") or []
    if not isinstance(parents, list) or not all(isinstance(p, str) for p in parents):
        raise EvalSetError(f"{path}: parents must be a list of class names")
    return parents


def class_chain(names: list[str], classes_root: Path) -> list[str]:
    """The named classes and their parents, parents first, each class once."""
    order: list[str] = []
    visiting: set[str] = set()

    def visit(n: str) -> None:
        if n in order:
            return
        if n in visiting:
            raise EvalSetError(f"class parents loop at {n!r}")
        visiting.add(n)
        for p in class_parents(n, classes_root):
            visit(p)
        visiting.discard(n)
        order.append(n)

    for n in names:
        visit(n)
    return order


def declared_classes(skill_md: Path) -> list[str]:
    """metadata.apex-classes in a SKILL.md's frontmatter as a list ([] when
    absent), read by the admission runner's own reader
    (classes/steward/scripts/run_checks.py)."""
    try:
        return run_checks.declared_classes(skill_md)
    except (run_checks.ClassError, run_checks.FrontmatterError) as e:
        raise EvalSetError(f"{skill_md}: {e}") from e


def class_targets(repo_root: Path = REPO_ROOT, classes_root: Path | None = None,
                  explicit: dict[str, dict[str, bool]] = EXPLICIT_CLASS_TARGETS,
                  refused: dict[str, str] | None = None) -> dict[str, dict[str, bool]]:
    """Each class's targets: the explicit list, plus every skill whose
    metadata.apex-classes names the class or one of its children (a member
    of a class is a member of its parents), as a blocking target. A
    devops-agent copy is never one (SKILL_GLOBS also reads devops-agent/
    for class admission). A SKILL.md whose classes cannot be read is left out
    and its folder's error goes into `refused`, so it stops only its own
    run (build_eval_set, run_task_evals.run_skill), not every import."""
    classes_root = classes_root or (repo_root / "classes")
    targets = {cls: dict(listed) for cls, listed in explicit.items()}
    for pattern in run_checks.SKILL_GLOBS:
        for skill_md in sorted(repo_root.glob(pattern)):
            rel = skill_md.parent.relative_to(repo_root).as_posix()
            if rel.startswith("devops-agent/"):
                continue
            try:
                names = declared_classes(skill_md)
            except EvalSetError as e:
                if refused is None:
                    raise
                refused[rel] = str(e)
                continue
            if not names:
                continue
            for cls in class_chain(names, classes_root):
                targets.setdefault(cls, {})[rel] = True
    return targets


# Folder (repo-relative) -> why its SKILL.md's classes could not be read.
CLASS_TARGETS_REFUSED: dict[str, str] = {}
CLASS_TARGETS: dict[str, dict[str, bool]] = class_targets(refused=CLASS_TARGETS_REFUSED)


def _check_cases(cases, where: str) -> list[dict]:
    if not isinstance(cases, list):
        raise EvalSetError(f"{where}: must be a JSON list of cases")
    for i, c in enumerate(cases):
        if (not isinstance(c, dict) or not isinstance(c.get("query"), str)
                or not isinstance(c.get("should_trigger"), bool)):
            raise EvalSetError(f"{where}[{i}]: needs a string query and a bool should_trigger")
        if "id" in c and (not isinstance(c["id"], int) or isinstance(c["id"], bool)):
            raise EvalSetError(f"{where}[{i}]: id must be an integer")
    return cases


def build_eval_set(member_set: Path | None, classes: list[str], skill_dir: Path,
                   classes_root: Path | None = None,
                   targets: dict[str, dict[str, bool]] | None = None) -> tuple[list[dict], dict]:
    """Merge the member's own cases (source "member") with each named
    class's shared cases (source "class:<name>"), parents first. Returns
    (cases, meta); meta holds run_key, target, classes and blocking (None
    with no class). A class with no shared trigger file is skipped with a
    message on stderr. Refuses a skill that is not on a named class's target
    list, a merged set with no case, and repeated case ids."""
    classes_root = classes_root or (REPO_ROOT / "classes")
    targets = CLASS_TARGETS if targets is None else targets
    cases: list[dict] = []
    if member_set is not None:
        where = str(member_set)
        try:
            loaded = json.loads(Path(member_set).read_text())
        except (OSError, ValueError) as e:
            raise EvalSetError(f"cannot read {where}: {e}") from e
        cases += [dict(c, source="member") for c in _check_cases(loaded, where)]
    target = target_path(skill_dir)
    if target in CLASS_TARGETS_REFUSED:
        raise EvalSetError(CLASS_TARGETS_REFUSED[target])
    blocking = None
    chain: list[str] = []
    if classes:
        for name in classes:
            listed = targets.get(name)
            if listed is None:
                raise EvalSetError(f"class {name!r} has no target list in CLASS_TARGETS")
            if target not in listed:
                raise EvalSetError(f"{target or skill_dir} is not a target of class {name!r}")
            blocking = bool(blocking) or listed[target]
        chain = class_chain(classes, classes_root)
        for name in chain:
            path = classes_root / name / "evals" / "trigger" / "triggering.json"
            if not path.is_file():
                print(f"[run_triggering] class {name}: no shared trigger evals "
                      f"(evals/trigger/triggering.json), skipped", file=sys.stderr)
                continue
            try:
                loaded = json.loads(path.read_text())
            except (OSError, ValueError) as e:
                raise EvalSetError(f"cannot read {path}: {e}") from e
            cases += [dict(c, source=f"class:{name}") for c in _check_cases(loaded, str(path))]
    ids = [c["id"] for c in cases if "id" in c]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise EvalSetError(f"case ids repeat across the merged set: {dup}")
    if not cases:
        raise EvalSetError("no cases: pass --eval-set, --class or both")
    meta = {"run_key": run_key_for(skill_dir), "target": target,
            "classes": chain, "blocking": blocking}
    return cases, meta


# ---------- CLI ---------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--eval-set", default=None,
                        help="Path to the skill's own triggering.json")
    parser.add_argument("--skill-path", default=None,
                        help="Path to skills/<name>/ or devops-agent/<name>/")
    parser.add_argument("--class", dest="classes", action="append", default=[],
                        metavar="CLASS",
                        help="Also run this class's shared trigger evals (and its parents'); "
                             "the skill must be on the class's target list. Repeatable")
    parser.add_argument("--run-key", default=None,
                        help="The gate's form, in place of --eval-set, --skill-path and --class: "
                             "the run key's misc/evals/<key>/triggering.json, skill folder and "
                             "classes (run_task_evals.resolve_target). A key with no trigger case "
                             "prints {\"run_key\": <key>, \"skipped\": <why>} and exits 0")
    parser.add_argument("--harness", choices=HARNESSES, default="claude")
    parser.add_argument("--num-workers", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=90, help="Per-query wallclock seconds")
    parser.add_argument("--runs-per-query", type=int, default=3)
    parser.add_argument("--trigger-threshold", type=float, default=0.5)
    parser.add_argument("--model", default=None,
                        help="The claude subject's model (a Bedrock id)")
    parser.add_argument("--subject-model", default=None,
                        help="The subject's model on any harness; default --model on claude, "
                             "else HARNESS_SUBJECT_MODELS (codex "
                             f"{HARNESS_SUBJECT_MODELS['codex']}, kiro "
                             f"{HARNESS_SUBJECT_MODELS['kiro']})")
    parser.add_argument("--base-ref", default=None,
                        help="Also run every case on the skill as it was at this git ref (arm "
                             "base_skill, read from git objects as run_task_evals.py --base-ref "
                             "does), printed under \"base\"; a skill absent there gets no base "
                             "arm. Default: run_task_evals.py's default ref with --run-key (the "
                             "gate compares old against new), else none; none: no base arm")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    model = subject_model(args.harness, args.model, args.subject_model)

    if args.run_key:
        if args.eval_set or args.skill_path or args.classes:
            print("error: --run-key takes no --eval-set, --skill-path or --class", file=sys.stderr)
            return 1
        import run_task_evals  # its target resolution; imported here, as it imports this module
        t = run_task_evals.resolve_target(args.run_key)
        own = run_task_evals.EVALS_ROOT / args.run_key / "triggering.json"
        try:
            shared = [c for c in class_chain(t["classes"], REPO_ROOT / "classes")
                      if (REPO_ROOT / "classes" / c / "evals" / "trigger" / "triggering.json").is_file()]
        except EvalSetError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        if not own.is_file() and not shared:
            print(json.dumps({"run_key": args.run_key,
                              "skipped": "no trigger case: no triggering.json and no class trigger file"}))
            return 0
        args.eval_set = str(own) if own.is_file() else None
        args.skill_path, args.classes = str(t["skill_repo_dir"]), t["classes"]
        if args.base_ref is None:
            args.base_ref = run_task_evals.DEFAULT_BASE_REF

    if not args.skill_path:
        print("error: --skill-path is required", file=sys.stderr)
        return 1
    skill_dir = Path(args.skill_path).resolve()
    if not (skill_dir / "SKILL.md").exists():
        print(f"error: no SKILL.md at {skill_dir}", file=sys.stderr)
        return 1
    try:
        eval_set, meta = build_eval_set(
            Path(args.eval_set) if args.eval_set else None, args.classes, skill_dir)
    except EvalSetError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    base_ref = None if (args.base_ref or "none").lower() in ("", "none") else args.base_ref
    base_sha = None
    if base_ref:
        import run_task_evals  # its --base-ref helpers; imported here, as it imports this module
        if meta["target"] is None:
            print(f"error: --base-ref needs a skill inside {REPO_ROOT}", file=sys.stderr)
            return 1
        try:
            base_sha = run_task_evals.resolve_base_ref(base_ref)
        except run_task_evals.BaseRefError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    name, description = read_skill_meta(skill_dir)

    version_error = check_cli_versions([args.harness])
    if version_error:
        print(f"error: {version_error}", file=sys.stderr)
        return 2
    try:
        creds = mint_eval_role_credentials(timeout=args.timeout, source="--timeout")
    except EvalCredentialError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"[run_triggering] skill={name} run_key={meta['run_key']} harness={args.harness} "
              f"prompts={len(eval_set)} runs={args.runs_per_query} workers={args.num_workers} "
              f"model={model}",
              file=sys.stderr)

    run_args = dict(eval_set=eval_set, num_workers=args.num_workers, timeout=args.timeout,
                    runs_per_query=args.runs_per_query, trigger_threshold=args.trigger_threshold,
                    model=model, creds=creds, harness=args.harness)
    base_tmp = Path(tempfile.mkdtemp(prefix="triggering-base-ref-"))
    try:
        output = run_eval(skill_name=name, description=description, repo_skill_dir=skill_dir,
                          **run_args)
        if base_sha:
            base_dir = run_task_evals.materialise_skill_at_ref(base_sha, meta["target"], base_tmp)
            base = {"base_ref": base_ref, "base_ref_sha": base_sha, "arm": None}
            if base_dir is None:
                base["note"] = f"{meta['target']} does not exist at {base_ref}: no base arm"
            else:
                base_name, base_description = read_skill_meta(base_dir)
                base_out = run_eval(skill_name=base_name, description=base_description,
                                    repo_skill_dir=base_dir, **run_args)
                base.update(arm="base_skill", results=base_out["results"],
                            summary=base_out["summary"])
            output["base"] = base
    except EvalCredentialError as e:
        print(f"error: eval-role session refresh failed, stopping: {e}", file=sys.stderr)
        return 2
    except (run_task_evals.BaseRefError if base_sha else ()) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(base_tmp, ignore_errors=True)
    output.update(meta)

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
