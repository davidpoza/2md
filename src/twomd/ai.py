"""Cliente OpenAI y comprobaciones explícitas de capacidad."""

import base64
import socket
import ssl
from collections.abc import Callable
from io import BytesIO

from twomd.config import AISettings, NetworkSettings
from twomd.network import create_http_client


def _pixel() -> str:
    from PIL import Image

    image = BytesIO()
    Image.new("RGB", (1, 1), "white").save(image, format="PNG")
    return base64.b64encode(image.getvalue()).decode("ascii")


def check_connection(
    ai: AISettings,
    network: NetworkSettings,
    api_key: str,
    proxy_password: str | None,
    vision: bool,
    *,
    on_request: Callable[[], None] | None = None,
    on_response: Callable[[int], None] | None = None,
) -> None:
    from openai import OpenAI

    if not ai.enabled or not ai.base_url or not ai.model or not api_key:
        raise ValueError("Activa la IA e indica URL, modelo y API Key.")
    content = [{"type": "text", "text": "Responde OK."}]
    if vision:
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_pixel()}"}}
        )
    with (
        create_http_client(network, proxy_password) as http_client,
        OpenAI(
            base_url=ai.base_url,
            api_key=api_key,
            timeout=ai.timeout,
            max_retries=ai.max_retries,
            http_client=http_client,
        ) as client,
    ):
        if on_request is not None:
            http_client.event_hooks["request"].append(lambda request: on_request())
        if on_response is not None:
            http_client.event_hooks["response"].append(
                lambda response: on_response(response.status_code)
            )
        client.chat.completions.create(
            model=ai.model, messages=[{"role": "user", "content": content}]
        )


def safe_error(error: Exception) -> str:
    import httpx
    import openai

    current: BaseException | None = error
    seen: set[int] = set()
    proxy_failure = False
    connect_failure = False
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLError) or "certificate" in str(current).lower():
            return "Error de certificado TLS. Comprueba los certificados corporativos."
        if isinstance(current, httpx.ProxyError):
            if "407" in str(current):
                return "El proxy rechazó la autenticación (HTTP 407)."
            proxy_failure = True
        if isinstance(current, socket.gaierror):
            return "No se pudo resolver el nombre DNS del servidor o proxy."
        if isinstance(current, (httpx.TimeoutException, TimeoutError)):
            return "La conexión ha superado el tiempo de espera."
        if isinstance(current, httpx.ConnectError):
            connect_failure = True
        current = current.__cause__ or current.__context__
    if proxy_failure:
        return "No se pudo conectar con el proxy."
    if connect_failure:
        return "No se pudo establecer la conexión con el servidor."
    if isinstance(error, openai.APIStatusError):
        if error.status_code == 407:
            return "El proxy rechazó la autenticación (HTTP 407)."
        return f"El servidor respondió con HTTP {error.status_code}."
    if isinstance(error, ValueError):
        return "La configuración de conexión no es válida; revisa los campos."
    return "No se pudo completar la conexión. Comprueba red, proxy y endpoint."
