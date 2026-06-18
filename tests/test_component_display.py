from ui.component_metrics import component_text, normalize_components


def test_component_normalization_accepts_legacy_cloud_keys() -> None:
    components = normalize_components(
        {
            "gru": {"probabilities": [0.1, 0.2, 0.3, 0.4]},
            "tcn": {"probability": 0.55},
            "xgboost": [0.2, 0.1, 0.6, 0.1],
        }
    )

    assert components["final_xgb"]["probability"] == 0.7
    assert components["boost_xgb"]["probability"] == 0.55
    assert components["targeted_xgb"]["probability"] == 0.7


def test_missing_component_is_not_rendered_as_zero() -> None:
    assert component_text("Final XGB", None).endswith("--")
