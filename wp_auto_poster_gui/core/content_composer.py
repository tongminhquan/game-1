from __future__ import annotations

import html
import re

from .models import IMAGE_SIZE_WIDTH, UploadedMedia

# Match any block-level HTML element: <p>, <h2>, <h3>, <h4>, <ul>, <ol>, <table>, <blockquote>, <div>, <section>
_BLOCK_TAG_RE = re.compile(
    r"(<(?:p|h[1-6]|ul|ol|li|table|blockquote|div|section|figure|figcaption)\b[^>]*>.*?</(?:p|h[1-6]|ul|ol|li|table|blockquote|div|section|figure|figcaption)>)",
    re.IGNORECASE | re.DOTALL,
)

_P_TAG_RE = re.compile(r"(<p\b[^>]*>.*?</p>)", re.IGNORECASE | re.DOTALL)
_IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=["\'])([^"\']+)(["\'][^>]*>)', re.IGNORECASE)
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
_FIGURE_OPEN_RE = re.compile(r"<figure\b[^>]*>", re.IGNORECASE | re.DOTALL)
_ALIGN_CLASSES = {"aligncenter", "alignleft", "alignright", "alignnone"}


def _image_html(
    media: UploadedMedia,
    title: str,
    alignment: str = "aligncenter",
    display_size: str = "auto",
    custom_width: int = 800,
) -> str:
    """Build an ``<img>`` tag wrapped in ``<p>`` with configurable alignment and size."""

    alt = html.escape(title, quote=True)
    src = html.escape(media.source_url, quote=True)
    css_class = f"wp-image-{media.media_id} {alignment}"

    # Build width / style attributes based on display_size
    attrs = ""
    if display_size == "full":
        attrs = ' style="width:100%;height:auto"'
    elif display_size == "custom":
        attrs = f' width="{custom_width}"'
    else:
        width = IMAGE_SIZE_WIDTH.get(display_size)
        if width is not None:
            attrs = f' width="{width}"'

    return (
        f'<p><img src="{src}" alt="{alt}" '
        f'class="{css_class}"{attrs} /></p>'
    )


def _split_paragraphs(content: str) -> tuple[list[str], str]:
    stripped = content.strip()
    if not stripped:
        return [], "plain"

    # Try block-level HTML elements first (broader than just <p>)
    html_parts = [part for part in _BLOCK_TAG_RE.split(content) if part]
    block_segments = [part for part in html_parts if _BLOCK_TAG_RE.fullmatch(part)]
    if block_segments:
        return html_parts, "html"

    # Fallback: plain text split by double newlines
    plain_segments = [segment.strip() for segment in re.split(r"\n\s*\n", content) if segment.strip()]
    return plain_segments, "plain"


def _replace_local_image_sources(content: str, uploaded_images: list[UploadedMedia]) -> tuple[str, set[int]]:
    filename_to_media = {
        media.filename.lower(): media
        for media in uploaded_images
        if media.filename
    }
    used_media_ids: set[int] = set()

    def replace(match: re.Match[str]) -> str:
        prefix, src, suffix = match.groups()
        filename = src.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].split("?", 1)[0].lower()
        media = filename_to_media.get(filename)
        if not media:
            return match.group(0)
        used_media_ids.add(media.media_id)
        escaped_src = html.escape(media.source_url, quote=True)
        return f"{prefix}{escaped_src}{suffix}"

    return _IMG_SRC_RE.sub(replace, content), used_media_ids


def compose_content_with_images(
    content: str,
    title: str,
    uploaded_images: list[UploadedMedia],
    leading_images: list[UploadedMedia] | None = None,
    alignment: str = "aligncenter",
    display_size: str = "auto",
    custom_width: int = 800,
) -> str:
    """Insert uploaded content images evenly through the post body."""

    leading_images = leading_images or []
    all_uploaded_images = [*leading_images, *uploaded_images]
    if not all_uploaded_images:
        return content

    content, replaced_media_ids = _replace_local_image_sources(content, all_uploaded_images)
    leading_images = [media for media in leading_images if media.media_id not in replaced_media_ids]
    uploaded_images = [media for media in uploaded_images if media.media_id not in replaced_media_ids]
    if leading_images:
        leading_tags = [
            _image_html(media, title, alignment, display_size, custom_width)
            for media in leading_images
        ]
        prefix = "\n".join(leading_tags)
        content = f"{prefix}\n{content.lstrip()}" if content.strip() else prefix

    if not uploaded_images:
        return content

    segments, mode = _split_paragraphs(content)
    image_tags = [
        _image_html(media, title, alignment, display_size, custom_width)
        for media in uploaded_images
    ]

    if not segments:
        suffix = "\n".join(image_tags)
        return f"{content.rstrip()}\n{suffix}" if content.strip() else suffix

    paragraph_indexes: list[int]
    if mode == "html":
        # Insert after any block element, not just <p>
        paragraph_indexes = [i for i, part in enumerate(segments) if _BLOCK_TAG_RE.fullmatch(part)]
    else:
        paragraph_indexes = list(range(len(segments)))

    if not paragraph_indexes:
        return f"{content.rstrip()}\n" + "\n".join(image_tags)

    positions: dict[int, list[str]] = {}
    m = len(paragraph_indexes)
    n = len(image_tags)
    for k, tag in enumerate(image_tags, start=1):
        paragraph_position = round(k * (m + 1) / (n + 1))
        paragraph_position = max(1, min(m, paragraph_position))
        insert_after_index = paragraph_indexes[paragraph_position - 1]
        positions.setdefault(insert_after_index, []).append(tag)

    output: list[str] = []
    for i, segment in enumerate(segments):
        output.append(segment)
        output.extend(positions.get(i, []))

    separator = "" if mode == "html" else "\n\n"
    return separator.join(output)


def rewrite_existing_image_layout(
    content: str,
    alignment: str = "aligncenter",
    display_size: str = "auto",
    custom_width: int = 800,
) -> str:
    """Rewrite alignment and size attributes on existing image markup."""

    normalized_alignment = alignment if alignment in _ALIGN_CLASSES else "aligncenter"

    def rewrite_img(match: re.Match[str]) -> str:
        return _apply_image_attrs(match.group(0), normalized_alignment, display_size, custom_width)

    def rewrite_figure(match: re.Match[str]) -> str:
        tag = match.group(0)
        class_value = _get_attr(tag, "class")
        if not class_value:
            return tag
        classes = class_value.split()
        if "wp-block-image" not in classes and not any(item in _ALIGN_CLASSES for item in classes):
            return tag
        return _set_attr(tag, "class", _with_alignment(class_value, normalized_alignment))

    content = _FIGURE_OPEN_RE.sub(rewrite_figure, content)
    return _IMG_TAG_RE.sub(rewrite_img, content)


def _apply_image_attrs(tag: str, alignment: str, display_size: str, custom_width: int) -> str:
    tag = _set_attr(tag, "class", _with_alignment(_get_attr(tag, "class") or "", alignment))
    tag = _remove_attr(tag, "width")
    tag = _remove_attr(tag, "height")
    tag = _set_image_style(tag, display_size)

    width: int | None = None
    if display_size == "custom":
        width = custom_width
    elif display_size not in {"auto", "full"}:
        width = IMAGE_SIZE_WIDTH.get(display_size)
    if width:
        tag = _set_attr(tag, "width", str(width))
    return tag


def _with_alignment(class_value: str, alignment: str) -> str:
    classes = [item for item in class_value.split() if item not in _ALIGN_CLASSES]
    classes.append(alignment)
    return " ".join(classes)


def _set_image_style(tag: str, display_size: str) -> str:
    style = _get_attr(tag, "style") or ""
    declarations: list[str] = []
    for item in style.split(";"):
        if not item.strip() or ":" not in item:
            continue
        name, value = item.split(":", 1)
        if name.strip().lower() in {"width", "height"}:
            continue
        declarations.append(f"{name.strip()}:{value.strip()}")

    if display_size == "full":
        declarations.extend(["width:100%", "height:auto"])

    if declarations:
        return _set_attr(tag, "style", ";".join(declarations))
    return _remove_attr(tag, "style")


def _get_attr(tag: str, name: str) -> str | None:
    match = re.search(rf"""\s{name}\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))""", tag, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return next(group for group in match.groups()[1:] if group is not None)


def _set_attr(tag: str, name: str, value: str) -> str:
    escaped = html.escape(value, quote=True)
    pattern = re.compile(rf"""\s{name}\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))""", re.IGNORECASE | re.DOTALL)
    replacement = f' {name}="{escaped}"'
    if pattern.search(tag):
        return pattern.sub(replacement, tag, count=1)
    insert_at = tag.rfind("/>") if tag.rstrip().endswith("/>") else tag.rfind(">")
    if insert_at < 0:
        return tag
    return tag[:insert_at].rstrip() + replacement + tag[insert_at:]


def _remove_attr(tag: str, name: str) -> str:
    return re.sub(rf"""\s{name}\s*=\s*("([^"]*)"|'([^']*)'|[^\s>]+)""", "", tag, flags=re.IGNORECASE | re.DOTALL)
