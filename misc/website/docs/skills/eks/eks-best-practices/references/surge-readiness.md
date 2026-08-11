---
title: "Surge Readiness — Planned Traffic Peaks & Flash Events"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-best-practices/references/surge-readiness.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-best-practices/references/surge-readiness.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-best-practices/references/surge-readiness.md). Edit the source, not this page.
:::

# Surge Readiness — Planned Traffic Peaks & Flash Events

> **Part of:** [eks-best-practices](../)
> **Purpose:** Prepare an Amazon EKS cluster for a known, high-slope traffic peak — a flash sale, marketing push, product launch, or seasonal peak event. Covers spike *shape* (not just magnitude), scheduled pre-scaling, capacity assurance, load-test realism, graceful degradation, and a descriptive pre-event readiness checklist. This is an **advisory, planning-time** guide: it describes what to test and what "ready" looks like — it does not compute sizing verdicts, headroom numbers, or a max absorbable step for you.

---

## Table of Contents

1. [Read the Spike Shape, Not Just the Magnitude](#read-the-spike-shape-not-just-the-magnitude)
2. [Scheduled Pre-Scaling for Known Events](#scheduled-pre-scaling-for-known-events)
3. [Capacity Assurance Before the Event](#capacity-assurance-before-the-event)
4. [Load-Test Realism](#load-test-realism)
5. [Graceful Degradation & Load Shedding](#graceful-degradation--load-shedding)
6. [Pre-Event Readiness Checklist](#pre-event-readiness-checklist)
7. [During and After the Event](#during-and-after-the-event)
8. [Related Guidance](#related-guidance)

---

## Read the Spike Shape, Not Just the Magnitude

A planned peak driven by an outbound trigger (a push notification, an email blast, a countdown timer) does not ramp — it arrives as a near-instantaneous **step** to many multiples of baseline at a fixed clock time. Planning only for the peak *magnitude* misses the problem: it is the **rate of arrival** that breaks systems that could comfortably serve the same load if it had ramped over minutes.

Separate the three layers that each react at a different speed — none of them is instant, and they are not interchangeable:

| Layer | What it governs | Why it is not instant |
|---|---|---|
| **Control-plane scale-out** | API server / etcd capacity for the churn of a mass scale-up | Auto-scales but is rate-limited; large step changes need lead time (see [scalability.md — Control Plane Scaling](scalability#control-plane-scaling)) |
| **Node provisioning** | New EC2 capacity for pending pods | Node launch is not pod-ready time; a launched instance still has to join, pull images, and pass readiness |
| **Pod / HPA reaction** | Replica count responding to a metric | Metric-driven scaling reacts *after* load is already arriving — a lagging signal for a step function |

> **Do not build step math on node scale-up latency.** The "~30s" figure in [autoscaling.md](autoscaling) is *instance provisioning* speed, not application-ready speed, and there is no published "maximum absorbable step" for EKS. Treat all three layers as things to **pre-warm ahead of time**, not to rely on reacting in the moment.

**Plan for multiple peaks, not one curve.** A single event is usually a sequence — a pre-event build-up, a primary peak, and secondary peaks as later triggers fire — with many smaller push-driven micro-spikes across the window. The classic, purely-advisory failure mode is **scaling down (or consolidating) in the trough between peaks** and then getting caught cold by the next spike. Hold your scaled-up floor for the whole event window rather than chasing each trough.

---

## Scheduled Pre-Scaling for Known Events

The defining property of a planned peak is that **you know when it will happen**. That changes the autoscaling decision from reactive to proactive.

**Decision axis — match the mechanism to what you know:**

| You know… | Use | Notes |
|---|---|---|
| **The clock time** (sale start, launch) | Scheduled floors — raise `minReplicas` / desired counts on a schedule *ahead* of the trigger | KEDA's Cron scaler scales within a defined **time window** (`start`/`end` cron), not as a one-shot alarm — it holds the floor for the window then releases it. See [KEDA Cron scaler](https://keda.sh/docs/2.20/scalers/cron/). |
| **Only that demand will rise** (organic, unpredictable timing) | Metric / event-driven autoscaling (HPA on custom metrics, KEDA on queue depth) | Reactive by nature — a top-up layer, not the primary defense for a step function |

Best practice for a known event is to **set scheduled floors and keep reactive autoscaling as a top-up**, not the other way around. Pre-scaling pods, warming node capacity, and raising control-plane readiness *before* the trigger fires is exactly the case AWS documents for [EKS Provisioned Control Plane — "Anticipated high-demand events"](https://docs.aws.amazon.com/eks/latest/userguide/eks-provisioned-control-plane.html): provisioning control-plane capacity in advance of an expected surge rather than waiting for auto-scaling to react.

Mechanics already covered in this skill — link, do not re-invent:

- **Overprovisioning with low-priority pause pods** to hold warm headroom for a fast scale-up: [autoscaling.md — Overprovisioning](autoscaling#overprovisioning).
- **MNG warm pools** (pre-initialized instances) to cut cold-launch latency: [autoscaling.md](autoscaling) and the [Autoscaler Selection note in SKILL.md](../#autoscaling-quick-reference).
- **Karpenter disruption budgets** to *freeze* node disruption during the event window (a `nodes: "0"` scheduled budget) so consolidation does not fight your pre-scaled floor: [karpenter.md — Disruption Budgets](karpenter#disruption-budgets).

For hands-on engineering support around a critical event, AWS's event-support offering is [AWS Countdown Premium](https://aws.amazon.com/premiumsupport/countdown-premium/).

---

## Capacity Assurance Before the Event

Pre-scaling only works if the underlying capacity is actually available. "How fast does Karpenter react?" is a different question from "**can EC2 give me the nodes at all** when the event starts?" — and the second is answered days ahead, not in the moment.

- **Service-quota pre-checks.** Confirm headroom on the account limits a mass scale-up consumes: vCPU quotas per instance family, Elastic IPs and ENIs, ALB/target-group and LCU limits, and ECR image-pull throughput. These are Well-Architected REL01 prior art; a scale-up that hits a soft quota fails silently as pending pods. (IP-address headroom has its own strategies — [networking.md — IP Exhaustion Strategies](networking#ip-exhaustion-strategies).)
- **EC2 capacity assurance via ODCR.** For a fixed-time peak, an On-Demand Capacity Reservation guarantees the instances exist. Karpenter (v1) can prioritize reserved capacity via `capacityReservationSelectorTerms` on the EC2NodeClass, falling back to on-demand/spot after the reservation is consumed — see [Karpenter NodeClasses](https://karpenter.sh/docs/concepts/nodeclasses/) (feature is in Beta; verify its state for your Karpenter version).
- **Load-balancer warm-up.** Load balancers themselves need to scale into a step of new connections; the AWS Best Practices Guide explicitly names [warming load balancers](https://docs.aws.amazon.com/eks/latest/best-practices/scale-control-plane.html) as part of making infrastructure fully ready for a large scale-up. Pre-scaling pods and nodes without warming the ingress path leaves a gap at the front door.

---

## Load-Test Realism

A load test is only as good as the scenarios it exercises — and a test that passes can still miss the failure that hits production.

**Tell both halves of the story.** A realistic load test earns its keep: it will surface real bottlenecks (rate limits set for business-as-usual traffic, CPU throttling from tight `requests == limits`, connection-pool saturation) *before* the event. But a test that replays **request volume** without reproducing the **resource-consumption pattern** of a workload can hit its throughput target and still miss a memory-pressure failure — because the harness never exercised the access pattern that drives memory growth. "Reached the target RPS" is not the same as "passed": a stretch target can be reached while real issues go unaddressed.

**The lesson is scenario coverage, not test volume.** New features and changed access patterns introduce consumption shapes the old test plan never modeled. Keep load-test scenarios tracking feature and access-pattern changes, exercise resource-consumption shapes (memory, connections, cache working-set) and not just request rates, and **act on the findings before the event** — a caught issue that ships unfixed is indistinguishable from one never found. This is Well-Architected [REL12-BP03 — test scaling and performance](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_testing_resiliency_test_non_functional.html), whose anti-patterns call out "unrealistic or insufficient load scenarios" and failing to "test for peak loads, sudden spikes."

**Rehearse recovery, not just load.** A game day is distinct from a load test: it rehearses the *response* — who does what, which levers get pulled, and how long recovery actually takes for each component — in a production-like environment before the real event. See Well-Architected [REL12-BP05 — conduct game days regularly](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_testing_resiliency_game_days_resiliency.html). For chaos/fault-injection mechanics, see [reliability-advanced.md — Chaos Engineering with AWS FIS](reliability-advanced#chaos-engineering-with-aws-fis); for the component recovery mechanisms themselves, see [reliability-advanced.md — Recovery Scenarios](reliability-advanced#recovery-scenarios).

---

## Graceful Degradation & Load Shedding

Not every surge can be fully absorbed, and the goal under overload is to stay *up in a degraded form* rather than fail hard. Decide in advance **what you turn off** so the core path survives:

- Feature flags to disable non-essential features (recommendations, personalization, heavy analytics) under load.
- Load shedding / prioritization at the edge so the revenue path is served before best-effort traffic.
- Circuit breakers and degraded responses on shared dependencies rather than failing readiness cluster-wide (a shared-dependency readiness failure removes *all* endpoints at once — see [reliability-core.md — Probe Anti-Patterns](reliability-core#probe-anti-patterns)).

Rehearse these levers in the game day so the team knows which flag to pull and what the degraded experience looks like.

---

## Pre-Event Readiness Checklist

Descriptive — **what "ready" looks like before a surge event.** This is a planning aid, not a scored audit: there are no pass/fail gates, no colour ratings, and no recovery-time targets here (for a live operational assessment with ratings, that is [eks-operation-review](../../eks-operation-review/)'s lane; for upgrade readiness, [eks-upgrade-check](../../eks-upgrade-check/)).

- [ ] **Scheduled floors** set to pre-scale pods ahead of each known trigger, holding across the whole event window (not per-trough).
- [ ] **Reactive autoscaling** configured as a top-up layer on top of the floor.
- [ ] **Node capacity pre-warmed** — pause-pod overprovisioning and/or MNG warm pools sized for the step.
- [ ] **Capacity guaranteed** — ODCR (or equivalent) in place for fixed-time peaks; Karpenter set to prefer it.
- [ ] **Service quotas checked** — vCPU, EIP/ENI, ALB/LCU, ECR pull rate all have headroom for the scaled-up state.
- [ ] **Ingress path warmed** — load balancers pre-scaled, not just pods and nodes.
- [ ] **Consolidation / disruption frozen** for the event window (Karpenter scheduled budget) so scale-in does not fight the floor.
- [ ] **Deploy / change freeze** window spanning from before through after the event — no risky rollouts mid-peak.
- [ ] **Rate limits audited against event traffic**, not business-as-usual — a limit sized for BAU will trip under the peak (and your own load test should have surfaced it).
- [ ] **Graceful-degradation levers identified** and their triggers documented.
- [ ] **Load test exercised the event's access patterns** (consumption shapes, new features) and its findings were acted on.
- [ ] **Game day rehearsed** the response and measured each component's own recovery time.
- [ ] **Control-plane readiness** considered for large clusters (see [Related Guidance](#related-guidance) for the etcd/PCP signals).
- [ ] **Scale-down sequencing** planned — the order in which floors are released after the event (see below).

The generic event-readiness skeleton (comms plan, roles, runbook) is Operational-Readiness-Review and AWS Countdown territory — link to those; the items above are the EKS-specific deltas.

---

## During and After the Event

- **Hold the floor** across the full window; resist consolidating or scaling down in troughs between peaks.
- **Scale down in sequence, not all at once**, after traffic has durably subsided — release reactive layers first, then the scheduled floors, then lift the disruption freeze so Karpenter can consolidate the now-idle capacity.
- **Reduce etcd churn from the scale-up** — a large, short-lived burst of objects (Jobs, Pods, Events) leaves the control plane with cleanup to do; confirm TTLs and finalizers are set so the object count returns to baseline (see [scalability.md — Control Plane Scaling](scalability#control-plane-scaling)).
- **Run a retro.** Capture what actually happened versus the plan — where the spike shape differed, which lever fired, what the load test missed — and feed it back into the next event's scenarios. This is the same act-on-findings discipline as the load test itself.

---

## Related Guidance

Every mechanic referenced here is documented in depth elsewhere in this skill — this doc is the surge-readiness orchestrator, not a restatement:

- **In-cluster stateful cache sizing & blast radius** (a right-sized memory ceiling, managed off-ramp, failure-domain isolation): [reliability-core.md](reliability-core) and [reliability-advanced.md](reliability-advanced).
- **Control-plane / etcd scaling signals under load** (size cap, PCP, growth-rate alerting, correlated LIST + etcd attribution): [scalability.md — Control Plane Scaling](scalability#control-plane-scaling) and [observability.md — API vs etcd Latency](observability#api-vs-etcd-latency).
- **Autoscaling mechanics** (overprovisioning, warm pools, HPA/KEDA): [autoscaling.md](autoscaling).
- **Karpenter disruption control**: [karpenter.md — Disruption Budgets](karpenter#disruption-budgets).
- **Recovery mechanisms and chaos testing**: [reliability-advanced.md](reliability-advanced).
- **IP-address headroom**: [networking.md — IP Exhaustion Strategies](networking#ip-exhaustion-strategies).

**Sources:**

- [Amazon EKS Provisioned Control Plane](https://docs.aws.amazon.com/eks/latest/userguide/eks-provisioned-control-plane.html)
- [AWS Well-Architected — REL12-BP03 Test scaling and performance requirements](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_testing_resiliency_test_non_functional.html)
- [AWS Well-Architected — REL12-BP05 Conduct game days regularly](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_testing_resiliency_game_days_resiliency.html)
- [KEDA Cron scaler](https://keda.sh/docs/2.20/scalers/cron/)
- [Karpenter NodeClasses — Capacity Reservation Selector Terms](https://karpenter.sh/docs/concepts/nodeclasses/)
- [AWS EKS Best Practices Guide — Kubernetes Control Plane (load-balancer warming)](https://docs.aws.amazon.com/eks/latest/best-practices/scale-control-plane.html)
- [AWS Countdown Premium](https://aws.amazon.com/premiumsupport/countdown-premium/)
