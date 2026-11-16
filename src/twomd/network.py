"""Construcción explícita del transporte para la API de IA."""

import ipaddress
import re
import ssl
from pathlib import Path

from twomd.config import NetworkSettings


def _bypass_mounts(exclusions: str) -> dict[str, None]:
    mounts: dict[str, None] = {}
    for entry in exclusions.split(","):
        host = entry.strip().lower()
        if not host:
            continue
        if host == "*":
            mounts["all://"] = None
            continue
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            domain = host.lstrip(".")
            if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*", domain):
                raise ValueError("Las exclusiones deben ser nombres de host o direcciones IP.")
            pattern = f"*{domain}" if not host.startswith(".") else f"*.{domain}"
            mounts[f"all://{pattern}"] = None
        else:
            formatted = f"[{address}]" if address.version == 6 else str(address)
            mounts[f"all://{formatted}"] = None
    return mounts


def create_http_client(settings: NetworkSettings, password: str | None):
    import httpx
    import truststore

    if settings.ca_bundle:
        bundle = Path(settings.ca_bundle)
        if not bundle.is_file():
            raise ValueError("No se encuentra el archivo de certificados CA.")
        context = ssl.create_default_context(cafile=str(bundle))
    else:
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    if settings.mode == "system":
        return httpx.Client(verify=context, trust_env=True, follow_redirects=False)
    if settings.mode == "none":
        return httpx.Client(verify=context, trust_env=False, follow_redirects=False)
    if not settings.proxy_host or any(c in settings.proxy_host for c in "/@?#"):
        raise ValueError("Indica un servidor proxy válido, sin URL ni credenciales.")
    if settings.proxy_user and not password:
        raise ValueError("Falta la contraseña del proxy.")
    proxy_url = httpx.URL(
        scheme=settings.proxy_scheme, host=settings.proxy_host, port=settings.proxy_port
    )
    auth = (settings.proxy_user, password) if settings.proxy_user and password else None
    proxy = httpx.Proxy(proxy_url, auth=auth, ssl_context=context)
    mounts = _bypass_mounts(settings.proxy_exclusions)
    return httpx.Client(
        verify=context,
        proxy=proxy,
        mounts=mounts,
        trust_env=False,
        follow_redirects=False,
    )
