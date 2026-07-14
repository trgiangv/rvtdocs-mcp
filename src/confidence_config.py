from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MethodWeights:
    method_token: float = 0.45
    class_token: float = 0.35
    signature_hints: float = 0.20
    structured_synopsis: float = 0.25
    structured_parameters: float = 0.15
    structured_method_page: float = 0.15
    structured_returns: float = 0.05


@dataclass
class ClassWeights:
    fqcn: float = 0.70
    namespace_plus_class: float = 0.55
    class_context: float = 0.20
    structured_members: float = 0.15
    structured_class_page: float = 0.15
    class_in_title: float = 0.20


@dataclass
class Thresholds:
    pass_min: float = 0.80
    warn_min: float = 0.40
    method_exact_min: float = 0.80
    method_partial_min: float = 0.50
    class_exact_min: float = 0.75
    class_partial_min: float = 0.45


@dataclass
class ConfidenceConfig:
    method: MethodWeights = field(default_factory=MethodWeights)
    class_weights: ClassWeights = field(default_factory=ClassWeights)
    thresholds: Thresholds = field(default_factory=Thresholds)
    method_signature_hints: list[str] = field(
        default_factory=lambda: [
            "parameters",
            "syntax",
            "returns",
            "overloads",
            "exceptions",
        ]
    )
    class_signature_hints: list[str] = field(
        default_factory=lambda: [
            "methods",
            "properties",
            "constructors",
            "namespace",
            "inheritance",
        ]
    )


def _merge_dataclass(cls: type, data: dict[str, Any] | None) -> Any:
    if not data or not isinstance(data, dict):
        return cls()
    defaults = cls()
    kwargs: dict[str, Any] = {}
    for key in defaults.__dataclass_fields__:
        if key in data:
            kwargs[key] = data[key]
    return cls(**kwargs)


def load_confidence_config(config_path: Path | None = None) -> ConfidenceConfig:
    """Load from JSON file if exists, otherwise return defaults."""
    if config_path and config_path.exists():
        try:
            raw = config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                return ConfidenceConfig(
                    method=_merge_dataclass(MethodWeights, data.get("method")),
                    class_weights=_merge_dataclass(ClassWeights, data.get("class_weights")),
                    thresholds=_merge_dataclass(Thresholds, data.get("thresholds")),
                    method_signature_hints=list(
                        data.get("method_signature_hints")
                        or ConfidenceConfig().method_signature_hints
                    ),
                    class_signature_hints=list(
                        data.get("class_signature_hints")
                        or ConfidenceConfig().class_signature_hints
                    ),
                )
        except Exception:
            pass
    return ConfidenceConfig()


_config: ConfidenceConfig | None = None


def get_confidence_config() -> ConfidenceConfig:
    global _config
    if _config is None:
        config_dir = Path(__file__).parent / "data"
        _config = load_confidence_config(config_dir / "confidence_config.json")
    return _config


def reset_confidence_config() -> None:
    """Reset module singleton (useful for tests)."""
    global _config
    _config = None
