#!/usr/bin/env python3
"""Confined launches for the eval runners.

Every `claude -p` the runners start (triggering subject, task subject, each
turn of a multi-turn subject, grader) runs here, as the system user
`apex-eval`, in its own transient systemd unit:

  sudo -n systemd-run --unit=apex-eval-<launch id> --uid=apex-eval ...
    --pipe --wait --collect -- /opt/apex-eval/bin/claude ...

What the unit gets:

  - Credentials: one role session per launch, minted by the parent with
    `aws sts assume-role` into the Bedrock-only role ROLE_NAME (role_arn():
    the account is the parent profile's own, read at run time with
    `aws sts get-caller-identity`, so no account id is in the code), through
    the profile PARENT_PROFILE in PARENT_AWS_CONFIG (whose credential_process
    returns the payer account's admin session; that session never enters a
    unit). The keys go into an env file (0600, in the invoking user's 0700
    dir) that PID 1 reads at unit start, never into argv. The file is deleted
    when the launch ends.
  - Files: an empty /home, /root and /run/user, a private /tmp, /var/tmp and
    /dev/shm, its own run root from the runs tree (read-only, with home/ and
    sandbox/ writable), its skill copy bound read-only, and a root-owned copy
    of claude under /opt/apex-eval/bin. /var/log and the paths in
    HOST_HIDDEN_FILE are hidden; /etc, /usr and the rest of /var stay
    readable (ProtectSystem=strict makes them read-only, not hidden).
  - Network: no loopback, link-local (instance metadata), the IP_DENY ranges
    or the instance's public IPv4; the host's resolver (from
    /etc/resolv.conf) and every address outside those ranges.

Launches run one at a time (a host-wide flock), because every unit runs as
the same uid and could otherwise read another unit's environment through
/proc. The parent reads a unit's files back only through a read-back unit
(`tar`, which never follows links) and deletes them through a cleanup unit.

The host steps (user, directories, the claude copy) are done once by
misc/evals/setup/install-eval-boundary.sh; a documented example of the role's
two policies is misc/evals/setup/eval-bedrock-invoke-*.json.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import io
import itertools
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# Settings: the role name, the parent profile and the Region may be set in
# the environment. The account is never in the code: role_arn() reads it at
# run time. setup/eval-bedrock-invoke-*.json are a documented example of the
# role's two policies.
ROLE_NAME = os.environ.get("APEX_EVAL_ROLE_NAME", "apex-eval-bedrock-invoke")
PARENT_AWS_CONFIG = Path.home() / ".apex-eval" / "aws-config"
PARENT_PROFILE = os.environ.get("APEX_EVAL_PROFILE", "apex-eval-admin")
AWS_REGION = os.environ.get("APEX_EVAL_REGION", "us-west-2")

EVAL_USER = "apex-eval"
STATE_ROOT = Path("/var/lib/apex-eval")
RUNS_ROOT = STATE_ROOT / "runs"
ENV_DIR = STATE_ROOT / "env"
LOCK_FILE = ENV_DIR / "launch.lock"
OPT_ROOT = Path("/opt/apex-eval")
CLAUDE_BIN = OPT_ROOT / "bin" / "claude"
UNIT_PATH = f"{OPT_ROOT}/bin:/usr/local/bin:/usr/bin"

# The host's resolver is the one private address a unit may reach.
RESOLV_CONF = Path("/etc/resolv.conf")
# Loopback, link-local and multicast, RFC 1918, RFC 6598 shared space and
# IPv6 unique local addresses.
IP_DENY = [
    "localhost", "link-local", "multicast",
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10",
    "fd00::/8",
]
# Hidden on top of ProtectHome; "-" skips a path the host does not have.
INACCESSIBLE = ["-/var/log"]
# This host's own paths to hide as well: one absolute path per line. Absent
# means none.
HOST_HIDDEN_FILE = Path.home() / ".apex-eval" / "inaccessible-paths"
# The account the parent profile must resolve to: one 12-digit id, written
# by the operator on this host. Required: role_arn() refuses any other.
HOST_ACCOUNT_FILE = Path.home() / ".apex-eval" / "expected-account"

# Role chaining caps a session at one hour, and AssumeRole takes 900 s at least.
SESSION_MIN, SESSION_MAX, SESSION_SLACK = 900, 3600, 300
RUNTIME_SLACK = 60
HOST_MODEL_VARS = (
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
)
_ID_RE = re.compile(r"[A-Za-z0-9_.-]+")
_counter = itertools.count(1)


class ConfinedError(RuntimeError):
    """A launch, mint or host check failed; the run must stop or record it."""


@dataclass
class Run:
    """One run root: runs/<run_id>/{home,sandbox}. A multi-turn subject is
    one Run with several launches (turns), so HOME stays the same."""

    run_id: str
    root: Path
    # Paths cleanup_run could not remove, for the run's results.
    left: list[str] = field(default_factory=list)

    @property
    def home(self) -> Path:
        return self.root / "home"

    @property
    def sandbox(self) -> Path:
        return self.root / "sandbox"

    @property
    def env_file(self) -> Path:
        return ENV_DIR / f"{self.run_id}.env"


def new_run_id() -> str:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{os.getpid()}-{next(_counter):04d}"


# ---------- host checks -------------------------------------------------------


def preflight(timeout: int, *, include_live_only: bool = False) -> str:
    """Refuse to run unless the boundary can hold. Returns the version of the
    claude copy the units run, for the run's results."""
    if include_live_only:
        raise ConfinedError(
            "--include-live-only is refused: no unit gets a cluster credential, "
            "so live-cluster prompts stay off"
        )
    check_timeout(timeout)
    if shutil.which("aws") is None:
        raise ConfinedError("the AWS CLI (aws) is not on PATH: every session is minted with it")
    for argv, what in (
        (["sudo", "-n", "true"], "passwordless sudo (sudo -n true)"),
        (["systemd-run", "--version"], "systemd-run"),
    ):
        try:
            r = subprocess.run(argv, capture_output=True, text=True)
        except FileNotFoundError:
            raise ConfinedError(f"{what} is not available") from None
        if r.returncode != 0:
            raise ConfinedError(f"{what} failed: {r.stderr.strip()[-200:]}")
    if not PARENT_AWS_CONFIG.is_file():
        raise ConfinedError(f"missing parent AWS config {PARENT_AWS_CONFIG}")
    for path in (RUNS_ROOT, ENV_DIR, CLAUDE_BIN):
        if not path.exists():
            raise ConfinedError(
                f"missing {path}: run misc/evals/setup/install-eval-boundary.sh first"
            )
    r = subprocess.run([str(CLAUDE_BIN), "--version"], capture_output=True, text=True)
    if r.returncode != 0:
        raise ConfinedError(f"{CLAUDE_BIN} --version failed")
    # Every launch needs these; read them now, before any session is minted.
    role_arn()
    public_ipv4()
    resolver()
    inaccessible_paths()
    return r.stdout.strip()


def check_timeout(timeout: int) -> None:
    if timeout + SESSION_SLACK > SESSION_MAX:
        raise ConfinedError(
            f"timeout {timeout}s plus {SESSION_SLACK}s passes the {SESSION_MAX}s "
            "role-chaining session cap; lower the timeout"
        )


_public_ipv4: list[str] | None = None


def public_ipv4() -> list[str]:
    """The instance's own public IPv4, read by the parent (IMDSv2), so a unit
    cannot reach host services through it. Empty when IMDS answers 404 (no
    public IPv4); any other failure raises, so the deny never goes missing."""
    global _public_ipv4
    if _public_ipv4 is None:
        base = "http://169.254.169.254/latest"
        try:
            req = urllib.request.Request(
                f"{base}/api/token", method="PUT",
                headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
            )
            token = urllib.request.urlopen(req, timeout=2).read().decode()
            req = urllib.request.Request(
                f"{base}/meta-data/public-ipv4",
                headers={"X-aws-ec2-metadata-token": token},
            )
            try:
                ip = urllib.request.urlopen(req, timeout=2).read().decode().strip()
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                ip = None
        except Exception as e:  # noqa: BLE001
            raise ConfinedError(
                "cannot read the public IPv4 from IMDS (the runners need an EC2 "
                f"instance with IMDSv2 reachable): {e!r}") from None
        if ip is not None and not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip):
            raise ConfinedError(f"IMDS public-ipv4 is not an IPv4 address: {ip[:40]!r}")
        _public_ipv4 = [ip] if ip else []
    return _public_ipv4


def resolver() -> str:
    """The first IPv4 nameserver in /etc/resolv.conf, read by the parent. A
    loopback one (a local stub) is refused: a unit cannot reach loopback."""
    try:
        text = RESOLV_CONF.read_text()
    except OSError as e:
        raise ConfinedError(f"cannot read {RESOLV_CONF}: {e.strerror}") from None
    found = re.findall(r"^\s*nameserver\s+(\d{1,3}(?:\.\d{1,3}){3})\s*$", text, re.M)
    if not found:
        raise ConfinedError(f"no IPv4 nameserver in {RESOLV_CONF}")
    if found[0].startswith("127."):
        raise ConfinedError(
            f"{RESOLV_CONF} names loopback {found[0]}, which a unit cannot reach"
        )
    return found[0]


def inaccessible_paths() -> list[str]:
    """INACCESSIBLE plus this host's HOST_HIDDEN_FILE list. An unreadable
    file, or a line that is not a plain absolute path, raises."""
    try:
        text = HOST_HIDDEN_FILE.read_text()
    except FileNotFoundError:
        return list(INACCESSIBLE)
    except (OSError, UnicodeDecodeError) as e:
        raise ConfinedError(f"cannot read {HOST_HIDDEN_FILE}: {e}") from None
    extra = []
    for line in text.splitlines():
        path = line.strip()
        if not path:
            continue
        if (not path.startswith("/") or not path.strip("/") or ".." in path.split("/")
                or re.search(r"[\s\"'\\\x00]", path)):
            raise ConfinedError(f"{HOST_HIDDEN_FILE}: not a plain absolute path: {path[:80]!r}")
        extra.append(f"-{path}")
    return INACCESSIBLE + extra


# ---------- credentials -------------------------------------------------------


def _parent_aws_env() -> dict:
    """The environment of the parent's own aws calls: no AWS_* variable of
    the caller, only PARENT_AWS_CONFIG, never ~/.aws."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("AWS_")}
    env["AWS_CONFIG_FILE"] = str(PARENT_AWS_CONFIG)
    env["AWS_SHARED_CREDENTIALS_FILE"] = os.devnull
    return env


def _signin_hint(err: str) -> str:
    if "custom-process" in err or "credential_process" in err:
        return (f" (the {PARENT_PROFILE} profile's credential_process failed; "
                "renew its sign-in, then rerun)")
    return ""


_account: str | None = None


def role_arn() -> str:
    """The role's ARN in the parent profile's own account. The account is
    read once per process with `aws sts get-caller-identity` and must equal
    HOST_ACCOUNT_FILE; any failure raises, so no launch runs on a guessed or
    unexpected account."""
    global _account
    if _account is None:
        expected = expected_account()
        r = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--profile", PARENT_PROFILE,
             "--region", AWS_REGION, "--query", "Account", "--output", "text"],
            capture_output=True, text=True, env=_parent_aws_env(),
        )
        account = r.stdout.strip()
        if r.returncode != 0 or not re.fullmatch(r"\d{12}", account):
            detail = (r.stderr.strip() or account)[-200:]
            raise ConfinedError(
                f"cannot read the account of profile {PARENT_PROFILE}{_signin_hint(r.stderr)} "
                f"(aws sts get-caller-identity): {detail}")
        if account != expected:
            raise ConfinedError(
                f"profile {PARENT_PROFILE} resolves to account {account}, not the "
                f"{expected} in {HOST_ACCOUNT_FILE}")
        _account = account
    return f"arn:aws:iam::{_account}:role/{ROLE_NAME}"


def expected_account() -> str:
    """The one 12-digit account id in HOST_ACCOUNT_FILE. Absent, unreadable
    or any other content raises."""
    try:
        text = HOST_ACCOUNT_FILE.read_text()
    except (OSError, UnicodeDecodeError) as e:
        raise ConfinedError(
            f"cannot read {HOST_ACCOUNT_FILE} (write the eval account id there, "
            f"misc/evals/README.md Step 0): {e}") from None
    account = text.strip()
    if not re.fullmatch(r"\d{12}", account):
        raise ConfinedError(f"{HOST_ACCOUNT_FILE}: not one 12-digit account id")
    return account


def mint_role_session(session_name: str, timeout: int) -> dict:
    """Assume the Bedrock-only role for one launch. Duration is the launch
    timeout plus SESSION_SLACK, within 900 to 3600 s."""
    if len(session_name) > 64 or not _ID_RE.fullmatch(session_name):
        raise ConfinedError(f"bad role session name {session_name!r}")
    check_timeout(timeout)
    duration = max(SESSION_MIN, timeout + SESSION_SLACK)
    cmd = [
        "aws", "sts", "assume-role",
        "--profile", PARENT_PROFILE,
        "--region", AWS_REGION,
        "--role-arn", role_arn(),
        "--role-session-name", session_name,
        "--duration-seconds", str(duration),
        "--output", "json",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, env=_parent_aws_env())
    if r.returncode != 0:
        err = r.stderr.strip()
        raise ConfinedError(f"role session mint failed{_signin_hint(err)}: {err[-300:]}")
    return json.loads(r.stdout)["Credentials"]


def write_env_file(run: Run, creds: dict | None) -> None:
    """The unit's whole environment. 0600, owned by the parent; PID 1 reads it."""
    lines = {
        "HOME": str(run.home),
        "PATH": UNIT_PATH,
        "LANG": "C.UTF-8",
        "DISABLE_AUTOUPDATER": "1",
    }
    if creds is not None:
        lines.update({
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": AWS_REGION,
            "AWS_ACCESS_KEY_ID": creds["AccessKeyId"],
            "AWS_SECRET_ACCESS_KEY": creds["SecretAccessKey"],
            "AWS_SESSION_TOKEN": creds["SessionToken"],
        })
        for var in HOST_MODEL_VARS:
            if os.environ.get(var):
                lines[var] = os.environ[var]
    for k, v in lines.items():
        if "\n" in v or '"' in v or "\\" in v:
            raise ConfinedError(f"env value for {k} cannot go in an env file")
    data = "".join(f'{k}="{v}"\n' for k, v in lines.items())
    fd = os.open(run.env_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(data)


# ---------- staging -----------------------------------------------------------


@contextlib.contextmanager
def staging_umask(mask: int):
    old = os.umask(mask)
    try:
        yield
    finally:
        os.umask(old)


def stage_run(skill_name: str | None = None, repo_skill_dir: Path | None = None) -> Run:
    """Make runs/<id>/{home,sandbox} (group-writable, setgid from runs/) and,
    for a with-skill run, copy the skill to home/.claude/skills/<name>, its
    files read-only to the unit. Pair with cleanup_run()."""
    run_id = new_run_id()
    run = Run(run_id, RUNS_ROOT / run_id)
    with staging_umask(0o007):
        run.root.mkdir()
        run.home.mkdir()
        run.sandbox.mkdir()
        (run.home / ".claude").mkdir()
    if skill_name is not None and repo_skill_dir is not None:
        try:
            stage_readonly_copy(Path(repo_skill_dir), run.home / ".claude" / "skills" / skill_name)
        except BaseException:
            # Nothing has run in the unit yet, so the parent owns every path.
            shutil.rmtree(run.root, ignore_errors=True)
            raise
    return run


def stage_readonly_copy(src: Path, dest: Path) -> None:
    """Copy a tree the unit may read but not change (group read-only)."""
    _stage_copy(src, dest, group_write=False)


def stage_writable_copy(src: Path, dest: Path) -> None:
    """Copy a tree into a run the unit may change (fixtures); merges into dest."""
    _stage_copy(src, dest, group_write=True)


def _stage_copy(src: Path, dest: Path, *, group_write: bool) -> None:
    # Source modes are not kept (a 0664 checkout would make a read-only
    # copy group-writable): dirs 0750/0770, files 0640/0660, exec bit kept.
    # A link is refused, never copied: copytree(symlinks=False) would copy
    # its target, which may be outside the repo (~/.aws/credentials). That
    # holds for src itself and every dir above it, as well as inside it.
    if os.path.realpath(src) != os.path.abspath(src):
        raise ConfinedError(f"refusing to stage through a symlink: {src}")
    group = 0o070 if group_write else 0o050
    with staging_umask(0o007 if group_write else 0o027):
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            pairs = [(src, dest)]
            for dirpath, dirnames, filenames in os.walk(src):
                for name in [*dirnames, *filenames]:
                    s = Path(dirpath) / name
                    if s.is_symlink():
                        raise ConfinedError(f"refusing to stage a symlink: {s}")
                    pairs.append((s, dest / s.relative_to(src)))
            shutil.copytree(
                src, dest, symlinks=False,
                copy_function=shutil.copyfile, dirs_exist_ok=group_write,
            )
        else:
            shutil.copyfile(src, dest)
            pairs = [(src, dest)]
    for s, d in pairs:
        if d.is_dir():
            d.chmod(0o2700 | group)
        else:
            mode = 0o600 | (group & 0o060)
            if s.stat().st_mode & 0o100:
                mode |= 0o100 | (group & 0o010)
            d.chmod(mode)


def cleanup_run(run: Run) -> list[str]:
    """Delete a run root. The unit's files belong to apex-eval, so a cleanup
    unit (no AWS keys) deletes them; the parent then removes the empty dirs.
    Returns the paths left over, for the results, and keeps them in run.left."""
    left = run.left
    # Give group write back to what the parent staged read-only (the skill
    # copy, a grader's input/), wherever the unit moved it. Dirs the unit
    # made are not readable by the parent, and os.walk skips them.
    uid = os.getuid()
    for top in (run.home, run.sandbox):
        for dirpath, dirnames, filenames in os.walk(top):
            for name in [*dirnames, *filenames]:
                p = Path(dirpath) / name
                with contextlib.suppress(OSError):
                    st = p.lstat()
                    if st.st_uid == uid and not p.is_symlink():
                        p.chmod(st.st_mode | 0o070)
    try:
        with launch_confined(
            run,
            ["/usr/bin/find", str(run.home), str(run.sandbox), "-mindepth", "1", "-delete"],
            policy_kind="none",
            timeout=SESSION_MIN,
            unit_suffix="cleanup",
            lock_skills=False,
        ) as proc:
            proc.communicate()
        if proc.returncode != 0:
            left.append(f"cleanup unit exited {proc.returncode}")
    except ConfinedError as e:
        left.append(f"cleanup unit failed: {e}")
    for p in (run.home, run.sandbox, run.root):
        try:
            p.rmdir()
        except OSError as e:
            left.append(f"{p}: {e.strerror}")
    with contextlib.suppress(FileNotFoundError):
        run.env_file.unlink()
    return left


# ---------- launch ------------------------------------------------------------


def unit_name(run: Run, suffix: str | None) -> str:
    return f"apex-eval-{run.run_id}" + (f"-{suffix}" if suffix else "")


def systemd_run_argv(
    run: Run, unit: str, argv: list[str], timeout: int, lock_skills: bool = True,
) -> list[str]:
    deny = " ".join(IP_DENY + public_ipv4())
    props = [
        f"EnvironmentFile={run.env_file}",
        f"WorkingDirectory={run.sandbox}",
        f"TemporaryFileSystem={RUNS_ROOT}",
        f"BindReadOnlyPaths={run.root}",
        "TemporaryFileSystem=/opt:ro",
        f"BindReadOnlyPaths={OPT_ROOT}",
        "InaccessiblePaths=" + " ".join(inaccessible_paths()),
        "ProtectSystem=strict",
        f"ReadWritePaths={run.home}",
        f"ReadWritePaths={run.sandbox}",
        "ProtectHome=tmpfs",
        "PrivateTmp=yes",
        "PrivateDevices=yes",
        # PrivateDevices keeps the host's /dev/shm; this makes it private
        # and, like a host /dev/shm, writable.
        "TemporaryFileSystem=/dev/shm:mode=1777",
        "NoNewPrivileges=yes",
        "UMask=0007",
        f"IPAddressAllow={resolver()}",
        f"IPAddressDeny={deny}",
        f"RuntimeMaxSec={timeout + RUNTIME_SLACK}",
    ]
    skills = run.home / ".claude" / "skills"
    if lock_skills and skills.is_dir():
        # The skill copy is read-only, and neither it nor .claude above it
        # can be renamed and replaced: a mount point cannot be renamed or
        # removed. The cleanup unit, which deletes the copy, goes without.
        props += [f"BindPaths={run.home / '.claude'}", f"BindReadOnlyPaths={skills}"]
    cmd = [
        "sudo", "-n", "systemd-run", f"--unit={unit}",
        f"--uid={EVAL_USER}", f"--gid={EVAL_USER}",
        "--pipe", "--wait", "--collect", "--quiet",
    ]
    for p in props:
        cmd += ["-p", p]
    return cmd + ["--", *argv]


def _active_units() -> list[str]:
    r = subprocess.run(
        ["systemctl", "list-units", "--state=active,activating,deactivating",
         "--no-legend", "--plain", "apex-eval-*"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise ConfinedError(f"systemctl list-units failed: {r.stderr.strip()[-200:]}")
    return [line.split()[0] for line in r.stdout.splitlines() if line.strip()]


def stop_unit(unit: str, wait: float = 30.0) -> None:
    """SIGKILL every process in the unit's cgroup, then wait until it is gone."""
    subprocess.run(
        ["sudo", "-n", "systemctl", "kill", "--signal=SIGKILL", f"{unit}.service"],
        capture_output=True,
    )
    end = time.time() + wait
    while time.time() < end:
        r = subprocess.run(
            ["systemctl", "is-active", f"{unit}.service"], capture_output=True, text=True
        )
        if r.stdout.strip() not in ("active", "activating", "deactivating", "reloading"):
            return
        time.sleep(0.5)
    raise ConfinedError(f"unit {unit} still active {wait:.0f}s after SIGKILL")


@contextlib.contextmanager
def launch_confined(
    run: Run,
    argv: list[str],
    policy_kind: str,
    timeout: int,
    unit_suffix: str | None = None,
    session_suffix: str | None = None,
    stderr=subprocess.PIPE,
    lock_skills: bool = True,
):
    """Start argv in a confined unit and yield the local systemd-run client
    (stdout is the unit's stdout). policy_kind "bedrock" mints a role session
    into the env file; "none" gives the unit no AWS keys. A caller that never
    reads stderr passes stderr=subprocess.DEVNULL, so the unit cannot block
    on a full pipe.

    On exit, whatever happened, the unit is killed if still running and
    waited on, the env file is deleted and the host lock is released. Callers
    may still call proc.kill() on a timeout: that stops only the local client.
    """
    if policy_kind not in ("bedrock", "none"):
        raise ConfinedError(f"unknown policy_kind {policy_kind!r}")
    unit = unit_name(run, unit_suffix)
    lock = os.open(LOCK_FILE, os.O_WRONLY | os.O_CREAT, 0o600)
    proc = None
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        leftover = _active_units()
        if leftover:
            raise ConfinedError(f"refusing to launch while units are active: {leftover}")
        creds = None
        if policy_kind == "bedrock":
            name = f"evals-{run.run_id}" + (f"-{session_suffix}" if session_suffix else "")
            creds = mint_role_session(name, timeout)
        write_env_file(run, creds)
        proc = subprocess.Popen(
            systemd_run_argv(run, unit, argv, timeout, lock_skills),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=stderr,
        )
        yield proc
    finally:
        try:
            if proc is not None:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
                stop_unit(unit)
        finally:
            with contextlib.suppress(FileNotFoundError):
                run.env_file.unlink()
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)


def claude_argv(args: list[str]) -> list[str]:
    """The claude command a unit runs: the root-owned copy, never the host's."""
    return [str(CLAUDE_BIN), *args]


# ---------- read-back ---------------------------------------------------------


def read_back(run: Run, dest: Path) -> list[str]:
    """Copy the unit's sandbox (minus .claude/) into dest without following
    links. Only after the unit has stopped: a read-back unit tars the
    sandbox (tar stores links as links), and the parent keeps only regular
    files and dirs with safe names. Returns what was dropped, for the log."""
    dest.mkdir(parents=True, exist_ok=True)
    with launch_confined(
        run,
        ["/usr/bin/tar", "-C", str(run.sandbox), "--exclude=./.claude", "-cf", "-", "."],
        policy_kind="none",
        timeout=SESSION_MIN,
        unit_suffix="readback",
    ) as proc:
        data, err = proc.communicate()
        if proc.returncode != 0:
            raise ConfinedError(f"read-back failed: {err.decode(errors='replace')[-300:]}")
    return extract_safe(data, dest)


def extract_safe(data: bytes, dest: Path) -> list[str]:
    dropped: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
        for m in tf:
            name = m.name
            parts = Path(name).parts
            if name.startswith("/") or ".." in parts:
                dropped.append(f"{name} (unsafe name)")
                continue
            rel = Path(*[p for p in parts if p != "."]) if parts else Path()
            if str(rel) in ("", "."):
                continue
            target = dest / rel
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif m.isreg():
                target.parent.mkdir(parents=True, exist_ok=True)
                f = tf.extractfile(m)
                target.write_bytes(f.read() if f else b"")
            else:
                kind = "link" if (m.issym() or m.islnk()) else "special file"
                dropped.append(f"{name} ({kind})")
    return dropped
