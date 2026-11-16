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


from twomd.ai import safe_error
