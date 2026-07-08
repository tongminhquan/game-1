from __future__ import annotations

import html
from pathlib import Path
import json
import re
from threading import Event

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Mapping from display label to internal value
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

from wp_auto_poster_gui.core.excel_reader import ExcelValidationError, read_posts_from_excel
from wp_auto_poster_gui.core.history_store import RunHistoryStore, current_timestamp
from wp_auto_poster_gui.core.image_matcher import match_images_for_posts
from wp_auto_poster_gui.core.models import PosterOptions, WordPressConfig
from wp_auto_poster_gui.core.poster_service import export_links_to_source_excel, prepare_image_source, publish_from_excel
from wp_auto_poster_gui.core.scheduler_service import SchedulerService
from wp_auto_poster_gui.app_info import APP_ICON_PATH, APP_NAME
from wp_auto_poster_gui.gui.config_dialog import AdvancedSettingsDialog
from wp_auto_poster_gui.gui.history_tab import HistoryTab
from wp_auto_poster_gui.gui.preview_table import fill_preview_table, fill_result_table, orphan_label_text
from wp_auto_poster_gui.gui.schedule_tab import ScheduleTab
from wp_auto_poster_gui.gui.tray_icon import create_tray_icon
from wp_auto_poster_gui.gui.workers import (
    BulkPublishWorker,
    ConnectionTestWorker,
    ImageLayoutUpdateWorker,
    PosterWorker,
    WebsiteBulkPublishWorker,
    WebsiteImageLayoutUpdateWorker,
    WebsitePostsLoadWorker,
)


class SelectPanel(QFrame):
    clicked = Signal()

    def __init__(self, title: str, placeholder: str):
        super().__init__()
        self.setObjectName("selectPanel")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(78)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("selectPanelTitle")
        self.path_label = QLabel(placeholder)
        self.path_label.setObjectName("selectPanelPath")
        self.path_label.setAlignment(Qt.AlignCenter)
        self.path_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(2)
        layout.addStretch(1)
        layout.addWidget(self.title_label, 0, Qt.AlignCenter)
        layout.addWidget(self.path_label, 0, Qt.AlignCenter)
        layout.addStretch(1)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def set_path(self, value: str, placeholder: str) -> None:
        path = Path(value) if value else None
        self.path_label.setText(path.name if path else placeholder)


class MainWindow(QMainWindow):
    schedule_message = Signal(str)
    history_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(1180, 760)

        self.settings_path = Path("config/settings.json")
        self.scheduler = SchedulerService("config/schedule.json")
        self.history_store = RunHistoryStore("config/run_history.json")
        self.results = []
        self.poster_worker: PosterWorker | None = None
        self.image_layout_worker: ImageLayoutUpdateWorker | None = None
        self.bulk_publish_worker: BulkPublishWorker | None = None
        self.website_loader_worker: WebsitePostsLoadWorker | None = None
        self.website_bulk_publish_worker: WebsiteBulkPublishWorker | None = None
        self.website_image_layout_worker: WebsiteImageLayoutUpdateWorker | None = None
        self.connection_worker: ConnectionTestWorker | None = None
        self.website_posts: list[dict] = []
        self.stop_event = Event()
        self._quitting = False
        self._manual_run_started_at: str | None = None

        self.delay_seconds = 0
        self.retry_count = 3
        self.timeout_seconds = 30

        self._apply_style()
        self._build_ui()
        self._load_settings()

        self.tray_icon = create_tray_icon(self, self.windowIcon() or QIcon())
        self.schedule_message.connect(lambda message: self.tray_icon.showMessage(APP_NAME, message))
        self.history_changed.connect(self.history_tab.refresh)
        self.schedule_tab.load_config(self.scheduler.config)
        self._apply_schedule()

    def _build_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._manual_tab_compact(), "📝 Đăng thủ công")
        tabs.addTab(self._website_posts_tab(), "🌐 Bài trên web")
        self.schedule_tab = ScheduleTab()
        self.schedule_tab.config_changed.connect(self._on_schedule_changed)
        tabs.addTab(self.schedule_tab, "⏰ Lịch tự động")
        self.history_tab = HistoryTab(self.history_store)
        tabs.addTab(self.history_tab, "🕘 Lịch sử")
        self.setCentralWidget(tabs)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #f4f4f2;
                color: #202020;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 9pt;
            }
            QTabWidget::pane {
                border: 1px solid #bdbdbd;
                background: #f7f7f5;
                top: -1px;
            }
            QTabBar::tab {
                background: #eeeeec;
                border: 1px solid #bdbdbd;
                border-bottom-color: #aaaaaa;
                padding: 5px 13px;
                margin-right: 1px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                border-bottom-color: #ffffff;
            }
            QGroupBox {
                border: 1px solid #d5d5d2;
                margin-top: 12px;
                padding: 8px;
                background: #fafaf8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                background: #f4f4f2;
            }
            QLineEdit, QComboBox, QSpinBox, QTimeEdit, QDateTimeEdit {
                min-height: 22px;
                border: 1px solid #b8b8b4;
                background: #ffffff;
                padding: 2px 5px;
            }
            QPushButton {
                min-height: 24px;
                border: 1px solid #adadad;
                background: #eeeeec;
                padding: 3px 11px;
            }
            QPushButton:hover { background: #f8f8f6; }
            QPushButton:pressed { background: #dededc; }
            QPushButton:disabled {
                color: #9a9a9a;
                background: #eeeeee;
            }
            QTableWidget {
                gridline-color: #c8c8c5;
                background: #ffffff;
                alternate-background-color: #f5f5f3;
                border: 1px solid #c7c7c4;
            }
            QHeaderView::section {
                background: #eeeeec;
                border: 1px solid #c7c7c4;
                padding: 4px;
                font-weight: 600;
            }
            QTextEdit {
                background: #ffffff;
                border: 1px solid #c7c7c4;
                font-family: Consolas, "Courier New", monospace;
            }
            QLabel#mutedLabel { color: #747474; }
            QLabel#warningLabel {
                color: #9a6400;
                background: #fff7df;
                border: 1px solid #eed39b;
                padding: 3px 6px;
            }
            QFrame#selectPanel {
                border: 2px dashed #8f8f8c;
                border-radius: 9px;
                background: #fbfbfa;
            }
            QFrame#selectPanel:hover {
                background: #ffffff;
                border-color: #6f6f6b;
            }
            QLabel#selectPanelTitle {
                font-weight: 700;
                background: transparent;
            }
            QLabel#selectPanelPath {
                color: #555555;
                background: transparent;
            }
            """
        )

    def _manual_tab_compact(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        connection_box = QGroupBox("1. Kết nối WordPress")
        connection_layout = QVBoxLayout(connection_box)
        connection_row = QHBoxLayout()
        self.site_url_edit = QLineEdit()
        self.site_url_edit.setPlaceholderText("https://ten-mien-cua-ban.com")
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("username")
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Application Password")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.connection_status = QLabel("Chưa kiểm tra kết nối.")
        save_button = QPushButton("💾 Lưu")
        save_button.clicked.connect(self._save_settings)
        test_button = QPushButton("🔌 Kiểm tra kết nối")
        test_button.clicked.connect(self._test_connection)

        connection_row.addWidget(QLabel("URL:"))
        connection_row.addWidget(self.site_url_edit, 3)
        connection_row.addWidget(QLabel("User:"))
        connection_row.addWidget(self.username_edit, 2)
        connection_row.addWidget(QLabel("App Password:"))
        connection_row.addWidget(self.password_edit, 3)
        connection_row.addWidget(save_button)
        connection_row.addWidget(test_button)
        connection_layout.addLayout(connection_row)
        connection_layout.addWidget(self.connection_status)

        source_box = QGroupBox("2. Dữ liệu")
        source_layout = QVBoxLayout(source_box)
        self.excel_edit = QLineEdit()
        self.image_folder_edit = QLineEdit()
        self.excel_edit.hide()
        self.image_folder_edit.hide()
        self.max_images_spin = QSpinBox()
        self.max_images_spin.setRange(0, 50)
        self.max_images_spin.setValue(2)
        self.max_images_spin.setFixedWidth(86)
        self.max_images_spin.setAccelerated(True)
        self.max_images_spin.valueChanged.connect(lambda *_args: self._refresh_preview())

        self.image_size_combo = QComboBox()
        for label, _value in _IMAGE_SIZE_OPTIONS:
            self.image_size_combo.addItem(label)
        self.image_custom_width_spin = QSpinBox()
        self.image_custom_width_spin.setRange(100, 2000)
        self.image_custom_width_spin.setValue(800)
        self.image_custom_width_spin.setSuffix(" px")
        self.image_custom_width_spin.setVisible(False)
        self.image_size_combo.currentIndexChanged.connect(self._on_image_size_changed)

        self.image_align_combo = QComboBox()
        for label, _value in _IMAGE_ALIGN_OPTIONS:
            self.image_align_combo.addItem(label)

        self.excel_panel = SelectPanel("File Excel bài viết", "Chưa chọn file Excel")
        self.excel_panel.clicked.connect(self._choose_excel)
        self.image_panel = SelectPanel("Thư mục ảnh hoặc ZIP (tùy chọn)", "Chưa chọn nguồn ảnh")
        self.image_panel.clicked.connect(self._choose_image_folder)
        source_cards = QHBoxLayout()
        source_cards.setSpacing(8)
        source_cards.addWidget(self.excel_panel, 1)
        source_cards.addWidget(self.image_panel, 1)
        source_layout.addLayout(source_cards)

        source_options = QHBoxLayout()
        source_options.addWidget(QLabel("Số ảnh tối đa chèn mỗi bài:"))
        source_options.addWidget(self.max_images_spin)
        clear_images_button = QPushButton("Bỏ chọn nguồn ảnh")
        clear_images_button.clicked.connect(self._clear_image_folder)
        source_options.addWidget(clear_images_button)
        source_options.addSpacing(10)
        source_options.addWidget(QLabel("Kích thước:"))
        source_options.addWidget(self.image_size_combo)
        source_options.addWidget(self.image_custom_width_spin)
        source_options.addWidget(QLabel("Căn ảnh:"))
        source_options.addWidget(self.image_align_combo)
        self.publish_now_check = QCheckBox("Xuất bản ngay khi đăng mới")
        source_options.addWidget(self.publish_now_check)
        source_options.addStretch(1)
        source_layout.addLayout(source_options)

        preview_box = QGroupBox("3. Xem trước")
        preview_layout = QVBoxLayout(preview_box)
        self.preview_table = QTableWidget()
        self.preview_table.setAlternatingRowColors(True)
        self.orphan_label = QLabel()
        self.orphan_label.setObjectName("warningLabel")
        self.orphan_label.setWordWrap(True)
        preview_layout.addWidget(self.preview_table, 1)
        preview_layout.addWidget(self.orphan_label)

        self.post_button = QPushButton("🚀 Đăng ngay")
        self.post_button.setFixedWidth(112)
        self.post_button.clicked.connect(self._start_publish)
        self.update_image_layout_button = QPushButton("🖼 Sửa ảnh bài đã đăng")
        self.update_image_layout_button.setFixedWidth(168)
        self.update_image_layout_button.clicked.connect(self._start_update_image_layout)
        self.bulk_publish_button = QPushButton("📣 Xuất bản hàng loạt")
        self.bulk_publish_button.setFixedWidth(152)
        self.bulk_publish_button.clicked.connect(self._start_bulk_publish)
        self.stop_button = QPushButton("■ Dừng")
        self.stop_button.setFixedWidth(90)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_publish)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        action_row = QHBoxLayout()
        action_row.addWidget(self.post_button)
        action_row.addWidget(self.update_image_layout_button)
        action_row.addWidget(self.bulk_publish_button)
        action_row.addWidget(self.stop_button)
        action_row.addWidget(self.progress, 1)
        action_row.addStretch(1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        log_layout.addWidget(self.log_box)

        result_box = QGroupBox("4. Kết quả")
        result_layout = QVBoxLayout(result_box)
        self.result_table = QTableWidget()
        self.result_table.setAlternatingRowColors(True)
        report_button = QPushButton("📊 Xuất Excel gốc + link")
        report_button.clicked.connect(self._export_report)
        result_layout.addWidget(self.result_table)
        result_layout.addWidget(report_button)
        bottom_row.addWidget(log_box, 5)
        bottom_row.addWidget(result_box, 7)

        advanced_button = QPushButton("⚙ Cài đặt nâng cao...")
        advanced_button.clicked.connect(self._open_advanced_settings)
        advanced_row = QHBoxLayout()
        advanced_row.addWidget(advanced_button)
        advanced_row.addStretch(1)

        layout.addWidget(connection_box)
        layout.addWidget(source_box)
        layout.addWidget(preview_box, 4)
        layout.addLayout(action_row)
        layout.addLayout(bottom_row, 3)
        layout.addLayout(advanced_row)
        self._update_source_panels()
        return page

    def _website_posts_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        list_box = QGroupBox("1. Nhận diện bài đang có trên website")
        list_layout = QVBoxLayout(list_box)
        list_actions = QHBoxLayout()
        self.website_load_button = QPushButton("🔄 Tải bài từ website")
        self.website_load_button.clicked.connect(self._load_website_posts)
        self.website_select_all_button = QPushButton("Chọn tất cả")
        self.website_select_all_button.clicked.connect(self._select_all_website_posts)
        self.website_clear_selection_button = QPushButton("Bỏ chọn")
        self.website_clear_selection_button.clicked.connect(self._clear_website_post_selection)
        self.website_status_label = QLabel("Chưa tải danh sách bài viết.")
        self.website_status_label.setObjectName("mutedLabel")
        list_actions.addWidget(self.website_load_button)
        list_actions.addWidget(self.website_select_all_button)
        list_actions.addWidget(self.website_clear_selection_button)
        list_actions.addWidget(self.website_status_label, 1)
        list_layout.addLayout(list_actions)

        self.website_posts_table = QTableWidget()
        self.website_posts_table.setAlternatingRowColors(True)
        list_layout.addWidget(self.website_posts_table, 1)

        action_box = QGroupBox("2. Thao tác hàng loạt")
        action_layout = QVBoxLayout(action_box)
        image_options = QHBoxLayout()
        self.website_image_size_combo = QComboBox()
        for label, _value in _IMAGE_SIZE_OPTIONS:
            self.website_image_size_combo.addItem(label)
        self.website_image_custom_width_spin = QSpinBox()
        self.website_image_custom_width_spin.setRange(100, 2000)
        self.website_image_custom_width_spin.setValue(800)
        self.website_image_custom_width_spin.setSuffix(" px")
        self.website_image_custom_width_spin.setVisible(False)
        self.website_image_size_combo.currentIndexChanged.connect(self._on_website_image_size_changed)
        self.website_image_align_combo = QComboBox()
        for label, _value in _IMAGE_ALIGN_OPTIONS:
            self.website_image_align_combo.addItem(label)
        image_options.addWidget(QLabel("Kích thước ảnh:"))
        image_options.addWidget(self.website_image_size_combo)
        image_options.addWidget(self.website_image_custom_width_spin)
        image_options.addWidget(QLabel("Căn ảnh:"))
        image_options.addWidget(self.website_image_align_combo)
        image_options.addStretch(1)
        action_layout.addLayout(image_options)

        website_actions = QHBoxLayout()
        self.website_publish_button = QPushButton("📣 Xuất bản bài đã chọn")
        self.website_publish_button.clicked.connect(self._start_website_bulk_publish)
        self.website_update_image_button = QPushButton("🖼 Sửa cỡ/căn ảnh bài đã chọn")
        self.website_update_image_button.clicked.connect(self._start_website_image_layout_update)
        self.website_stop_button = QPushButton("■ Dừng")
        self.website_stop_button.setFixedWidth(90)
        self.website_stop_button.setEnabled(False)
        self.website_stop_button.clicked.connect(self._stop_website_bulk_action)
        self.website_progress = QProgressBar()
        self.website_progress.setRange(0, 0)
        self.website_progress.hide()
        website_actions.addWidget(self.website_publish_button)
        website_actions.addWidget(self.website_update_image_button)
        website_actions.addWidget(self.website_stop_button)
        website_actions.addWidget(self.website_progress, 1)
        action_layout.addLayout(website_actions)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        web_log_box = QGroupBox("Log")
        web_log_layout = QVBoxLayout(web_log_box)
        self.website_log_box = QTextEdit()
        self.website_log_box.setReadOnly(True)
        web_log_layout.addWidget(self.website_log_box)
        web_result_box = QGroupBox("3. Kết quả")
        web_result_layout = QVBoxLayout(web_result_box)
        self.website_result_table = QTableWidget()
        self.website_result_table.setAlternatingRowColors(True)
        web_result_layout.addWidget(self.website_result_table)
        bottom_row.addWidget(web_log_box, 5)
        bottom_row.addWidget(web_result_box, 7)

        layout.addWidget(list_box, 5)
        layout.addWidget(action_box)
        layout.addLayout(bottom_row, 3)
        self._fill_website_posts_table()
        return page

    def _manual_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        connection_box = QGroupBox("Kết nối WordPress")
        connection_form = QFormLayout(connection_box)
        self.site_url_edit = QLineEdit()
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.connection_status = QLabel("Chưa kiểm tra")
        save_button = QPushButton("Lưu")
        save_button.clicked.connect(self._save_settings)
        test_button = QPushButton("Kiểm tra kết nối")
        test_button.clicked.connect(self._test_connection)
        advanced_button = QPushButton("Cài đặt nâng cao")
        advanced_button.clicked.connect(self._open_advanced_settings)

        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addWidget(test_button)
        actions.addWidget(advanced_button)
        actions.addStretch(1)

        connection_form.addRow("URL", self.site_url_edit)
        connection_form.addRow("Username", self.username_edit)
        connection_form.addRow("Application password", self.password_edit)
        connection_form.addRow("Trạng thái", self.connection_status)
        connection_form.addRow("", actions)

        source_box = QGroupBox("Nguồn dữ liệu")
        source_form = QFormLayout(source_box)
        self.excel_edit = QLineEdit()
        self.image_folder_edit = QLineEdit()
        self.max_images_spin = QSpinBox()
        self.max_images_spin.setRange(0, 50)
        self.max_images_spin.setValue(2)

        # Image display settings
        self.image_size_combo = QComboBox()
        for label, _value in _IMAGE_SIZE_OPTIONS:
            self.image_size_combo.addItem(label)
        self.image_custom_width_spin = QSpinBox()
        self.image_custom_width_spin.setRange(100, 2000)
        self.image_custom_width_spin.setValue(800)
        self.image_custom_width_spin.setSuffix(" px")
        self.image_custom_width_spin.setVisible(False)
        self.image_size_combo.currentIndexChanged.connect(self._on_image_size_changed)

        self.image_align_combo = QComboBox()
        for label, _value in _IMAGE_ALIGN_OPTIONS:
            self.image_align_combo.addItem(label)

        excel_button = QPushButton("Chọn Excel")
        excel_button.clicked.connect(self._choose_excel)
        image_button = QPushButton("Chọn thư mục ảnh")
        image_button.clicked.connect(self._choose_image_folder)

        excel_row = QHBoxLayout()
        excel_row.addWidget(self.excel_edit)
        excel_row.addWidget(excel_button)
        image_row = QHBoxLayout()
        image_row.addWidget(self.image_folder_edit)
        image_row.addWidget(image_button)

        image_size_row = QHBoxLayout()
        image_size_row.addWidget(self.image_size_combo)
        image_size_row.addWidget(self.image_custom_width_spin)
        image_size_row.addStretch(1)

        preview_button = QPushButton("Preview")
        preview_button.clicked.connect(self._refresh_preview)
        self.post_button = QPushButton("Đăng ngay")
        self.post_button.clicked.connect(self._start_publish)
        self.stop_button = QPushButton("Dừng")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_publish)
        report_button = QPushButton("Xuất Excel gốc + link")
        report_button.clicked.connect(self._export_report)

        run_row = QHBoxLayout()
        run_row.addWidget(preview_button)
        run_row.addWidget(self.post_button)
        run_row.addWidget(self.stop_button)
        run_row.addWidget(report_button)
        run_row.addStretch(1)

        source_form.addRow("File Excel", excel_row)
        source_form.addRow("Thư mục ảnh", image_row)
        source_form.addRow("Ảnh tối đa mỗi bài", self.max_images_spin)
        source_form.addRow("Kích thước ảnh", image_size_row)
        source_form.addRow("Căn chỉnh ảnh", self.image_align_combo)
        source_form.addRow("", run_row)

        self.preview_table = QTableWidget()
        self.result_table = QTableWidget()
        self.orphan_label = QLabel()
        self.orphan_label.setWordWrap(True)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()

        tables = QSplitter(Qt.Vertical)
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.addWidget(QLabel("Preview"))
        preview_layout.addWidget(self.preview_table)
        preview_layout.addWidget(self.orphan_label)
        result_container = QWidget()
        result_layout = QVBoxLayout(result_container)
        result_layout.addWidget(QLabel("Kết quả"))
        result_layout.addWidget(self.result_table)
        tables.addWidget(preview_container)
        tables.addWidget(result_container)

        layout.addWidget(connection_box)
        layout.addWidget(source_box)
        layout.addWidget(tables, 1)
        layout.addWidget(QLabel("Log"))
        layout.addWidget(self.log_box)
        layout.addWidget(self.progress)
        return page

    def _choose_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file Excel", "", "Excel (*.xlsx *.xls)")
        if path:
            self.excel_edit.setText(path)
            self._update_source_panels()
            self._refresh_preview()

    def _choose_image_folder(self) -> None:
        choice = QMessageBox(self)
        choice.setWindowTitle("Chọn nguồn ảnh")
        choice.setText("Bạn muốn chọn thư mục ảnh đã giải nén hay chọn file ZIP ảnh?")
        folder_button = choice.addButton("Chọn thư mục", QMessageBox.AcceptRole)
        zip_button = choice.addButton("Chọn file ZIP", QMessageBox.ActionRole)
        choice.addButton("Hủy", QMessageBox.RejectRole)
        choice.setDefaultButton(folder_button)
        choice.exec()

        path = ""
        if choice.clickedButton() == folder_button:
            path = QFileDialog.getExistingDirectory(self, "Chọn thư mục ảnh")
        elif choice.clickedButton() == zip_button:
            path, _ = QFileDialog.getOpenFileName(self, "Chọn file ZIP ảnh", "", "ZIP (*.zip)")
        if path:
            self.image_folder_edit.setText(path)
            self._update_source_panels()
            self._refresh_preview()

    def _clear_image_folder(self) -> None:
        self.image_folder_edit.clear()
        self._update_source_panels()
        self._refresh_preview()

    def _update_source_panels(self) -> None:
        if hasattr(self, "excel_panel"):
            self.excel_panel.set_path(self.excel_edit.text().strip(), "Chưa chọn file Excel")
        if hasattr(self, "image_panel"):
            self.image_panel.set_path(self.image_folder_edit.text().strip(), "Chưa chọn nguồn ảnh")

    def _refresh_preview(self) -> bool:
        excel_path = self.excel_edit.text().strip()
        if not excel_path:
            return False
        try:
            posts = read_posts_from_excel(excel_path)
            cleanup = None
            try:
                prepared_source, cleanup = prepare_image_source(
                    excel_path,
                    self.image_folder_edit.text().strip() or None,
                    posts,
                    self._poster_options(),
                    self._log,
                )
                matches, orphan_files = match_images_for_posts(
                    prepared_source,
                    [post.ma_bai or "" for post in posts if post.ma_bai],
                    self.max_images_spin.value(),
                )
            finally:
                if cleanup is not None:
                    cleanup.cleanup()
            fill_preview_table(self.preview_table, posts, matches)
            self.orphan_label.setText(orphan_label_text(orphan_files))
            self._log(f"Preview {len(posts)} bài")
            return True
        except (ExcelValidationError, FileNotFoundError, RuntimeError, ValueError) as exc:
            QMessageBox.warning(self, "Không đọc được dữ liệu", str(exc))
            self._log(f"Lỗi preview: {exc}")
            return False

    def _current_config(self, show_errors: bool = True) -> WordPressConfig | None:
        site_url = self.site_url_edit.text().strip()
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()
        if not site_url or not username or not password:
            if show_errors:
                QMessageBox.warning(self, "Thiếu cấu hình", "Cần nhập URL, username và application password.")
            return None
        return WordPressConfig(
            site_url=site_url,
            username=username,
            application_password=password,
            timeout_seconds=self.timeout_seconds,
            retry_count=self.retry_count,
            delay_seconds=self.delay_seconds,
        )

    def _on_image_size_changed(self, *_args) -> None:
        """Show/hide custom width spin based on selected image size."""
        index = self.image_size_combo.currentIndex()
        size_value = _IMAGE_SIZE_OPTIONS[index][1] if index < len(_IMAGE_SIZE_OPTIONS) else "auto"
        self.image_custom_width_spin.setVisible(size_value == "custom")

    def _current_image_settings(self) -> tuple[str, str, int]:
        """Return (image_alignment, image_display_size, image_custom_width) from UI."""
        size_index = self.image_size_combo.currentIndex()
        display_size = _IMAGE_SIZE_OPTIONS[size_index][1] if size_index < len(_IMAGE_SIZE_OPTIONS) else "auto"
        align_index = self.image_align_combo.currentIndex()
        alignment = _IMAGE_ALIGN_OPTIONS[align_index][1] if align_index < len(_IMAGE_ALIGN_OPTIONS) else "aligncenter"
        custom_width = self.image_custom_width_spin.value()
        return alignment, display_size, custom_width

    def _on_website_image_size_changed(self, *_args) -> None:
        index = self.website_image_size_combo.currentIndex()
        size_value = _IMAGE_SIZE_OPTIONS[index][1] if index < len(_IMAGE_SIZE_OPTIONS) else "auto"
        self.website_image_custom_width_spin.setVisible(size_value == "custom")

    def _current_website_image_settings(self) -> tuple[str, str, int]:
        size_index = self.website_image_size_combo.currentIndex()
        display_size = _IMAGE_SIZE_OPTIONS[size_index][1] if size_index < len(_IMAGE_SIZE_OPTIONS) else "auto"
        align_index = self.website_image_align_combo.currentIndex()
        alignment = _IMAGE_ALIGN_OPTIONS[align_index][1] if align_index < len(_IMAGE_ALIGN_OPTIONS) else "aligncenter"
        custom_width = self.website_image_custom_width_spin.value()
        return alignment, display_size, custom_width

    def _website_poster_options(self) -> PosterOptions:
        alignment, display_size, custom_width = self._current_website_image_settings()
        return PosterOptions(
            max_images_per_post=0,
            image_alignment=alignment,
            image_display_size=display_size,
            image_custom_width=custom_width,
        )

    def _load_website_posts(self) -> None:
        config = self._current_config()
        if not config:
            return
        self._set_website_busy(True)
        self.website_status_label.setText("Đang tải danh sách bài viết...")
        self.website_loader_worker = WebsitePostsLoadWorker(config)
        self.website_loader_worker.progress.connect(self._website_log)
        self.website_loader_worker.completed.connect(self._on_website_posts_loaded)
        self.website_loader_worker.start()

    def _on_website_posts_loaded(self, posts) -> None:
        self.website_posts = list(posts)
        self._fill_website_posts_table()
        self._set_website_busy(False)
        self.website_status_label.setText(f"Đã tải {len(self.website_posts)} bài viết.")
        self._website_log(f"Đã nhận diện {len(self.website_posts)} bài viết trên website")

    def _fill_website_posts_table(self) -> None:
        headers = ["Chọn", "ID", "Trạng thái", "Tiêu đề", "Slug", "Link"]
        self.website_posts_table.setColumnCount(len(headers))
        self.website_posts_table.setHorizontalHeaderLabels(headers)
        self.website_posts_table.setRowCount(len(self.website_posts))
        for row_index, payload in enumerate(self.website_posts):
            check_item = QTableWidgetItem("")
            check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check_item.setCheckState(Qt.Unchecked)
            self.website_posts_table.setItem(row_index, 0, check_item)

            values = [
                str(_website_payload_id(payload) or ""),
                _website_payload_status(payload),
                _website_payload_title(payload),
                _website_payload_slug(payload),
                _website_payload_link(payload),
            ]
            for column, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.website_posts_table.setItem(row_index, column, item)
        self.website_posts_table.resizeColumnsToContents()
        self.website_posts_table.horizontalHeader().setStretchLastSection(True)

    def _select_all_website_posts(self) -> None:
        for row in range(self.website_posts_table.rowCount()):
            item = self.website_posts_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)
        self.website_status_label.setText(f"Đã chọn {self.website_posts_table.rowCount()} bài viết.")

    def _clear_website_post_selection(self) -> None:
        for row in range(self.website_posts_table.rowCount()):
            item = self.website_posts_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)
        self.website_status_label.setText("Đã bỏ chọn tất cả bài viết.")

    def _selected_website_posts(self) -> list[dict]:
        selected: list[dict] = []
        for row in range(self.website_posts_table.rowCount()):
            item = self.website_posts_table.item(row, 0)
            if item and item.checkState() == Qt.Checked and row < len(self.website_posts):
                selected.append(self.website_posts[row])
        return selected

    def _start_website_bulk_publish(self) -> None:
        selected_posts = self._selected_website_posts()
        if not selected_posts:
            QMessageBox.warning(self, "Chưa chọn bài", "Cần tick chọn ít nhất một bài viết trên website.")
            return
        config = self._current_config()
        if not config:
            return
        if QMessageBox.question(
            self,
            "Xác nhận xuất bản bài trên web",
            f"Ứng dụng sẽ chuyển {len(selected_posts)} bài đã chọn sang trạng thái publish. Nội dung bài viết không bị thay đổi.",
        ) != QMessageBox.Yes:
            return

        self._manual_run_started_at = current_timestamp()
        self.stop_event.clear()
        self._set_website_busy(True, allow_stop=True)
        self.website_bulk_publish_worker = WebsiteBulkPublishWorker(selected_posts, config, self.stop_event)
        self.website_bulk_publish_worker.progress.connect(self._website_log)
        self.website_bulk_publish_worker.completed.connect(self._on_website_bulk_publish_completed)
        self.website_bulk_publish_worker.start()

    def _start_website_image_layout_update(self) -> None:
        selected_posts = self._selected_website_posts()
        if not selected_posts:
            QMessageBox.warning(self, "Chưa chọn bài", "Cần tick chọn ít nhất một bài viết trên website.")
            return
        config = self._current_config()
        if not config:
            return
        if QMessageBox.question(
            self,
            "Xác nhận sửa ảnh bài trên web",
            f"Ứng dụng sẽ sửa kích thước và căn ảnh trong {len(selected_posts)} bài đã chọn. Nội dung chữ, SEO, danh mục và tags không bị thay đổi.",
        ) != QMessageBox.Yes:
            return

        self._manual_run_started_at = current_timestamp()
        self.stop_event.clear()
        self._set_website_busy(True, allow_stop=True)
        self.website_image_layout_worker = WebsiteImageLayoutUpdateWorker(
            selected_posts,
            config,
            self._website_poster_options(),
            self.stop_event,
        )
        self.website_image_layout_worker.progress.connect(self._website_log)
        self.website_image_layout_worker.completed.connect(self._on_website_image_layout_update_completed)
        self.website_image_layout_worker.start()

    def _stop_website_bulk_action(self) -> None:
        self.stop_event.set()
        self._website_log("Đã yêu cầu dừng sau bài hiện tại")

    def _on_website_bulk_publish_completed(self, results) -> None:
        self.results = list(results)
        fill_result_table(self.website_result_table, self.results)
        fill_result_table(self.result_table, self.results)
        self._mark_website_posts_published(self.results)
        self._set_website_busy(False)
        success = sum(1 for result in self.results if result.status == "success")
        self.website_status_label.setText(f"Xuất bản xong: {success}/{len(self.results)} thành công.")
        self._website_log(f"Hoàn tất xuất bản bài trên web: {success}/{len(self.results)} thành công")
        record = self._append_run_history(
            mode="website_bulk_publish",
            results=self.results,
            excel_path="",
            image_folder=None,
            export_path=None,
            orphan_files=[],
            started_at=self._manual_run_started_at,
        )
        self._manual_run_started_at = None
        self._website_log(f"Đã lưu lịch sử xuất bản bài trên web: {record.finished_at}")

    def _on_website_image_layout_update_completed(self, results) -> None:
        self.results = list(results)
        fill_result_table(self.website_result_table, self.results)
        fill_result_table(self.result_table, self.results)
        self._set_website_busy(False)
        success = sum(1 for result in self.results if result.status == "success")
        self.website_status_label.setText(f"Sửa ảnh xong: {success}/{len(self.results)} thành công.")
        self._website_log(f"Hoàn tất sửa ảnh bài trên web: {success}/{len(self.results)} thành công")
        record = self._append_run_history(
            mode="website_image_layout",
            results=self.results,
            excel_path="",
            image_folder=None,
            export_path=None,
            orphan_files=[],
            started_at=self._manual_run_started_at,
        )
        self._manual_run_started_at = None
        self._website_log(f"Đã lưu lịch sử sửa ảnh bài trên web: {record.finished_at}")

    def _mark_website_posts_published(self, results) -> None:
        published_ids = {
            int(result.row_number)
            for result in results
            if result.status == "success" and str(result.row_number).isdigit()
        }
        if not published_ids:
            return
        for payload in self.website_posts:
            post_id = _website_payload_id(payload)
            if post_id in published_ids:
                payload["status"] = "publish"
        self._fill_website_posts_table()

    def _set_website_busy(self, busy: bool, allow_stop: bool = False) -> None:
        self.website_progress.setVisible(busy)
        self.website_load_button.setEnabled(not busy)
        self.website_select_all_button.setEnabled(not busy)
        self.website_clear_selection_button.setEnabled(not busy)
        self.website_publish_button.setEnabled(not busy)
        self.website_update_image_button.setEnabled(not busy)
        self.website_stop_button.setEnabled(busy and allow_stop)

    def _website_log(self, message: str) -> None:
        if hasattr(self, "website_log_box"):
            self.website_log_box.append(message)
            self.website_log_box.verticalScrollBar().setValue(self.website_log_box.verticalScrollBar().maximum())
        self._log(message)

    def _poster_options(self, max_images: int | None = None, schedule_config=None) -> PosterOptions:
        if schedule_config is not None:
            return PosterOptions(
                max_images_per_post=max_images if max_images is not None else self.max_images_spin.value(),
                image_alignment=schedule_config.image_alignment,
                image_display_size=schedule_config.image_display_size,
                image_custom_width=schedule_config.image_custom_width,
            )
        alignment, display_size, custom_width = self._current_image_settings()
        return PosterOptions(
            max_images_per_post=max_images if max_images is not None else self.max_images_spin.value(),
            default_status="publish" if self.publish_now_check.isChecked() else "draft",
            force_status="publish" if self.publish_now_check.isChecked() else None,
            image_alignment=alignment,
            image_display_size=display_size,
            image_custom_width=custom_width,
        )

    def _test_connection(self) -> None:
        config = self._current_config()
        if not config:
            return
        self.connection_status.setText("Đang kiểm tra...")
        self.connection_worker = ConnectionTestWorker(config)
        self.connection_worker.finished_with_result.connect(self._on_connection_tested)
        self.connection_worker.start()

    def _on_connection_tested(self, ok: bool, message: str) -> None:
        self.connection_status.setText(("OK: " if ok else "Lỗi: ") + message)

    def _start_publish(self) -> None:
        if not self._refresh_preview():
            return
        config = self._current_config()
        if not config:
            return
        if QMessageBox.question(
            self,
            "Xác nhận đăng bài",
            "Ứng dụng sẽ gửi nội dung trong Excel lên WordPress theo trạng thái của từng dòng.",
        ) != QMessageBox.Yes:
            return

        self._manual_run_started_at = current_timestamp()
        self.stop_event.clear()
        self.progress.show()
        self.post_button.setEnabled(False)
        self.update_image_layout_button.setEnabled(False)
        self.bulk_publish_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.poster_worker = PosterWorker(
            self.excel_edit.text().strip(),
            self.image_folder_edit.text().strip() or None,
            config,
            self._poster_options(),
            self.stop_event,
        )
        self.poster_worker.progress.connect(self._log)
        self.poster_worker.completed.connect(self._on_publish_completed)
        self.poster_worker.start()

    def _start_update_image_layout(self) -> None:
        excel_path = self.excel_edit.text().strip()
        if not excel_path:
            QMessageBox.warning(self, "Chưa có file Excel", "Cần chọn file Excel để xác định các bài đã đăng cần sửa ảnh.")
            return
        config = self._current_config()
        if not config:
            return
        if QMessageBox.question(
            self,
            "Xác nhận sửa ảnh bài đã đăng",
            "Ứng dụng sẽ tìm các bài đã đăng theo Slug hoặc tiêu đề trong Excel, sau đó cập nhật lại kích thước và căn ảnh theo lựa chọn hiện tại. Nội dung chữ, SEO, danh mục và tags không bị thay đổi.",
        ) != QMessageBox.Yes:
            return

        self._manual_run_started_at = current_timestamp()
        self.stop_event.clear()
        self.progress.show()
        self.post_button.setEnabled(False)
        self.update_image_layout_button.setEnabled(False)
        self.bulk_publish_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.image_layout_worker = ImageLayoutUpdateWorker(
            excel_path,
            config,
            self._poster_options(),
            self.stop_event,
        )
        self.image_layout_worker.progress.connect(self._log)
        self.image_layout_worker.completed.connect(self._on_image_layout_update_completed)
        self.image_layout_worker.start()

    def _start_bulk_publish(self) -> None:
        excel_path = self.excel_edit.text().strip()
        if not excel_path:
            QMessageBox.warning(self, "Chưa có file Excel", "Cần chọn file Excel để xác định các bài cần xuất bản.")
            return
        config = self._current_config()
        if not config:
            return
        if QMessageBox.question(
            self,
            "Xác nhận xuất bản hàng loạt",
            "Ứng dụng sẽ tìm các bài đã có trên WordPress theo Slug hoặc tiêu đề trong Excel và chuyển trạng thái sang publish. Nội dung bài viết không bị thay đổi.",
        ) != QMessageBox.Yes:
            return

        self._manual_run_started_at = current_timestamp()
        self.stop_event.clear()
        self.progress.show()
        self.post_button.setEnabled(False)
        self.update_image_layout_button.setEnabled(False)
        self.bulk_publish_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.bulk_publish_worker = BulkPublishWorker(
            excel_path,
            config,
            self._poster_options(),
            self.stop_event,
        )
        self.bulk_publish_worker.progress.connect(self._log)
        self.bulk_publish_worker.completed.connect(self._on_bulk_publish_completed)
        self.bulk_publish_worker.start()

    def _stop_publish(self) -> None:
        self.stop_event.set()
        self._log("Đã yêu cầu dừng sau bài hiện tại")

    def _on_publish_completed(self, results, orphan_files) -> None:
        self.results = list(results)
        fill_result_table(self.result_table, self.results)
        self.orphan_label.setText(orphan_label_text(list(orphan_files)))
        self.progress.hide()
        self.post_button.setEnabled(True)
        self.update_image_layout_button.setEnabled(True)
        self.bulk_publish_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        success = sum(1 for result in self.results if result.status == "success")
        self._log(f"Hoàn tất: {success}/{len(self.results)} thành công")
        export_path = self._auto_export_source_link_excel()
        record = self._append_run_history(
            mode="manual",
            results=self.results,
            excel_path=self.excel_edit.text().strip(),
            image_folder=self.image_folder_edit.text().strip() or None,
            export_path=export_path,
            orphan_files=list(orphan_files),
            started_at=self._manual_run_started_at,
        )
        self._manual_run_started_at = None
        self._log(f"Đã lưu lịch sử chạy: {record.finished_at}")

    def _on_image_layout_update_completed(self, results) -> None:
        self.results = list(results)
        fill_result_table(self.result_table, self.results)
        self.orphan_label.clear()
        self.progress.hide()
        self.post_button.setEnabled(True)
        self.update_image_layout_button.setEnabled(True)
        self.bulk_publish_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        success = sum(1 for result in self.results if result.status == "success")
        self._log(f"Hoàn tất sửa ảnh: {success}/{len(self.results)} thành công")
        record = self._append_run_history(
            mode="image_layout",
            results=self.results,
            excel_path=self.excel_edit.text().strip(),
            image_folder=self.image_folder_edit.text().strip() or None,
            export_path=None,
            orphan_files=[],
            started_at=self._manual_run_started_at,
        )
        self._manual_run_started_at = None
        self._log(f"Đã lưu lịch sử sửa ảnh: {record.finished_at}")

    def _on_bulk_publish_completed(self, results) -> None:
        self.results = list(results)
        fill_result_table(self.result_table, self.results)
        self.orphan_label.clear()
        self.progress.hide()
        self.post_button.setEnabled(True)
        self.update_image_layout_button.setEnabled(True)
        self.bulk_publish_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        success = sum(1 for result in self.results if result.status == "success")
        self._log(f"Hoàn tất xuất bản hàng loạt: {success}/{len(self.results)} thành công")
        record = self._append_run_history(
            mode="bulk_publish",
            results=self.results,
            excel_path=self.excel_edit.text().strip(),
            image_folder=self.image_folder_edit.text().strip() or None,
            export_path=None,
            orphan_files=[],
            started_at=self._manual_run_started_at,
        )
        self._manual_run_started_at = None
        self._log(f"Đã lưu lịch sử xuất bản hàng loạt: {record.finished_at}")

    def _export_report(self) -> None:
        if not self.results:
            QMessageBox.information(self, "Chưa có kết quả", "Chưa có kết quả để xuất.")
            return
        excel_path = self.excel_edit.text().strip()
        if not excel_path:
            QMessageBox.information(self, "Chưa có file Excel", "Cần chọn file Excel gốc trước khi xuất.")
            return
        source = Path(excel_path)
        default_path = source.with_name(f"{source.stem}_ket_qua_dang_bai.xlsx")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Xuất Excel gốc kèm link bài viết",
            str(default_path),
            "Excel (*.xlsx)",
        )
        if path:
            export_path = self._export_source_link_excel(path)
            self._log(f"Đã xuất Excel gốc kèm link bài viết: {export_path}")

    def _auto_export_source_link_excel(self) -> Path | None:
        if not self.results:
            return None
        try:
            export_path = self._export_source_link_excel()
        except Exception as exc:
            self._log(f"Lỗi xuất Excel gốc kèm link bài viết: {exc}")
            return None
        self._log(f"Đã tự động xuất Excel gốc kèm link bài viết: {export_path}")
        return export_path

    def _export_source_link_excel(self, output_path: str | Path | None = None) -> Path:
        excel_path = self.excel_edit.text().strip()
        if not excel_path:
            raise RuntimeError("Chưa chọn file Excel gốc")
        return export_links_to_source_excel(excel_path, self.results, output_path)

    def _append_run_history(
        self,
        mode: str,
        results,
        excel_path: str,
        image_folder: str | None,
        export_path: str | Path | None,
        orphan_files,
        started_at: str | None,
        summary: str | None = None,
        error: str | None = None,
    ):
        record = self.history_store.append_run(
            mode=mode,
            excel_path=excel_path,
            image_folder=image_folder,
            results=list(results),
            export_excel_path=export_path,
            started_at=started_at,
            summary=summary,
            error=error,
            orphan_files=list(orphan_files),
        )
        self.history_changed.emit()
        return record

    def _on_schedule_changed(self) -> None:
        self.scheduler.config = self.schedule_tab.to_config()
        self.scheduler.save_config()
        self._apply_schedule()

    def _apply_schedule(self) -> None:
        try:
            self.scheduler.start(self._run_scheduled_job)
            self.schedule_tab.set_next_run(self.scheduler.next_run_time())
        except Exception as exc:
            self.schedule_tab.set_next_run(f"Lỗi lịch: {exc}")
            self._log(f"Lỗi lịch: {exc}")

    def _run_scheduled_job(self) -> str:
        started_at = current_timestamp()
        config = self._current_config(show_errors=False)
        if not config:
            raise RuntimeError("Thiếu cấu hình WordPress trong phiên hiện tại")
        schedule = self.scheduler.config
        try:
            results, orphan_files = publish_from_excel(
                schedule.excel_path,
                schedule.image_folder or None,
                config,
                self._poster_options(schedule.max_images_per_post, schedule_config=schedule),
            )
            success = sum(1 for result in results if result.status == "success")
            summary = f"Đăng thành công {success}/{len(results)} bài"
            export_path = None
            try:
                export_path = export_links_to_source_excel(schedule.excel_path, list(results))
                summary = f"{summary} - Excel: {export_path.name}"
            except Exception as exc:
                summary = f"{summary} - lỗi xuất Excel: {exc}"
            self._append_run_history(
                mode="scheduled",
                results=list(results),
                excel_path=schedule.excel_path,
                image_folder=schedule.image_folder or None,
                export_path=export_path,
                orphan_files=list(orphan_files),
                started_at=started_at,
                summary=summary,
            )
        except Exception as exc:
            summary = f"Thất bại: {exc}"
            self._append_run_history(
                mode="scheduled",
                results=[],
                excel_path=schedule.excel_path,
                image_folder=schedule.image_folder or None,
                export_path=None,
                orphan_files=[],
                started_at=started_at,
                summary=summary,
                error=str(exc),
            )
            raise
        self.schedule_message.emit(summary)
        return summary

    def _open_advanced_settings(self) -> None:
        dialog = AdvancedSettingsDialog(self.delay_seconds, self.retry_count, self.timeout_seconds)
        if dialog.exec():
            self.delay_seconds, self.retry_count, self.timeout_seconds = dialog.values()
            self._save_settings()

    def _load_settings(self) -> None:
        if not self.settings_path.exists():
            return
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:
            return
        self.site_url_edit.setText(data.get("site_url", ""))
        self.username_edit.setText(data.get("username", ""))
        self.delay_seconds = int(data.get("delay_seconds", 0))
        self.retry_count = int(data.get("retry_count", 3))
        self.timeout_seconds = int(data.get("timeout_seconds", 30))

        # Restore image display settings
        saved_size = data.get("image_display_size", "auto")
        for i, (_label, value) in enumerate(_IMAGE_SIZE_OPTIONS):
            if value == saved_size:
                self.image_size_combo.setCurrentIndex(i)
                if hasattr(self, "website_image_size_combo"):
                    self.website_image_size_combo.setCurrentIndex(i)
                break
        saved_align = data.get("image_alignment", "aligncenter")
        for i, (_label, value) in enumerate(_IMAGE_ALIGN_OPTIONS):
            if value == saved_align:
                self.image_align_combo.setCurrentIndex(i)
                if hasattr(self, "website_image_align_combo"):
                    self.website_image_align_combo.setCurrentIndex(i)
                break
        self.image_custom_width_spin.setValue(int(data.get("image_custom_width", 800)))
        if hasattr(self, "website_image_custom_width_spin"):
            self.website_image_custom_width_spin.setValue(int(data.get("image_custom_width", 800)))
        self.publish_now_check.setChecked(bool(data.get("publish_now", False)))
        self._on_image_size_changed()
        if hasattr(self, "website_image_size_combo"):
            self._on_website_image_size_changed()

    def _save_settings(self) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        alignment, display_size, custom_width = self._current_image_settings()
        data = {
            "site_url": self.site_url_edit.text().strip(),
            "username": self.username_edit.text().strip(),
            "delay_seconds": self.delay_seconds,
            "retry_count": self.retry_count,
            "timeout_seconds": self.timeout_seconds,
            "image_alignment": alignment,
            "image_display_size": display_size,
            "image_custom_width": custom_width,
            "publish_now": self.publish_now_check.isChecked(),
        }
        self.settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._log("Đã lưu cấu hình không gồm password")

    def _log(self, message: str) -> None:
        self.log_box.append(message)
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def show_normal_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_application(self) -> None:
        self._quitting = True
        self.scheduler.stop()
        self.tray_icon.hide()
        QApplication.instance().quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting:
            event.accept()
            return

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Đóng ứng dụng")
        dialog.setIcon(QMessageBox.Question)
        dialog.setText("Bạn muốn tắt hoàn toàn hay thu gọn cửa sổ để app tiếp tục chạy ngầm?")
        minimize_button = dialog.addButton("Thu gọn chạy ngầm", QMessageBox.AcceptRole)
        quit_button = dialog.addButton("Tắt hoàn toàn", QMessageBox.DestructiveRole)
        cancel_button = dialog.addButton("Hủy", QMessageBox.RejectRole)
        dialog.setDefaultButton(minimize_button)
        dialog.exec()

        clicked_button = dialog.clickedButton()
        if clicked_button == quit_button:
            self._quitting = True
            self.scheduler.stop()
            self.tray_icon.hide()
            event.accept()
            QApplication.instance().quit()
            return

        if clicked_button == minimize_button:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(APP_NAME, "Ứng dụng vẫn chạy ngầm ở khay hệ thống")
            return

        if clicked_button == cancel_button:
            event.ignore()
            return

        event.ignore()


def _website_payload_id(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    try:
        return int(payload.get("id"))
    except (TypeError, ValueError):
        return None


def _website_payload_title(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    title = payload.get("title")
    value = ""
    if isinstance(title, dict):
        value = str(title.get("raw") or title.get("rendered") or "")
    elif isinstance(title, str):
        value = title
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def _website_payload_status(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    status = payload.get("status")
    return str(status or "")


def _website_payload_slug(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    slug = payload.get("slug")
    return str(slug or "")


def _website_payload_link(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    link = payload.get("link")
    return str(link or "")
