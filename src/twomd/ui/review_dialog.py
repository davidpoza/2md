from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from twomd.ai import safe_error
from twomd.config import Settings
from twomd.credentials import get_secret
from twomd.diagrams import DiagramProposal, propose_diagram
from twomd.mermaid import render_mermaid
from twomd.review import PictureReference, accept_diagram, picture_references


class ReviewSignals(QObject):
    finished = Signal(object, str)


class ReviewWorker(QRunnable):
    def __init__(self, operation, network_error: bool = False) -> None:
        super().__init__()
        self.operation = operation
        self.network_error = network_error
        self.signals = ReviewSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.operation()
        except Exception as error:  # noqa: BLE001
            message = safe_error(error) if self.network_error else str(error)
            self.signals.finished.emit(None, message)
        else:
            self.signals.finished.emit(result, "")


class ReviewDialog(QDialog):
    def __init__(self, markdown: Path, settings: Settings, parent: QWidget) -> None:
        super().__init__(parent)
        self.markdown = markdown
        self.settings = settings.model_copy(deep=True)
        self.references = picture_references(markdown)
        self.pool = QThreadPool(self)
        self.worker: ReviewWorker | None = None
        self.validated_code: str | None = None
        self.proposal_model: str | None = None
        self.setWindowTitle("Revisión de imágenes y diagramas")
        self.resize(1000, 700)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "La imagen original se conserva. Comprueba visualmente la propuesta antes de aceptarla."
            )
        )
        self.pictures = QListWidget()
        for reference in self.references:
            self.pictures.addItem(f"Imagen {reference.index}: {reference.image.name}")
        layout.addWidget(self.pictures)
        comparison = QHBoxLayout()
        self.original = QLabel("Original")
        self.preview = QLabel("Vista Mermaid")
        for image in (self.original, self.preview):
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image.setMinimumSize(250, 220)
            comparison.addWidget(image)
        layout.addLayout(comparison)
        self.message = QLabel("Selecciona una imagen.")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Código Mermaid editable")
        layout.addWidget(self.editor)
        buttons = QHBoxLayout()
        self.generate = QPushButton("Generar o regenerar con IA")
        self.generate.clicked.connect(self.generate_proposal)
        self.validate = QPushButton("Validar y previsualizar")
        self.validate.clicked.connect(self.validate_code)
        self.accept_button = QPushButton("Aceptar diagrama")
        self.accept_button.clicked.connect(self.save_diagram)
        self.close_button = QPushButton("Cerrar sin aceptar")
        self.close_button.clicked.connect(self.close)
        for button in (self.generate, self.validate, self.accept_button, self.close_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.editor.textChanged.connect(self.invalidate)
        self.pictures.currentRowChanged.connect(self.select_picture)
        if self.references:
            self.pictures.setCurrentRow(0)
        self.update_buttons()

    def current_reference(self) -> PictureReference | None:
        row = self.pictures.currentRow()
        return self.references[row] if 0 <= row < len(self.references) else None

    def update_buttons(self) -> None:
        ready = self.worker is None and self.current_reference() is not None
        self.pictures.setEnabled(self.worker is None)
        self.editor.setEnabled(self.worker is None)
        self.generate.setEnabled(ready and self.settings.ai.enabled)
        self.validate.setEnabled(ready and bool(self.editor.toPlainText().strip()))
        self.accept_button.setEnabled(
            ready
            and self.validated_code is not None
            and self.validated_code == self.editor.toPlainText()
        )

    def invalidate(self) -> None:
        self.validated_code = None
        self.preview.clear()
        self.update_buttons()

    def select_picture(self) -> None:
        self.editor.clear()
        self.proposal_model = None
        reference = self.current_reference()
        self.original.clear()
        if reference:
            pixmap = QPixmap(str(reference.image))
            self.original.setPixmap(
                pixmap.scaled(
                    400,
                    260,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.message.setText("Genera una propuesta o introduce Mermaid manualmente.")
        self.update_buttons()

    def start_worker(self, operation, callback, network_error: bool = False) -> None:
        self.worker = ReviewWorker(operation, network_error)
        self.worker.signals.finished.connect(callback)
        self.update_buttons()
        self.pool.start(self.worker)

    def generate_proposal(self) -> None:
        reference = self.current_reference()
        if reference is None:
            return
        answer = QMessageBox.question(
            self,
            "Enviar imagen a IA",
            "Se enviarán la imagen seleccionada y su contexto al endpoint de IA configurado. "
            "¿Deseas continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            key = get_secret("api") or ""
            password = get_secret("proxy")
        except Exception:  # noqa: BLE001
            self.message.setText("No se pudieron leer las credenciales de Windows.")
            return
        self.message.setText("Analizando la imagen...")
        self.start_worker(
            lambda: propose_diagram(
                reference.image,
                reference.context,
                self.settings.ai,
                self.settings.network,
                key,
                password,
            ),
            self.proposal_finished,
            network_error=True,
        )

    def proposal_finished(self, result: object, error: str) -> None:
        self.worker = None
        if error:
            self.message.setText(error)
        elif isinstance(result, DiagramProposal):
            self.message.setText(f"Clasificación: {result.categoria}. {result.motivo}")
            self.editor.setPlainText(result.mermaid if result.fiable and result.mermaid else "")
            self.proposal_model = self.settings.ai.model if result.fiable else None
        self.update_buttons()

    def validate_code(self) -> None:
        code = self.editor.toPlainText()
        self.invalidate()
        self.message.setText("Preparando recursos y validando Mermaid...")
        self.start_worker(
            lambda: render_mermaid(code),
            lambda result, error: self.render_finished(code, result, error),
        )

    def render_finished(self, code: str, result: object, error: str) -> None:
        self.worker = None
        if error:
            self.message.setText(error)
        elif isinstance(result, bytes):
            pixmap = QPixmap()
            if pixmap.loadFromData(result, "PNG"):
                self.preview.setPixmap(
                    pixmap.scaled(
                        400,
                        260,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self.validated_code = code
                self.message.setText("Validación correcta. Compara el resultado antes de aceptar.")
            else:
                self.message.setText("La imagen renderizada no se pudo abrir.")
        self.update_buttons()

    def save_diagram(self) -> None:
        reference = self.current_reference()
        code = self.editor.toPlainText()
        if reference is None or self.validated_code != code:
            return
        try:
            path = accept_diagram(self.markdown, reference, code, self.proposal_model)
            self.references = picture_references(self.markdown)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
            QMessageBox.critical(self, "Error de revisión", str(error))
            return
        self.message.setText(f"Diagrama guardado: {path.name}. Se conserva la imagen original.")
        self.invalidate()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker is not None:
            QMessageBox.information(self, "Revisión", "Espera a que termine la operación en curso.")
            event.ignore()
        else:
            event.accept()

    def reject(self) -> None:
        if self.worker is None:
            super().reject()
        else:
            QMessageBox.information(self, "Revisión", "Espera a que termine la operación en curso.")
