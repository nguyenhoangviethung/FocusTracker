import pytest

from utils.focus_signal import presentation_signal


def test_presentation_signal_maps_high_class_to_upper_band() -> None:
    assert presentation_signal(3, [0.1, 0.2, 0.25, 0.45], 0.45) == pytest.approx(0.835)


def test_presentation_signal_maps_supported_medium_class_to_middle_band() -> None:
    assert presentation_signal(2, [0.1, 0.15, 0.50, 0.25], 0.25) == pytest.approx(0.60)


def test_presentation_signal_maps_unsupported_medium_class_below_fifty() -> None:
    assert presentation_signal(2, [0.1, 0.2, 0.55, 0.15], 0.15) == pytest.approx(0.41)


def test_presentation_signal_maps_low_classes_to_lower_bands() -> None:
    assert presentation_signal(1, [0.1, 0.60, 0.2, 0.1], 0.1) == pytest.approx(0.42)
    assert presentation_signal(0, [0.70, 0.1, 0.1, 0.1], 0.1) == pytest.approx(0.21)


def test_presentation_signal_falls_back_to_raw_score_without_class() -> None:
    assert presentation_signal(None, None, 0.47) == pytest.approx(0.47)
