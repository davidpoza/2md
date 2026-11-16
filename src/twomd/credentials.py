"""Almacenamiento de secretos exclusivamente en Windows Credential Manager."""

import sys


def _backend():
    if sys.platform != "win32":
        raise RuntimeError("El almacenamiento seguro requiere Windows.")
    from keyring.backends.Windows import WinVaultKeyring

    return WinVaultKeyring()


def get_secret(name: str) -> str | None:
    return _backend().get_password(f"2MD/{name}", "2MD")


def set_secret(name: str, secret: str) -> None:
    _backend().set_password(f"2MD/{name}", "2MD", secret)
