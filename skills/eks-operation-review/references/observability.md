# Observability

## Purpose
Assess observability across three layers: control plane, data plane (nodes), and workloads — covering metrics, logs, and alerting.

## Checks to Execute

### 4.1 — EKS Control Plane Logging

**What to check:**
- Which of the 5 log types are enabled (api, audit, authenticator, controllerManager, scheduler)
- CloudWatch log group existence and retention policy

**How to check:**
1. Describe cluster → `logging.clusterLogging` → check each entry for `enabled: true` and which `types`. If `eks:DescribeCluster` returns 403/Forbidden → mark the control-plane-logging signal UNKNOWN (do not rate RED "logging disabled" on a forbidden describe).
2. Use CloudWatch tools to check log group `/aws/eks/{cluster-name}/cluster` retention (the >= 30-day audit-log recommendation is a skill-defined heuristic, not an AWS-published requirement; no retention policy = logs kept forever at cost). If `logs:DescribeLogGroups` returns 403/Forbidden → mark the retention signal UNKNOWN (do not conclude "no retention policy defined"); a successful read with no `retentionInDays` means retention is genuinely undefined. Do NOT route an all-5-types-on + forbidden-retention case to UNKNOWN; per the 403 retention-signal rule in the Rating block, cap it at AMBER-with-note (logging confirmed enabled, retention unverifiable).

**Rating:**
- 🟢 GREEN: All 5 log types enabled with defined retention policy — AND both the log-type read (`eks:DescribeCluster`) and the retention read (`logs:DescribeLogGroups`) SUCCEEDED (an unverifiable retention signal cannot award GREEN — see 403 retention-signal rule)
- 🟡 AMBER: Audit enabled but not all 5 log types on, or all 5 types on but retention confirmed undefined (successful log-group read, no `retentionInDays`), or all 5 types on but the retention read returned 403 (logging confirmed enabled, retention unverifiable — see 403 retention-signal rule)
- 🔴 RED: Control plane logging completely disabled, or audit logs specifically disabled (confirmed via a *successful* `eks:DescribeCluster` — this RED survives a 403 on the retention read; see 403 retention-signal rule)
- ⬜ UNKNOWN: `eks:DescribeCluster` forbidden AND that forbidden read was the sole discriminator (log-type state unknowable and nothing else yields a color)
- **403 retention-signal rule:** a confirmed RED survives a 403 on a different read — a "logging disabled / audit disabled" RED observed via a *successful* `eks:DescribeCluster` stays RED even if the retention `logs:DescribeLogGroups` read returned 403 (CONFIRMED FLOOR); a 403 on a different signal never downgrades it to UNKNOWN. GREEN requires the retention policy *confirmed* via a successful log-group read, so an all-5-types-on + retention-403 case must NOT award a clean GREEN and must NOT route to UNKNOWN — cap it at AMBER with the note "logging enabled but retention could not be verified". Whole-check UNKNOWN only when `eks:DescribeCluster` was forbidden AND that was the sole discriminator (no successfully-read signal yields a color).
- **Evaluation order:** assess RED first (on successfully-read signals); if not RED, assess AMBER; otherwise GREEN. Keeps the bands exhaustive and non-overlapping.

**Key talking point:** EKS control plane logging is OFF by default. The audit log is your security camera for every API call.

---

### 4.2 — Metrics Collection & Dashboards

**What to check:**
- CloudWatch Container Insights add-on (`amazon-cloudwatch-observability`)
- Prometheus pods (labels: `app.kubernetes.io/name=prometheus` or `app=prometheus`)
- Grafana pods
- kube-state-metrics deployment (critical for cluster state visibility)
- node-exporter DaemonSet
- ADOT add-on
- Third-party monitoring DaemonSets (Datadog, New Relic, Dynatrace)

**How to check:**
1. Describe addon `amazon-cloudwatch-observability`. If `eks:DescribeAddon`/`eks:ListAddons` returns 403/Forbidden → mark the Container-Insights signal UNKNOWN (do not conclude the add-on is absent).
2. List pods with label `app.kubernetes.io/name=prometheus` across all namespaces
3. List pods with label `app.kubernetes.io/name=grafana`
4. List pods with label `app.kubernetes.io/name=kube-state-metrics`. For steps 2-4: Pod (core v1) is a core API so 404 is not expected; a 403/Forbidden on any of these pod lists → mark that signal UNKNOWN (do not conclude the component is absent); an empty successful list means none exist.
5. List DaemonSets across all namespaces (catches node-exporter and third-party agents). If 403/Forbidden → mark the metrics-collection signal UNKNOWN (do not conclude absent); DaemonSet (apps/v1) and Pod (core v1) are core APIs so 404 is not expected; an empty successful list means none exist. Do not rate RED for 'no metrics collection' on a forbidden list — route to UNKNOWN.

   **403 → RED guard (all reads):** the RED "no metrics collection at all" band is reachable only when every read above (steps 1-5) succeeded and returned nothing. If ANY of these reads was forbidden (403), RED is unreachable — route to UNKNOWN.

**Rating:**
- 🟢 GREEN: Metrics collection + kube-state-metrics + dashboards (Container Insights or Prometheus+Grafana or third-party) — AND every read (steps 1-5) that establishes a GREEN precondition SUCCEEDED (an unconfirmable good signal caps at AMBER-with-note, never GREEN — see 403 floor-and-cap rule)
- 🟡 AMBER: Partial stack (e.g., Container Insights but no kube-state-metrics, or Prometheus without Grafana), or a GREEN-worthy stack where one contributing read returned 403 (a confirmed good signal present but a different precondition unverifiable — see 403 floor-and-cap rule)
- 🔴 RED: No metrics collection at all — reachable ONLY when all reads (steps 1-5) succeeded and each returned nothing; if any read was forbidden, this RED is unreachable (route to UNKNOWN only per the floor-and-cap rule)
- ⬜ UNKNOWN: a metrics-source read (steps 1-5) was forbidden AND that forbidden read was the sole discriminator, so no successfully-read signal yields a color — do NOT rate RED, and do NOT downgrade a signal that a *successful* read already colored
- **403 floor-and-cap rule:** a confirmed AMBER survives a 403 on a different read — e.g. Container Insights confirmed present (successful step 1) + kube-state-metrics confirmed absent (successful step 4) is a CONFIRMED AMBER and STAYS AMBER even if the DaemonSet list (step 5) returned 403; the 403 only marks its own signal (node-exporter/third-party agents) UNKNOWN and never downgrades the confirmed AMBER (CONFIRMED FLOOR). Still evaluate successfully-read signals RED-first then AMBER. GREEN requires all preconditions confirmed by successful reads, so a 403 on a GREEN-contributing read caps at AMBER-with-note ("...could not verify X") when other signals are GREEN-worthy — never GREEN. Whole-check UNKNOWN only when the 403 was the sole discriminator (no successfully-read signal yields a color).
- **Evaluation order:** assess RED first (on successfully-read signals); if not RED, assess AMBER; otherwise GREEN. Keeps the bands exhaustive and non-overlapping.

**Investigate manually:** Whether dashboards are actively used (viewership) is not observable via API — a present dashboard resource does not prove it is watched; suggest the user confirm.

---

### 4.3 — Centralized Log Aggregation for Workloads

**What to check:**
- Fluent Bit DaemonSet (labels: `app.kubernetes.io/name=fluent-bit` or `k8s-app=fluent-bit`)
- Fluentd DaemonSet
- CloudWatch agent DaemonSet in `amazon-cloudwatch` namespace
- Application log groups in CloudWatch

**How to check:**
1. List DaemonSets with Fluent Bit labels across all namespaces. If 403/Forbidden → mark the log-collection signal UNKNOWN (do not conclude absent); DaemonSet (apps/v1) and Pod (core v1) are core APIs so 404 is not expected; an empty successful list means none exist. Do not rate RED for 'no centralized log collection' on a forbidden list — route to UNKNOWN.
2. List DaemonSets in `amazon-cloudwatch` namespace
3. Use CloudWatch tools to check for **application/workload** log groups under `/aws/containerinsights/{cluster-name}/…` (specifically the `application`, `host`, and `dataplane` groups). Note: `/aws/eks/{cluster-name}/cluster` is the CONTROL-PLANE log group, not workload logs — do not use it to assess application logging. If `logs:DescribeLogGroups` returns 403/Forbidden → mark the retention signal UNKNOWN (do not conclude "no retention policy"); a successful read with no `retentionInDays` means retention is genuinely undefined. Do NOT route a shipper-present + forbidden-retention case to UNKNOWN; per the 403 retention-signal rule in the Rating block, cap it at AMBER-with-note (shipper confirmed present, retention unverifiable).

**Rating:**
- 🟢 GREEN: Log shipper deployed, logs centralized with retention policy — AND both the shipper DaemonSet read (step 1) and the retention read (step 3) SUCCEEDED (an unverifiable retention signal cannot award GREEN — see 403 retention-signal rule)
- 🟡 AMBER: Log shipper exists but retention confirmed absent (successful log-group read, no `retentionInDays`), or log shipper confirmed present but the retention read returned 403 (shipper confirmed present, retention unverifiable — see 403 retention-signal rule)
- 🔴 RED: No centralized log collection — teams rely on kubectl logs (confirmed via a *successful* DaemonSet list returning no shipper — this RED survives a 403 on the retention read; see 403 retention-signal rule)
- ⬜ UNKNOWN: the DaemonSet list (step 1) returned 403/Forbidden AND that forbidden read was the sole discriminator (shipper presence unknowable and nothing else yields a color)
- **403 retention-signal rule:** a confirmed RED survives a 403 on a different read — a "no centralized log collection" RED observed via a *successful* DaemonSet list (step 1) returning no shipper stays RED even if the retention `logs:DescribeLogGroups` read (step 3) returned 403 (CONFIRMED FLOOR); a 403 on a different signal never downgrades it to UNKNOWN. GREEN requires the retention policy *confirmed* via a successful log-group read, so a shipper-present + retention-403 case must NOT award a clean GREEN and must NOT route to UNKNOWN — cap it at AMBER with the note "log shipping enabled but retention could not be verified". Whole-check UNKNOWN only when the DaemonSet list was forbidden AND that was the sole discriminator (no successfully-read signal yields a color).
- **Evaluation order:** assess RED first (on successfully-read signals); if not RED, assess AMBER; otherwise GREEN. Keeps the bands exhaustive and non-overlapping.

**Investigate manually:** Log format (structured vs unstructured logging) — not observable via API; requires sampling actual log records.

---

### 4.4 — Alerting Defined and Actionable

**What to check:**
- CloudWatch Alarms related to EKS/ContainerInsights
- Prometheus Alertmanager pods
- PrometheusRule resources (alert definitions)

**How to check:**
1. List pods with label `app.kubernetes.io/name=alertmanager`. If 403/Forbidden → mark the alerting signal UNKNOWN (do not conclude absent); Pod (core v1) is a core API so 404 is not expected; an empty successful list means none exist. Do not rate RED for 'no alerting configured' on a forbidden list — route to UNKNOWN. Note alerting can also be satisfied by CloudWatch alarms (step 3): a 403 on this k8s alertmanager list must not RED if CloudWatch alarms are present or the alarm read itself failed.
2. List PrometheusRule resources. If 404/NotFound (CRD not installed) → Prometheus Operator not deployed, rate alerting based on CloudWatch only. If 403/Forbidden → mark UNKNOWN.
3. Use CloudWatch tools to list alarms with ContainerInsights namespace. If `cloudwatch:DescribeAlarms` returns 403/Forbidden → mark the CloudWatch-alerting signal UNKNOWN (do not conclude "no CloudWatch alarms"); a successful read returning zero alarms means none exist. Do not rate RED "no alerting configured" when this alarm read was forbidden — route to UNKNOWN, since CloudWatch alarms may exist and be unreadable.

**Rating:**
- 🟢 GREEN: Alerts cover critical scenarios (node, pod, capacity) — AND every alerting-source read (steps 1-3) that establishes a GREEN precondition SUCCEEDED (an unconfirmable good signal caps at AMBER-with-note, never GREEN — see 403 floor-and-cap rule)
- 🟡 AMBER: Some alerts exist but incomplete coverage, or a GREEN-worthy alerting posture where one contributing read returned 403 (a confirmed good signal present but a different precondition unverifiable — see 403 floor-and-cap rule)
- 🔴 RED: No alerting configured — reachable ONLY when all three reads succeeded and each was conclusively empty: alertmanager pod list succeeded and returned zero pods, PrometheusRule returned 404 (CRD absent) or succeeded with zero rules, AND `cloudwatch:DescribeAlarms` succeeded and returned zero alarms. If any of these reads was forbidden (403), this RED is unreachable (route to UNKNOWN only per the floor-and-cap rule).
- ⬜ UNKNOWN: an alerting-source read was forbidden — alertmanager list 403 (step 1), PrometheusRule 403 (step 2), or `cloudwatch:DescribeAlarms` 403 (step 3) — AND that forbidden read was the sole discriminator, so no successfully-read signal yields a color; do NOT rate RED, and do NOT downgrade a signal that a *successful* read already colored
- **403 floor-and-cap rule:** a confirmed AMBER survives a 403 on a different read — e.g. CloudWatch alarms confirmed present with incomplete coverage (successful step 3) is a CONFIRMED AMBER and STAYS AMBER even if the PrometheusRule read (step 2) returned 403; the 403 only marks its own signal (Prometheus alert rules) UNKNOWN and never downgrades the confirmed AMBER (CONFIRMED FLOOR). Still evaluate successfully-read signals RED-first then AMBER. GREEN requires all preconditions confirmed by successful reads, so a 403 on a GREEN-contributing read caps at AMBER-with-note ("...could not verify X") when other signals are GREEN-worthy — never GREEN. Whole-check UNKNOWN only when the 403 was the sole discriminator (no successfully-read signal yields a color).
- **Evaluation order:** assess RED first (on successfully-read signals); if not RED, assess AMBER; otherwise GREEN. Keeps the bands exhaustive and non-overlapping.

**Investigate manually:** Runbooks linked to alerts, and whether on-call actually monitors the alerts — neither is observable via `cloudwatch:DescribeAlarms` or cluster state; requires reviewing alert/notification configuration and on-call process directly.

**Minimum viable alert set:** NodeNotReady, PodCrashLooping, PodPendingTooLong, HighAPIServerLatency, IPExhaustion.
