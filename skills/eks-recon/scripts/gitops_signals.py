#!/usr/bin/env python3
"""Extract GitOps tracking evidence from a successful Kubernetes List read.

Metadata is evidence of tracking, not proof of a live hub or reconciliation.
This helper never declares GitOps absent and does not hide collection failures.
"""

import argparse
import json
import sys


ARGO_TRACKING = "argocd.argoproj.io/tracking-id"
ARGO_PREFIX = "argocd.argoproj.io/"
INSTANCE_LABEL = "app.kubernetes.io/instance"
FLUX_NAME = "kustomize.toolkit.fluxcd.io/name"
FLUX_NAMESPACE = "kustomize.toolkit.fluxcd.io/namespace"
SAMPLES_PER_GROUP = 3
WARNING_SAMPLES = 5
DISPLAY_CHARS = 256
LABEL_KEY_CHARS = 317


def text(value):
    return isinstance(value, str) and bool(value.strip())


def display(value, limit=DISPLAY_CHARS):
    """Shorten examples only, after classification of the original values."""
    if isinstance(value, str) and len(value) > limit:
        marker = "...[truncated]"
        return value[:limit - len(marker)] + marker
    if isinstance(value, dict):
        return {key: display(item, LABEL_KEY_CHARS if key == "key" else DISPLAY_CHARS)
                for key, item in value.items()}
    return value


def collect(inventory, instance_label_key=None, cluster_scoped=False):
    """Return evidence only; the caller retains API scope and coverage errors."""
    if not isinstance(inventory, dict) or not isinstance(inventory.get("items"), list):
        raise ValueError("Expected a successful Kubernetes List with an items array")
    groups = {}
    warnings = []
    warning_count = 0
    scanned = 0
    sampled = False

    def warn(message):
        nonlocal warning_count
        warning_count += 1
        if len(warnings) < WARNING_SAMPLES:
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
        if not isinstance(labels, dict):
            warn(f"items[{index}]: invalid labels")
            labels = {}
        if not isinstance(annotations, dict):
            warn(f"items[{index}]: invalid annotations")
            annotations = {}

        def emit(tool, signal, key, value, strength, corroboration=None):
            nonlocal sampled
            # Wildcard annotation names share one bounded evidence family.
            group_key = (tool, signal, strength, ARGO_PREFIX if signal == "unverified_argocd_annotation" else key)
            samples = groups.setdefault(group_key, [])
            if len(samples) < SAMPLES_PER_GROUP:
                record = {"tool": tool, "signal": signal, "kind": kind,
                          "namespace": namespace, "name": name,
                          "key": key, "value": value, "strength": strength}
                if corroboration:
                    record["corroboration"] = {"key": corroboration, "value": "present"}
                samples.append(display(record))
            else:
                sampled = True

        tracking = annotations.get(ARGO_TRACKING)
        self_reference = False
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
        elif ARGO_TRACKING in annotations:
            warn(f"items[{index}]: empty or non-string tracking-id annotation")
        # Other Argo annotations corroborate a label on THIS resource only.
        # Record presence, never their values (which may contain application data).
        corroboration = ARGO_TRACKING if self_reference else None
        for key, value in annotations.items():
            if isinstance(key, str) and key.startswith(ARGO_PREFIX) and key != ARGO_TRACKING:
                if not isinstance(value, str):
                    warn(f"items[{index}]: non-string Argo annotation")
                elif text(value) and corroboration is None:
                    corroboration = key
        if corroboration and not self_reference and not text(labels.get(INSTANCE_LABEL)):
            emit("argocd", "unverified_argocd_annotation", corroboration, "present", "ambiguous")
        label_keys = {INSTANCE_LABEL}
        if instance_label_key:
            label_keys.add(instance_label_key)
        for key in sorted(label_keys):
            value = labels.get(key)
            if text(value):
                # The caller confirms target-linked tracking configuration;
                # unprefixed keys require an explicit user-supplied key.
                configured = key == instance_label_key
                corroborated = key == INSTANCE_LABEL and corroboration is not None
                emit("argocd" if configured or corroborated else None,
                     "configured_tracking_label" if configured else
                     "corroborated_instance_label" if corroborated else
                     "shared_instance_label" if key == INSTANCE_LABEL else "ambiguous_tracking_label",
                     key, value, "specific" if configured or corroborated else "ambiguous",
                     corroboration if corroborated and not configured else None)
            elif key in labels and not isinstance(value, str):
                warn(f"items[{index}]: non-string instance label")
        flux_name = labels.get(FLUX_NAME)
        flux_namespace = labels.get(FLUX_NAMESPACE)
        if any(key in labels and not isinstance(labels[key], str)
               for key in (FLUX_NAME, FLUX_NAMESPACE)):
            warn(f"items[{index}]: non-string Flux label")
        if text(flux_name) or text(flux_namespace):
            complete = text(flux_name) and text(flux_namespace)
            emit("flux", "kustomization_labels", FLUX_NAME,
                 {"name": flux_name if text(flux_name) else None,
                  "namespace": flux_namespace if text(flux_namespace) else None},
                 "specific" if complete else "ambiguous")
    return {"resources_scanned": scanned,
            "tools_with_tracking": sorted({tool for tool, _, strength, _ in groups if strength == "specific"}),
            "evidence": [sample for samples in groups.values() for sample in samples],
            "evidence_sampled": sampled,
            "warning_count": warning_count, "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", nargs="?", default="-", help="Kubernetes List JSON file, or - for stdin")
    parser.add_argument("--argocd-instance-label-key", help="Confirmed Argo tracking key for this target; unprefixed keys must be user-supplied")
    parser.add_argument("--cluster-scoped", action="store_true", help="Single-kind inventory confirmed cluster-scoped by API discovery/request context")
    args = parser.parse_args()
    try:
        if args.inventory == "-":
            inventory = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
        else:
            with open(args.inventory, encoding="utf-8-sig") as source:
                inventory = json.load(source)
        print(json.dumps(collect(inventory, args.argocd_instance_label_key,
                                 args.cluster_scoped), indent=2))
    except (OSError, ValueError) as error:
        parser.exit(2, f"GitOps inventory unavailable: {error}\n")


if __name__ == "__main__":
    main()
