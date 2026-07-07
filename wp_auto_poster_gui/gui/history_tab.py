from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from wp_auto_poster_gui.core.history_store import RunHistoryRecord, RunHistoryStore


class HistoryTab(QWidget):
    def __init__(self, store: RunHistoryStore):
        super().__init__()
        self.store = store
        self.records: list[RunHistoryRecord] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        title = QLabel("Lịch sử các lần chạy")
        title.setObjectName("sectionTitle")
        refresh_button = QPushButton("Làm mới")
        refresh_button.clicked.connect(self.refresh)
        top_row.addWidget(title)
        top_row.addStretch(1)
        top_row.addWidget(refresh_button)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._show_selected_detail)

        self.detail_box = QTextEdit()
        self.detail_box.setReadOnly(True)
        self.detail_box.setMinimumHeight(170)

        layout.addLayout(top_row)
        layout.addWidget(self.table, 3)
        layout.addWidget(QLabel("Chi tiết"))
        layout.addWidget(self.detail_box, 2)

        self.refresh()

    def refresh(self) -> None:
        self.records = self.store.load_records()
        headers = [
            "Thời gian",
            "Kiểu",
            "File Excel",
            "Tổng",
            "Thành công",
            "Lỗi",
            "Bỏ qua",
            "File kết quả",
            "Ghi chú",
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(self.records))

        for row_index, record in enumerate(self.records):
            values = [
                record.finished_at,
                _mode_label(record.mode),
                _name_or_blank(record.excel_path),
                str(record.total),
                str(record.success),
                str(record.failed),
                str(record.skipped),
                _name_or_blank(record.export_excel_path),
                record.summary or record.error or "",
            ]
            tooltips = [
                record.run_id,
                record.mode,
                record.excel_path,
                "",
                "",
                "",
                "",
                record.export_excel_path or "",
                record.error or record.summary,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if tooltips[column]:
                    item.setToolTip(tooltips[column])
                self.table.setItem(row_index, column, item)

        self.table.resizeColumnsToContents()
        if self.records:
            self.table.selectRow(0)
        else:
            self.detail_box.setPlainText("Chưa có lịch sử chạy.")

    def _show_selected_detail(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.records):
            return
        record = self.records[row]
        lines = [
            f"ID: {record.run_id}",
            f"Thời gian bắt đầu: {record.started_at}",
            f"Thời gian hoàn tất: {record.finished_at}",
            f"Kiểu chạy: {_mode_label(record.mode)}",
            f"File Excel: {record.excel_path}",
            f"Thư mục ảnh: {record.image_folder or ''}",
            f"File Excel kết quả: {record.export_excel_path or ''}",
            f"Kết quả: {record.success}/{record.total} thành công, {record.failed} lỗi, {record.skipped} bỏ qua",
        ]
        if record.summary:
            lines.append(f"Ghi chú: {record.summary}")
        if record.error:
            lines.append(f"Lỗi chung: {record.error}")
        if record.orphan_files:
            lines.append("Ảnh không khớp: " + ", ".join(record.orphan_files[:20]))
            if len(record.orphan_files) > 20:
                lines.append(f"... và {len(record.orphan_files) - 20} file khác")

        lines.append("")
        lines.append("Chi tiết từng bài:")
        if not record.results:
            lines.append("- Không có kết quả từng bài.")
        for item in record.results[:250]:
            note = item.link or item.error or ""
            lines.append(f"- Dòng {item.row_number}: [{item.status}] {item.title} {note}")
        if len(record.results) > 250:
            lines.append(f"... và {len(record.results) - 250} dòng khác")

        self.detail_box.setPlainText("\n".join(lines))


def _mode_label(mode: str) -> str:
    if mode == "scheduled":
        return "Lịch tự động"
    if mode == "manual":
        return "Thủ công"
    return mode


def _name_or_blank(value: str | None) -> str:
    return Path(value).name if value else ""
