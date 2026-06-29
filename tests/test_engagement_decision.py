from tracking.inference import engagement_decision


def test_high_argmax_is_engaged() -> None:
    state, decision = engagement_decision([0.1, 0.2, 0.25, 0.45])

    assert state == "ENGAGED"
    assert decision["decision_rule"] == "high_argmax_or_medium_with_high_support"


def test_medium_argmax_with_high_support_is_engaged() -> None:
    state, decision = engagement_decision([0.05, 0.25, 0.50, 0.20])

    assert state == "ENGAGED"
    assert decision["medium_with_high_support"] is True


def test_medium_argmax_without_high_support_is_distracted() -> None:
    state, decision = engagement_decision([0.05, 0.36, 0.50, 0.09])

    assert state == "DISTRACTED"
    assert decision["medium_with_high_support"] is False


def test_low_or_very_low_argmax_is_distracted() -> None:
    assert engagement_decision([0.45, 0.25, 0.15, 0.15])[0] == "DISTRACTED"
    assert engagement_decision([0.10, 0.50, 0.25, 0.15])[0] == "DISTRACTED"
