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
        self.last_path = None

    def _request(self, method: str, path: str, **kwargs):
        self.last_payload = kwargs.get("json")
        self.last_path = path
        return _FakeResponse({"link": "https://example.com/post"})


class ListPostsClient(WordPressClient):
    def __init__(self):
        self.calls = []

    def _request(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs.get("params", {})))
        params = kwargs.get("params", {})
        status = params.get("status")
        page = params.get("page")
        payloads = {
            ("publish", 1): [
                {"id": 2, "title": {"rendered": "Published"}, "status": "publish", "date": "2026-07-01T00:00:00"},
            ],
            ("publish", 2): [
                {"id": 3, "title": {"rendered": "Newer"}, "status": "publish", "date": "2026-07-03T00:00:00"},
            ],
            ("draft", 1): [
                {"id": 1, "title": {"rendered": "Draft"}, "status": "draft", "date": "2026-07-02T00:00:00"},
            ],
        }
        return _FakeResponse(payloads.get((status, page), []))


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

    def test_update_post_content_only_sends_only_content(self) -> None:
        client = PayloadClient()

        client.update_post_content(123, '<p><img src="https://example.com/image.jpg" /></p>')

        self.assertEqual(client.last_path, "posts/123")
        self.assertEqual(client.last_payload, {"content": '<p><img src="https://example.com/image.jpg" /></p>'})

    def test_update_post_status_only_sends_only_status(self) -> None:
        client = PayloadClient()

        client.update_post_status(123, "publish")

        self.assertEqual(client.last_path, "posts/123")
        self.assertEqual(client.last_payload, {"status": "publish"})

    def test_list_posts_fetches_common_statuses_with_pagination(self) -> None:
        client = ListPostsClient()

        posts = client.list_posts(per_page=1)

        self.assertEqual([post["id"] for post in posts], [3, 1, 2])
        self.assertIn(("GET", "posts", {"context": "edit", "status": "draft", "per_page": 1, "page": 1, "orderby": "date", "order": "desc"}), client.calls)
        self.assertIn(("GET", "posts", {"context": "edit", "status": "private", "per_page": 1, "page": 1, "orderby": "date", "order": "desc"}), client.calls)


if __name__ == "__main__":
    unittest.main()
