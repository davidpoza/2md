from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import twomd
from twomd.config import Settings, save_settings
from twomd.conversion import ConversionOutcome
from twomd.credentials import set_secret
from twomd.documents import supported_documents
from twomd.ui.conversion_worker import ConversionWorker
from twomd.ui.review_dialog import ReviewDialog
from twomd.ui.settings_dialog import SettingsDialog


class DropArea(QLabel):
    paths_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__("Arrastra aquí archivos DOCX, PDF o carpetas")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(90)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.paths_dropped.emit(paths)
            event.acceptProposedAction()


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, config_path: Path) -> None:
        super().__init__()
        self.settings = settings
        self.config_path = config_path
        self.documents: list[Path] = []
        self.outcomes: dict[int, ConversionOutcome] = {}
        self.workers: dict[int, ConversionWorker] = {}
        self.pending: list[int] = []
        self.cancel_event = Event()
        self.batch_total = 0
        self.batch_done = 0
        self.batch_destination = Path()
        self.batch_models: Path | None = None
        self.thread_pool = QThreadPool(self)
        self.setWindowTitle("2MD — Conversor documental")
        self.resize(920, 680)

        central = QWidget()
        layout = QVBoxLayout(central)
        self.setCentralWidget(central)
        title = QLabel("2MD · Conversor documental")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(QLabel("Prepara documentos Word y PDF para su conversión a Markdown."))

        drop = DropArea()
        drop.paths_dropped.connect(self.add_paths)
        layout.addWidget(drop)
        buttons = QHBoxLayout()
        add_files = QPushButton("Añadir archivos")
        add_files.clicked.connect(self.choose_files)
        add_folder = QPushButton("Añadir carpeta")
        add_folder.setToolTip("Añade los archivos DOCX y PDF de la carpeta, sin subcarpetas.")
        add_folder.clicked.connect(self.choose_folder)
        settings_button = QPushButton("Configuración")
        settings_button.clicked.connect(self.configure)
        buttons.addWidget(add_files)
        buttons.addWidget(add_folder)
        buttons.addStretch()
        buttons.addWidget(settings_button)
        layout.addLayout(buttons)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Documento", "Estado", "Progreso"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, 1)

        destination = QHBoxLayout()
        destination.addWidget(QLabel("Carpeta de destino:"))
        self.destination = QLineEdit(settings.output_directory)
        self.destination.setReadOnly(True)
        destination.addWidget(self.destination, 1)
        choose_destination = QPushButton("Seleccionar")
        choose_destination.clicked.connect(self.choose_destination)
        destination.addWidget(choose_destination)
        layout.addLayout(destination)

        layout.addWidget(QLabel("Progreso global"))
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        self.start_button = QPushButton("Iniciar")
        self.start_button.clicked.connect(self.start_conversion)
        actions.addWidget(self.start_button)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_conversion)
        actions.addWidget(self.cancel_button)
        self.retry_button = QPushButton("Reintentar")
        self.retry_button.clicked.connect(self.retry_failed)
        actions.addWidget(self.retry_button)
        review_button = QPushButton("Revisar diagramas")
        review_button.clicked.connect(self.review_diagrams)
        actions.addWidget(review_button)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addWidget(QLabel("Actividad"))
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumHeight(110)
        self.activity.appendPlainText(
            "Añade documentos y selecciona una carpeta de destino para iniciar la conversión."
        )
        layout.addWidget(self.activity)

    def add_paths(self, paths: list[Path]) -> None:
        files = []
        for path in paths:
            if path.is_dir():
                try:
                    files.extend(sorted(path.iterdir(), key=lambda item: item.name.casefold()))
                except OSError as error:
                    self.activity.appendPlainText(f"No se puede leer la carpeta {path}: {error}")
            else:
                files.append(path)
        try:
            candidates = supported_documents(files)
        except OSError as error:
            self.activity.appendPlainText(f"No se pueden leer los archivos: {error}")
            return
        existing = {str(path).casefold() for path in self.documents}
        added = 0
        for path in candidates:
            if str(path).casefold() in existing:
                continue
            existing.add(str(path).casefold())
            self.documents.append(path)
            row = self.table.rowCount()
            self.table.insertRow(row)
            for column, value in enumerate((str(path), "Pendiente", "0 %")):
                self.table.setItem(row, column, QTableWidgetItem(value))
            added += 1
        self.activity.appendPlainText(f"Documentos añadidos: {added}.")

    def choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Añadir documentos", "", "Documentos (*.docx *.pdf)"
        )
        if files:
            self.add_paths([Path(file) for file in files])

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Añadir carpeta")
        if folder:
            self.add_paths([Path(folder)])

    def persist(self, settings: Settings) -> bool:
        try:
            save_settings(self.config_path, settings)
        except OSError as error:
            QMessageBox.critical(self, "Error de configuración", f"No se pudo guardar: {error}")
            return False
        self.settings = settings
        return True

    def choose_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta de destino", self.settings.output_directory
        )
        if folder:
            updated = self.settings.model_copy(update={"output_directory": folder})
            if self.persist(updated):
                self.destination.setText(folder)

    def configure(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                if dialog.api_key.text():
                    set_secret("api", dialog.api_key.text())
                if dialog.proxy_password.text():
                    set_secret("proxy", dialog.proxy_password.text())
            except Exception:  # noqa: BLE001
                QMessageBox.critical(
                    self, "Credenciales", "No se pudieron guardar las credenciales de Windows."
                )
                return
            self.persist(dialog.values())

    def start_conversion(self) -> None:
        if self.workers or self.pending:
            return
        rows = [
            row
            for row in range(len(self.documents))
            if self.table.item(row, 1).text() == "Pendiente"
        ]
        if not rows:
            QMessageBox.information(self, "Conversión", "No hay documentos pendientes.")
            return
        if not self.settings.output_directory:
            QMessageBox.information(self, "Conversión", "Selecciona una carpeta de destino.")
            return
        models = (
            Path(self.settings.models_directory)
            if self.settings.models_directory
            else Path(twomd.__file__).parent / "resources" / "models"
        )
        if (
            any(self.documents[row].suffix.lower() == ".pdf" for row in rows)
            and not models.is_dir()
        ):
            QMessageBox.information(
                self,
                "Modelos de Docling",
                "Selecciona en Configuración una carpeta con los modelos locales de Docling. "
                "Las descargas automáticas aún no están integradas con el proxy. "
                "Los archivos PDF se marcarán como error; los DOCX continuarán.",
            )
        self.cancel_event = Event()
        self.pending = rows
        self.batch_total = len(rows)
        self.batch_done = 0
        self.batch_destination = Path(self.settings.output_directory)
        self.batch_models = models if models.is_dir() else None
        self.thread_pool.setMaxThreadCount(self.settings.document_concurrency)
        self.start_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, self.batch_total)
        self.progress.setValue(0)
        self.schedule()

    def schedule(self) -> None:
        while self.pending and len(self.workers) < self.thread_pool.maxThreadCount():
            row = self.pending.pop(0)
            source = self.documents[row]
            worker = ConversionWorker(
                row, source, self.batch_destination, self.cancel_event, self.batch_models
            )
            worker.signals.finished.connect(self.conversion_finished)
            worker.signals.failed.connect(self.conversion_failed)
            worker.signals.cancelled.connect(self.conversion_cancelled)
            self.workers[row] = worker
            self.table.item(row, 1).setText("Extrayendo contenido")
            self.table.item(row, 2).setText("En curso")
            self.activity.appendPlainText(f"Convirtiendo: {source}")
            self.thread_pool.start(worker)

    def conversion_finished(self, row: int, outcome: ConversionOutcome) -> None:
        self.outcomes[row] = outcome
        status = "Completado con advertencias" if outcome.warnings else "Completado"
        self.table.item(row, 1).setText(status)
        self.table.item(row, 2).setText("100 %")
        self.activity.appendPlainText(f"Markdown generado: {outcome.markdown}")
        for warning in outcome.warnings:
            self.activity.appendPlainText(f"Advertencia: {warning}")
        self.complete_row(row)

    def review_diagrams(self) -> None:
        row = self.table.currentRow()
        outcome = self.outcomes.get(row)
        if outcome is None:
            QMessageBox.information(self, "Revisión", "Selecciona un documento convertido.")
            return
        try:
            dialog = ReviewDialog(outcome.markdown, self.settings, self)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Revisión", f"No se puede abrir la revisión: {error}")
            return
        if not dialog.references:
            QMessageBox.information(self, "Revisión", "No hay imágenes locales para revisar.")
            return
        dialog.exec()

    def conversion_failed(self, row: int, message: str) -> None:
        self.table.item(row, 1).setText("Error")
        self.table.item(row, 2).setText("—")
        self.activity.appendPlainText(f"Error: {message}")
        self.complete_row(row)

    def conversion_cancelled(self, row: int) -> None:
        self.table.item(row, 1).setText("Cancelado")
        self.table.item(row, 2).setText("—")
        self.complete_row(row)

    def complete_row(self, row: int) -> None:
        del self.workers[row]
        self.batch_done += 1
        self.progress.setValue(self.batch_done)
        self.schedule()
        if not self.pending and not self.workers:
            self.start_button.setEnabled(True)
            self.retry_button.setEnabled(True)
            self.cancel_button.setEnabled(False)

    def cancel_conversion(self) -> None:
        self.cancel_event.set()
        for row in self.pending:
            self.table.item(row, 1).setText("Cancelado")
            self.table.item(row, 2).setText("—")
            self.batch_done += 1
        self.pending.clear()
        self.progress.setValue(self.batch_done)
        self.cancel_button.setEnabled(False)
        self.activity.appendPlainText(
            "Cancelación solicitada; la extracción en curso debe finalizar primero."
        )

    def retry_failed(self) -> None:
        for row in range(len(self.documents)):
            if self.table.item(row, 1).text() in ("Error", "Cancelado"):
                self.table.item(row, 1).setText("Pendiente")
                self.table.item(row, 2).setText("0 %")
        self.start_conversion()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.workers:
            QMessageBox.information(
                self, "Conversión en curso", "Espera a que termine antes de cerrar 2MD."
            )
            event.ignore()
        else:
            event.accept()
