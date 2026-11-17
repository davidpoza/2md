import json
import ssl

import httpx
import pytest
from pydantic import ValidationError

from twomd.config import AISettings, NetworkSettings, Settings
from twomd.network import _bypass_mounts


def test_proxy_exclusions_are_explicit_mounts():
    mounts = _bypass_mounts("example.com,.internal.test,127.0.0.1")
    assert mounts == {
        "all://*example.com": None,
        "all://*.internal.test": None,
        "all://127.0.0.1": None,
    }


@pytest.mark.parametrize(
    "values",
    [
        {"proxy_host": "user:secret@proxy.example"},
        {"proxy_exclusions": "https://user:secret@private.example"},
    ],
)
def test_credentials_cannot_be_embedded_in_proxy_configuration(values):
    with pytest.raises(ValidationError):
        NetworkSettings(**values)


def test_credentials_cannot_be_embedded_in_endpoint():
    with pytest.raises(ValidationError):
        AISettings(base_url="https://user:secret@example.com/v1")


def test_configuration_has_no_secret_fields():
    assert "secret" not in Settings().model_dump_json()


def test_proxy_error_does_not_expose_credentials():
    message = safe_error(httpx.ProxyError("407 secret"))
    assert "407" in message
    assert "secret" not in message


def test_tls_error_is_reported_without_raw_details():
    error = httpx.ConnectError("secret")
    error.__cause__ = ssl.SSLCertVerificationError("secret")
    message = safe_error(error)
    assert "TLS" in message
    assert "secret" not in message


def test_ai_connection_reports_each_http_attempt(monkeypatch):
    from twomd import ai

    requests = []
    activity = []
    statuses = []

    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(500, headers={"retry-after": "0"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr(
        ai,
        "create_http_client",
        lambda settings, password: httpx.Client(transport=httpx.MockTransport(respond)),
    )
    settings = AISettings(
        enabled=True, base_url="https://example.com/v1", model="vision", max_retries=1
    )
    ai.check_connection(
        settings,
        NetworkSettings(),
        "clave",
        None,
        True,
        on_request=lambda: activity.append("solicitud"),
        on_response=statuses.append,
    )
    assert len(activity) == len(requests) == 2
    assert statuses == [500, 200]
    body = json.loads(requests[-1].content)
    assert body["messages"][0]["content"][1]["type"] == "image_url"


from twomd.ai import safe_error
