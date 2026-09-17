"""Importing runs on a worker thread so the window stays responsive."""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QThread, Signal

from ..core.library import ImportProgress, ImportReport, Library


class ImportWorker(QThread):
    """Parses the dropped files; nothing is written to the database here."""

    progressed = Signal(object)          # ImportProgress
    completed = Signal(object)           # ImportReport
    failed = Signal(str)

    def __init__(self, library: Library, paths: Sequence[str], parent=None) -> None:
        super().__init__(parent)
        self._library = library
        self._paths = list(paths)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:                                   # pragma: no cover - thread body
        try:
            report = self._library.import_paths(
                self._paths,
                progress=self.progressed.emit,
                should_cancel=lambda: self._cancelled)
            self.completed.emit(report)
        except Exception as error:                            # noqa: BLE001
            self.failed.emit(str(error))


def describe(progress: ImportProgress) -> str:
    page = f" page {progress.page_number}" if progress.page_number else ""
    return (f"{progress.file_name}{page}: {progress.stage} "
            f"({progress.file_index + 1} of {progress.file_count})")


def describe_report(report: ImportReport) -> str:
    parts = [f"{len(report.pages)} page(s), {report.product_count} products "
             f"in {report.seconds:.0f}s"]
    if report.failures:
        parts.append(f"{len(report.failures)} file(s) failed")
    return ", ".join(parts)
