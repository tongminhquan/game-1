from __future__ import annotations

import unittest

from wp_auto_poster_gui.core.content_composer import compose_content_with_images, rewrite_existing_image_layout
from wp_auto_poster_gui.core.models import UploadedMedia


class ContentComposerTest(unittest.TestCase):
    def test_inserts_images_evenly_into_html_paragraphs(self) -> None:
        content = "<p>A</p><p>B</p><p>C</p>"
        images = [
            UploadedMedia(11, "https://example.com/1.jpg"),
            UploadedMedia(12, "https://example.com/2.jpg"),
        ]

        output = compose_content_with_images(content, "Demo", images)

        self.assertIn('class="wp-image-11 aligncenter"', output)
        self.assertIn('class="wp-image-12 aligncenter"', output)
        self.assertLess(output.index("wp-image-11"), output.index("wp-image-12"))
        self.assertEqual(output.count("<img"), 2)

    def test_returns_original_without_images(self) -> None:
        self.assertEqual(compose_content_with_images("A", "Demo", []), "A")

    def test_replaces_existing_local_image_sources_without_duplicates(self) -> None:
        content = '<p>A</p><p><img src="bai01_1.jpg" alt="Alt"></p><p>B</p>'
        images = [UploadedMedia(11, "https://example.com/uploads/bai01_1.jpg", "bai01_1.jpg")]

        output = compose_content_with_images(content, "Demo", images)

        self.assertIn('src="https://example.com/uploads/bai01_1.jpg"', output)
        self.assertNotIn('src="bai01_1.jpg"', output)
        self.assertEqual(output.count("<img"), 1)

    def test_prepends_leading_image_before_content_images(self) -> None:
        content = "<p>A</p><p>B</p>"
        leading = [UploadedMedia(10, "https://example.com/uploads/bai01_bg.jpg", "bai01_bg.jpg")]
        images = [
            UploadedMedia(11, "https://example.com/uploads/bai01_1.jpg", "bai01_1.jpg"),
            UploadedMedia(12, "https://example.com/uploads/bai01_2.jpg", "bai01_2.jpg"),
        ]

        output = compose_content_with_images(content, "Demo", images, leading_images=leading)

        self.assertEqual(output.count("<img"), 3)
        self.assertLess(output.index("bai01_bg.jpg"), output.index("bai01_1.jpg"))
        self.assertLess(output.index("bai01_1.jpg"), output.index("bai01_2.jpg"))

    def test_replaces_existing_leading_image_without_duplicate(self) -> None:
        content = '<p><img src="bai01_thumb.jpg" alt="Thumb"></p><p>A</p>'
        leading = [UploadedMedia(10, "https://example.com/uploads/bai01_thumb.jpg", "bai01_thumb.jpg")]

        output = compose_content_with_images(content, "Demo", [], leading_images=leading)

        self.assertIn('src="https://example.com/uploads/bai01_thumb.jpg"', output)
        self.assertNotIn('src="bai01_thumb.jpg"', output)
        self.assertEqual(output.count("<img"), 1)

    def test_rewrites_existing_image_alignment_and_size(self) -> None:
        content = (
            '<figure class="wp-block-image alignleft">'
            '<img src="https://example.com/a.jpg" class="wp-image-10 alignleft" width="300" style="width:100%;height:auto" />'
            "</figure>"
        )

        output = rewrite_existing_image_layout(content, alignment="alignright", display_size="medium")

        self.assertIn('class="wp-block-image alignright"', output)
        self.assertIn('class="wp-image-10 alignright"', output)
        self.assertIn('width="600"', output)
        self.assertNotIn("alignleft", output)
        self.assertNotIn("width:100%", output)


if __name__ == "__main__":
    unittest.main()
