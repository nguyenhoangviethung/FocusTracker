from __future__ import annotations

from typing import Any


def normalize_components(raw_components: Any) -> dict[str, dict]:
    if not isinstance(raw_components, dict):
        return {}

    aliases = {
        "layer1_extra_trees": ("layer1_extra_trees",),
        "layer1_random_forest": ("layer1_random_forest",),
        "layer2_cascade": ("layer2_cascade",),
    }
    normalized = {}
    for target, keys in aliases.items():
        component = next(
            (raw_components[key] for key in keys if key in raw_components),
            None,
        )
        parsed = parse_component(component)
        if parsed is not None:
            normalized[target] = parsed
    return normalized


def parse_component(component: Any) -> dict | None:
    if isinstance(component, dict):
        probabilities = component.get("probabilities")
        probability = component.get("probability")
    elif isinstance(component, (list, tuple)):
        probabilities = component
        probability = None
    elif isinstance(component, (float, int)):
        probabilities = None
        probability = float(component)
    else:
        return None

    if probability is None and isinstance(probabilities, (list, tuple)) and len(probabilities) >= 4:
        probability = float(probabilities[2]) + float(probabilities[3])
    if probability is None:
        return None
    return {"probability": max(0.0, min(1.0, float(probability)))}


def component_text(name: str, component: dict | None) -> str:
    if not component:
        return f"{name:<11}: --"
    probability = float(component.get("probability", 0.0))
    return f"{name:<8} : {probability * 100:5.1f}%"
