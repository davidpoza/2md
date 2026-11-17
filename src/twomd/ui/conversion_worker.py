import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from threading import BoundedSemaphore, Event

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from twomd.config import Settings
from twomd.conversion import ConversionCancelled, convert_document


@dataclass(frozen=True)
class AutomaticOptions:
    settings: Settings
    api_key: str = field(repr=False)
    proxy_password: str | None = field(repr=False)
    requests: BoundedSemaphore = field(repr=False)


class ConversionSignals(QObject):
    finished = Signal(int, object)
    failed = Signal(int, str)
    cancelled = Signal(int)
    activity = Signal(int, str)


class ConversionWorker(QRunnable):
    def __init__(
        self,
        row: int,
        source: Path,
        destination: Path,
        cancel: Event,
        automatic: AutomaticOptions | None = None,
    ) -> None:
        super().__init__()
        self.row = row
        self.source = source
        self.destination = destination
        self.cancel = cancel
        self.automatic = automatic
        self.signals = ConversionSignals()

    @Slot()
    def run(self) -> None:
        try:
            variant = ""
            if self.automatic:
                variant = hashlib.sha256(
                    ("auto-v1:" + self.automatic.settings.ai.model_dump_json()).encode("utf-8")
                ).hexdigest()
            outcome = convert_document(
                self.source, self.destination, self.cancel, cache_variant=variant
            )
            if self.automatic:
                from twomd.automatic_diagrams import process_automatic_diagrams

                outcome = process_automatic_diagrams(
                    outcome,
                    self.automatic.settings,
                    self.automatic.api_key,
                    self.automatic.proxy_password,
                    self.cancel,
                    self.automatic.requests,
                    progress=lambda message: self.signals.activity.emit(self.row, message),
                )
        except ConversionCancelled:
            self.signals.cancelled.emit(self.row)
        except Exception as error:  # noqa: BLE001
            self.signals.failed.emit(self.row, f"{type(error).__name__}: {error}")
        else:
            self.signals.finished.emit(self.row, outcome)
