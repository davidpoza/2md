"""Vista ampliada de diagramas renderizados."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QPainter, QPixmap, QResizeEvent, QShortcut, QWheelEvent
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ImageView(QGraphicsView):
    zoom_changed = Signal(float)

    def __init__(self, pixmap: QPixmap, parent: QWidget) -> None:
        super().__init__(parent)
        scene = QGraphicsScene(self)
        scene.addPixmap(pixmap)
        self.setScene(scene)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.fitted = True

    def fit_image(self) -> None:
        self.fitted = True
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom_changed.emit(self.transform().m11())

    def actual_size(self) -> None:
        self.fitted = False
        self.resetTransform()
        self.zoom_changed.emit(1.0)

    def zoom(self, factor: float) -> None:
        current = self.transform().m11()
        target = min(32.0, max(0.01, current * factor))
        self.fitted = False
        self.scale(target / current, target / current)
        self.zoom_changed.emit(target)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta:
            self.zoom(1.25 if delta > 0 else 0.8)
        event.accept()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.fitted:
            self.fit_image()


class ImagePreviewDialog(QDialog):
    def __init__(self, pixmap: QPixmap, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Previsualización Mermaid")
        self.setModal(True)
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.zoom_label = QLabel()
        self.view = ImageView(pixmap, self)
        self.view.zoom_changed.connect(
            lambda scale: self.zoom_label.setText(f"{scale * 100:.0f} %")
        )
        self.zoom_out = QPushButton("Alejar (-)")
        self.zoom_out.clicked.connect(lambda: self.view.zoom(0.8))
        self.zoom_in = QPushButton("Acercar (+)")
        self.zoom_in.clicked.connect(lambda: self.view.zoom(1.25))
        self.actual = QPushButton("100 %")
        self.actual.clicked.connect(self.view.actual_size)
        self.fit = QPushButton("Ajustar a pantalla")
        self.fit.clicked.connect(self.view.fit_image)
        close = QPushButton("Cerrar (Esc)")
        close.clicked.connect(self.reject)
        for button in (self.zoom_out, self.zoom_in, self.actual, self.fit, close):
            button.setAutoDefault(False)
            toolbar.addWidget(button)
        toolbar.addWidget(self.zoom_label)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        layout.addWidget(self.view, 1)
        layout.addWidget(QLabel("Rueda: zoom · Arrastrar: desplazar · Esc: cerrar"))
        for key, action in (
            ("+", lambda: self.view.zoom(1.25)),
            ("=", lambda: self.view.zoom(1.25)),
            ("-", lambda: self.view.zoom(0.8)),
            ("0", self.view.actual_size),
            ("F", self.view.fit_image),
        ):
            QShortcut(QKeySequence(key), self, activated=action)
