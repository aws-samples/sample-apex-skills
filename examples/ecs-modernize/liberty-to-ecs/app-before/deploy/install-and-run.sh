#!/usr/bin/env bash
# =============================================================================
# Legacy host deployment procedure for the Orders application.
#
# This is the script the operations team runs on the VM today. It is included in
# the exercise as evidence, NOT as something you should run.
#
# PLANTED BLOCKERS:
#
#  1. (process_model) The deployment expects a host init system: it registers
#     and starts a systemd unit, and relies on the HOST to supervise the server
#     process. A container supervises exactly one process tree of its own.
#
#  2. (process_model) A cron entry on the host runs the nightly settlement
#     batch — a scheduled job registered outside the application process.
#
#  3. (build_reproducibility) Deployment is a documented manual host procedure
#     (copy a WAR into a server directory, edit config in place, restart the
#     host service) rather than a repeatable, artifact-driven deploy.
# =============================================================================
set -euo pipefail

WLP_HOME=/opt/was/wlp
SERVER_NAME=ordersServer

echo "==> installing WAR into the server's dropins"
cp target/orders.war "${WLP_HOME}/usr/servers/${SERVER_NAME}/dropins/"

echo "==> patching server config in place (manual step, per runbook section 4.2)"
# The runbook instructs the operator to hand-edit the datasource host here for
# the target environment. This is why the same artifact cannot move between
# environments unchanged.
vi "${WLP_HOME}/usr/servers/${SERVER_NAME}/server.xml"

echo "==> registering the host service"
# PLANTED: host init-system dependence.
cat >/etc/systemd/system/orders.service <<UNIT
[Unit]
Description=Orders Liberty server
After=network.target

[Service]
Type=forking
ExecStart=${WLP_HOME}/bin/server start ${SERVER_NAME}
ExecStop=${WLP_HOME}/bin/server stop ${SERVER_NAME}
Restart=always
User=was

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now orders.service

echo "==> registering the nightly settlement cron job"
# PLANTED: host scheduler dependence, outside the application process.
cat >/etc/cron.d/orders-settlement <<'CRON'
15 2 * * * was /opt/was/orders/bin/run-settlement.sh >>/var/log/orders/settlement.log 2>&1
CRON

echo "done — verify with: systemctl status orders.service"
