# Severity Rationale (score weighting)

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**This file is the single source of truth for which tier each question is in — the tables below are read
as data, not just by people.** `assets/reduce.sh` parses them on every run and weights the published
score with what it finds; `assets/render-report.py` takes the same parsed map back out of `scores.json`,
so the Severity column and the Immediate/Short-term/Strategic ordering in the report are the weights the
score was computed from. Neither file carries its own copy of the tiers. Move a question to a
different table here and the score changes; there is nothing else to edit, and nothing else to keep in
step. (What this file does *not* own is what a tier is *worth*: `High = 3 / Medium = 2 / Low = 1` is a
constant that also appears in `reduce.sh`'s parser, in `render-report.py`'s weight validator, and in
prose here and in SKILL.md. Four copies, nothing enforcing they agree. Changing one changes every score.)

**The rule that decides a weight, in one sentence:** a data row's tier is the tier of the nearest
preceding `### High` / `### Medium` / `### Low` heading. So **any** edit that changes which heading is
nearest to a row changes that question's weight — retyping a heading, deleting one, inserting one, or
moving the row. That is the whole mechanism, and it is why the table shape below is load-bearing rather
than cosmetic.

`reduce.sh` refuses with a `reduce.sh:` message and exit 1, never a default weight, when any of these
six rules is broken. **Every refusal names a line number**, and none asserts an edit the parser holds no
evidence for. Quoting the line is a narrower promise and is stated narrowly, because it is easy to
over-claim: a refusal quotes the line when the line's *text* is the evidence — a row that
lost its leading `|`, an indented row, an unreadable ID cell, a heading this parser would not accept. Four
refusals inside rules 1–4 name a line and deliberately quote nothing, because the text is not what is wrong
with it: an **empty first cell**, a **delimiter row whose cell count does not match its header**, a **tier
heading owning no data rows**, and a **blank line splitting a table** (quoting a blank line prints nothing,
which reads as a parser bug rather than as evidence). Where a quoted line contains characters a terminal
does not display, the message says so and gives the byte offset, because a quote that *looks* correct is
worse than no quote. Five characters are named (tab, no-break space, zero-width space, form feed, vertical
tab) and **everything else is caught by a byte-level fallback** that reports the first byte outside printable
ASCII with its octal value while saying plainly that it cannot name the character. That fallback exists
because five names are not a complete list: U+FEFF, U+200E, U+200F, U+2060, U+00AD and
about fourteen other space-like characters all print as nothing or as a space, and one of them made
`| sec-2<U+FEFF> |` print a quoted token character-for-character identical to the required shape. The
fallback is **not** a completeness claim either — it cannot tell you which character a multibyte sequence
encodes. The
refusals about the file or the id set have no single line at all: a missing or unreadable file, an id with
two rows, a question with no row, and a row for a retired id.

1. **A row's first cell is the only one read.** It must be a question id (`sec-12`), a ` / `-separated
   list of ids sharing one rationale (`sec-27 / sec-28`), or a contiguous range (`fargate-1..2`). An id
   named in a *rationale* rather than in a first cell is prose, not a weight — `net-4`'s row mentions
   `sec-31` and does not thereby give it one.
2. **Each tier heading owns exactly one well-formed table**: an `| ID | … |` header row, a `|----|`
   separator, then at least one data row. The tier ends where that table ends. This is what makes the
   three structural accidents loud instead of silent — **deleting** a `### Medium` line does not promote
   its table to High (the orphaned rows belong to no tier), **inserting** a tier heading into the middle
   of a table is refused (the rows below it would have no header row of their own), and inserting one
   just above another table's header is refused too (the heading above would own no rows). Splitting a
   table with **any** line that does not begin with `|` orphans everything after the break the same way,
   and the refusal reports **the line it read** rather than guessing which kind of line it was. The examples
   are examples, **not a closed list** — members outside any short list of them are easy to
   construct: a blank line, a code fence, a row that lost its leading pipe, a
   line indented four or more columns, and a bare form feed, vertical tab, no-break space or zero-width
   space. An **HTML comment** belongs on the list only with a caveat: `<!-- note -->` does *not* orphan the
   rows below it in every renderer — one that escapes raw HTML renders it as an extra table row, while one
   that passes raw HTML through drops the rows. This parser ends the tier either way. A blank line or a
   sentence *between* a heading and its table is fine.
3. **This file may contain no other markdown table.** Any `|`-delimited table that is not a severity
   table is refused — inside a tier because its cells are not question ids or it is a second table under
   one heading, outside a tier because its rows belong to none. That holds even for a header-only table
   whose first column happens to be called `ID`. **Do not put a table, or a tier heading, inside a fenced
   code block** — but the two placements fail by *different* mechanisms, and it is easy to assume
   the first one for both. A fence that **interrupts** a tier table ends the tier at the
   fence line, and the rows after it are refused as belonging to none. A fence that carries its **own**
   `### Low` heading and its own table raises nothing at parse time: the fenced heading opens a tier and
   the fenced id becomes a real weight (measured: 133 rows parsed instead of 132, zero parse complaints).
   **An UNTERMINATED fence is refused outright, before anything is parsed**, and this is the one refusal in
   the file that exists purely to protect the *reader's* view: an unclosed `` ``` `` before the tables renders
   the whole document as **0 tables / 0 rows** in a CommonMark/GFM renderer, while the parser publishes
   a full and correct weight map. The refusal reports how many table lines follow the fence, and states that
   count as a **ceiling**: the scan does not model HTML blocks or link-reference definitions, and a fence
   inside one of those is inert to some renderers — inside an `<!-- -->` comment a renderer that passes raw
   HTML through leaves the document unaffected, and inside a multi-line link-reference-definition title some
   renderers do too. If either is the case, take the fence out of the construct rather than
   closing it. The reducer tracks fence **state**, not a count — counting
   openers and refusing an odd total would let three two-keystroke forms walk straight through, because a fence
   closes only with the **same character**, a run **at least as long**, and **no info string** on the closer.
   So `` ``` `` does not close `~~~`, `` ``` `` does not close ```` ```` ````, and `` ```bash `` closes
   nothing. A *terminated* fence is a different problem, and it is the one described next.
   It is caught two gates later, by the staleness gate, only because that id is a question nothing emits.
   A fenced id that *is* a live question is **not** silent on its own: the real row is still there, so the
   fenced one is a second row for that id and the duplicate-id gate refuses it by name. It goes silent only
   if the real row is deleted **as well** — and then it moves the score (measured: a fenced `### Low` table
   carrying `| sec-21 |` with the real High row removed gives exit 0 and a changed overall, the whole edit
   invisible inside a code fence).
4. **Every table line must begin with `|`, and no line of a table may be indented four or more columns.**
   Both are stricter than GFM, and both are refused *because* GFM is laxer, not in spite of it. GFM lets a
   row omit its outer pipes, so `sec-21 | … | … |` renders identically to the piped form — measured, 15
   tables / 134 rows in both renderers, byte-identical to pristine — which makes this the one class of
   edit the rendered document cannot disclose, so the refusal quotes the offending line back to you. Four
   columns of indentation makes a line an **indented code block** in GFM — except on a **delimiter** row,
   where the header row above has already opened a paragraph and the indented line is absorbed into it as a
   lazy continuation, so the table becomes one paragraph of literal pipes with no code block at all
   (measured: `<pre>` count 1 for an indented header row, data row or heading; **0** for a delimiter row).
   An indented **data** row drops itself and every row below it *in its own table*; that is the rule, and the
   number is whatever that table has left below the row — the largest table in this file has 20 data rows, so
   20 rows is the most a single indented data row has been measured to remove (134 → 114). An indented
   **header or delimiter** row drops the whole table instead (14 tables / 118 rows against pristine 15 / 134).
   Three columns is still a table line.
5. **The file must have LF line endings and no carriage returns anywhere**, refused in four arms because a
   `\r` has four shapes with different consequences. A predicate that decides *which* repair to
   recommend is easy to get wrong on some
   input, and then the wrong side is told to run a command that destroys the file. The three arms where a carriage
   return is acting as a line terminator therefore prescribe one command, and it is quoted here in the only
   form this file may print it — `reduce.sh`'s own `CR_FIX` string, **`LC_ALL=C` on both stages**:
   `LC_ALL=C awk '{sub(/\r$/,"")} 1' severity.md | LC_ALL=C tr '\r' '\n' > fixed`.
   **The `LC_ALL=C` is the load-bearing part**: without it the repair is itself a
   command that destroys the file. Measured, on a CRLF copy of this file carrying one
   Windows-1252 `0x92` byte in its first data row ID cell: the unpinned form kept **under half the
   file** — awk stops at that row with `awk: towc: multibyte conversion failure`, and tr, fed only
   awk's output, is silent — while the pipeline still exited
   **0**, so the redirection kept the truncation. The reducer then refuses the truncated result with
   *"the `### High` heading here owns no table with data rows (the file ended)"* — a command-caused truncation
   described as pre-existing malformation, naming no carriage return and no command, so the maintainer
   concludes the text was already broken. The pinned form restores the same input to **this file
   exactly, bar that byte**, with empty stderr, and its refusal then names the real defect (`ID cell token "\x92sec-2" is
   not a question id`). Measured across thirteen carriage-return shapes, the pinned form produced exactly the
   LF-equivalent of its input with empty stderr on **thirteen of thirteen**, and restored this file
   byte-for-byte on the **four** whose only corruption was the line endings — all-CRLF, all-bare-CR, mixed,
   and an interior `\r` in a delimiter row. It promises no more than that: the other nine carry an injected
   byte or an interior `\r` that correctly becomes a newline, so the command loses no text but does not
   reproduce pristine, and the reducer then refuses **visibly** on eight of those nine rather than publishing
   a weight map that disagrees with the rendered tables. Neither single-step command is a substitute:
   `tr -d '\r'` deletes line boundaries that
   cannot be recovered, and `tr '\r' '\n'` turns every CRLF into a blank line and renders **0 tables**. Two of
   the four arms do offer an alternative and one gives `CR_FIX` as a fallback, so "one repair" is the terminator
   arms only: the uniformly-CRLF and mixed-endings arms accept `LC_ALL=C tr -d '\r'` as equivalent, because
   every carriage return there terminates a line, while the **interior**-`\r` arm asks for a per-line
   judgement first — where the carriage return sits genuinely *inside a cell*, deleting that one
   character is what rejoins the text — and names the lines so you can make it. **CRLF endings** and **mixed endings** are a *hygiene* refusal: the reducer strips carriage
   returns before matching, so an all-CRLF copy of a well-formed file was measured to produce the identical
   weight map and an identical rendered document, and what the refusal protects is the readability of this
   file's diff, which is read as a score change. **Bare-CR endings** are a *parse* failure — awk sees runs of
   lines as single records, so nothing inside them parses — and the repair is to **convert**, never delete.
   A **`\r` inside a line** is refused on its own terms, and the message distinguishes the placements rather
   than assuming one, because the same claim pointed three different ways. Inside a **data row** it splits that
   row for a renderer (135 `<tr>` for one, 136 for two, against 134), so the rendered table stops matching the
   documented weights. Inside a **header** row it renders 14 tables / 118 — a table *lost*, the opposite
   direction. Inside a **delimiter** row the row *count* is unchanged at 15 / 134 — but the first table's
   header drops from **3 cells to 2**: the real header row is demoted to a paragraph of literal pipes,
   `|----|---` becomes the header, and **the entire third column disappears**. Inside a **heading**, 15 `<h3>` again — but `### Hi⏎gh`
   renders `<h3>Hi</h3>` plus a stray `<p>gh</p>`, so the tier word `High` ceases to exist, which is the one
   thing a `### High`-keyed parser depends on. **A matching count is not a matching document**, and two of
   these four placements prove it. The message asserts the arithmetic only when every affected line is a data row, and otherwise gives
   all four figures and asserts none. Either way it names the line numbers, and says how many it is showing of
   how many there are.
6. **Every question needs exactly one row, and every row needs a live question.** A question with no
   row, an id with two rows, and a row naming a question the scorers do not emit are each refusals.

**What no gate can catch**, because it cannot be told apart from intent: any edit that leaves *every*
tier heading owning a structurally complete table while changing which heading is nearest to some row.
Retyping `### Medium` as `### Low` and moving a row between tables are two instances of it, not the whole
of it — the set is defined by that property. Those re-tier their questions silently, and must, because
that is exactly how a deliberate re-tiering is expressed in this file. **Read a `severity.md` diff as a
score change.** The parser also never falls back to a default weight: **a fallback would let a
question be documented Low and scored Medium, silently.**

Every measured question carries a WAF-style risk weight, applied by the reducer:
**High = 3, Medium = 2, Low = 1**. These tiers are this skill's own editorial assignment, not an
AWS-published risk level — no Well-Architected Tool risk classification, CIS Benchmark severity or EKS
Best Practices Guide tiering backs them. They exist to order findings within a pillar, not to borrow
AWS's authority for that ordering. The pillar score is the severity-weighted average of applicable
answers, so a missing High-risk control moves the number three times as much as a missing Low-risk extra.

**What puts a question in each tier:**
- **High** — absence creates a *direct, exploitable exposure* or a *loss-of-availability / data-loss / cost-leak* that a reasonable operator must fix. These define whether a cluster is fundamentally sound.
- **Medium** — a real best practice that materially reduces risk or waste, but whose absence is survivable or context-dependent.
- **Low** — an optimization or advanced/aspirational practice. Valuable, but many well-run clusters legitimately skip it. One Low answer moves a pillar a third as far as one High answer.

**A Low tier is not a small share of the weight.** Weights are per question, so what a tier is worth
inside a pillar depends on how many questions that pillar puts in it. Performance Efficiency scores 11
measured questions — 1 High, 2 Medium, 8 Low (`perf-7` in its Medium table is a governance question, not assessed) — so its
Low tier carries **over half** the applicable weight: 8 of 15 when all eleven apply. Fixing only four Low
failures there (VPA, affinity refinement, `ndots`, topology-aware routing) is worth 4 of those 15, about
**27 points** — enough to lift 59 into the 80s and flip `Poor · High risk` to `Good · Low risk` — while `perf-1`,
the pillar's only High question, can stay at `some`. So a pillar's band,
and the risk label derived from it, cannot tell you whether a High-severity control is met. Read the
High findings themselves.

**The discounts below are conditional.** Where a Medium rationale discounts a control because a more
specific check covers the same ground, the discount holds only while that other check passes. A cluster
missing the whole layer pays the discounted weight for every part of it, which is less than the gap
deserves — read those questions as a group, not one at a time.

Governance questions are unweighted in the *score* — they are reported separately as Not
Assessed. They still need a row, because the
report labels them with a severity like any other question, and because a question with no row here is
refused rather than defaulted.

---

## Security

### High
| ID | Check | Why High |
|----|-------|----------|
| sec-2 | API server not reachable from the whole internet | An internet-reachable control plane is the single biggest EKS attack vector. Decided in order: any `/0` prefix fails first (so `::/0` fails too, not only `0.0.0.0/0`), then merged IPv4 coverage fails a set that reaches everything in pieces (`0.0.0.0/1` + `128.0.0.0/1`), and only then is an unparseable entry reported as unmeasured. The coverage threshold is exactly 100% — 255 of 256 `/8`s still passes — and whether the surviving ranges are the *right* ones is not judged. |
| sec-4 | NetworkPolicies present per namespace | Flat pod networking lets one compromised pod reach everything; isolation is baseline containment. |
| sec-6 | Pod-level AWS identity (EKS Pod Identity **or** IRSA) | Falling back to node-role credentials gives every pod on the node broad AWS access — huge blast radius. The detection accepts either mechanism: Pod Identity is what AWS now recommends and it uses no ServiceAccount annotation, so an IRSA-only rationale would describe a check narrower than the one that runs. |
| sec-11 | Pod Security Standards enforced | Without PSS, privileged/root pods deploy unchecked — the entry point for most container escapes. |
| sec-18 | OIDC provider associated | Prerequisite for IRSA; without it fine-grained pod IAM is impossible. |
| sec-21 | Cluster EBS volumes encrypted at rest | Unencrypted data at rest is a direct compliance and confidentiality failure. |
| sec-38 | Cluster **configured** to envelope-encrypt Secrets with a customer-managed KMS key | Without it, Secrets are protected by an AWS-owned key the customer cannot audit, scope or revoke. Read from `cluster.encryptionConfig`, so it evidences the key future writes use — **not** that Secrets predating the key have been rewritten through it. Distinct from sec-21, which covers the disks rather than the Secret objects. |
| sec-26 | Kubernetes audit logging enabled | No audit trail means breaches can't be detected or investigated. |
| sec-29 | Ingress terminates TLS | Plaintext ingress exposes credentials and data in transit. |
| sec-30 | No SSH (port 22) open to the internet | Open SSH is a direct node-takeover path. Reads `0.0.0.0/0` **and** `::/0` on the cluster security groups; prefix lists, peered CIDRs and SG-referenced sources are not resolved, `sshd` itself is never inspected, and no SSM data is collected so the Systems Manager replacement path is not verified. |
| net-2 | Security groups have no `0.0.0.0/0` or `::/0` on non-web ports | Wide-open SGs are direct network exposure. Both address families are read (the same test sec-30 applies to port 22); prefix lists, peered CIDRs and SG-referenced sources are not resolved. |
| podsec-2 | Workload containers not privileged | A privileged container is effectively root on the node. |
| podsec-4 | Added capabilities stay within the Pod Security Standards Baseline allowlist | A capability outside it (SYS_ADMIN, NET_ADMIN, SYS_PTRACE, ALL…) enables container-to-host escape. |
| rbac-1 | `cluster-admin` bound only to Group `system:masters` and User `eks:addon-manager` | A stray cluster-admin binding is full cluster takeover. |
| lens-11 | IMDSv2 enforced (`HttpTokens=required`) | IMDSv1 enables SSRF-based theft of node credentials. |

### Medium
| ID | Check | Why Medium |
|----|-------|-----------|
| sec-1 | Private API endpoint enabled | Strong control, but sec-2 (restricting public) is the harder gate; often paired. |
| sec-9 | Non-system ClusterRoles avoid wildcard verbs/resources | Least-privilege matters, but only a literal `*` is counted and the scope excludes just `system:*`, `eks:*` and `cluster-admin` — the built-in `admin`, `edit` and `view` roles are **inside** the denominator, so broad *named* grants (full CRUD on `secrets`, `impersonate`) pass. Bounded impact, and a pass is narrower than "least privilege". |
| sec-10 | Non-AWS validating webhook whose rules match Pod creation present | Enforcement point for policy — discounted only while sec-11 (PSS) is enforcing the baseline. With both absent, nothing inspects a pod spec before it runs, which is worse than either weight suggests. Only `rules` are read (Pod `CREATE`); `failurePolicy` and the namespace and object selectors are not, so this does not establish that the webhook sees every Pod or fails closed. |
| sec-15 | Containers set a security context | The umbrella check: discounted only because podsec-1..5 measure the same properties directly and are scored separately. If those are failing too, this weight understates a cluster that sets no securityContext anywhere. |
| sec-16 | Policy engine deployed with at least one policy loaded | Enables enforcement; value depends on the policies actually loaded, and **this row scores deployment only**. Whether any loaded policy refuses at admission is **neither scored nor reported**: no count of how many refuse versus how many only report is printed, because the three collected files cannot settle an admission outcome and such a count is wrong on ordinary policies. A Pass says an engine is carrying rules, nothing more. A Gatekeeper Constraint in `dryrun` or `warn` counts as loaded and is not distinguished from one that denies. Which Pod fields the policies cover is not inspected either. Pod Security Standards labels are sec-11, not this row. |
| sec-25 | StorageClasses set `encrypted: true` | Sets the default for every volume created from here on; discounted only because sec-21 covers the volumes that exist today. Both failing means unencrypted disks now *and* unencrypted disks later. |
| net-4 | Cluster SG default allow-all egress narrowed | Removes the outbound path used for exfiltration and second-stage pulls; not itself an inbound hole. Reads egress to `0.0.0.0/0` **and** `::/0`; prefix-list and SG-referenced destinations are not resolved. (sec-31, on control-plane/node SG separation, is not scored — AWS says that split is no longer required.) |
| sec-31 | Worker-node and control-plane security groups separated — **RETIRED** | Kept only so every question this skill emits has a documented weight. The scorer still emits `sec-31`, always as `na` with the note "retired: AWS no longer recommends separating control-plane and node security groups", so it is excluded from every pillar numerator and denominator and this weight never reaches a score — it reaches the report's Severity column and nothing else. Filed Medium only so the Severity column has a tier to show; do not read the tier as a live judgement about SG separation — net-4 above is the live control. |
| sec-33 | Runtime threat monitoring agent present (GuardDuty/Falco/Sysdig/Tetragon) | Detection layer; valuable but not a preventive control — and **presence only**: the add-on appearing in the cluster's add-on list is sufficient, Pod phase is not read, and per-node coverage is not compared against the node count, so a cluster passes on a DaemonSet that reaches only some of its nodes. |
| adm-1 | Admission policies (Gatekeeper/Kyverno) deployed | An engine with policies loaded is the precondition for every policy-based control, but loading is not blocking. **This row scores deployment only**: any one loaded policy scores, no ≥5-policy bar drives the state, and coverage depth (the 5-10 target in the remediation) is disclosed in the detail line instead of scored. How many loaded policies refuse at admission is **not disclosed at all**, here or in sec-16, adm-2 and adm-3, so there is no enforcement number for the four hand-written copies of the disclosure sentence to disagree about. The `SCORED ON DEPLOYMENT ONLY` marker is hand-written once per scorer with nothing binding the copies: no gate reads it (`reduce.sh`, `score.sh` and `render-report.py` contain no reference to it) and no automated check compares the four arms against each other, so agreement between them rests on careful editing. Their STATES are expected to AGREE everywhere: where nothing is loaded at all — no policies and no ConstraintTemplates — all four measure `none`, and on a templates-only cluster all four measure `none` too, so a difference in either place WOULD be drift. (An `na` on the first of those would make the scale non-monotonic; see sec-16's panel.) `dryrun`/`warn` Gatekeeper Constraints count as loaded and are not distinguished from ones that deny. Under deployment scoring this overlaps sec-16 heavily — the two differ in what they disclose, not in what they score. |
| adm-2 | Admission policy engine deployed with at least one policy loaded, able to carry a privileged-container restriction | Policy-level backstop for podsec-2 — discounted only while podsec-2 itself passes. Privileged pods present *and* no policy blocking them means nothing stops the next one either. **This row scores deployment only**: whether a loaded policy actually restricts privileged is disclosed in the detail line rather than scored, so a Pass is not evidence that privileged pods are blocked — read podsec-2 for that. That disclosure is Kyverno-only: it reads the policy body for a `privileged: false` requirement in a rule whose declared action resolves to `Enforce`, and Gatekeeper Constraints are neither credited nor discounted in it because which Pod field a Constraint covers is not read. It is a claim about what a policy document REQUIRES, not about what the API server would refuse — this skill does not judge enforcement depth. |
| adm-3 | Admission policy engine deployed with at least one policy loaded | Audit-only still surfaces issues, so enforce is an upgrade not a baseline — but **this row neither scores nor reports that upgrade**. It scores deployment only. The enforce-vs-audit split is not disclosed in the detail line, because the three collected files cannot settle whether a request would be refused and an `N of M loaded policy/ies refuse at admission` count is wrong on ordinary policies. Read the state for "an engine is carrying policies" and read nothing here about what is armed: enforcement depth is deliberately not judged. |
| podsec-1 | Containers run as non-root | Root in the container is the starting position for every escape: a hostPath mount, a writable host socket or a runtime CVE turns it into root on the node. Medium rather than High because a root container that is *not* privileged is still bounded by the runtime's default capability set. |
| podsec-3 | Pods avoid hostPath mounts | hostPath is a common escape vector but often needed by legit tooling. |
| podsec-5 | Containers drop ALL capabilities | Best practice; discounted only while podsec-2/4 pass. A container that is neither privileged nor adding a capability outside the Baseline allowlist still keeps the runtime's default set (CHOWN, SETUID, NET_RAW…), so with those failing too this weight understates the gap. |
| rbac-2 | ServiceAccounts use namespace-scoped RoleBindings | Scoping reduces blast radius; medium because cluster roles may be legitimate. |
| rbac-3 | No stale/dangling role bindings | Hygiene; low exploitability on its own. |
| rbac-4 | Default ServiceAccounts don't auto-mount tokens | Reduces token theft surface for workloads that don't need API access. |
| lens-12 | ECR scan-on-push (cluster repos) | Surfaces known CVEs in the images this cluster actually pulls. Medium because scanning *reports* — on its own it does not stop a vulnerable image from being deployed. |
| sec-3 / sec-7 / sec-13 / sec-14 / sec-19 / sec-20 / sec-22 / sec-24 / sec-34 | Governance/process (IAM mapping, kube-system access, env separation, CIS, change mgmt, EFS, secrets strategy, rotation) | Real risk-reduction practices, not assessed. |

### Low
| ID | Check | Why Low |
|----|-------|---------|
| sec-5 | Dedicated cluster-creation role | Process nicety; minimal runtime risk. Not assessed. |
| sec-8 | External Secrets Operator | KMS envelope encryption already covers the baseline; ESO is an enhancement. |
| sec-12 | Workload images pinned to a digest or an explicit tag (not `:latest`) | Reproducibility and image provenance rather than a live exposure. `imagePullPolicy` is deliberately **not** what is measured: the API server defaults it on admission, so it is never absent in collected data and a check for an "explicit" policy would pass every cluster unconditionally. The reference test is `:latest$` / `@sha256:\|:[^/]+$`, which correctly fails a trailing-colon reference such as `repo/name:`; the denominator is `spec.containers` only, so initContainers are out of scope. |
| sec-17 | Access-entry (API) auth mode | Modern default; low direct risk either way. `CONFIG_MAP`-only scores `none`, not a partial — it is the legacy path with no access entries at all. The `aws-auth` ConfigMap's *contents* are not read by this question, so a pass is never a statement that the mappings were reviewed. |
| sec-23 | EFS encryption in transit | Applies only if EFS is used; niche. Not assessed. |
| sec-27 / sec-28 | Service mesh control plane / sidecar presence (mTLS mode not assessed) | Strong for zero-trust, but most clusters run fine without a mesh. sec-27 matches Istio, Linkerd and Consul by name — **not** App Mesh — and measures the control plane's presence, not that any workload is meshed. |
| sec-32 | Image signing | Supply-chain enhancement; adoption still uncommon. Not assessed. |
| sec-35 / sec-36 / sec-37 | Rotation cadence, compliance scanning extras | Maturity practices; not assessed. |
| net-1 | Subnets have ≥100 free IPs | Capacity planning; only bites at scale. |
| net-3 | VPC CNI prefix delegation | IP-density optimization, not a security control. |
| lens-13 | ECR immutable tags | Stops a reviewed tag being re-pointed at different content. Low because it hardens the registry rather than anything already running in the cluster. |

---

## Reliability

### High
| ID | Check | Why High |
|----|-------|----------|
| rel-1 | Nodes span multiple AZs | Single-AZ means an AZ outage takes the whole cluster down. |
| rel-6 | Containers have readiness probes | Without them, traffic routes to unready pods → user-facing outages. |
| rel-7 | Deployments run >1 replica | Single-replica workloads have no failover; any pod loss is downtime. |
| rel-12 | Backup/snapshot policy exists | No backups = permanent data loss on failure. **Not assessed**, and the only High-weighted question that is: the scorer emits it on the governance track, so it reports Not Assessed and never enters the Reliability number. A high Reliability score is not evidence that backups exist — ask. |
| rel-13 | Monitoring & alerting deployed | Without it, failures go unnoticed until users complain. |
| lens-15 | Worker nodes in private subnets | Public-subnet nodes are directly reachable and a resilience/security risk. |

### Medium
| ID | Check | Why Medium |
|----|-------|-----------|
| rel-2 | PodDisruptionBudgets cover deployments | Prevents mass eviction during drains; matters mostly during maintenance. |
| rel-3 | Containers set CPU/memory limits | Prevents noisy-neighbor starvation; some teams intentionally omit CPU limits. |
| rel-4 | Cluster autoscaler / Karpenter present | Handles capacity; static clusters can still be reliable. |
| rel-5 | HPAs on deployments | Absorbs load spikes; not every workload needs autoscaling. |
| rel-8 | Pod anti-affinity | Spreads replicas off single nodes; incremental over multi-replica. |
| rel-9 | Topology spread constraints | Spreads across zones; refinement of anti-affinity. |
| rel-14 | HA ingress controller | Matters only when ingress is on the critical path; not assessed. |
| rel-18 | Deployments use RollingUpdate | Enables zero-downtime deploys; default for most. |
| rel-21 | StatefulSets use persistent volume templates | Prevents data loss on reschedule for stateful apps. |
| rel-22 | StatefulSets run HA (>1 replica) | HA for stateful apps; many are single-instance by design. |
| lens-14 | NAT gateway per AZ | Avoids a cross-AZ egress SPOF; cost/resilience tradeoff. |
| rel-10 | Volume snapshot class configured | Enables backups; not assessed. |
| rel-24 | Cluster deletion protection enabled | An accidental `delete-cluster` is unrecoverable; the flag makes EKS refuse it. **Medium, not Low**, because the rationale argues Medium. The tier this table gives it is the weight the score uses: there is no default weight and no second copy, so the tier this table shows is always the tier the score used. Moving it to Low can change Reliability on any cluster where it applies — a real change, made deliberately here or not at all. |

### Low
| ID | Check | Why Low |
|----|-------|---------|
| rel-11 | PVCs are Bound | A symptom check, not a design control. |
| rel-15 | LoadBalancer services used appropriately | Architecture choice, not a reliability gate; not assessed. |
| rel-16 | Service mesh | Adds resilience features but optional. |
| rel-17 | DNS / service discovery setup | CoreDNS is present by default; not assessed. |
| rel-19 | DaemonSets use RollingUpdate | Minor operational detail. |
| rel-20 | DaemonSets set requests+limits | Hygiene for node agents. |
| rel-23 | Distributed tracing | Observability enhancement, not availability. |
| lens-2 | NodeLocal DNSCache | Latency/reliability optimization at scale. |
| lens-3 | CoreDNS autoscaler | Only matters at high DNS QPS. |

---

## Operational Excellence

### High
| ID | Check | Why High |
|----|-------|----------|
| ope-5 | Control-plane metrics collected | You can't operate what you can't see; core observability. |
| ope-6 | Control-plane logging enabled (all types) | Without logs, incident response and audit are blind. |
| ope-11 | CloudTrail enabled | The record of who did what in the account; essential for forensics. |
| ope-12 | Kubernetes audit logging on | API-level audit trail for the cluster. |

### Medium
| ID | Check | Why Medium |
|----|-------|-----------|
| ope-1 | Infrastructure as Code | Reproducibility/drift control; not assessed. |
| ope-2 | AWS integration controllers (LB/ExternalDNS/EBS-CSI) | Operational glue; partial adoption is common. |
| ope-7 | Node-level metrics (node-exporter or CloudWatch agent) | Complements control-plane metrics. |
| ope-8 | Centralized log forwarding | Aggregation aids ops; apps can log without it short-term. |
| ope-9 | Alarms on API 401/403 spikes | Early breach signal; not assessed. |
| ope-13 | Documented upgrade plan | Avoids falling out of support; process. Not assessed. |
| ope-15 | EKS-managed node groups (or Auto Mode) | Managed lifecycle/patching; self-managed is viable but heavier. |
| ope-16 | Core addons EKS-managed | Keeps CNI/CoreDNS/kube-proxy patched. |
| ope-19 | Capacity planning process | Prevents saturation; process. Not assessed. |
| lens-7 | VPC CNI add-on managed, current, ACTIVE, no health issues | Networking foundation health. |
| ope-20 | EKS upgrade-readiness insights passing | AWS names the next upgrade’s blockers; ignoring them is how an upgrade fails mid-flight. |

### Low
| ID | Check | Why Low |
|----|-------|---------|
| ope-3 | GitOps (ArgoCD/Flux) | Great practice, but not required for a sound cluster. |
| ope-4 | Templating (Helm/Kustomize) | Packaging preference. Not assessed. |
| ope-10 | CNI metrics helper | Niche observability add-on. |
| ope-14 | Non-prod test environment | Org practice, not assessed. |
| ope-18 | CronJob concurrency policy | Only relevant if CronJobs exist. |
| fargate-1 / fargate-2 / fargate-4 | Fargate profile/logging specifics | Apply only to Fargate clusters. |
| lens-1 | Node Problem Detector | Useful signal, easily lived without. |

---

## Performance Efficiency

### High
| ID | Check | Why High |
|----|-------|----------|
| perf-1 | Containers set CPU/memory requests | Without requests the scheduler can't place or bin-pack correctly — the root of both waste and contention. |

### Medium
| ID | Check | Why Medium |
|----|-------|-----------|
| perf-3 | Appropriate/modern instance types | Right-sizing the fleet; impacts perf and cost. |
| perf-7 | Node utilization in a healthy band | Efficiency signal; needs live metrics (not assessed). |
| lens-6 | EKS-optimized AMIs (Bottlerocket/AL2023) | Better boot/runtime characteristics. |

### Low
| ID | Check | Why Low |
|----|-------|---------|
| perf-2 | Vertical Pod Autoscaler | Right-sizing aid; recommendation-mode optional. |
| perf-4 | RollingUpdate strategy | Overlaps rel-18. |
| perf-5 | Scheduling constraints tuned | Refinement of affinity/spread. |
| perf-6 | Instance-type diversity | Helps Spot/availability; not core perf. |
| lens-5 | Standard `app.kubernetes.io/*` labels | Tooling/consistency nicety. |
| lens-8 | CoreDNS `ndots` tuned | Micro-optimization for DNS-heavy apps. |
| lens-9 | LB `externalTrafficPolicy: Local` | Preserves source IP / cuts a hop; situational. |
| lens-10 | Topology-aware routing | Cross-AZ traffic optimization. |

---

## Cost Optimization

### High
| ID | Check | Why High |
|----|-------|----------|
| cost-6 | No idle/unused PersistentVolumes | Idle EBS bills every hour for zero value — direct, ongoing waste. |
| cost-8 | No unattached (orphaned) EBS volumes | Same as above from the orphaned-resource angle; pure leak. |
| cost-9 | Storage on gp3 (not gp2) | gp3 is ~20% cheaper on storage. Below ~1,000 GiB it is at or above gp2's baseline IOPS, though gp2 volumes of 334 GiB and larger sustain 250 MiB/s against gp3's default 125 MiB/s, so set `throughput: 250` for those volumes (from 170 to 334 GiB gp2 reaches 250 MiB/s only by burst, and the extra gp3 throughput, about $0.04 per MiB/s-month, can cost more than gp2 below about 250 GiB). At or above ~1,000 GiB a gp2 volume already exceeds gp3's default 3,000 IOPS, and migrating without provisioning `iops: min(size × 3, 16000)` is a **performance downgrade** — gp2's baseline stops climbing at 16,000 IOPS, reached at 5,334 GiB, and every larger gp2 volume gets the same 16,000, so an uncapped `size × 3` formula overshoots gp2 parity (and overpays for IOPS never delivered) above that size. See [cost-analysis.md](cost-analysis.md) for the crossover. Still weighted High because the overspend is unforced, not because the migration is free. |

### Medium
| ID | Check | Why Medium |
|----|-------|-----------|
| cost-1 | cpu/memory ResourceQuotas per namespace | Caps runaway consumption; governance guardrail. |
| cost-2 | cpu/memory LimitRanges per namespace | Sensible defaults prevent oversized pods. |
| cost-5 | Storage requested-vs-used efficiency | Right-sizing; needs usage data (not assessed). |
| cost-7 | Cost-allocation tags present | You can't optimize what you can't attribute. |

### Low
| ID | Check | Why Low |
|----|-------|---------|
| cost-3 | Off-peak / event-driven scaling (KEDA) | Savings for bursty workloads; not universal. |
| cost-4 | Data-transfer cost monitoring | Visibility practice; not assessed. |
| lens-4 | Cost-visibility tooling (Kubecost/OpenCost) | Helpful, but chargeback is optional. |
| lens-16 | VPC endpoints for S3/ECR/STS | Trims NAT data-processing cost where nodes egress through a NAT gateway; modest savings. |

---

*Note: `lens-12` and `lens-13` (ECR scan-on-push, immutable tags) are scored under **Security**, not
here — they are supply-chain controls, and `cost-optimization.md` records the move. Do not look for them
in a low Cost score.*

*Note: the compute-cost heavyweights — Graviton, Spot, and Extended Support — are handled in
[cost-analysis.md](cost-analysis.md) as narrative savings opportunities, not scored pillar questions,
because they are recommendations rather than pass/fail controls.*
