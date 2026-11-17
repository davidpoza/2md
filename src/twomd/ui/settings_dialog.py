from itertools import count
from pathlib import Path

from pydantic import ValidationError
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from twomd.ai import check_connection, safe_error
from twomd.config import AISettings, MCPSettings, NetworkSettings, Settings
from twomd.credentials import get_secret
from twomd.network import create_http_client


class CheckSignals(QObject):
    finished = Signal(str, bool)
    activity = Signal(str)


class ConnectionCheck(QRunnable):
    def __init__(
        self, settings: Settings, api_key: str, proxy_password: str | None, kind: str
    ) -> None:
        super().__init__()
        self.settings = settings
        self.api_key = api_key
        self.proxy_password = proxy_password
        self.kind = kind
        self.signals = CheckSignals()

    @Slot()
    def run(self) -> None:
        try:
            if self.kind == "network":
                if not self.settings.ai.base_url:
                    raise ValueError("Falta la URL del endpoint.")
                with create_http_client(self.settings.network, self.proxy_password) as client:
                    response = client.get(
                        self.settings.ai.base_url, timeout=self.settings.ai.timeout
                    )
                    if response.status_code == 407:
                        self.signals.finished.emit(
                            "El proxy rechazó la autenticación (HTTP 407).", False
                        )
                        return
                message = f"Conexión de red establecida (HTTP {response.status_code})."
            else:
                attempts = count(1)
                kind = "visión" if self.kind == "vision" else "conexión"
                check_connection(
                    self.settings.ai,
                    self.settings.network,
                    self.api_key,
                    self.proxy_password,
                    self.kind == "vision",
                    on_request=lambda: self.signals.activity.emit(
                        f"IA: prueba de {kind}, solicitud, intento {next(attempts)}."
                    ),
                    on_response=lambda status: self.signals.activity.emit(
                        f"IA: prueba de {kind}, respuesta HTTP {status}."
                    ),
                )
                message = (
                    "Prueba de visión correcta."
                    if self.kind == "vision"
                    else ("Conexión con el modelo correcta.")
                )
        except ImportError:
            message = "Faltan dependencias necesarias para comprobar la conexión."
            success = False
        except Exception as error:  # noqa: BLE001
            message = safe_error(error)
            success = False
        else:
            success = True
        self.signals.finished.emit(message, success)


def _secret_input() -> tuple[QWidget, QLineEdit]:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    field = QLineEdit()
    field.setEchoMode(QLineEdit.EchoMode.Password)
    field.setPlaceholderText("Dejar vacío para conservar la credencial guardada")
    show = QCheckBox("Mostrar")
    show.toggled.connect(
        lambda checked: field.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )
    )
    layout.addWidget(field)
    layout.addWidget(show)
    return container, field


class SettingsDialog(QDialog):
    activity = Signal(str)

    def __init__(self, settings: Settings, parent: QWidget) -> None:
        super().__init__(parent)
        self.settings = settings
        self.worker: ConnectionCheck | None = None
        self.pool = QThreadPool(self)
        self.setWindowTitle("Configuración")
        self.resize(650, 540)
        outer = QVBoxLayout(self)
        tabs = QTabWidget()
        outer.addWidget(tabs)

        general = QWidget()
        form = QFormLayout(general)
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 8)
        self.concurrency.setValue(settings.document_concurrency)
        form.addRow("Documentos simultáneos:", self.concurrency)
        self.models_directory = QLineEdit(settings.models_directory)
        choose_models = QPushButton("Seleccionar modelos locales")
        choose_models.clicked.connect(self.choose_models)
        form.addRow("Carpeta de modelos Docling:", self.models_directory)
        form.addRow(choose_models)
        tabs.addTab(general, "General")

        ai = QWidget()
        form = QFormLayout(ai)
        self.enabled = QCheckBox("Activar IA")
        self.enabled.setChecked(settings.ai.enabled)
        self.base_url = QLineEdit(settings.ai.base_url)
        self.model = QLineEdit(settings.ai.model)
        api_widget, self.api_key = _secret_input()
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 600)
        self.timeout.setValue(settings.ai.timeout)
        self.retries = QSpinBox()
        self.retries.setRange(0, 10)
        self.retries.setValue(settings.ai.max_retries)
        self.ai_concurrency = QSpinBox()
        self.ai_concurrency.setRange(1, 8)
        self.ai_concurrency.setValue(settings.ai.concurrency)
        self.temperature = QLineEdit(
            "" if settings.ai.temperature is None else str(settings.ai.temperature)
        )
        self.max_tokens = QLineEdit(
            "" if settings.ai.max_tokens is None else str(settings.ai.max_tokens)
        )
        for label, field in (
            ("", self.enabled),
            ("URL del endpoint:", self.base_url),
            ("API Key:", api_widget),
            ("Modelo:", self.model),
            ("Tiempo de espera (s):", self.timeout),
            ("Reintentos:", self.retries),
            ("Solicitudes simultáneas:", self.ai_concurrency),
            ("Temperatura opcional:", self.temperature),
            ("Tokens opcionales:", self.max_tokens),
        ):
            form.addRow(label, field)
        test_text = QPushButton("Probar conexión")
        test_text.clicked.connect(lambda: self.start_check("text"))
        test_vision = QPushButton("Comprobar visión")
        test_vision.clicked.connect(lambda: self.start_check("vision"))
        form.addRow(test_text, test_vision)
        tabs.addTab(ai, "Inteligencia artificial")

        network = QWidget()
        form = QFormLayout(network)
        self.mode = QComboBox()
        for label, value in (
            ("Sin proxy", "none"),
            ("Sistema o entorno", "system"),
            ("Proxy manual", "manual"),
        ):
            self.mode.addItem(label, value)
        self.mode.setCurrentIndex(self.mode.findData(settings.network.mode))
        self.scheme = QComboBox()
        self.scheme.addItems(["http", "https"])
        self.scheme.setCurrentText(settings.network.proxy_scheme)
        self.host = QLineEdit(settings.network.proxy_host)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(settings.network.proxy_port)
        self.user = QLineEdit(settings.network.proxy_user)
        proxy_widget, self.proxy_password = _secret_input()
        self.exclusions = QLineEdit(settings.network.proxy_exclusions)
        self.ca_bundle = QLineEdit(settings.network.ca_bundle)
        choose_ca = QPushButton("Seleccionar archivo CA")
        choose_ca.clicked.connect(self.choose_ca)
        form.addRow("Modo:", self.mode)
        form.addRow("Protocolo:", self.scheme)
        form.addRow("Servidor:", self.host)
        form.addRow("Puerto:", self.port)
        form.addRow("Usuario:", self.user)
        form.addRow("Contraseña:", proxy_widget)
        form.addRow("Exclusiones (separadas por comas):", self.exclusions)
        form.addRow("Certificados CA:", self.ca_bundle)
        form.addRow(choose_ca)
        form.addRow(QLabel("NTLM y Kerberos no están implementados."))
        test_network = QPushButton("Probar conexión de red")
        test_network.clicked.connect(lambda: self.start_check("network"))
        form.addRow(test_network)
        tabs.addTab(network, "Red y proxy")

        mcp = QWidget()
        form = QFormLayout(mcp)
        self.mcp_enabled = QCheckBox("Activar MCP local por stdio")
        self.mcp_enabled.setChecked(settings.mcp.enabled)
        self.mcp_directory = QLineEdit(settings.mcp.working_directory)
        choose_mcp_directory = QPushButton("Seleccionar directorio permitido")
        choose_mcp_directory.clicked.connect(self.choose_mcp_directory)
        form.addRow(self.mcp_enabled)
        form.addRow("Directorio permitido:", self.mcp_directory)
        form.addRow(choose_mcp_directory)
        form.addRow(
            QLabel(
                "Los clientes locales podrán leer documentos de este directorio y sus "
                "subcarpetas. Los resultados se guardan en la carpeta de destino."
            )
        )
        tabs.addTab(mcp, "MCP")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def choose_ca(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar certificados CA", "", "PEM (*.pem *.crt)"
        )
        if file:
            self.ca_bundle.setText(file)

    def choose_models(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar modelos Docling")
        if folder:
            self.models_directory.setText(folder)

    def choose_mcp_directory(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar directorio permitido")
        if folder:
            self.mcp_directory.setText(folder)

    def values(self) -> Settings:
        ai = AISettings(
            enabled=self.enabled.isChecked(),
            base_url=self.base_url.text().strip(),
            model=self.model.text().strip(),
            timeout=self.timeout.value(),
            max_retries=self.retries.value(),
            concurrency=self.ai_concurrency.value(),
            temperature=self.temperature.text().strip() or None,
            max_tokens=self.max_tokens.text().strip() or None,
        )
        network = NetworkSettings(
            mode=self.mode.currentData(),
            proxy_scheme=self.scheme.currentText(),
            proxy_host=self.host.text().strip(),
            proxy_port=self.port.value(),
            proxy_user=self.user.text().strip(),
            proxy_exclusions=self.exclusions.text().strip(),
            ca_bundle=self.ca_bundle.text().strip(),
        )
        return self.settings.model_copy(
            update={
                "document_concurrency": self.concurrency.value(),
                "models_directory": self.models_directory.text().strip(),
                "ai": ai,
                "network": network,
                "mcp": MCPSettings(
                    enabled=self.mcp_enabled.isChecked(),
                    working_directory=self.mcp_directory.text().strip(),
                ),
            }
        )

    def accept(self) -> None:
        if self.worker is not None:
            return
        try:
            settings = self.values()
        except (ValueError, ValidationError):
            QMessageBox.warning(self, "Configuración", "Revisa los valores de configuración.")
            return
        directory = Path(settings.mcp.working_directory)
        if settings.mcp.enabled and (not directory.is_absolute() or not directory.is_dir()):
            QMessageBox.warning(
                self, "MCP", "Selecciona un directorio permitido absoluto y existente."
            )
            return
        if settings.ai.enabled and not self.api_key.text():
            try:
                if not get_secret("api"):
                    QMessageBox.warning(
                        self, "Configuración", "Indica una API Key para activar IA."
                    )
                    return
            except Exception:  # noqa: BLE001
                QMessageBox.critical(
                    self, "Credenciales", "No se pudo acceder al almacén de Windows."
                )
                return
        super().accept()

    def reject(self) -> None:
        if self.worker is None:
            super().reject()

    def start_check(self, kind: str) -> None:
        if self.worker is not None:
            return
        try:
            settings = self.values()
            api_key = self.api_key.text() or (get_secret("api") if kind != "network" else "") or ""
            password = self.proxy_password.text() or (
                get_secret("proxy")
                if settings.network.mode == "manual" and settings.network.proxy_user
                else None
            )
        except (ValueError, ValidationError):
            QMessageBox.warning(self, "Configuración", "Revisa los valores de configuración.")
            return
        except Exception:  # noqa: BLE001
            QMessageBox.critical(self, "Credenciales", "No se pudo acceder al almacén de Windows.")
            return
        if kind != "network" and settings.ai.base_url.lower().startswith("http://"):
            answer = QMessageBox.warning(
                self,
                "Conexión sin cifrar",
                "La API Key se enviará sin cifrar porque la URL usa HTTP. ¿Deseas continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.worker = ConnectionCheck(settings, api_key, password, kind)
        self.worker.signals.finished.connect(self.check_finished)
        self.worker.signals.activity.connect(self.activity.emit)
        if kind != "network":
            label = "visión" if kind == "vision" else "conexión"
            self.activity.emit(f"IA: preparando prueba de {label}.")
        self.pool.start(self.worker)
        QMessageBox.information(self, "Conexión", "La comprobación se está ejecutando.")

    def check_finished(self, message: str, success: bool) -> None:
        if self.worker is not None and self.worker.kind != "network":
            self.activity.emit(
                f"IA: {'prueba completada' if success else 'error en la prueba'}. {message}"
            )
        self.worker = None
        QMessageBox.information(self, "Resultado de la conexión", message)
