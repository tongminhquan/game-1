from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
import json
import uuid

from .models import PostResult


@dataclass
class RunHistoryItem:
    row_number: int
    title: str
    status: str
    link: str | None = None
    error: str | None = None


@dataclass
class RunHistoryRecord:
    run_id: str
    mode: str
    started_at: str
    finished_at: str
    excel_path: str
    image_folder: str | None = None
    export_excel_path: str | None = None
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    summary: str = ""
    error: str | None = None
    orphan_files: list[str] = field(default_factory=list)
    results: list[RunHistoryItem] = field(default_factory=list)


class RunHistoryStore:
    def __init__(self, history_path: str | Path = "config/run_history.json", max_records: int = 300):
        self.history_path = Path(history_path)
        self.max_records = max_records

    def load_records(self) -> list[RunHistoryRecord]:
        if not self.history_path.exists():
            return []
        try:
            raw = json.loads(self.history_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if not isinstance(raw, list):
            return []
        return [_record_from_dict(item) for item in raw if isinstance(item, dict)]

    def append_run(
        self,
        mode: str,
        excel_path: str | Path,
        image_folder: str | Path | None,
        results: list[PostResult],
        export_excel_path: str | Path | None = None,
        started_at: str | None = None,
        summary: str | None = None,
        error: str | None = None,
        orphan_files: list[str | Path] | None = None,
    ) -> RunHistoryRecord:
        items = [
            RunHistoryItem(
                row_number=result.row_number,
                title=result.title,
                status=result.status,
                link=result.link,
                error=result.error,
            )
            for result in results
        ]
        success = sum(1 for item in items if item.status == "success")
        failed = sum(1 for item in items if item.status == "failed")
        skipped = sum(1 for item in items if item.status == "skipped")
        total = len(items)
        finished_at = current_timestamp()
        record = RunHistoryRecord(
            run_id=_new_run_id(),
            mode=mode,
            started_at=started_at or finished_at,
            finished_at=finished_at,
            excel_path=str(excel_path),
            image_folder=str(image_folder) if image_folder else None,
            export_excel_path=str(export_excel_path) if export_excel_path else None,
            total=total,
            success=success,
            failed=failed,
            skipped=skipped,
            summary=summary or f"{success}/{total} thành công",
            error=error,
            orphan_files=[str(path) for path in (orphan_files or [])],
            results=items,
        )
        self.append_record(record)
        return record

    def append_record(self, record: RunHistoryRecord) -> None:
        records = [record, *self.load_records()]
        self._write_records(records[: self.max_records])

    def clear(self) -> None:
        self._write_records([])

    def _write_records(self, records: list[RunHistoryRecord]) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(record) for record in records]
        temp_path = self.history_path.with_suffix(self.history_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.history_path)


def current_timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_run_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _record_from_dict(data: dict) -> RunHistoryRecord:
    results = [_item_from_dict(item) for item in data.get("results", []) if isinstance(item, dict)]
    total = _as_int(data.get("total"), len(results))
    return RunHistoryRecord(
        run_id=str(data.get("run_id") or _new_run_id()),
        mode=str(data.get("mode") or "manual"),
        started_at=str(data.get("started_at") or data.get("finished_at") or ""),
        finished_at=str(data.get("finished_at") or ""),
        excel_path=str(data.get("excel_path") or ""),
        image_folder=_as_optional_str(data.get("image_folder")),
        export_excel_path=_as_optional_str(data.get("export_excel_path")),
        total=total,
        success=_as_int(data.get("success"), sum(1 for item in results if item.status == "success")),
        failed=_as_int(data.get("failed"), sum(1 for item in results if item.status == "failed")),
        skipped=_as_int(data.get("skipped"), sum(1 for item in results if item.status == "skipped")),
        summary=str(data.get("summary") or ""),
        error=_as_optional_str(data.get("error")),
        orphan_files=[str(path) for path in data.get("orphan_files", []) if path],
        results=results,
    )


def _item_from_dict(data: dict) -> RunHistoryItem:
    return RunHistoryItem(
        row_number=_as_int(data.get("row_number"), 0),
        title=str(data.get("title") or ""),
        status=str(data.get("status") or ""),
        link=_as_optional_str(data.get("link")),
        error=_as_optional_str(data.get("error")),
    )


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
