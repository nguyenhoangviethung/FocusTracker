from __future__ import annotations

from edge.auth_client import AuthClient, AuthRequestError


def test_auth_request_error_string_is_friendly() -> None:
    error = AuthRequestError(422, "Mật khẩu phải có ít nhất 8 ký tự.")
    assert str(error) == "Mật khẩu phải có ít nhất 8 ký tự."


def test_friendly_http_error_parses_validation_payload() -> None:
    client = AuthClient(api_url="http://example.com", api_key="secret")
    message = client._friendly_http_error(
        422,
        '{"detail":[{"type":"string_too_short","loc":["body","password"],"msg":"String should have at least 8 characters","input":"123456","ctx":{"min_length":8}}]}',
    )
    assert message == "Mật khẩu phải có ít nhất 8 ký tự."
