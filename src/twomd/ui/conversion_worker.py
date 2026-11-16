from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from twomd.conversion import ConversionCancelled, convert_document


class ConversionSignals(QObject):
    finished = Signal(int, object)
    failed = Signal(int, str)
    cancelled = Signal(int)


class ConversionWorker(QRunnable):
    def __init__(
        self, row: int, source: Path, destination: Path, cancel: Event, models: Path | None
    ) -> None:
        super().__init__()
        self.row = row
        self.source = source
        self.destination = destination
        self.cancel = cancel
        self.models = models
        self.signals = ConversionSignals()

    @Slot()
    def run(self) -> None:
        try:
            outcome = convert_document(self.source, self.destination, self.cancel, self.models)
        except ConversionCancelled:
            self.signals.cancelled.emit(self.row)
        except Exception as error:  # noqa: BLE001
            self.signals.failed.emit(self.row, f"{type(error).__name__}: {error}")
        else:
            self.signals.finished.emit(self.row, outcome)
