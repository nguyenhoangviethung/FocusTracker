import pytest
from pydantic import ValidationError

from shared.contracts import RAW_FRAME_FEATURE_DIM, SEQUENCE_LENGTH, TelemetryPacket


def test_telemetry_contract_accepts_model_shape() -> None:
    packet = TelemetryPacket(
        session_id="session-1",
        device_id="device-1",
        sequence_number=1,
        raw_feature_sequence=[[0.0] * RAW_FRAME_FEATURE_DIM for _ in range(SEQUENCE_LENGTH)],
        face_found=True,
    )
    assert len(packet.raw_feature_sequence) == SEQUENCE_LENGTH
    assert len(packet.raw_feature_sequence[0]) == RAW_FRAME_FEATURE_DIM


def test_telemetry_contract_rejects_wrong_shape() -> None:
    with pytest.raises(ValidationError):
        TelemetryPacket(
            session_id="session-1",
            device_id="device-1",
            sequence_number=1,
            raw_feature_sequence=[[0.0] * (RAW_FRAME_FEATURE_DIM - 1) for _ in range(SEQUENCE_LENGTH)],
            face_found=True,
        )
