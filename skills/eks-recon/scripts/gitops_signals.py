#!/usr/bin/env python3
"""Extract GitOps tracking evidence from a successful Kubernetes List read.

Metadata is evidence of tracking, not proof of a live hub or reconciliation.
This helper never declares GitOps absent and does not hide collection failures.
"""

import argparse
import json
import sys


ARGO_TRACKING = "argocd.argoproj.io/tracking-id"
INSTANCE_LABEL = "app.kubernetes.io/instance"
FLUX_NAME = "kustomize.toolkit.fluxcd.io/name"
FLUX_NAMESPACE = "kustomize.toolkit.fluxcd.io/namespace"
SHARED_PREFIXES = ("app.kubernetes.io/", "helm.sh/",
                   "kustomize.toolkit.fluxcd.io/", "helm.toolkit.fluxcd.io/")
SAMPLES_PER_GROUP = 3
WARNING_SAMPLES = 5
DISPLAY_CHARS = 256
LABEL_KEY_CHARS = 317


def text(value):
    return isinstance(value, str) and bool(value.strip())


def display(record):
    """Bound displayed strings, retaining lengths instead of silently clipping."""
    shortened = {}

    def bound(value, path):
        limit = LABEL_KEY_CHARS if path == "key" else DISPLAY_CHARS
        if isinstance(value, str) and len(value) > limit:
            shortened[path] = len(value)
            marker = "...[truncated]"
            return value[:limit - len(marker)] + marker
        if isinstance(value, dict):
            return {key: bound(item, f"{path}.{key}" if path else key)
                    for key, item in value.items()}
        return value

    result = bound(record, "")
    if shortened:
        result["truncated_fields"] = shortened
    return result


def collect(inventory, instance_label_key=None, full_evidence=False, cluster_scoped=False):
    """Return evidence only; the caller retains API scope and coverage errors."""
    if not isinstance(inventory, dict) or not isinstance(inventory.get("items"), list):
        raise ValueError("Expected a successful Kubernetes List with an items array")
    groups = {}
    warnings = []
    warning_count = 0
    scanned = 0

    def warn(message):
        nonlocal warning_count
        warning_count += 1
        if full_evidence or len(warnings) < WARNING_SAMPLES:
            warnings.append(message)

    if instance_label_key and len(instance_label_key) > LABEL_KEY_CHARS:
        warn("Configured custom label key exceeds Kubernetes' 317-character limit; custom key ignored")
        instance_label_key = None

    for index, resource in enumerate(inventory["items"]):
        if not isinstance(resource, dict) or not isinstance(resource.get("metadata"), dict):
            warn(f"items[{index}]: missing resource metadata")
            continue
        metadata = resource["metadata"]
        name = metadata.get("name")
        namespace = metadata.get("namespace", "")
        kind = resource.get("kind")
        version = resource.get("apiVersion")
        if not all(text(v) for v in (name, kind, version)) or not isinstance(namespace, str):
            warn(f"items[{index}]: incomplete resource identity")
            continue
        if (not namespace and not cluster_scoped) or (namespace and cluster_scoped):
            warn(f"items[{index}]: namespace and confirmed API scope disagree or are missing")
            continue
        scanned += 1
        labels = metadata.get("labels")
        annotations = metadata.get("annotations")
        labels = {} if labels is None else labels
        annotations = {} if annotations is None else annotations
        if not isinstance(labels, dict) or not isinstance(annotations, dict):
            warn(f"items[{index}]: invalid labels or annotations")
            continue

        def emit(tool, signal, key, value, strength):
            group_key = (tool, signal, strength, key)
            group = groups.setdefault(group_key, {"tool": tool, "signal": signal,
                                      "strength": strength, "key": key, "count": 0, "samples": []})
            group["count"] += 1
            if full_evidence or len(group["samples"]) < SAMPLES_PER_GROUP:
                record = {"tool": tool, "signal": signal, "kind": kind,
                          "namespace": namespace, "name": name,
                          "key": key, "value": value, "strength": strength}
                group["samples"].append(record if full_evidence else display(record))

        tracking = annotations.get(ARGO_TRACKING)
        if text(tracking):
            group = version.rsplit("/", 1)[0] if "/" in version else ""
            parts = tracking.split(":")
            target = parts[2].split("/") if len(parts) == 3 else []
            self_reference = (len(parts) == 3 and text(parts[0])
                              and parts[1] == f"{group}/{kind}"
                              and len(target) == 2 and target[1] == name
                              and (cluster_scoped or target[0] == namespace))
            emit("argocd", "tracking_annotation" if self_reference else "unverified_tracking_annotation",
                 ARGO_TRACKING, tracking, "specific" if self_reference else "ambiguous")
        elif tracking is not None and not isinstance(tracking, str):
            warn(f"items[{index}]: non-string tracking-id annotation")
        label_keys = {INSTANCE_LABEL}
        if instance_label_key:
            label_keys.add(instance_label_key)
        for key in sorted(label_keys):
            value = labels.get(key)
            if text(value):
                # A supplied key must designate dedicated Argo tracking for this
                # target. Qualification is necessary here, not proof of that
                # provenance; shared labels remain ambiguous even when supplied.
                custom = (key == instance_label_key and "/" in key
                          and not key.startswith(SHARED_PREFIXES))
                emit("argocd" if custom else None,
                     "configured_tracking_label" if custom else
                     "shared_instance_label" if key == INSTANCE_LABEL else "ambiguous_tracking_label",
                     key, value, "specific" if custom else "ambiguous")
        flux_name = labels.get(FLUX_NAME)
        flux_namespace = labels.get(FLUX_NAMESPACE)
        if text(flux_name) or text(flux_namespace):
            complete = text(flux_name) and text(flux_namespace)
            emit("flux", "kustomization_labels", FLUX_NAME,
                 {"name": flux_name, "namespace": flux_namespace},
                 "specific" if complete else "ambiguous")
    evidence = [sample for group in groups.values() for sample in group["samples"]]
    counts = [{key: value for key, value in group.items() if key != "samples"}
              for group in groups.values()]
    count = sum(group["count"] for group in groups.values())
    return {"resources_scanned": scanned,
            "tools_with_tracking": sorted({g["tool"] for g in groups.values() if g["strength"] == "specific"}),
            "evidence_counts": counts if full_evidence else [display(group) for group in counts],
            "evidence_count": count, "evidence": evidence,
            "evidence_sample_limit_per_group": None if full_evidence else SAMPLES_PER_GROUP,
            "evidence_sampled": count > len(evidence),
            "warning_count": warning_count, "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", nargs="?", default="-", help="Kubernetes List JSON file, or - for stdin")
    parser.add_argument("--argocd-instance-label-key", help="Confirmed dedicated, qualified Argo key for this target; do not pass shared/colliding keys")
    parser.add_argument("--cluster-scoped", action="store_true", help="Single-kind inventory confirmed cluster-scoped by API discovery/request context")
    parser.add_argument("--full-evidence", action="store_true", help="Explicit full export; save to a separate file instead of model context")
    args = parser.parse_args()
    try:
        if args.inventory == "-":
            inventory = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
        else:
            with open(args.inventory, encoding="utf-8-sig") as source:
                inventory = json.load(source)
        print(json.dumps(collect(inventory, args.argocd_instance_label_key,
                                 args.full_evidence, args.cluster_scoped), indent=2))
    except (OSError, ValueError) as error:
        parser.exit(2, f"GitOps inventory unavailable: {error}\n")


if __name__ == "__main__":
    main()
