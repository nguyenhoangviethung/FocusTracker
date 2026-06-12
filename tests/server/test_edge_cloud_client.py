from edge.cloud_client import CloudClientConfig, FocusFlowCloudClient


def test_cloud_client_builds_secure_websocket_url() -> None:
    client = FocusFlowCloudClient(
        CloudClientConfig(
            base_url="https://focusflow.example/api-root",
            api_key="secret",
            device_id="device 1",
        )
    )

    assert client._websocket_url("session/1") == (
        "wss://focusflow.example/api-root/v1/ws/sessions/session%2F1"
        "?device_id=device%201"
    )
