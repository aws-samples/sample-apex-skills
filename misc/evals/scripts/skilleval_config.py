"""Parse .skilleval.yaml with upward traversal and merge defaults."""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    sys.exit("Error: PyYAML required. Install with: pip install pyyaml")

EVALS_ROOT = Path(__file__).resolve().parent.parent

# Upfront size guard before YAML parsing (config files are small).
_MAX_CONFIG_BYTES = 256 * 1024

DEFAULT_WEIGHTS = {
    "triggering": 0.20,
    "process": 0.15,
    "artifact": 0.25,
    "knowledge": 0.25,
    "quality": 0.15,
}

GRADE_THRESHOLDS = [
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (0, "F"),
]


@dataclass
class LayerConfig:
    enabled: bool = True
    threshold: Optional[float] = None
    validators: list[str] = field(default_factory=list)
    model: Optional[str] = None
    runs_per_query: int = 3
    threshold_tpr: float = 0.85
    threshold_tnr: float = 0.80


@dataclass
class SkillEvalConfig:
    skill_name: str
    artifact_type: Optional[str] = None
    artifacts: list[dict[str, str]] = field(default_factory=list)
    layers: dict[str, LayerConfig] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    regression_threshold: float = 5.0
    pass_k: int = 3
    timeout: int = 600
    model: Optional[str] = None
    eval_set_hash: Optional[str] = None

    def effective_weights(self) -> dict[str, float]:
        """Return weights with redistribution for disabled/missing layers.

        When a layer is disabled, its weight is redistributed proportionally
        to the remaining enabled layers.
        """
        base = self.weights if self.weights else dict(DEFAULT_WEIGHTS)
        enabled_layers = {k for k, v in self.layers.items() if v.enabled}
        if not enabled_layers:
            enabled_layers = set(base.keys())

        disabled_weight = sum(w for k, w in base.items() if k not in enabled_layers)
        if disabled_weight == 0:
            return base

        enabled_total = sum(w for k, w in base.items() if k in enabled_layers)
        if enabled_total == 0:
            count = len(enabled_layers)
            return {k: 1.0 / count for k in enabled_layers}

        scale = 1.0 / enabled_total
        return {k: w * scale for k, w in base.items() if k in enabled_layers}


def _parse_layer(raw: dict[str, Any]) -> LayerConfig:
    return LayerConfig(
        enabled=raw.get("enabled", True),
        threshold=raw.get("threshold"),
        validators=raw.get("validators", []),
        model=raw.get("model"),
        runs_per_query=raw.get("runs_per_query", 3),
        threshold_tpr=raw.get("threshold_tpr", 0.85),
        threshold_tnr=raw.get("threshold_tnr", 0.80),
    )


def _merge_configs(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge override into base (override wins on leaf values)."""
    merged = dict(base)
    for k, v in override.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _merge_configs(merged[k], v)
        else:
            merged[k] = v
    return merged


def _find_configs(skill_dir: Path) -> list[Path]:
    """Walk upward from skill_dir to EVALS_ROOT collecting .skilleval.yaml files.

    Returns in precedence order: project-level first, skill-level last (last wins).
    """
    configs: list[Path] = []
    current = skill_dir
    while True:
        candidate = current / ".skilleval.yaml"
        if candidate.exists():
            configs.append(candidate)
        if current == EVALS_ROOT or current == current.parent:
            break
        current = current.parent
    configs.reverse()
    return configs


def load_config(skill: str, cli_overrides: Optional[dict[str, Any]] = None) -> SkillEvalConfig:
    """Load and merge .skilleval.yaml for a skill.

    Layering order: project-level < skill-level < CLI flags.
    """
    skill_dir = EVALS_ROOT / skill
    configs = _find_configs(skill_dir)

    merged: dict[str, Any] = {}
    for config_path in configs:
        text = config_path.read_text()
        if len(text.encode("utf-8")) > _MAX_CONFIG_BYTES:
            raise RuntimeError(f"config file exceeds maximum allowed size: {config_path}")
        raw = yaml.safe_load(text) or {}
        merged = _merge_configs(merged, raw)

    if cli_overrides:
        merged = _merge_configs(merged, cli_overrides)

    layers_raw = merged.get("layers", {})
    layers: dict[str, LayerConfig] = {}
    for layer_name in DEFAULT_WEIGHTS:
        if layer_name in layers_raw:
            layers[layer_name] = _parse_layer(layers_raw[layer_name])
        else:
            layers[layer_name] = LayerConfig()

    weights_raw = merged.get("weights", {})
    weights = {}
    for layer_name in DEFAULT_WEIGHTS:
        if layer_name in weights_raw:
            weights[layer_name] = float(weights_raw[layer_name])
        else:
            weights[layer_name] = DEFAULT_WEIGHTS[layer_name]

    regression_raw = merged.get("regression", {})

    return SkillEvalConfig(
        skill_name=merged.get("skill_name", skill),
        artifact_type=merged.get("artifact_type"),
        artifacts=merged.get("artifacts", []),
        layers=layers,
        weights=weights,
        regression_threshold=float(regression_raw.get("threshold", 5.0)),
        pass_k=int(regression_raw.get("pass_k", 3)),
        timeout=int(merged.get("timeout", 600)),
        model=merged.get("model"),
        eval_set_hash=merged.get("eval_set_hash"),
    )


def score_to_grade(score: float) -> str:
    """Convert a 0-100 composite score to a letter grade."""
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"
