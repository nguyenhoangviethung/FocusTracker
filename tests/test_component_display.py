from ui.component_metrics import component_text, normalize_components


def test_component_normalization_accepts_triple_xgb_keys() -> None:
    components = normalize_components(
        {
            "final_xgb": {"probabilities": [0.1, 0.2, 0.3, 0.4]},
            "boost_xgb": {"probability": 0.55},
            "targeted_xgb": [0.2, 0.1, 0.6, 0.1],
        }
    )

    assert components["final_xgb"]["probability"] == 0.4
    assert components["boost_xgb"]["probability"] == 0.55
    assert components["targeted_xgb"]["probability"] == 0.1


def test_component_normalization_keeps_legacy_deep_forest_keys() -> None:
    components = normalize_components(
        {
            "layer1_extra_trees": {"probability": 0.65},
            "layer1_random_forest": {"probability": 0.55},
            "layer2_cascade": [0.2, 0.1, 0.6, 0.1],
        }
    )

    assert components["final_xgb"]["probability"] == 0.65
    assert components["boost_xgb"]["probability"] == 0.55
    assert components["targeted_xgb"]["probability"] == 0.1


def test_missing_component_is_not_rendered_as_zero() -> None:
    assert component_text("Layer 2 Cascade", None).endswith("--")
