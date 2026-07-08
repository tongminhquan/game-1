from __future__ import annotations

from threading import Event

from PySide6.QtCore import QThread, Signal

from wp_auto_poster_gui.core.excel_reader import read_posts_from_excel
from wp_auto_poster_gui.core.models import PosterOptions, WordPressConfig
from wp_auto_poster_gui.core.poster_service import (
    list_website_posts,
    publish_existing_posts_bulk,
    publish_from_excel,
    publish_website_posts_bulk,
    update_existing_posts_image_layout,
    update_website_posts_image_layout,
)
from wp_auto_poster_gui.core.wp_client import WordPressClient


class ConnectionTestWorker(QThread):
    finished_with_result = Signal(bool, str)

    def __init__(self, config: WordPressConfig):
        super().__init__()
        self.config = config

    def run(self) -> None:
        try:
            ok, message = WordPressClient(self.config).test_connection()
            self.finished_with_result.emit(ok, message)
        except Exception as exc:
            self.finished_with_result.emit(False, str(exc))


class PosterWorker(QThread):
    progress = Signal(str)
    completed = Signal(object, object)

    def __init__(
        self,
        excel_path: str,
        image_folder: str | None,
        config: WordPressConfig,
        options: PosterOptions,
        stop_event: Event,
    ):
        super().__init__()
        self.excel_path = excel_path
        self.image_folder = image_folder
        self.config = config
        self.options = options
        self.stop_event = stop_event

    def run(self) -> None:
        try:
            results, orphan_files = publish_from_excel(
                self.excel_path,
                self.image_folder,
                self.config,
                self.options,
                progress_callback=self.progress.emit,
                stop_event=self.stop_event,
            )
            self.completed.emit(results, orphan_files)
        except Exception as exc:
            self.progress.emit(f"Lỗi: {exc}")
            self.completed.emit([], [])


class ImageLayoutUpdateWorker(QThread):
    progress = Signal(str)
    completed = Signal(object)

    def __init__(
        self,
        excel_path: str,
        config: WordPressConfig,
        options: PosterOptions,
        stop_event: Event,
    ):
        super().__init__()
        self.excel_path = excel_path
        self.config = config
        self.options = options
        self.stop_event = stop_event

    def run(self) -> None:
        try:
            posts = read_posts_from_excel(self.excel_path, default_status=self.options.default_status)
            results = update_existing_posts_image_layout(
                posts,
                self.config,
                self.options,
                progress_callback=self.progress.emit,
                stop_event=self.stop_event,
            )
            self.completed.emit(results)
        except Exception as exc:
            self.progress.emit(f"Lỗi: {exc}")
            self.completed.emit([])


class BulkPublishWorker(QThread):
    progress = Signal(str)
    completed = Signal(object)

    def __init__(
        self,
        excel_path: str,
        config: WordPressConfig,
        options: PosterOptions,
        stop_event: Event,
    ):
        super().__init__()
        self.excel_path = excel_path
        self.config = config
        self.options = options
        self.stop_event = stop_event

    def run(self) -> None:
        try:
            posts = read_posts_from_excel(self.excel_path, default_status=self.options.default_status)
            results = publish_existing_posts_bulk(
                posts,
                self.config,
                progress_callback=self.progress.emit,
                stop_event=self.stop_event,
            )
            self.completed.emit(results)
        except Exception as exc:
            self.progress.emit(f"Lỗi: {exc}")
            self.completed.emit([])


class WebsitePostsLoadWorker(QThread):
    progress = Signal(str)
    completed = Signal(object)

    def __init__(self, config: WordPressConfig):
        super().__init__()
        self.config = config

    def run(self) -> None:
        try:
            posts = list_website_posts(self.config, progress_callback=self.progress.emit)
            self.completed.emit(posts)
        except Exception as exc:
            self.progress.emit(f"Lỗi: {exc}")
            self.completed.emit([])


class WebsiteBulkPublishWorker(QThread):
    progress = Signal(str)
    completed = Signal(object)

    def __init__(
        self,
        posts: list[dict],
        config: WordPressConfig,
        stop_event: Event,
    ):
        super().__init__()
        self.posts = posts
        self.config = config
        self.stop_event = stop_event

    def run(self) -> None:
        try:
            results = publish_website_posts_bulk(
                self.posts,
                self.config,
                progress_callback=self.progress.emit,
                stop_event=self.stop_event,
            )
            self.completed.emit(results)
        except Exception as exc:
            self.progress.emit(f"Lỗi: {exc}")
            self.completed.emit([])


class WebsiteImageLayoutUpdateWorker(QThread):
    progress = Signal(str)
    completed = Signal(object)

    def __init__(
        self,
        posts: list[dict],
        config: WordPressConfig,
        options: PosterOptions,
        stop_event: Event,
    ):
        super().__init__()
        self.posts = posts
        self.config = config
        self.options = options
        self.stop_event = stop_event

    def run(self) -> None:
        try:
            results = update_website_posts_image_layout(
                self.posts,
                self.config,
                self.options,
                progress_callback=self.progress.emit,
                stop_event=self.stop_event,
            )
            self.completed.emit(results)
        except Exception as exc:
            self.progress.emit(f"Lỗi: {exc}")
            self.completed.emit([])
