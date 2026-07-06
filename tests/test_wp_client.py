from __future__ import annotations

import unittest

from wp_auto_poster_gui.core.models import Post, WordPressConfig
from wp_auto_poster_gui.core.wp_client import WordPressClient


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.text = ""

    def json(self):
        return self._payload


class PayloadClient(WordPressClient):
    def __init__(self):
        try:
            super().__init__(WordPressConfig("https://example.com", "user", "pass"))
        except RuntimeError:
            raise unittest.SkipTest("requests is not installed")
        self.last_payload = None

    def _request(self, method: str, path: str, **kwargs):
        self.last_payload = kwargs.get("json")
        return _FakeResponse({"link": "https://example.com/post"})


class WordPressClientTest(unittest.TestCase):
    def test_create_post_includes_slug_and_excerpt(self) -> None:
        client = PayloadClient()
        post = Post(
            row_number=2,
            title="Title",
            content="<p>Body</p>",
            slug="custom-slug",
            seo_title="SEO Title",
            meta_description="Meta description",
            focus_keywords=["main keyword", "secondary keyword"],
        )

        client.create_post(post, post.content)

        self.assertEqual(client.last_payload["slug"], "custom-slug")
        self.assertEqual(client.last_payload["excerpt"], "Meta description")
        self.assertEqual(client.last_payload["meta"]["rank_math_title"], "SEO Title")
        self.assertEqual(client.last_payload["meta"]["rank_math_description"], "Meta description")
        self.assertEqual(
            client.last_payload["meta"]["rank_math_focus_keyword"],
            "main keyword, secondary keyword",
        )
        self.assertEqual(client.last_payload["tags"], [])

    def test_update_post_includes_content_featured_media_and_rank_math_meta(self) -> None:
        client = PayloadClient()
        post = Post(
            row_number=2,
            title="Title",
            content="<p>Body</p>",
            slug="custom-slug",
            seo_title="SEO Title",
            meta_description="Meta description",
            focus_keywords=["keyword"],
        )

        client.update_post(123, post, '<p>Body</p><p><img src="https://example.com/image.jpg" /></p>', 55)

        self.assertEqual(client.last_payload["content"], '<p>Body</p><p><img src="https://example.com/image.jpg" /></p>')
        self.assertEqual(client.last_payload["featured_media"], 55)
        self.assertEqual(client.last_payload["meta"]["rank_math_title"], "SEO Title")
        self.assertEqual(client.last_payload["meta"]["rank_math_description"], "Meta description")
        self.assertEqual(client.last_payload["meta"]["rank_math_focus_keyword"], "keyword")
        self.assertEqual(client.last_payload["meta"]["rank_math_permalink"], "custom-slug")
        self.assertEqual(client.last_payload["tags"], [])
        self.assertNotIn("status", client.last_payload)

    def test_update_post_seo_sends_rank_math_meta(self) -> None:
        client = PayloadClient()
        post = Post(
            row_number=2,
            title="Title",
            content="<p>Body</p>",
            slug="custom-slug",
            meta_description="Meta description",
            focus_keywords=["keyword"],
        )

        client.update_post_seo(123, post)

        self.assertEqual(client.last_payload["slug"], "custom-slug")
        self.assertEqual(client.last_payload["excerpt"], "Meta description")
        self.assertEqual(client.last_payload["meta"]["rank_math_title"], "Title")
        self.assertEqual(client.last_payload["meta"]["rank_math_description"], "Meta description")
        self.assertEqual(client.last_payload["meta"]["rank_math_focus_keyword"], "keyword")


if __name__ == "__main__":
    unittest.main()
