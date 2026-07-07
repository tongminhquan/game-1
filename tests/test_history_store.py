from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from wp_auto_poster_gui.core.history_store import RunHistoryStore
from wp_auto_poster_gui.core.models import PostResult


class RunHistoryStoreTest(unittest.TestCase):
    def test_append_run_persists_record_and_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "run_history.json"
            store = RunHistoryStore(history_path)

            record = store.append_run(
                mode="manual",
                excel_path="posts.xlsx",
                image_folder="images",
                results=[
                    PostResult(2, "Bài 1", "success", link="https://example.com/bai-1"),
                    PostResult(3, "Bài 2", "failed", error="Lỗi đăng"),
                ],
                export_excel_path="posts_ket_qua.xlsx",
                started_at="2026-07-07T09:00:00",
                orphan_files=["khong_khop.jpg"],
            )

            loaded = RunHistoryStore(history_path).load_records()

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].run_id, record.run_id)
            self.assertEqual(loaded[0].mode, "manual")
            self.assertEqual(loaded[0].excel_path, "posts.xlsx")
            self.assertEqual(loaded[0].image_folder, "images")
            self.assertEqual(loaded[0].export_excel_path, "posts_ket_qua.xlsx")
            self.assertEqual(loaded[0].total, 2)
            self.assertEqual(loaded[0].success, 1)
            self.assertEqual(loaded[0].failed, 1)
            self.assertEqual(loaded[0].skipped, 0)
            self.assertEqual(loaded[0].orphan_files, ["khong_khop.jpg"])
            self.assertEqual(loaded[0].results[0].link, "https://example.com/bai-1")
            self.assertEqual(loaded[0].results[1].error, "Lỗi đăng")

    def test_append_run_keeps_newest_records_with_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "run_history.json"
            store = RunHistoryStore(history_path, max_records=2)

            store.append_run("manual", "first.xlsx", None, [], started_at="2026-07-07T09:00:00")
            store.append_run("manual", "second.xlsx", None, [], started_at="2026-07-07T10:00:00")
            store.append_run("scheduled", "third.xlsx", None, [], started_at="2026-07-07T11:00:00")

            loaded = store.load_records()

            self.assertEqual([record.excel_path for record in loaded], ["third.xlsx", "second.xlsx"])

    def test_corrupt_history_file_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "run_history.json"
            history_path.write_text("{bad json", encoding="utf-8")

            self.assertEqual(RunHistoryStore(history_path).load_records(), [])


if __name__ == "__main__":
    unittest.main()
