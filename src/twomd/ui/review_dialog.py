from dataclasses import dataclass
from itertools import count
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QCloseEvent, QColor, QIcon, QPainter, QPen, QPixmap, QResizeEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from twomd.ai import safe_error
from twomd.config import Settings
from twomd.credentials import get_secret
from twomd.diagrams import DiagramProposal, propose_diagram
from twomd.mermaid import render_mermaid
from twomd.review import PictureReference, accept_diagram, picture_references, stored_diagram
from twomd.ui.image_preview import ImagePreviewDialog, load_diagram_fonts


@dataclass(frozen=True)
class SavedDiagram:
    path: Path
    references: list[PictureReference]


@dataclass
class DiagramState:
    code: str = ""
    validated_code: str | None = None
    proposal_model: str | None = None
    preview_svg: bytes | None = None
    preview_pixmap: QPixmap | None = None
    accepted_code: str | None = None
    message: str = "Genera una propuesta o introduce Mermaid manualmente."

    @property
    def accepted(self) -> bool:
        return self.accepted_code is not None and self.code.strip() == self.accepted_code


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
    activity = Signal(str)

    def __init__(self, markdown: Path, settings: Settings, parent: QWidget) -> None:
        super().__init__(parent)
        self.markdown = markdown
        self.settings = settings.model_copy(deep=True)
        self.references = picture_references(markdown)
        self.pool = QThreadPool(self)
        self.worker: ReviewWorker | None = None
        self.validated_code: str | None = None
        self.proposal_model: str | None = None
        self.preview_svg: bytes | None = None
        self.preview_viewer: ImagePreviewDialog | None = None
        self.diagram_states: dict[int, DiagramState] = {}
        self.current_index: int | None = None
        self.accepted_code: str | None = None
        check = QPixmap(24, 24)
        check.fill(Qt.GlobalColor.transparent)
        painter = QPainter(check)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#16803c"), 3))
        painter.drawLine(4, 12, 10, 18)
        painter.drawLine(10, 18, 21, 5)
        painter.end()
        self.accepted_icon = QIcon(check)
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
            diagram = stored_diagram(markdown, reference)
            if diagram is not None:
                self.diagram_states[reference.index] = DiagramState(
                    code=diagram.code,
                    accepted_code=None if diagram.pending else diagram.code,
                    message=(
                        "Propuesta automática pendiente de revisión. "
                        "Valídala y compárala con la imagen."
                        if diagram.pending
                        else "Diagrama aceptado. Valídalo para cargar la previsualización."
                    ),
                )
                self.update_picture_status(reference.index)
        layout.addWidget(self.pictures)
        comparison = QHBoxLayout()
        self.original = QLabel("Original")
        self.preview = QLabel("Vista Mermaid")
        for image in (self.original, self.preview):
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image.setMinimumSize(250, 220)
            comparison.addWidget(image)
        layout.addLayout(comparison)
        self.fullscreen_button = QPushButton("Ver previsualización a pantalla completa")
        self.fullscreen_button.clicked.connect(self.open_preview)
        layout.addWidget(self.fullscreen_button)
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
        self.loading_overlay = QWidget(self)
        self.loading_overlay.setObjectName("loadingOverlay")
        self.loading_overlay.setStyleSheet(
            "QWidget#loadingOverlay { background-color: rgba(20, 25, 35, 210); }"
            "QLabel { color: white; font-size: 16px; background: transparent; }"
        )
        self.loading_overlay.setCursor(Qt.CursorShape.WaitCursor)
        overlay_layout = QVBoxLayout(self.loading_overlay)
        overlay_layout.addStretch()
        self.loading_message = QLabel()
        self.loading_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_message.setWordWrap(True)
        overlay_layout.addWidget(self.loading_message)
        loading_bar = QProgressBar()
        loading_bar.setRange(0, 0)
        loading_bar.setMaximumWidth(320)
        overlay_layout.addWidget(loading_bar, alignment=Qt.AlignmentFlag.AlignHCenter)
        overlay_layout.addStretch()
        self.loading_overlay.hide()
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
            and self.editor.toPlainText().strip() != self.accepted_code
        )
        self.fullscreen_button.setEnabled(ready and self.preview_svg is not None)
        self.close_button.setEnabled(self.worker is None)
        if self.worker is not None:
            self.loading_message.setText(self.message.text())
            self.loading_overlay.setGeometry(self.rect())
            self.loading_overlay.show()
            self.loading_overlay.raise_()
        else:
            self.loading_overlay.hide()

    def invalidate(self) -> None:
        self.validated_code = None
        self.preview_svg = None
        self.preview.clear()
        if (
            self.accepted_code is not None
            and self.editor.toPlainText().strip() != self.accepted_code
        ):
            self.message.setText("Diagrama modificado. Vuelve a validarlo y aceptarlo.")
        self.remember_picture()
        self.update_buttons()

    def remember_picture(self) -> None:
        if self.current_index is None:
            return
        self.diagram_states[self.current_index] = DiagramState(
            code=self.editor.toPlainText(),
            validated_code=self.validated_code,
            proposal_model=self.proposal_model,
            preview_svg=self.preview_svg,
            preview_pixmap=self.preview.pixmap() if self.preview_svg is not None else None,
            accepted_code=self.accepted_code,
            message=self.message.text(),
        )
        self.update_picture_status(self.current_index)

    def update_picture_status(self, index: int) -> None:
        state = self.diagram_states[index]
        item = self.pictures.item(index - 1)
        item.setIcon(self.accepted_icon if state.accepted else QIcon())
        item.setToolTip("Diagrama aceptado" if state.accepted else "Pendiente de aceptación")

    def select_picture(self) -> None:
        self.remember_picture()
        reference = self.current_reference()
        self.current_index = reference.index if reference is not None else None
        state = (
            self.diagram_states.get(reference.index, DiagramState())
            if reference
            else DiagramState()
        )
        self.editor.blockSignals(True)
        self.editor.setPlainText(state.code)
        self.editor.blockSignals(False)
        self.validated_code = state.validated_code
        self.proposal_model = state.proposal_model
        self.preview_svg = state.preview_svg
        self.accepted_code = state.accepted_code
        self.preview.clear()
        if state.preview_pixmap is not None:
            self.preview.setPixmap(state.preview_pixmap)
        self.message.setText(state.message)
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
        self.update_buttons()

    def start_worker(self, operation, callback, network_error: bool = False) -> None:
        if self.worker is not None:
            return
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
        self.activity.emit(
            f"IA [{self.markdown.name}]: preparando revisión de imagen {reference.index}."
        )
        attempts = count(1)
        self.start_worker(
            lambda: propose_diagram(
                reference.image,
                reference.context,
                self.settings.ai,
                self.settings.network,
                key,
                password,
                on_request=lambda: self.activity.emit(
                    f"IA [{self.markdown.name}]: revisión de imagen {reference.index}, "
                    f"solicitud, intento {next(attempts)}."
                ),
                on_response=lambda status: self.activity.emit(
                    f"IA [{self.markdown.name}]: revisión de imagen {reference.index}, "
                    f"respuesta HTTP {status}."
                ),
            ),
            self.proposal_finished,
            network_error=True,
        )

    def proposal_finished(self, result: object, error: str) -> None:
        self.worker = None
        if error:
            self.message.setText(error)
            self.activity.emit(f"IA [{self.markdown.name}]: error en la revisión. {error}")
        elif isinstance(result, DiagramProposal):
            self.activity.emit(f"IA [{self.markdown.name}]: respuesta de revisión recibida.")
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
            try:
                load_diagram_fonts()
            except RuntimeError as font_error:
                self.message.setText(str(font_error))
                self.update_buttons()
                return
            renderer = QSvgRenderer(result)
            if renderer.isValid():
                size = renderer.defaultSize().scaled(400, 260, Qt.AspectRatioMode.KeepAspectRatio)
                pixmap = QPixmap(size)
                pixmap.fill(Qt.GlobalColor.white)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                self.preview.setPixmap(pixmap)
                self.preview_svg = result
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
        self.message.setText("Guardando el diagrama y actualizando el informe...")
        model = self.proposal_model

        def save() -> SavedDiagram:
            path = accept_diagram(self.markdown, reference, code, model)
            return SavedDiagram(path, picture_references(self.markdown))

        self.start_worker(save, self.save_finished)

    def save_finished(self, result: object, error: str) -> None:
        self.worker = None
        self.update_buttons()
        if error or not isinstance(result, SavedDiagram):
            self.message.setText("No se pudo guardar el diagrama.")
            QMessageBox.critical(
                self, "Error de revisión", error or "El guardado no devolvió un resultado válido."
            )
            return
        self.references = result.references
        self.message.setText(
            f"Diagrama guardado: {result.path.name}. Se conserva la imagen original."
        )
        self.accepted_code = self.editor.toPlainText().strip()
        self.remember_picture()
        self.update_buttons()

    def open_preview(self) -> None:
        if self.preview_svg is None or self.worker is not None:
            return
        if self.preview_viewer is not None:
            self.preview_viewer.deleteLater()
        self.preview_viewer = ImagePreviewDialog(self.preview_svg, self)
        self.preview_viewer.showFullScreen()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "loading_overlay"):
            self.loading_overlay.setGeometry(self.rect())

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
