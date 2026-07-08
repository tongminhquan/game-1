from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from wp_auto_poster_gui.core.excel_reader import read_posts_from_excel


class ExcelReaderTest(unittest.TestCase):
    def test_reads_vietnamese_seo_html_sheet(self) -> None:
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas is not installed")

        with tempfile.TemporaryDirectory() as directory:
            workbook = Path(directory) / "seo.xlsx"
            with pd.ExcelWriter(workbook) as writer:
                pd.DataFrame({"Ghi chú": ["không phải dữ liệu bài"]}).to_excel(
                    writer,
                    sheet_name="Tổng quan",
                    index=False,
                )
                pd.DataFrame(
                    [
                        {
                            "STT": 1,
                            "Từ khóa chính": "thang máy gia đình",
                            "Từ khóa phụ đã phủ thêm": "thang máy kính, thang máy mini",
                            "Tiêu đề SEO": "Thang Máy Gia Đình",
                            "Nội dung HTML thuần": "<h2>Thang Máy Gia Đình</h2><h3>Mục 1</h3><p>Nội dung</p>",
                            "Slug": "thang-may-gia-dinh",
                            "Mô tả Meta SEO": "Mô tả ngắn",
                            "Danh mục": "Tin Tức",
                        }
                    ]
                ).to_excel(writer, sheet_name="Bài SEO HTML", index=False)

            posts = read_posts_from_excel(workbook)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].title, "Thang Máy Gia Đình")
        self.assertIn("<h3>Mục 1</h3>", posts[0].content)
        self.assertEqual(posts[0].slug, "thang-may-gia-dinh")
        self.assertEqual(posts[0].seo_title, "Thang Máy Gia Đình")
        self.assertEqual(posts[0].meta_description, "Mô tả ngắn")
        self.assertEqual(posts[0].category, "Tin Tức")
        self.assertEqual(posts[0].tags, [])
        self.assertEqual(posts[0].focus_keywords, ["thang máy gia đình", "thang máy kính", "thang máy mini"])

    def test_uses_slug_as_image_code_when_ma_bai_is_missing(self) -> None:
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas is not installed")

        with tempfile.TemporaryDirectory() as directory:
            workbook = Path(directory) / "seo.xlsx"
            pd.DataFrame(
                [
                    {
                        "Tiêu đề SEO": "Xịt Côn Trùng",
                        "Nội dung HTML": "<p>Nội dung</p>",
                        "Slug": "/xit-con-trung/",
                        "Mô tả": "Mô tả SEO",
                    }
                ]
            ).to_excel(workbook, sheet_name="30 Bài SEO HTML", index=False)

            posts = read_posts_from_excel(workbook)

        self.assertEqual(posts[0].slug, "/xit-con-trung/")
        self.assertEqual(posts[0].ma_bai, "xit-con-trung")
        self.assertEqual(posts[0].meta_description, "Mô tả SEO")


if __name__ == "__main__":
    unittest.main()
