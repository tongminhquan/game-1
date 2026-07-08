from __future__ import annotations

import io
import mimetypes
from pathlib import Path
import time
from typing import Any
from urllib.parse import urljoin

from .models import Post, UploadedMedia, WordPressConfig


class WordPressClientError(RuntimeError):
    pass


class WordPressClient:
    def __init__(self, config: WordPressConfig):
        self.config = config
        self.site_url = config.site_url.rstrip("/") + "/"

        try:
            import requests
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("requests is required for WordPress API access") from exc

        self._requests = requests
        self._session = requests.Session()
        self._session.auth = (config.username, config.application_password)
        self._session.headers.update({"User-Agent": "WordPressAutoPosterGUI/0.1"})

    def _api(self, path: str) -> str:
        return urljoin(self.site_url, f"wp-json/wp/v2/{path.lstrip('/')}")

    def _request(self, method: str, path: str, **kwargs: Any):
        kwargs.setdefault("timeout", self.config.timeout_seconds)
        response = self._session.request(method, self._api(path), **kwargs)
        if response.status_code >= 400:
            raise WordPressClientError(
                f"WordPress API error {response.status_code}: {response.text[:500]}"
            )
        return response

    def test_connection(self) -> tuple[bool, str]:
        try:
            response = self._request("GET", "users/me")
            user = response.json()
            return True, f"Connected as {user.get('name') or user.get('slug') or self.config.username}"
        except Exception as exc:
            return False, str(exc)

    def upload_media(self, file_bytes: bytes, filename: str, mime_type: str) -> UploadedMedia:
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": mime_type,
        }
        response = self._request("POST", "media", data=file_bytes, headers=headers)
        payload = response.json()
        return UploadedMedia(
            media_id=int(payload["id"]),
            source_url=str(payload.get("source_url") or payload.get("guid", {}).get("rendered") or ""),
            filename=filename,
        )

    def upload_media_from_url(self, url: str) -> UploadedMedia:
        response = self._requests.get(url, timeout=self.config.timeout_seconds)
        response.raise_for_status()
        filename = Path(url.split("?", 1)[0]).name or "remote-image"
        mime_type = response.headers.get("Content-Type") or mimetypes.guess_type(filename)[0]
        if not mime_type:
            mime_type = "application/octet-stream"
        return self.upload_media(response.content, filename, mime_type)

    def upload_media_from_path(self, file_path: str | Path) -> UploadedMedia:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(path)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        file_bytes = _prepare_image_bytes(path, mime_type)
        upload_name = path.with_suffix(".jpg").name if len(file_bytes) != path.stat().st_size else path.name
        upload_mime = "image/jpeg" if upload_name.lower().endswith(".jpg") else mime_type
        return self.upload_media(file_bytes, upload_name, upload_mime)

    def get_or_create_term(self, taxonomy: str, name: str) -> int:
        search_response = self._request("GET", taxonomy, params={"search": name, "per_page": 20})
        for item in search_response.json():
            if str(item.get("name", "")).strip().lower() == name.strip().lower():
                return int(item["id"])
        create_response = self._request("POST", taxonomy, json={"name": name})
        return int(create_response.json()["id"])

    def find_post_by_title(self, title: str) -> dict[str, Any] | None:
        response = self._request("GET", "posts", params={"search": title, "per_page": 20})
        target = title.strip().lower()
        for post in response.json():
            rendered = post.get("title", {}).get("rendered", "")
            if _strip_html(rendered).strip().lower() == target:
                return post
        return None

    def find_post_by_slug(self, slug: str) -> dict[str, Any] | None:
        normalized = _normalize_slug(slug)
        if not normalized:
            return None
        response = self._request("GET", "posts", params={"slug": normalized, "per_page": 1})
        posts = response.json()
        return posts[0] if posts else None

    def get_post(self, post_id: int) -> dict[str, Any]:
        try:
            return self._request("GET", f"posts/{post_id}", params={"context": "edit"}).json()
        except WordPressClientError:
            return self._request("GET", f"posts/{post_id}").json()

    def list_posts(
        self,
        statuses: list[str] | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Return editable WordPress posts across common statuses."""

        target_statuses = statuses or ["publish", "draft", "pending", "future", "private"]
        page_size = max(1, min(int(per_page), 100))
        posts_by_id: dict[int, dict[str, Any]] = {}

        for status in target_statuses:
            page = 1
            while True:
                response = self._request(
                    "GET",
                    "posts",
                    params={
                        "context": "edit",
                        "status": status,
                        "per_page": page_size,
                        "page": page,
                        "orderby": "date",
                        "order": "desc",
                    },
                )
                total_pages = _response_total_pages(response)
                batch = response.json()
                if not isinstance(batch, list) or not batch:
                    break

                for item in batch:
                    if isinstance(item, dict) and item.get("id") is not None:
                        posts_by_id[int(item["id"])] = item

                if total_pages is not None and page >= total_pages:
                    break
                if len(batch) < page_size:
                    break
                page += 1

        return sorted(
            posts_by_id.values(),
            key=lambda payload: str(payload.get("date") or payload.get("modified") or ""),
            reverse=True,
        )

    def check_duplicate_by_title(self, title: str) -> bool:
        return self.find_post_by_title(title) is not None

    def create_post(self, post: Post, content: str, featured_media_id: int | None = None) -> dict[str, Any]:
        payload = self._build_post_payload(post, content, featured_media_id, include_status=True)

        last_error: Exception | None = None
        for attempt in range(1, self.config.retry_count + 1):
            try:
                return self._request("POST", "posts", json=payload).json()
            except Exception as exc:
                last_error = exc
                if attempt < self.config.retry_count:
                    time.sleep(min(2 * attempt, 10))
        raise WordPressClientError(str(last_error))

    def update_post(
        self,
        post_id: int,
        post: Post,
        content: str | None = None,
        featured_media_id: int | None = None,
    ) -> dict[str, Any]:
        payload = self._build_post_payload(post, content, featured_media_id, include_status=False)
        if not payload:
            return {}

        last_error: Exception | None = None
        for attempt in range(1, self.config.retry_count + 1):
            try:
                return self._request("POST", f"posts/{post_id}", json=payload).json()
            except Exception as exc:
                last_error = exc
                if attempt < self.config.retry_count:
                    time.sleep(min(2 * attempt, 10))
        raise WordPressClientError(str(last_error))

    def update_post_content(self, post_id: int, content: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.config.retry_count + 1):
            try:
                return self._request("POST", f"posts/{post_id}", json={"content": content}).json()
            except Exception as exc:
                last_error = exc
                if attempt < self.config.retry_count:
                    time.sleep(min(2 * attempt, 10))
        raise WordPressClientError(str(last_error))

    def update_post_status(self, post_id: int, status: str = "publish") -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.config.retry_count + 1):
            try:
                return self._request("POST", f"posts/{post_id}", json={"status": status}).json()
            except Exception as exc:
                last_error = exc
                if attempt < self.config.retry_count:
                    time.sleep(min(2 * attempt, 10))
        raise WordPressClientError(str(last_error))

    def _build_post_payload(
        self,
        post: Post,
        content: str | None = None,
        featured_media_id: int | None = None,
        include_status: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": post.title,
        }
        if content is not None:
            payload["content"] = content
        if include_status:
            payload["status"] = post.status or "draft"
        if post.slug:
            payload["slug"] = post.slug
        if post.meta_description:
            payload["excerpt"] = post.meta_description
        seo_meta = _rank_math_meta(post)
        if seo_meta:
            payload["meta"] = seo_meta
        if post.publish_date:
            payload["date"] = post.publish_date
        if featured_media_id:
            payload["featured_media"] = featured_media_id
        if post.category:
            payload["categories"] = [self.get_or_create_term("categories", post.category)]
        if post.tags:
            payload["tags"] = [self.get_or_create_term("tags", tag) for tag in post.tags]
        else:
            payload["tags"] = []

        return payload

    def update_post_seo(self, post_id: int, post: Post) -> dict[str, Any]:
        return self.update_post(post_id, post)


def _prepare_image_bytes(path: Path, mime_type: str) -> bytes:
    if not mime_type.startswith("image/"):
        raise WordPressClientError(f"Unsupported image type: {path.name}")

    try:
        from PIL import Image, ImageOps
    except ImportError:
        return path.read_bytes()

    max_bytes = 2 * 1024 * 1024
    raw = path.read_bytes()
    if len(raw) <= max_bytes:
        with Image.open(path) as image:
            image.verify()
        return raw

    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((1600, 1600))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85, optimize=True)
        return buffer.getvalue()


def _strip_html(value: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", value)


def _normalize_slug(value: str) -> str:
    text = value.strip().split("?", 1)[0].split("#", 1)[0]
    if "://" in text:
        text = text.rstrip("/").rsplit("/", 1)[-1]
    return text.strip("/")


def _response_total_pages(response: object) -> int | None:
    headers = getattr(response, "headers", {}) or {}
    value = headers.get("X-WP-TotalPages") or headers.get("x-wp-totalpages")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rank_math_meta(post: Post) -> dict[str, str]:
    meta: dict[str, str] = {}
    seo_title = (post.seo_title or post.title or "").strip()
    if seo_title:
        meta["rank_math_title"] = seo_title
    if post.meta_description:
        meta["rank_math_description"] = post.meta_description
    focus_keywords = post.focus_keywords or []
    focus_keyword_text = ", ".join(keyword.strip() for keyword in focus_keywords if keyword.strip())
    if focus_keyword_text:
        meta["rank_math_focus_keyword"] = focus_keyword_text
    if post.slug:
        meta["rank_math_permalink"] = post.slug
    return meta
