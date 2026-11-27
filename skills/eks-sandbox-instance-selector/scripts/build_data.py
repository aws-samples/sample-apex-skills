"""Build or update data/data.json for the Nitro Sandbox instance selector.

Usage: python3 build_data.py [RAW_DIR]   (default: <skill>/raw, produced by fetch_raw.sh)
Inputs: RAW_DIR/types-<region>.json (ec2 describe-instance-types) for any Regions that could be read,
        RAW_DIR/price-raw-<region>.json (pricing get-products) for each Region to update.
Output: <skill>/data/data.json, merged: the Regions with a price file in RAW_DIR are rebuilt, every
        other Region already in data.json is kept as it is.

Layout: "types" holds each supported type's specs once (specs don't differ by Region); "regions" maps
each Region to {"date", "prices": {type: USD per hour}}. A type is offered in a Region when that
Region has an on-demand Linux price for it.
Supported families/exceptions transcribed from
https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/amazon-ec2-nitro-sandboxes.html (checked 2026-11-25).
Only general purpose / compute / memory optimized families are included.
"""
import datetime, json, sys
from pathlib import Path

HERE = Path(__file__).parent
SKILL = HERE.parent
RAW = Path(sys.argv[1]) if len(sys.argv) > 1 else SKILL / "raw"
OUT = SKILL / "data" / "data.json"

# family -> sizes NOT supported (from EC2 doc)
SUPPORTED = {
    # General purpose
    "m5": ["large", "metal"], "m5a": ["large"], "m5ad": ["large"], "m5d": ["large", "metal"],
    "m5dn": ["large", "metal"], "m5n": ["large", "metal"], "m5zn": ["large", "metal"],
    "m6a": ["large", "metal"], "m6g": ["medium", "metal"], "m6gd": ["medium", "metal"],
    "m6i": ["large", "metal"], "m6id": ["large", "metal"], "m6idn": ["large", "metal"],
    "m6in": ["large", "metal"], "m7a": ["medium", "large", "metal-48xl"], "m7g": ["medium", "metal"],
    "m7gd": ["medium", "metal"], "m7i": ["large", "metal-24xl", "metal-48xl"],
    "m8a": ["medium", "metal-24xl", "metal-48xl"], "m8azn": ["medium", "metal-12xl", "metal-24xl"],
    "m8g": ["medium", "metal-24xl", "metal-48xl"], "m8gb": ["medium", "metal-24xl", "metal-48xl"],
    "m8gd": ["medium", "metal-24xl", "metal-48xl"], "m8gn": ["medium", "metal-24xl", "metal-48xl"],
    "m8i": ["large", "metal-48xl", "metal-96xl"], "m8id": ["large", "metal-48xl", "metal-96xl"],
    "m8in": ["large", "metal-48xl", "metal-96xl"], "m8idn": ["large", "metal-48xl", "metal-96xl"],
    "m8ine": ["large"], "m8ib": ["large", "metal-48xl", "metal-96xl"],
    "m8idb": ["large", "metal-48xl", "metal-96xl"], "m9g": ["medium", "metal-48xl"],
    "m9gd": ["medium", "metal-48xl"],
    # Compute optimized
    "c5": ["large", "metal"], "c5a": ["large"], "c5ad": ["large"], "c5d": ["large", "metal"],
    "c5n": ["large", "metal"], "c6a": ["large", "metal"], "c6g": ["medium", "metal"],
    "c6gd": ["medium", "metal"], "c6gn": ["medium"], "c6i": ["large", "metal"],
    "c6id": ["large", "metal"], "c6in": ["large", "metal"], "c7a": ["medium", "large", "metal-48xl"],
    "c7g": ["medium", "metal"], "c7gd": ["medium", "metal"], "c7i": ["large", "metal-24xl", "metal-48xl"],
    "c8a": ["medium", "metal-24xl", "metal-48xl"], "c8g": ["medium", "metal-24xl", "metal-48xl"],
    "c8gb": ["medium", "metal-24xl", "metal-48xl"], "c8gd": ["medium", "metal-24xl", "metal-48xl"],
    "c8gn": ["medium", "metal-24xl", "metal-48xl"], "c8i": ["large", "metal-48xl", "metal-96xl"],
    "c8id": ["large", "metal-48xl", "metal-96xl"], "c8in": ["large", "metal-48xl", "metal-96xl"],
    "c8ine": ["large"], "c8ib": ["large", "metal-48xl", "metal-96xl"], "c9g": ["medium", "metal-48xl"],
    "c9gd": ["medium", "metal-48xl"],
    # Memory optimized
    "r5": ["large", "metal"], "r5a": ["large"], "r5ad": ["large"], "r5b": ["large", "metal"],
    "r5d": ["large", "metal"], "r5dn": ["large", "metal"], "r5n": ["large", "metal"],
    "r6a": ["large", "metal"], "r6g": ["medium", "metal"], "r6gd": ["medium", "metal"],
    "r6i": ["large", "metal"], "r6id": ["large", "metal"], "r6idn": ["large", "metal"],
    "r6in": ["large", "metal"], "r7a": ["medium", "large", "metal-48xl"], "r7g": ["medium", "metal"],
    "r7gd": ["medium", "metal"], "r7i": ["large", "metal-24xl", "metal-48xl"],
    "r7iz": ["large", "metal-16xl", "metal-32xl"], "r8a": ["medium", "metal-24xl", "metal-48xl"],
    "r8g": ["medium", "metal-24xl", "metal-48xl"], "r8gb": ["medium", "metal-24xl", "metal-48xl"],
    "r8gd": ["medium", "metal-24xl", "metal-48xl"], "r8gn": ["medium", "metal-24xl", "metal-48xl"],
    "r8i": ["large", "metal-48xl", "metal-96xl"], "r8id": ["large", "metal-48xl", "metal-96xl"],
    "r8in": ["large", "metal-48xl", "metal-96xl"], "r8idn": ["large", "metal-48xl", "metal-96xl"],
    "r8ib": ["large", "metal-48xl", "metal-96xl"], "r8idb": ["large", "metal-48xl", "metal-96xl"],
    "r9g": ["medium", "metal-48xl"], "r9gd": ["medium", "metal-48xl"],
    "x2gd": ["medium", "metal"], "x2idn": ["metal"], "x2iedn": ["metal"], "x2iezn": ["metal"],
    "x8g": ["medium", "metal-24xl", "metal-48xl"], "x8aedz": ["metal-12xl", "metal-24xl"],
    "x8i": ["large", "metal-48xl", "metal-96xl"], "z1d": ["large", "metal"],
}
# EKS sandboxing-limitations: temporarily unavailable on Auto Mode
AUTO_MODE_BLOCKED = {"r5a", "r5ad", "m5ad"}


def prices(region):
    out = {}
    for item in json.load(open(RAW / f"price-raw-{region}.json"))["PriceList"]:
        p = json.loads(item)
        t = p["product"]["attributes"].get("instanceType")
        for term in p.get("terms", {}).get("OnDemand", {}).values():
            for dim in term["priceDimensions"].values():
                usd = float(dim["pricePerUnit"].get("USD", 0))
                if usd > 0:
                    out[t] = usd
    return out


def spec(it):
    fam = it["t"].partition(".")[0]
    return {
        "t": it["t"], "fam": fam, "cat": fam[0], "gen": int("".join(ch for ch in fam[1:] if ch.isdigit())[:1] or 0),
        "vcpu": it["v"], "tpc": it.get("tpc") or 1, "mem": it["m"],
        "arch": "arm64" if "arm64" in it["a"] else "x86_64",
        "eni": it["eni"], "ip": it["ip"], "metal": it["bm"], "autoBlocked": fam in AUTO_MODE_BLOCKED,
    }


def supported(t):
    fam, _, size = t.partition(".")
    return fam in SUPPORTED and size not in SUPPORTED[fam] and "flex" not in fam


def build():
    data = json.loads(OUT.read_text()) if OUT.exists() else {"types": {}, "regions": {}}
    for f in sorted(RAW.glob("types-*.json")):  # specs are the same in every Region; the newest read wins
        for it in json.load(open(f)):
            if supported(it["t"]):
                data["types"][it["t"]] = spec(it)
    for f in sorted(RAW.glob("price-raw-*.json")):
        r = f.name[len("price-raw-"):-len(".json")]
        pr = prices(r)
        offered = {t: pr[t] for t in sorted(pr) if supported(t)}
        missing = [t for t in offered if t not in data["types"]]
        data["regions"][r] = {
            "date": datetime.date.fromtimestamp(f.stat().st_mtime).isoformat(),
            "prices": {t: p for t, p in offered.items() if t in data["types"]},
        }
        print(r, len(data["regions"][r]["prices"]), "types", f"(skipped, no specs: {', '.join(missing)})" if missing else "", file=sys.stderr)
    data["types"] = dict(sorted(data["types"].items()))
    data["regions"] = dict(sorted(data["regions"].items()))
    return data


if __name__ == "__main__":
    data = build()
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print("wrote", OUT, len(data["types"]), "types,", len(data["regions"]), "Regions", file=sys.stderr)
