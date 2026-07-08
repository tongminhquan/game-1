from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal


ProgressCallback = Callable[[str], None]


@dataclass
class Post:
    row_number: int
    title: str
    content: str
    featured_image_url: str | None = None
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    status: str = "draft"
    publish_date: str | None = None
    ma_bai: str | None = None
    slug: str | None = None
    seo_title: str | None = None
    meta_description: str | None = None
    focus_keywords: list[str] = field(default_factory=list)


@dataclass
class UploadedMedia:
    media_id: int
    source_url: str
    filename: str | None = None


@dataclass
class MatchedImages:
    background: Path | None = None
    content_images: list[Path] = field(default_factory=list)


PostStatus = Literal["success", "failed", "skipped"]


@dataclass
class PostResult:
    row_number: int
    title: str
    status: PostStatus
    link: str | None = None
    error: str | None = None


@dataclass
class WordPressConfig:
    site_url: str
    username: str
    application_password: str
    timeout_seconds: int = 30
    retry_count: int = 3
    delay_seconds: float = 0.0


ImageAlignment = Literal["aligncenter", "alignleft", "alignright", "alignnone"]
ImageDisplaySize = Literal["auto", "small", "medium", "large", "full", "custom"]

IMAGE_SIZE_WIDTH: dict[str, int | None] = {
    "auto": None,
    "small": 300,
    "medium": 600,
    "large": 900,
    "full": None,
    "custom": None,
}


@dataclass
class PosterOptions:
    max_images_per_post: int = 2
    default_status: str = "draft"
    force_status: str | None = None
    skip_duplicates: bool = True
    dry_run: bool = False
    image_alignment: str = "aligncenter"
    image_display_size: str = "auto"
    image_custom_width: int = 800
