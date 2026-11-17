"""Preferencias locales no sensibles."""

import ipaddress
import os
import re
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AISettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    base_url: str = ""
    model: str = ""
    timeout: int = Field(default=60, ge=1, le=600)
    max_retries: int = Field(default=2, ge=0, le=10)
    concurrency: int = Field(default=1, ge=1, le=8)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=1000000)

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value:
            return value
        url = urlsplit(value)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
        ):
            raise ValueError("La URL debe ser HTTP(S), sin credenciales ni parámetros.")
        return value

    @model_validator(mode="after")
    def require_endpoint_and_model(self):
        if self.enabled and (not self.base_url or not self.model.strip()):
            raise ValueError("La IA requiere una URL y un identificador de modelo.")
        return self


class NetworkSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["none", "system", "manual"] = "system"
    proxy_scheme: Literal["http", "https"] = "http"
    proxy_host: str = ""
    proxy_port: int = Field(default=8080, ge=1, le=65535)
    proxy_user: str = ""
    proxy_exclusions: str = ""
    ca_bundle: str = ""

    @field_validator("proxy_host")
    @classmethod
    def validate_proxy_host(cls, value: str) -> str:
        if not value:
            return value
        try:
            ipaddress.ip_address(value)
        except ValueError:
            if not re.fullmatch(r"[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*", value):
                raise ValueError("El servidor proxy debe ser un nombre o una dirección IP.")
        return value

    @field_validator("proxy_exclusions")
    @classmethod
    def validate_exclusions(cls, value: str) -> str:
        for item in value.split(","):
            host = item.strip()
            if not host or host == "*":
                continue
            try:
                ipaddress.ip_address(host)
            except ValueError:
                if not re.fullmatch(r"[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*", host.lstrip(".")):
                    raise ValueError("Las exclusiones deben ser nombres o direcciones IP.")
        return value


class MCPSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    working_directory: str = ""

    @model_validator(mode="after")
    def require_working_directory(self):
        if self.enabled and not self.working_directory.strip():
            raise ValueError("Selecciona el directorio permitido para MCP.")
        return self


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_directory: str = ""
    document_concurrency: int = Field(default=2, ge=1, le=8)
    ai: AISettings = Field(default_factory=AISettings)
    network: NetworkSettings = Field(default_factory=NetworkSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)

    @model_validator(mode="before")
    @classmethod
    def remove_legacy_models_directory(cls, value: object) -> object:
        if isinstance(value, dict):
            value = value.copy()
            value.pop("models_directory", None)
        return value


def settings_path() -> Path:
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return root / "2MD" / "settings.json"


def load_settings(path: Path) -> Settings:
    if not path.exists():
        return Settings()
    return Settings.model_validate_json(path.read_text(encoding="utf-8"))


def save_settings(path: Path, settings: Settings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(settings.model_dump_json(indent=2))
            temporary.write("\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
