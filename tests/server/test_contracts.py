import pytest
from pydantic import ValidationError

from shared.contracts import TelemetryPacket


def test_telemetry_contract_accepts_model_shape() -> None:
    packet = TelemetryPacket(
        session_id="session-1",
        device_id="device-1",
        sequence_number=1,
        raw_feature_sequence=[[0.0] * 30 for _ in range(30)],
        face_found=True,
    )
    assert len(packet.raw_feature_sequence) == 30
    assert len(packet.raw_feature_sequence[0]) == 30


def test_telemetry_contract_rejects_wrong_shape() -> None:
    with pytest.raises(ValidationError):
        TelemetryPacket(
            session_id="session-1",
            device_id="device-1",
            sequence_number=1,
            raw_feature_sequence=[[0.0] * 29 for _ in range(30)],
            face_found=True,
        )
