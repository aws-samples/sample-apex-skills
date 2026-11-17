#!/usr/bin/env bash
# One-time host setup for the confined eval launches (misc/evals/scripts/confined.py).
# Run it yourself, as root, from a normal shell; the eval runners never run it:
#
#   sudo bash misc/evals/setup/install-eval-boundary.sh                 install
#   sudo bash misc/evals/setup/install-eval-boundary.sh --refresh-bin   re-copy claude after an upgrade
#   sudo bash misc/evals/setup/install-eval-boundary.sh --uninstall     undo the install
#
# Install does exactly three things:
#   1. Adds the system user and group apex-eval: no login shell, no home
#      directory, no sudo, no other groups.
#   2. Adds /var/lib/apex-eval (root, 0755) with runs/ (<you>:apex-eval,
#      2770: the run roots) and env/ (<you>, 0700: each launch's env file).
#   3. Copies your claude binary to /opt/apex-eval/bin/claude (root, 0755), so
#      a unit can run it while /home is hidden.
# <you> is the user who ran sudo (SUDO_USER). Pass --claude <path> to copy a
# different binary (default: the target of ~<you>/.local/bin/claude).
#
# It adds no firewall rule (each unit gets its own IP filter at launch) and
# installs no package. The runners need passwordless `sudo -n true` (their
# start check), `sudo -n systemd-run` and `sudo -n systemctl kill` for <you>;
# this script does not grant that. An existing apex-eval user is reused only
# when its only group is apex-eval and its shell is nologin or false;
# --uninstall removes the user only if this script created it.
set -euo pipefail

EVAL_USER=apex-eval
STATE_ROOT=/var/lib/apex-eval
OPT_ROOT=/opt/apex-eval
CREATED_MARK="${STATE_ROOT}/.user-created-by-install"

log() { printf '[install-eval-boundary] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

mode=install
claude_src=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --uninstall) mode=uninstall ;;
    --refresh-bin) mode=refresh ;;
    --claude) [[ $# -ge 2 ]] || die "--claude needs a path"; claude_src="$2"; shift ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
  shift
done

[[ "$(id -u)" -eq 0 ]] || die "run as root (sudo bash $0)"
owner="${SUDO_USER:-}"
[[ -n "${owner}" && "${owner}" != root ]] || die "run through sudo from the user who runs the evals"
owner_home="$(getent passwd "${owner}" | cut -d: -f6)"
[[ -n "${owner_home}" ]] || die "cannot read the home of ${owner}"

copy_claude() {
  local src="${claude_src:-$(readlink -f "${owner_home}/.local/bin/claude" || true)}"
  [[ -n "${src}" && -f "${src}" ]] || die "claude binary not found; pass --claude <path>"
  install -D -o root -g root -m 0755 "${src}" "${OPT_ROOT}/bin/claude"
  log "copied ${src} to ${OPT_ROOT}/bin/claude ($("${OPT_ROOT}/bin/claude" --version 2>/dev/null || echo 'version unreadable'))"
}

case "${mode}" in
  uninstall)
    if [[ -f "${CREATED_MARK}" ]]; then
      if id "${EVAL_USER}" >/dev/null 2>&1; then
        userdel "${EVAL_USER}"
        log "removed user ${EVAL_USER}"
      fi
      if getent group "${EVAL_USER}" >/dev/null; then groupdel "${EVAL_USER}"; fi
    else
      log "kept user ${EVAL_USER}: this script did not create it"
    fi
    rm -rf "${STATE_ROOT}" "${OPT_ROOT}"
    log "removed ${STATE_ROOT} and ${OPT_ROOT}"
    ;;
  refresh)
    [[ -d "${OPT_ROOT}/bin" ]] || die "not installed; run without --refresh-bin first"
    copy_claude
    ;;
  install)
    command -v systemd-run >/dev/null || die "systemd-run not found"
    # 1. The user the units run as. STATE_ROOT comes first, so the marker is
    # written the moment the user exists.
    if ! id "${EVAL_USER}" >/dev/null 2>&1; then
      install -d -o root -g root -m 0755 "${STATE_ROOT}"
      useradd --system --user-group --home-dir "${STATE_ROOT}" --no-create-home \
        --shell /sbin/nologin "${EVAL_USER}"
      install -o root -g root -m 0644 /dev/null "${CREATED_MARK}"
      log "added system user ${EVAL_USER}"
    elif [[ "$(id -nG "${EVAL_USER}")" != "${EVAL_USER}" ]]; then
      # systemd gives a unit every group of its user.
      die "user ${EVAL_USER} exists with groups '$(id -nG "${EVAL_USER}")'; only ${EVAL_USER} is allowed"
    else
      shell="$(getent passwd "${EVAL_USER}" | cut -d: -f7)"
      case "${shell}" in
        */nologin|*/false) ;;
        *) die "user ${EVAL_USER} exists with login shell '${shell}'; only nologin or false is allowed" ;;
      esac
    fi
    if id -nG "${owner}" | tr ' ' '\n' | grep -qx "${EVAL_USER}"; then
      die "${owner} is in group ${EVAL_USER}; remove it (it could then read unit files)"
    fi
    # 2. Run and env directories.
    install -d -o root -g root -m 0755 "${STATE_ROOT}"
    install -d -o "${owner}" -g "${EVAL_USER}" -m 2770 "${STATE_ROOT}/runs"
    install -d -o "${owner}" -g "$(id -gn "${owner}")" -m 0700 "${STATE_ROOT}/env"
    log "made ${STATE_ROOT}/runs (2770) and ${STATE_ROOT}/env (0700)"
    # 3. A root-owned claude the units can run.
    copy_claude
    log "done. undo with: sudo bash $0 --uninstall"
    ;;
esac
