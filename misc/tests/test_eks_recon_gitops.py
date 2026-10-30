"""Offline GitOps fixtures for the metadata extractor and runtime schema.

Expected values are hand-authored from the documented Argo tracking format and
Flux Kustomization labels. These tests do not prove live reconciliation or a
complete inventory of every resource kind/GitOps product.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/eks-recon/scripts/gitops_signals.py"
spec = importlib.util.spec_from_file_location("gitops_signals", SCRIPT)
signals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(signals)


def resource(kind="Deployment", version="apps/v1", namespace="team", name="web", labels=None, annotations=None):
    return {"apiVersion": version, "kind": kind,
            "metadata": {"name": name, "namespace": namespace, "labels": labels, "annotations": annotations}}


def collect(*items, key=None, cluster_scoped=False):
    return signals.collect({"items": list(items)}, key, cluster_scoped)


class TrackingFixtures(unittest.TestCase):
    def test_annotation_only_spoke(self):
        result = collect(resource(annotations={signals.ARGO_TRACKING: "shop:apps/Deployment:team/web"}))
        self.assertEqual(result["tools_with_tracking"], ["argocd"])
        self.assertEqual(result["evidence"][0]["signal"], "tracking_annotation")
        self.assertEqual(result["evidence"][0]["name"], "web")

    def test_core_resource_annotation(self):
        result = collect(resource("ConfigMap", "v1", annotations={signals.ARGO_TRACKING: "shop:/ConfigMap:team/web"}))
        self.assertEqual(result["tools_with_tracking"], ["argocd"])

    def test_cluster_scoped_annotation(self):
        result = collect(resource("Namespace", "v1", "", "team", annotations={signals.ARGO_TRACKING: "shop:/Namespace:/team"}), cluster_scoped=True)
        self.assertEqual(result["tools_with_tracking"], ["argocd"])

    def test_cluster_scope_allows_tracking_destination_namespace(self):
        # Argo v3.5.6 isSelfReferencedObj ignores the namespace comparison for
        # actual cluster-scoped objects. API/discovery supplies that scope.
        for kind, version, group in (("Namespace", "v1", ""), ("ClusterRole", "rbac.authorization.k8s.io/v1", "rbac.authorization.k8s.io")):
            with self.subTest(kind=kind):
                item = resource(kind, version, "", "team", annotations={signals.ARGO_TRACKING: f"shop:{group}/{kind}:destination/team"})
                self.assertEqual(collect(item, cluster_scoped=True)["tools_with_tracking"], ["argocd"])

    def test_cluster_scope_still_requires_group_kind_name(self):
        for tracking in ("shop:/Namespace:destination/other", "shop:/Node:destination/team", "shop:other/Namespace:destination/team"):
            with self.subTest(tracking=tracking):
                item = resource("Namespace", "v1", "", "team", annotations={signals.ARGO_TRACKING: tracking})
                self.assertEqual(collect(item, cluster_scoped=True)["tools_with_tracking"], [])

    def test_missing_namespace_requires_confirmed_scope(self):
        item = resource("Namespace", "v1", "", "team", annotations={signals.ARGO_TRACKING: "shop:/Namespace:destination/team"})
        result = collect(item)
        self.assertEqual(result["tools_with_tracking"], [])
        self.assertEqual(result["warning_count"], 1)

    def test_scope_flag_cannot_override_namespaced_object(self):
        item = resource(annotations={signals.ARGO_TRACKING: "shop:apps/Deployment:team/web"})
        result = collect(item, cluster_scoped=True)
        self.assertEqual(result["tools_with_tracking"], [])
        self.assertEqual(result["warning_count"], 1)

    def test_copied_annotations_are_ambiguous(self):
        for value in ("shop:apps/Deployment:other/web", "shop:apps/Deployment:team/other",
                      "shop:apps/StatefulSet:team/web", "shop:other/Deployment:team/web"):
            with self.subTest(value=value):
                result = collect(resource(annotations={signals.ARGO_TRACKING: value}))
                self.assertEqual(result["tools_with_tracking"], [])
                self.assertEqual(result["evidence"][0]["strength"], "ambiguous")

    def test_malformed_tracking_values(self):
        for value in ("app", ":apps/Deployment:team/web", "app:apps/Deployment:team/web:extra"):
            with self.subTest(value=value):
                result = collect(resource(annotations={signals.ARGO_TRACKING: value}))
                self.assertEqual(result["tools_with_tracking"], [])
                self.assertEqual(len(result["evidence"]), 1)

    def test_shared_instance_label_is_not_argo_proof(self):
        result = collect(resource(labels={signals.INSTANCE_LABEL: "helm-or-any-tool"}))
        self.assertEqual(result["tools_with_tracking"], [])
        self.assertIsNone(result["evidence"][0]["tool"])
        self.assertEqual(result["evidence"][0]["strength"], "ambiguous")

    def test_user_confirmed_default_label_tracking(self):
        result = collect(resource(labels={signals.INSTANCE_LABEL: "shop"}), key=signals.INSTANCE_LABEL)
        self.assertEqual(result["tools_with_tracking"], ["argocd"])
        self.assertEqual(result["evidence"][0]["signal"], "configured_tracking_label")
        self.assertEqual(len(result["evidence"]), 1)

    def test_addon_name_does_not_exempt_tracking_signals(self):
        item = resource("DaemonSet", "apps/v1", "kube-system", "aws-node",
                        labels={signals.INSTANCE_LABEL: "aws-vpc-cni"})
        self.assertEqual(collect(item)["evidence"][0]["strength"], "ambiguous")
        item["metadata"]["annotations"] = {
            signals.ARGO_TRACKING: "addons:apps/DaemonSet:kube-system/aws-node"}
        self.assertEqual(collect(item)["tools_with_tracking"], ["argocd"])

    def test_annotation_plus_shared_label(self):
        result = collect(resource(labels={signals.INSTANCE_LABEL: "shop"},
                                  annotations={signals.ARGO_TRACKING: "shop:apps/Deployment:team/web"}))
        self.assertEqual(result["tools_with_tracking"], ["argocd"])
        self.assertEqual({e["strength"] for e in result["evidence"]}, {"specific"})

    def test_confirmed_custom_label(self):
        result = collect(resource(labels={"team.example/argo": "shop"}), key="team.example/argo")
        self.assertEqual(result["tools_with_tracking"], ["argocd"])
        self.assertEqual(result["evidence"][0]["key"], "team.example/argo")

    def test_unknown_custom_label_is_not_guessed(self):
        result = collect(resource(labels={"team.example/argo": "shop"}))
        self.assertEqual(result["tools_with_tracking"], [])
        self.assertEqual(result["evidence"], [])

    def test_explicit_tracking_key_is_not_rejected_by_prefix(self):
        # A target-linked user statement is the provenance, not the key spelling.
        for key in ("app.kubernetes.io/name", "helm.sh/chart", "argocd-instance"):
            with self.subTest(key=key):
                result = collect(resource(labels={key: "ordinary-value"}), key=key)
                self.assertEqual(result["tools_with_tracking"], ["argocd"])
                self.assertEqual(result["evidence"][0]["strength"], "specific")
                self.assertEqual(result["evidence"][0]["key"], key)
                self.assertEqual(collect(resource(labels={key: "ordinary-value"}))["tools_with_tracking"], [])

    def test_explicit_colliding_key_preserves_both_tools(self):
        result = collect(resource(labels={signals.FLUX_NAME: "apps", signals.FLUX_NAMESPACE: "hub"}), key=signals.FLUX_NAME)
        self.assertEqual(result["tools_with_tracking"], ["argocd", "flux"])

    def test_chart_annotations_do_not_corroborate_shared_label(self):
        label = {signals.INSTANCE_LABEL: "shop"}
        for key in ("sync-wave", "sync-options", "installation-id"):
            annotation = {signals.ARGO_PREFIX + key: "present"}
            for custom_key in (None, "example.com/instance"):
                with self.subTest(annotation=key, custom_key=custom_key):
                    matched = collect(resource(labels=label, annotations=annotation), key=custom_key)
                    self.assertEqual(matched["tools_with_tracking"], [])
                    self.assertEqual({e["signal"] for e in matched["evidence"]},
                                     {"unverified_argocd_annotation", "shared_instance_label"})
                    self.assertTrue(all(e["strength"] == "ambiguous" and
                                        "corroboration" not in e for e in matched["evidence"]))
        annotation = {signals.ARGO_TRACKING: "shop:apps/Deployment:team/web"}
        for custom_key in (None, "example.com/instance"):
            with self.subTest(custom_key=custom_key):
                matched = collect(resource(labels=label, annotations=annotation), key=custom_key)
                self.assertEqual(matched["tools_with_tracking"], ["argocd"])
                self.assertEqual(matched["evidence"][-1]["corroboration"],
                                 {"key": signals.ARGO_TRACKING, "value": "present"})
                separate = collect(resource(labels=label), resource(name="other", annotations=annotation), key=custom_key)
                self.assertEqual(separate["tools_with_tracking"], [])
                self.assertEqual(collect(resource(annotations=annotation), key=custom_key)["tools_with_tracking"], ["argocd"])
                self.assertEqual(collect(resource(labels=label), key=custom_key)["tools_with_tracking"], [])


    def test_standalone_argo_annotation_is_ambiguous_and_private(self):
        key = "argocd.argoproj.io/sync-wave"
        marker = "PRIVATE_ANNOTATION_VALUE"
        for extra in ({}, {signals.ARGO_TRACKING: "invalid"}):
            with self.subTest(extra=extra):
                result = collect(resource(annotations={key: marker, **extra}))
                self.assertEqual(result["tools_with_tracking"], [])
                weak = [e for e in result["evidence"] if e["signal"] == "unverified_argocd_annotation"]
                self.assertEqual(len(weak), 1)
                self.assertEqual((weak[0]["key"], weak[0]["value"], weak[0]["strength"]),
                                 (key, "present", "ambiguous"))
                self.assertNotIn(marker, json.dumps(result))
        positive = collect(resource(labels={"my-key": "shop"}, annotations={key: marker}), key="my-key")
        self.assertEqual(positive["tools_with_tracking"], ["argocd"])

    def test_many_standalone_annotation_keys_are_bounded_and_keep_late_positive(self):
        items = [resource(name=f"web-{i}", annotations={f"argocd.argoproj.io/key-{i}": "private"})
                 for i in range(1000)]
        items.append(resource(name="last", labels={signals.FLUX_NAME: "apps", signals.FLUX_NAMESPACE: "hub"}))
        result = collect(*items)
        self.assertEqual(result["resources_scanned"], 1001)
        self.assertEqual(result["tools_with_tracking"], ["flux"])
        self.assertEqual(len(result["evidence"]), 4)
        self.assertTrue(result["evidence_sampled"])
        self.assertLess(len(json.dumps(result)), 5000)
        self.assertNotIn("private", json.dumps(result))

    def test_invalid_tracking_does_not_corroborate_shared_label(self):
        for value in ("copied:apps/Deployment:other/web", "malformed", "", " ", 42):
            with self.subTest(value=value):
                result = collect(resource(labels={signals.INSTANCE_LABEL: "shop"},
                                          annotations={signals.ARGO_TRACKING: value}))
                self.assertEqual(result["tools_with_tracking"], [])

    def test_empty_or_nonstring_argo_annotation_does_not_corroborate(self):
        for value in ("", " ", None, 42, {}):
            with self.subTest(value=value):
                result = collect(resource(labels={signals.INSTANCE_LABEL: "shop"},
                                          annotations={"argocd.argoproj.io/sync-wave": value}))
                self.assertEqual(result["tools_with_tracking"], [])

    def test_unrelated_metadata_values_are_not_disclosed(self):
        marker = "PRIVATE_CONFIGMAP_BODY"
        item = resource(labels={signals.INSTANCE_LABEL: "shop", "internal-data": marker}, annotations={
            "kubectl.kubernetes.io/last-applied-configuration": marker,
            "argocd.argoproj.io/sync-options": marker,
            "private.example/notes": marker})
        result = collect(item)
        self.assertEqual(result["tools_with_tracking"], [])
        self.assertNotIn(marker, json.dumps(result))

    def test_many_chart_annotation_keys_do_not_expand_sample_groups(self):
        items = [resource(name=f"web-{i}", labels={signals.INSTANCE_LABEL: "shop"},
                          annotations={f"argocd.argoproj.io/key-{i}": "present"}) for i in range(1000)]
        result = collect(*items)
        self.assertEqual(result["resources_scanned"], 1000)
        self.assertEqual(len(result["evidence"]), 6)  # Three per bounded signal family.
        self.assertTrue(result["evidence_sampled"])

    def test_metadata_only_identity_requires_request_context(self):
        item = resource("PartialObjectMetadata", "meta.k8s.io/v1",
                        annotations={signals.ARGO_TRACKING: "shop:apps/Deployment:team/web"})
        self.assertEqual(collect(item)["tools_with_tracking"], [])
        # The API request/discovery supplied this identity, not the annotation.
        item.update({"kind": "Deployment", "apiVersion": "apps/v1"})
        self.assertEqual(collect(item)["tools_with_tracking"], ["argocd"])

    def test_no_invented_tracking_annotation(self):
        result = collect(resource(annotations={signals.INSTANCE_LABEL: "shop"}))
        self.assertEqual(result["evidence"], [])

    def test_flux_pair(self):
        result = collect(resource(labels={signals.FLUX_NAME: "apps", signals.FLUX_NAMESPACE: "hub"}))
        self.assertEqual(result["tools_with_tracking"], ["flux"])
        self.assertEqual(result["evidence"][0]["value"], {"name": "apps", "namespace": "hub"})

    def test_partial_flux_pair(self):
        for labels in ({signals.FLUX_NAME: "apps"}, {signals.FLUX_NAMESPACE: "hub"},
                       {signals.FLUX_NAME: "apps", signals.FLUX_NAMESPACE: ""}):
            with self.subTest(labels=labels):
                result = collect(resource(labels=labels))
                self.assertEqual(result["tools_with_tracking"], [])
                self.assertEqual(result["evidence"][0]["strength"], "ambiguous")

    def test_mixed_tools_and_generic_labels(self):
        result = collect(resource(annotations={signals.ARGO_TRACKING: "shop:apps/Deployment:team/web"}),
                         resource(labels={signals.FLUX_NAME: "apps", signals.FLUX_NAMESPACE: "hub"}),
                         resource(labels={signals.INSTANCE_LABEL: "manual"}))
        self.assertEqual(result["tools_with_tracking"], ["argocd", "flux"])
        self.assertEqual(len(result["evidence"]), 3)

    def test_missing_null_empty_metadata(self):
        for labels, annotations in ((None, None), ({}, {})):
            with self.subTest(labels=labels):
                result = collect(resource(labels=labels, annotations=annotations))
                self.assertEqual(result["resources_scanned"], 1)
                self.assertEqual(result["evidence"], [])

    def test_bad_entry_does_not_hide_later_match(self):
        good = resource(annotations={signals.ARGO_TRACKING: "shop:apps/Deployment:team/web"})
        result = collect(None, {}, {"metadata": {}}, resource(labels=[]), resource(labels=0), good)
        self.assertEqual(result["tools_with_tracking"], ["argocd"])
        self.assertEqual(len(result["warnings"]), 5)

    def test_empty_successful_list_is_evidence_only(self):
        result = collect()
        self.assertEqual(result, {"resources_scanned": 0, "tools_with_tracking": [], "evidence": [],
                                 "evidence_sampled": False, "warning_count": 0, "warnings": []})
        self.assertNotIn("detected", result)

    def test_large_inventory_scans_all_and_keeps_late_flux(self):
        argo = [resource(name=f"web-{i}", annotations={signals.ARGO_TRACKING: f"shop:apps/Deployment:team/web-{i}"}) for i in range(1000)]
        generic = [resource(name=f"chart-{i}", labels={signals.INSTANCE_LABEL: f"release-{i}"}) for i in range(1000)]
        late_flux = resource(name="last", labels={signals.FLUX_NAME: "apps", signals.FLUX_NAMESPACE: "hub"})
        result = collect(*argo, *generic, late_flux)
        self.assertEqual(result["resources_scanned"], 2001)
        self.assertEqual(result["tools_with_tracking"], ["argocd", "flux"])
        self.assertEqual(len(result["evidence"]), 7)
        self.assertTrue(result["evidence_sampled"])
        self.assertLess(len(json.dumps(result)), 12000)

    def test_large_malformed_annotation_sample_is_bounded(self):
        value = "not-a-tracking-reference" * 10000
        result = collect(resource(annotations={signals.ARGO_TRACKING: value}))
        self.assertEqual(result["tools_with_tracking"], [])
        self.assertTrue(result["evidence"][0]["value"].endswith("[truncated]"))
        self.assertLessEqual(len(result["evidence"][0]["value"]), signals.DISPLAY_CHARS)
        self.assertLess(len(json.dumps(result)), 3000)

    def test_long_qualified_keys_preserve_evidence_identity(self):
        prefix = ".".join(["a" * 63] * 3 + ["a" * 61])
        keys = [prefix + "/" + suffix * 63 for suffix in ("x", "y")]
        evidence = []
        for key in keys:
            self.assertEqual(len(key), 317)
            result = collect(resource(labels={key: "shop"}), key=key)
            self.assertEqual(result["evidence"][0]["key"], key)
            evidence.append(result["evidence"][0])
        self.assertNotEqual(*evidence)

    def test_oversized_custom_key_does_not_hide_standard_signals(self):
        key = "a" * 318
        result = collect(resource(labels={key: "shop", signals.FLUX_NAME: "apps", signals.FLUX_NAMESPACE: "flux-system"}), key=key)
        self.assertEqual(result["tools_with_tracking"], ["flux"])
        self.assertEqual(result["warning_count"], 1)
        self.assertNotIn(key, json.dumps(result))

    def test_classification_uses_original_not_shortened_sample(self):
        name = ".".join(["x" * 60] * 4)
        value = f"shop:apps/Deployment:team/{name}"
        result = collect(resource(name=name, annotations={signals.ARGO_TRACKING: value}))
        self.assertEqual(result["tools_with_tracking"], ["argocd"])
        self.assertTrue(result["evidence"][0]["value"].endswith("[truncated]"))

    def test_warning_samples_are_bounded_without_losing_positive(self):
        item = resource(annotations={signals.ARGO_TRACKING: "shop:apps/Deployment:team/web"})
        result = collect(*([None] * 1000), item)
        self.assertEqual(result["warning_count"], 1000)
        self.assertEqual(len(result["warnings"]), 5)
        self.assertEqual(result["tools_with_tracking"], ["argocd"])

    def test_late_specific_annotation_survives_ambiguous_samples(self):
        ambiguous = resource(annotations={signals.ARGO_TRACKING: "copied:/ConfigMap:elsewhere/other"})
        positive = resource(annotations={signals.ARGO_TRACKING: "shop:apps/Deployment:team/web"})
        result = collect(*([ambiguous] * 1000), positive)
        self.assertEqual(result["tools_with_tracking"], ["argocd"])
        self.assertEqual([e["strength"] for e in result["evidence"]], ["ambiguous"] * 3 + ["specific"])

    def test_malformed_metadata_field_preserves_other_positive(self):
        argo = resource(labels=[], annotations={signals.ARGO_TRACKING: "shop:apps/Deployment:team/web"})
        flux = resource(annotations=[], labels={signals.FLUX_NAME: "apps", signals.FLUX_NAMESPACE: "hub"})
        result = collect(argo, flux)
        self.assertEqual(result["tools_with_tracking"], ["argocd", "flux"])
        self.assertEqual(result["warning_count"], 2)

    def test_malformed_flux_value_is_ambiguous_and_bounded(self):
        result = collect(resource(labels={signals.FLUX_NAME: "apps", signals.FLUX_NAMESPACE: ["x" * 1000] * 1000}))
        self.assertEqual(result["tools_with_tracking"], [])
        self.assertEqual(result["warning_count"], 1)
        self.assertEqual(result["evidence"][0]["value"], {"name": "apps", "namespace": None})
        self.assertLess(len(json.dumps(result)), 3000)

    def test_empty_or_non_string_tracking_annotation_warns(self):
        self.assertEqual(collect(resource())["warning_count"], 0)
        for value in ("", " ", 123, None, {}):
            with self.subTest(value=value):
                result = collect(resource(annotations={signals.ARGO_TRACKING: value}))
                self.assertEqual(result["warning_count"], 1)
                self.assertEqual(result["tools_with_tracking"], [])
                positive = collect(resource(
                    annotations={signals.ARGO_TRACKING: value},
                    labels={"appInstance": "shop", signals.FLUX_NAME: "apps",
                            signals.FLUX_NAMESPACE: "hub"}), key="appInstance")
                self.assertEqual(positive["tools_with_tracking"], ["argocd", "flux"])

    def test_malformed_signal_values_cannot_look_like_clean_no_match(self):
        for key in (signals.INSTANCE_LABEL, signals.FLUX_NAME, signals.FLUX_NAMESPACE, "my-argo-key"):
            for value in (None, [], {}, 42):
                with self.subTest(key=key, value=value):
                    result = collect(resource(labels={key: value}), key=key if key == "my-argo-key" else None)
                    self.assertGreater(result["warning_count"], 0)
                    self.assertEqual(result["tools_with_tracking"], [])
        both = collect(resource(labels={signals.FLUX_NAME: [], signals.FLUX_NAMESPACE: 42}))
        self.assertGreater(both["warning_count"], 0)

    def test_malformed_label_does_not_erase_other_positive(self):
        result = collect(resource(labels={signals.INSTANCE_LABEL: {}},
                                  annotations={signals.ARGO_TRACKING: "shop:apps/Deployment:team/web"}))
        self.assertEqual(result["tools_with_tracking"], ["argocd"])
        self.assertGreater(result["warning_count"], 0)

    def test_malformed_argo_annotation_warns(self):
        for value in (None, 42, {}):
            with self.subTest(value=value):
                result = collect(resource(annotations={"argocd.argoproj.io/sync-wave": value}))
                self.assertEqual(result["warning_count"], 1)
                self.assertEqual(result["tools_with_tracking"], [])

    def test_invalid_inventory_is_not_empty_success(self):
        for value in (None, [], {}, {"items": None}, {"items": {}}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                signals.collect(value)

    def test_input_is_not_modified(self):
        inventory = {"items": [resource(labels={signals.INSTANCE_LABEL: "manual"})]}
        original = copy.deepcopy(inventory)
        signals.collect(inventory)
        self.assertEqual(inventory, original)

    def test_only_top_level_tracking_counts(self):
        item = resource()
        item["spec"] = {"template": {"metadata": {"annotations": {signals.ARGO_TRACKING: "shop:apps/Deployment:team/web"}}}}
        self.assertEqual(collect(item)["evidence"], [])


@unittest.skipUnless(shutil.which("jq"), "jq required for controller projection checks")
class ControllerProjection(unittest.TestCase):
    def project(self, inventory):
        reference = (ROOT / "skills/eks-recon/references/cicd.md").read_text(encoding="utf-8")
        query = re.search(r"kubectl get deployments -A -o json \| jq '\n(.*?)'\n", reference, re.S).group(1)
        return subprocess.run(["jq", query], input=json.dumps(inventory), capture_output=True, text=True)

    def test_private_fields_do_not_reach_controller_output(self):
        item = resource(annotations={"kubectl.kubernetes.io/last-applied-configuration": "PRIVATE_BODY"},
                        labels={"internal": "PRIVATE_LABEL"})
        item["spec"] = {"template": {"spec": {"containers": [{
            "image": "quay.io/argoproj/argocd:v3.5.6", "command": ["/PRIVATE_PATH/argocd-server"],
            "args": ["PRIVATE_ARG"], "env": [{"name": "TOKEN", "value": "PRIVATE_ENV"}]}]}}}
        result = self.project({"items": [item]})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("PRIVATE", result.stdout)
        observed = json.loads(result.stdout)["items"][0]
        self.assertEqual((observed["kind"], observed["namespace"], observed["name"]),
                         ("Deployment", "team", "web"))
        self.assertEqual(observed["containers"][0]["executable"], "argocd-server")

    def test_default_command_and_unknown_override_remain_distinct(self):
        for command, expected in ((None, "image-default"), ([], "image-default"),
                                  (["sh", "-c", "PRIVATE_SCRIPT"], "other"),
                                  (["argocd", "version", "--client"], "other"),
                                  (["/usr/local/bin/source-controller"], "source-controller")):
            with self.subTest(command=command):
                item = resource()
                item["spec"] = {"template": {"spec": {"containers": [{"image": "controller:v1", "command": command}]}}}
                result = self.project({"items": [item]})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["items"][0]["containers"][0]["executable"], expected)
                self.assertNotIn("PRIVATE", result.stdout)

    def test_argo_default_entrypoint_accepts_only_known_executable_argument(self):
        for command, args, expected in ((None, ["/usr/local/bin/argocd-server", "PRIVATE"], "argocd-server"),
                                        (None, ["--PRIVATE_TOKEN"], "image-default"),
                                        (["sh"], ["argocd-server", "PRIVATE"], "other")):
            with self.subTest(command=command, args=args):
                item = resource()
                item["spec"] = {"template": {"spec": {"containers": [{
                    "image": "quay.io/argoproj/argocd:v3.5.6", "command": command, "args": args}]}}}
                result = self.project({"items": [item]})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["items"][0]["containers"][0]["executable"], expected)
                self.assertNotIn("PRIVATE", result.stdout)

    def test_continuation_and_late_items_are_preserved(self):
        items = []
        for i in range(20):
            item = resource(name=f"web-{i}")
            item["spec"] = {"template": {"spec": {"containers": [{"image": f"image-{i}"}]}}}
            items.append(item)
        result = self.project({"metadata": {"continue": "next-page"}, "items": items})
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = json.loads(result.stdout)
        self.assertEqual(observed["metadata"]["continue"], "next-page")
        self.assertEqual(len(observed["items"]), 20)
        self.assertEqual(observed["items"][-1]["containers"][0]["image"], "image-19")

    def test_invalid_list_is_not_projected_as_empty_success(self):
        for inventory in ({}, {"items": None}, {"items": {}}, {"items": False}):
            with self.subTest(inventory=inventory):
                self.assertNotEqual(self.project(inventory).returncode, 0)


class CliAndContract(unittest.TestCase):
    def test_cli_user_supplied_unprefixed_tracking_key(self):
        item = resource(labels={"argocd-instance": "shop"})
        result = subprocess.run([sys.executable, str(SCRIPT), "-", "--argocd-instance-label-key", "argocd-instance"],
                                input=json.dumps({"items": [item]}), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["tools_with_tracking"], ["argocd"])

    def test_cli_cluster_scope_context(self):
        item = resource("Namespace", "v1", "", "team", annotations={signals.ARGO_TRACKING: "shop:/Namespace:destination/team"})
        result = subprocess.run([sys.executable, str(SCRIPT), "-", "--cluster-scoped"], input=json.dumps({"items": [item]}), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["tools_with_tracking"], ["argocd"])

    def test_utf8_bom_stdin_ignores_windows_locale_codec(self):
        item = resource(annotations={signals.ARGO_TRACKING: "shop:apps/Deployment:team/web", "note": "\u4e01"})
        payload = b"\xef\xbb\xbf" + json.dumps({"items": [item]}, ensure_ascii=False).encode("utf-8")
        env = dict(os.environ, PYTHONIOENCODING="cp1252")
        result = subprocess.run([sys.executable, str(SCRIPT), "-"], input=payload, capture_output=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["tools_with_tracking"], ["argocd"])

    def test_cli_stdin(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "-"], input='{"items": []}', capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["resources_scanned"], 0)

    def test_cli_failed_or_invalid_read(self):
        for value in ("", "Forbidden", '{"items": null}'):
            with self.subTest(value=value):
                result = subprocess.run([sys.executable, str(SCRIPT), "-"], input=value, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("unavailable", result.stderr)

    def test_both_lanes_have_the_same_gitops_schema(self):
        schemas = []
        for lane in ("skills", "devops-agent"):
            data = (ROOT / lane / "eks-recon/references/cicd.md").read_text(encoding="utf-8")
            block = data.split("## Output Schema", 1)[1]
            schema = re.search(r"```yaml\n(.*?)```", block, re.S).group(1)
            # Strip runtime-specific comments; this checks the maintained shape.
            gitops = schema.split("  gitops:", 1)[1]
            gitops = gitops.split("\n  other_tools:", 1)[0]
            for field in ("    tool: string", "    status: string", "    detected: bool | null",
                          "    tools_detected: list", "    evidence: list"):
                self.assertIn(field, gitops)
            for field in ("detected: bool | null", "namespace: string | null", "version: string | null",
                          "eks_managed: bool | null", "applications: int | null",
                          "git_repositories: int | null", "kustomizations: int | null"):
                self.assertIn("      " + field, gitops)
            self.assertIn("not_observed", gitops)
            schemas.append([line.split("#", 1)[0].rstrip() for line in gitops.splitlines() if line.split("#", 1)[0].strip()])
        self.assertEqual(schemas[0], schemas[1])


if __name__ == "__main__":
    unittest.main()
