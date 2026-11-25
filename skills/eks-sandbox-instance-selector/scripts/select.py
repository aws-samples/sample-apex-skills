"""Nitro Sandbox instance selector for Amazon EKS.

Given a sandbox Pod's requests/limits, compute for every supported instance type how many sandboxes
fit per node, which limit binds first, and cost per sandbox / total. Prints Markdown.

Example:
  python select.py --region us-west-2 --mode auto --runtime-class isolated --count 100 --cpu-req 1 --mem-req 2048
"""
import argparse, json, math, sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "data.json"
LIM_NAME = {"slots": "slots", "vcpu": "vCPU budget", "mem": "memory", "cpu": "CPU", "pods": "max-pods", "hard": "896 hard cap"}


def fmt_usd(v):
    if v is None:
        return "—"
    return f"{v:.5f}" if v < 0.01 else f"{v:.4f}" if v < 1 else f"{v:.3f}"


def cpu_reserved_m(v):  # EKS standard kube-reserved CPU
    return 60 + (10 if v >= 2 else 0) + 5 * min(max(v - 2, 0), 2) + 2.5 * max(v - 4, 0)


def eval_type(it, p):
    auto = p.mode == "auto"
    max_pods = it["eni"] * (it["ip"] - 1) + (0 if auto else 2)
    if p.podcap:
        max_pods = min(max_pods, 110 if it["vcpu"] < 30 else 250)
    alloc_cpu = it["vcpu"] * 1000 - cpu_reserved_m(it["vcpu"]) - (150 if auto else 0) - p.ds_cpu
    mem_cap = it["mem"] * 0.9646 - 85
    alloc_mem = mem_cap - (255 + 11 * max_pods + 100) - (75 if auto else 0) - it["mem"] * p.sbres / 100 - p.ds_mem
    smt = it["tpc"] >= 2 and it["arch"] == "x86_64"
    g = p.guest_vcpu
    eff = 1 if not smt else (1 if g % 2 == 0 else g / (g + 1))
    if g > it["vcpu"]:
        return None
    mem_per_pod = p.mem_req + p.overhead
    lim = {
        "slots": it["vcpu"] * 5,
        "vcpu": it["vcpu"] * 5 // g,
        "hard": 896,
        "pods": max_pods - p.ds_pods,
        "mem": math.floor(alloc_mem / mem_per_pod),
        "cpu": math.floor(alloc_cpu * (eff if p.smt else 1) / p.cpu_req_m) if p.cpu_req_m > 0 else math.inf,
    }
    by = min(lim, key=lim.get)  # first key wins on ties, same as the JS loop
    fit = max(lim[by], 0)
    if fit == 0:
        return {"it": it, "fit": 0, "by": by}
    honor = min(1, alloc_cpu * eff / (p.cpu_req_m * fit)) if p.cpu_req_m > 0 else 1
    per = it["price"] / fit if it["price"] is not None else None
    nodes = math.ceil(p.count / fit) if p.count > 0 else None
    total = nodes * it["price"] if nodes is not None and it["price"] is not None else None
    return dict(it=it, fit=fit, by=by, lim=lim, alloc_cpu=alloc_cpu, alloc_mem=alloc_mem, max_pods=max_pods,
                cpu_use=p.cpu_req_m * fit / alloc_cpu, mem_use=mem_per_pod * fit / alloc_mem, honor=honor,
                per=per, nodes=nodes, total=total, smt=smt, eff=eff, numa=it["vcpu"] >= 96)


def parse():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", required=True)
    ap.add_argument("--mode", choices=["auto", "std"], required=True, help="auto = EKS Auto Mode; std = Standard EKS (Karpenter / node group)")
    ap.add_argument("--runtime-class", choices=["isolated", "confidential"], required=True, help="overhead 256Mi / 512Mi")
    ap.add_argument("--count", type=int, required=True, help="total sandboxes; 0 = rank by cost per sandbox")
    ap.add_argument("--cpu-req", type=float, required=True, help="CPU request in vCPU")
    ap.add_argument("--cpu-lim", type=float, default=0, help="CPU limit in vCPU (does not change guest vCPU)")
    ap.add_argument("--mem-req", type=float, required=True, help="memory request in MiB")
    ap.add_argument("--mem-lim", type=float, default=0, help="memory limit in MiB (scheduling uses request only)")
    ap.add_argument("--arch", choices=["any", "arm64", "x86_64"], default="any")
    ap.add_argument("--cats", default="c,m,r", help="comma list of c,m,r,x (x includes z)")
    ap.add_argument("--min-gen", type=int, default=6, choices=[5, 6, 7, 8])
    ap.add_argument("--no-smt", dest="smt", action="store_false", help="don't discount x86 SMT CPU to physical cores")
    ap.add_argument("--allow-numa", dest="nonuma", action="store_false", help="keep types with >=96 vCPU (maybe multi-NUMA)")
    ap.add_argument("--metal", action="store_true", help="include metal sizes")
    ap.add_argument("--sbres", type=float, default=12, help="extra sandbox-node memory reservation, %% of physical memory")
    ap.add_argument("--ds-pods", type=int, help="DaemonSet pods per node (default auto=0, std=3)")
    ap.add_argument("--ds-cpu", type=float, help="DaemonSet CPU requests total, millicores (default auto=0, std=150)")
    ap.add_argument("--ds-mem", type=float, help="DaemonSet memory requests total, MiB (default auto=0, std=200)")
    ap.add_argument("--no-podcap", dest="podcap", action="store_false", help="don't cap max-pods at 110 (<30 vCPU) / 250")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--data", type=Path, default=DATA)
    p = ap.parse_args()
    auto = p.mode == "auto"
    for k, a, s in [("ds_pods", 0, 3), ("ds_cpu", 0, 150), ("ds_mem", 0, 200)]:
        if getattr(p, k) is None:
            setattr(p, k, a if auto else s)
    p.overhead = 512 if p.runtime_class == "confidential" else 256
    p.cpu_req_m = round(p.cpu_req * 1000)
    p.guest_vcpu = max(1, math.ceil(p.cpu_req - 1e-9))
    p.cats = [c.strip() for c in p.cats.split(",") if c.strip()]
    return p


def bar(x):
    return f"{max(0, min(1, x or 0)) * 100:.0f}%"


def main():
    p = parse()
    data = json.loads(p.data.read_text())
    if p.region not in data["regions"]:
        sys.exit(f"region {p.region} not in data; available: {', '.join(data['regions'])}")
    cats = {y for c in p.cats for y in (["x", "z"] if c == "x" else [c])}
    rows = [it for it in data["regions"][p.region]
            if it["cat"] in cats and it["gen"] >= p.min_gen
            and (p.arch == "any" or it["arch"] == p.arch)
            and (p.metal or not it["metal"])
            and not (p.mode == "auto" and it["autoBlocked"])]
    rows = [r for r in map(lambda it: eval_type(it, p), rows) if r and r["fit"] > 0 and not (p.nonuma and r["numa"])]
    key = (lambda r: r["total"] if r["total"] is not None else math.inf) if p.count > 0 else \
          (lambda r: r["per"] if r["per"] is not None else math.inf)
    rows.sort(key=lambda r: (key(r), -r["fit"]))

    out = []
    w = out.append
    w("# Nitro Sandbox instance selection\n")
    w(f"Data: {p.region}, describe-instance-types + Pricing API ({data['source_date']}). These are estimates to shorten the list; test the types on your cluster.\n")
    w(f"Inputs: {'EKS Auto Mode' if p.mode == 'auto' else 'Standard EKS'} · "
      f"{'confidential-sandbox' if p.overhead == 512 else 'isolated-sandbox'} (overhead {p.overhead}Mi) · "
      f"CPU request {p.cpu_req:g} vCPU{f' / limit {p.cpu_lim:g} vCPU' if p.cpu_lim else ''} · memory request {p.mem_req:g}Mi"
      f"{f' / limit {p.mem_lim:g}Mi' if p.mem_lim else ''} · count {p.count or 'not set'} · arch {p.arch} · families {','.join(p.cats)} · gen >= {p.min_gen} · "
      f"DaemonSets {p.ds_pods} pods / {p.ds_cpu:g}m / {p.ds_mem:g}Mi · extra sandbox reserve {p.sbres:g}%")
    w(f"The guest sees {p.guest_vcpu} vCPU (CPU request rounded up).\n")

    warns = []
    if p.mem_req + p.overhead < 256: warns.append("The EC2 documentation recommends at least 256 MiB of memory per sandbox.")
    if p.cpu_lim and p.cpu_lim < p.cpu_req: warns.append("The CPU limit is less than the request. Kubernetes rejects this Pod.")
    if p.mem_lim and p.mem_lim < p.mem_req: warns.append("The memory limit is less than the request. Kubernetes rejects this Pod.")
    if p.cpu_req == 0: warns.append("CPU request is 0: the guest is estimated at 1 vCPU (not measured), and CPU is not used for bin packing.")
    if p.cpu_req_m > 0 and p.cpu_req_m % 1000 != 0:
        warns.append(f"CPU request {p.cpu_req:g} vCPU is not a whole number: the guest gets {p.guest_vcpu} vCPU, but the scheduler counts only {p.cpu_req_m}m. At full load, CPU contention on the node is higher than the numbers show.")
    if p.cpu_lim: warns.append("The CPU limit does not change the guest vCPU count (measured: request 100m + limit 2 still gives 1 guest vCPU).")

    if not rows:
        w("**No instance type matches.** Try more families, an older minimum generation, or another architecture.")
        print("\n".join(out)); return

    # best picks
    bests, seen = [], set()
    cands = [(f"Lowest cost overall ({'Graviton' if rows[0]['it']['arch'] == 'arm64' else 'x86'})", rows[0]),
             ("Lowest cost Graviton", next((r for r in rows if r["it"]["arch"] == "arm64"), None)),
             ("Lowest cost x86", next((r for r in rows if r["it"]["arch"] == "x86_64"), None))]
    for t, r in cands:
        if r is not None and id(r) not in seen:
            seen.add(id(r)); bests.append((t, r))
    w("## Recommendations\n")
    for t, r in bests:
        it = r["it"]
        line = (f"- **{t}: {it['t']}** — {it['vcpu']} vCPU / {it['mem'] / 1024:.0f} GiB · ${fmt_usd(it['price'])}/h; "
                f"**{r['fit']}** sandboxes per node, first limit reached: **{LIM_NAME[r['by']]}**; ${fmt_usd(r['per'])}/h per sandbox")
        if r["nodes"] is not None:
            line += f"; {p.count} sandboxes need **{r['nodes']}** nodes, ${fmt_usd(r['total'])}/h (about ${r['total'] * 730:.0f}/month)"
        if r["smt"]:
            line += f"; x86 SMT: at full load about {r['honor'] * 100:.0f}% of the CPU request is delivered"
        w(line)
    w("")

    # tips
    b, tips = rows[0], list(warns)
    if b["by"] in ("slots", "vcpu"):
        tips.append(f"{b['it']['t']} reaches the {LIM_NAME[b['by']]} limit first. At that point {b['mem_use'] * 100:.0f}% of memory and {b['cpu_use'] * 100:.0f}% of CPU are used; the rest stays idle. Types with less memory per vCPU (r to m, m to c) can cost less.")
    if b["by"] == "mem":
        tips.append(f"{b['it']['t']} reaches the memory limit first; only {b['fit'] / b['lim']['slots'] * 100:.0f}% of slots are used. Types with more memory per vCPU (c to m to r) can fit more.")
    if b["by"] == "cpu":
        tips.append(f"{b['it']['t']} reaches the CPU limit first{' (calculated on physical cores for SMT)' if b['smt'] and p.smt else ''}. If the CPU request is a conservative estimate, lower it and run again.")
    if b["by"] == "pods":
        tips.append(f"{b['it']['t']} reaches max-pods first. If you use prefix delegation or a custom max-pods, run again with --no-podcap.")
    alt = next((r for r in rows if r["by"] != b["by"]), None)
    if alt:
        cost = (lambda r: r["total"]) if p.count > 0 else (lambda r: r["per"])
        pct = (cost(alt) / cost(b) - 1) * 100 if cost(b) and cost(alt) is not None else None
        nodes_txt = f", {alt['nodes']} nodes" if p.count > 0 else ""
        pct_txt = f"{pct:.1f}% more than {b['it']['t']}" if pct is not None else "no price"
        tips.append(f"Comparison: the lowest-cost type with a different first limit is {alt['it']['t']} ({alt['it']['vcpu']} vCPU / {alt['it']['mem'] / 1024:.0f} GiB). "
                    f"It reaches {LIM_NAME[alt['by']]} first, {alt['fit']} per node{nodes_txt}, {pct_txt}. If the inputs change and the costs cross, it becomes the recommendation.")
    if any(r["smt"] for r in rows[:10]) and p.guest_vcpu % 2 == 1:
        tips.append("On x86 SMT types, a 1-vCPU sandbox leaves the other thread of its core idle, so at full load only about half of the CPU is delivered. Use Graviton for small sandboxes."
                    if p.cpu_req < 1 else
                    f"On x86 SMT types, {p.guest_vcpu} guest vCPUs is an odd number, so one thread stays idle. Set the CPU request to {p.guest_vcpu + 1} vCPU (even), or use Graviton.")
    if p.count == 0 and rows[0]["it"]["vcpu"] >= 32:
        tips.append("When sorted by cost per sandbox, large types win slightly because reserves are spread over more sandboxes, but the difference is usually small, and one node failure affects more sandboxes. Set --count to sort by total cost.")
    if p.mode == "auto":
        tips.append("Auto Mode selects the instance type itself. Use these results to decide which families to allow in the NodePool; the requirements are below.")
    w("## Notes\n")
    w("\n".join(f"- {t}" for t in tips) + "\n")

    # table
    n = min(p.top, len(rows))
    w(f"## All candidates ({len(rows)} types, top {n} shown, sorted by {'total cost' if p.count > 0 else 'cost per sandbox'})\n")
    hdr = ["Type", "Arch", "vCPU", "Mem GiB", "$/h", "Alloc CPU", "Alloc mem GiB", "Slots", "max-pods", "Per node", "First limit",
           "CPU used", "Mem used", "CPU delivered", "$/sandbox/h"] + (["Nodes", "Total $/h"] if p.count > 0 else [])
    w("| " + " | ".join(hdr) + " |")
    w("|" + "---|" * len(hdr))
    for r in rows[:n]:
        it = r["it"]
        cells = [it["t"] + (" (SMT)" if r["smt"] else ""), "arm64" if it["arch"] == "arm64" else "x86", it["vcpu"],
                 f"{it['mem'] / 1024:.0f}", fmt_usd(it["price"]), f"{r['alloc_cpu'] / 1000:.2f}", f"{r['alloc_mem'] / 1024:.1f}",
                 r["lim"]["slots"], r["max_pods"], f"**{r['fit']}**", LIM_NAME[r["by"]], bar(r["cpu_use"]), bar(r["mem_use"]),
                 f"{r['honor'] * 100:.0f}%", fmt_usd(r["per"])] + ([r["nodes"], fmt_usd(r["total"])] if p.count > 0 else [])
        w("| " + " | ".join(map(str, cells)) + " |")
    w("\nCPU delivered = CPU each sandbox gets when all sandboxes run at full load, divided by its request. For x86 SMT types this uses physical cores.\n")

    # NodePool snippet
    top10 = rows[:10]
    fams = list(dict.fromkeys(r["it"]["fam"] for r in top10))[:4]
    archs = list(dict.fromkeys("arm64" if r["it"]["arch"] == "arm64" else "amd64" for r in top10))
    fam_key = "eks.amazonaws.com/instance-family" if p.mode == "auto" else "karpenter.k8s.aws/instance-family"
    res = f'requests: {{cpu: "{p.cpu_req_m}m", memory: {p.mem_req:g}Mi}}'
    lims = ([f'cpu: "{round(p.cpu_lim * 1000)}m"'] if p.cpu_lim else []) + ([f"memory: {p.mem_lim:g}Mi"] if p.mem_lim else [])
    if lims:
        res += f"\n#     limits: {{{', '.join(lims)}}}"
    w(f"## {'Auto Mode' if p.mode == 'auto' else 'Karpenter'} NodePool requirements (families from the top 10)\n")
    w(f"""```yaml
spec:
  template:
    spec:
      requirements:
      - key: {fam_key}
        operator: In
        values: [{', '.join(f'"{f}"' for f in fams)}]
      - key: kubernetes.io/arch
        operator: In
        values: [{', '.join(f'"{a}"' for a in archs)}]
# In the Pod:
#   runtimeClassName: {'confidential-sandbox' if p.overhead == 512 else 'isolated-sandbox'}
#   resources:
#     {res}
```""")
    w("This snippet covers only the family and architecture requirements. Keep your existing values for the other NodePool fields (nodeClassRef, limits, disruption, and so on)."
      + (" Standard EKS also needs an AMI with the Nitro Sandbox components, Nitro Enclaves turned on, and a placeholder-Pod workaround for Karpenter scale-from-zero." if p.mode == "std" else ""))
    print("\n".join(out))


if __name__ == "__main__":
    main()
