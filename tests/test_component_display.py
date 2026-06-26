from ui.component_metrics import component_text, normalize_components


def test_component_normalization_accepts_deep_forest_keys() -> None:
    components = normalize_components(
        {
            "layer1_extra_trees": {"probabilities": [0.1, 0.2, 0.3, 0.4]},
            "layer1_random_forest": {"probability": 0.55},
            "layer2_cascade": [0.2, 0.1, 0.6, 0.1],
        }
    )

    assert components["layer1_extra_trees"]["probability"] == 0.7
    assert components["layer1_random_forest"]["probability"] == 0.55
    assert components["layer2_cascade"]["probability"] == 0.7


def test_missing_component_is_not_rendered_as_zero() -> None:
    assert component_text("Layer 2 Cascade", None).endswith("--")
