from __future__ import annotations

from PySide6.QtCore import QDateTime, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from wp_auto_poster_gui.core.scheduler_service import ScheduleConfig

_IMAGE_SIZE_OPTIONS = [
    ("Tự động", "auto"),
    ("Nhỏ (300px)", "small"),
    ("Vừa (600px)", "medium"),
    ("Lớn (900px)", "large"),
    ("Toàn chiều rộng", "full"),
    ("Tùy chỉnh", "custom"),
]

_IMAGE_ALIGN_OPTIONS = [
    ("Giữa", "aligncenter"),
    ("Trái", "alignleft"),
    ("Phải", "alignright"),
    ("Không căn", "alignnone"),
]

_WEEKDAY_OPTIONS = [
    ("Thứ hai", "mon"),
    ("Thứ ba", "tue"),
    ("Thứ tư", "wed"),
    ("Thứ năm", "thu"),
    ("Thứ sáu", "fri"),
    ("Thứ bảy", "sat"),
    ("Chủ nhật", "sun"),
]


class ScheduleTab(QWidget):
    config_changed = Signal()

    def __init__(self):
        super().__init__()

        self.enabled_check = QCheckBox("Bật lịch tự động")
        self.excel_edit = QLineEdit()
        self.excel_edit.setPlaceholderText("Chọn file Excel cố định cho lịch...")
        self.image_folder_edit = QLineEdit()
        self.image_folder_edit.setPlaceholderText("(Tùy chọn) thư mục ảnh hoặc file ZIP đặt tên theo ma_bai...")

        self.max_images_spin = QSpinBox()
        self.max_images_spin.setRange(0, 50)
        self.max_images_spin.setValue(2)

        self.image_size_combo = QComboBox()
        for label, value in _IMAGE_SIZE_OPTIONS:
            self.image_size_combo.addItem(label, value)
        self.image_custom_width_spin = QSpinBox()
        self.image_custom_width_spin.setRange(100, 2000)
        self.image_custom_width_spin.setValue(800)
        self.image_custom_width_spin.setSuffix(" px")
        self.image_custom_width_spin.setVisible(False)
        self.image_size_combo.currentIndexChanged.connect(self._on_image_size_changed)

        self.image_align_combo = QComboBox()
        for label, value in _IMAGE_ALIGN_OPTIONS:
            self.image_align_combo.addItem(label, value)

        self.frequency_combo = QComboBox()
        self.frequency_combo.addItem("Hàng ngày", "daily")
        self.frequency_combo.addItem("Hàng tuần", "weekly")
        self.frequency_combo.addItem("Một lần theo ngày giờ", "once")
        self.frequency_combo.addItem("Custom cron", "custom")

        self.weekday_combo = QComboBox()
        for label, value in _WEEKDAY_OPTIONS:
            self.weekday_combo.addItem(label, value)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.run_at_edit = QDateTimeEdit()
        self.run_at_edit.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.run_at_edit.setCalendarPopup(True)
        self.run_at_edit.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        self.cron_edit = QLineEdit()
        self.cron_edit.setPlaceholderText("Ví dụ: 0 9 * * 1-5")

        self.next_run_label = QLabel("Lần chạy kế tiếp: -- (lịch đang tắt)")
        self.last_run_label = QLabel("Lần chạy gần nhất: chưa chạy lần nào")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        data_box = QGroupBox("Dữ liệu dùng khi chạy theo lịch")
        data_form = QFormLayout(data_box)
        excel_row = QHBoxLayout()
        excel_button = QPushButton("Chọn file...")
        excel_button.clicked.connect(self._choose_excel)
        excel_row.addWidget(self.excel_edit, 1)
        excel_row.addWidget(excel_button)

        image_row = QHBoxLayout()
        image_button = QPushButton("Chọn thư mục...")
        image_button.clicked.connect(self._choose_image_folder)
        image_zip_button = QPushButton("Chọn ZIP...")
        image_zip_button.clicked.connect(self._choose_image_zip)
        image_row.addWidget(self.image_folder_edit, 1)
        image_row.addWidget(image_button)
        image_row.addWidget(image_zip_button)

        image_options = QHBoxLayout()
        image_options.addWidget(self.max_images_spin)
        image_options.addWidget(QLabel("Kích thước:"))
        image_options.addWidget(self.image_size_combo)
        image_options.addWidget(self.image_custom_width_spin)
        image_options.addWidget(QLabel("Căn ảnh:"))
        image_options.addWidget(self.image_align_combo)
        image_options.addStretch(1)

        data_form.addRow("File Excel:", excel_row)
        data_form.addRow("Thư mục ảnh:", image_row)
        data_form.addRow("Số ảnh tối đa mỗi bài:", image_options)

        frequency_box = QGroupBox("Tần suất chạy")
        frequency_form = QFormLayout(frequency_box)
        frequency_form.addRow("Tần suất:", self.frequency_combo)
        frequency_form.addRow("Thứ:", self.weekday_combo)
        frequency_form.addRow("Giờ chạy:", self.time_edit)
        frequency_form.addRow("Ngày giờ chạy:", self.run_at_edit)
        frequency_form.addRow("Cron:", self.cron_edit)

        save_row = QHBoxLayout()
        save_button = QPushButton("💾 Lưu lịch")
        save_button.clicked.connect(lambda *_args: self.config_changed.emit())
        save_row.addWidget(self.enabled_check)
        save_row.addStretch(1)
        save_row.addWidget(save_button)

        status_box = QGroupBox("Trạng thái")
        status_layout = QVBoxLayout(status_box)
        status_layout.addWidget(self.next_run_label)
        status_layout.addWidget(self.last_run_label)

        tip = QLabel(
            "💡 Khi đóng cửa sổ (nút X), ứng dụng thu nhỏ xuống khay hệ thống và lịch vẫn chạy ngầm. "
            "Muốn thoát hẳn: chuột phải vào icon ở khay → Thoát hẳn."
        )
        tip.setObjectName("mutedLabel")
        tip.setWordWrap(True)

        layout.addWidget(data_box)
        layout.addWidget(frequency_box)
        layout.addLayout(save_row)
        layout.addWidget(status_box)
        layout.addWidget(tip)
        layout.addStretch(1)

        for widget in [
            self.excel_edit,
            self.image_folder_edit,
            self.frequency_combo,
            self.weekday_combo,
            self.time_edit,
            self.run_at_edit,
            self.cron_edit,
            self.max_images_spin,
            self.image_size_combo,
            self.image_align_combo,
        ]:
            signal = getattr(widget, "textChanged", None) or getattr(widget, "currentTextChanged", None)
            if signal:
                signal.connect(lambda *_args: self.config_changed.emit())
        self.enabled_check.stateChanged.connect(lambda *_args: self.config_changed.emit())
        self.time_edit.timeChanged.connect(lambda *_args: self.config_changed.emit())
        self.run_at_edit.dateTimeChanged.connect(lambda *_args: self.config_changed.emit())
        self.max_images_spin.valueChanged.connect(lambda *_args: self.config_changed.emit())
        self.image_custom_width_spin.valueChanged.connect(lambda *_args: self.config_changed.emit())
        self.frequency_combo.currentTextChanged.connect(self._update_mode_visibility)
        self._update_mode_visibility()

    def load_config(self, config: ScheduleConfig) -> None:
        self.enabled_check.setChecked(config.enabled)
        self.excel_edit.setText(config.excel_path)
        self.image_folder_edit.setText(config.image_folder)

        _set_combo_data(self.frequency_combo, config.frequency)
        _set_combo_data(self.weekday_combo, config.weekday)

        parsed_time = QTime.fromString(config.time, "HH:mm")
        if parsed_time.isValid():
            self.time_edit.setTime(parsed_time)
        parsed_run_at = QDateTime.fromString(config.run_at, Qt.ISODate)
        if parsed_run_at.isValid():
            self.run_at_edit.setDateTime(parsed_run_at)
        elif config.frequency == "once":
            self.run_at_edit.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        self.cron_edit.setText(config.cron_expression)
        self.max_images_spin.setValue(config.max_images_per_post)

        _set_combo_data(self.image_size_combo, config.image_display_size)
        _set_combo_data(self.image_align_combo, config.image_alignment)
        self.image_custom_width_spin.setValue(config.image_custom_width)
        self._on_image_size_changed()

        self.last_run_label.setText("Lần chạy gần nhất: " + _status_text(config.last_run_at, config.last_result))
        self._update_mode_visibility()

    def to_config(self) -> ScheduleConfig:
        return ScheduleConfig(
            enabled=self.enabled_check.isChecked(),
            excel_path=self.excel_edit.text().strip(),
            image_folder=self.image_folder_edit.text().strip(),
            frequency=self._frequency(),
            time=self.time_edit.time().toString("HH:mm"),
            run_at=self.run_at_edit.dateTime().toString(Qt.ISODate),
            weekday=self.weekday_combo.currentData() or self.weekday_combo.currentText(),
            cron_expression=self.cron_edit.text().strip(),
            max_images_per_post=self.max_images_spin.value(),
            image_alignment=self.image_align_combo.currentData() or "aligncenter",
            image_display_size=self.image_size_combo.currentData() or "auto",
            image_custom_width=self.image_custom_width_spin.value(),
        )

    def set_next_run(self, value: str | None) -> None:
        self.next_run_label.setText(f"Lần chạy kế tiếp: {value or '-- (lịch đang tắt)'}")

    def _choose_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file Excel", "", "Excel (*.xlsx *.xls)")
        if path:
            self.excel_edit.setText(path)

    def _choose_image_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Chọn thư mục ảnh")
        if path:
            self.image_folder_edit.setText(path)

    def _choose_image_zip(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file ZIP ảnh", "", "ZIP (*.zip)")
        if path:
            self.image_folder_edit.setText(path)

    def _update_mode_visibility(self, *_args) -> None:
        frequency = self._frequency()
        self.weekday_combo.setEnabled(frequency == "weekly")
        self.time_edit.setEnabled(frequency in {"daily", "weekly"})
        self.run_at_edit.setEnabled(frequency == "once")
        self.cron_edit.setEnabled(frequency == "custom")

    def _on_image_size_changed(self, *_args) -> None:
        self.image_custom_width_spin.setVisible((self.image_size_combo.currentData() or "auto") == "custom")

    def _frequency(self) -> str:
        return self.frequency_combo.currentData() or self.frequency_combo.currentText()


def _set_combo_data(combo: QComboBox, value: str) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


def _status_text(last_run_at: str | None, last_result: str | None) -> str:
    if not last_run_at:
        return "chưa chạy lần nào"
    return f"{last_run_at}: {last_result or ''}"
