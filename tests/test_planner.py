"""动态规划核心算法的单元测试。

运行：``python -m pytest tests/``（pytest 未安装时也可直接执行本文件：
``python tests/test_planner.py``）。
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.planner import PlanningError, plan_pages  # noqa: E402


class TestPlanner(unittest.TestCase):
    def test_basic_two_pages(self):
        r = plan_pages([3, 3, 4, 4], [5, 2, 6, 0], 10, 3)
        self.assertEqual(r["page_count"], 2)
        self.assertEqual(r["breaks"], [3])
        self.assertEqual(r["min_turn_seconds"], 6)
        self.assertEqual(r["pages"][0]["start_measure"], 1)
        self.assertEqual(r["pages"][0]["end_measure"], 3)
        self.assertIsNone(r["pages"][1]["turn_after_measure"])

    def test_single_page_no_turn_point(self):
        r = plan_pages([3, 3], [1, 0], 10, 5)
        self.assertEqual(r["page_count"], 1)
        self.assertEqual(r["breaks"], [])
        self.assertIsNone(r["min_turn_seconds"])

    def test_maximize_min_silence_before_lexicographic(self):
        # 断在小节1后最短静默仅2秒；断在小节2后为5秒 —— min_silence 优先
        r = plan_pages([1, 1, 1, 1], [2, 5, 5, 0], 3, 2)
        self.assertEqual((r["page_count"], r["min_turn_seconds"], r["breaks"]),
                         (2, 5, [2]))

    def test_lexicographic_tie_break(self):
        # 页数与最短静默完全相同：[1] 字典序小于 [2]
        r = plan_pages([1, 1, 1, 1], [5, 5, 5, 0], 3, 1)
        self.assertEqual((r["page_count"], r["min_turn_seconds"], r["breaks"]),
                         (2, 5, [1]))

    def test_silence_threshold_forces_more_pages(self):
        r = plan_pages([2, 2, 2, 2, 2, 2], [10, 10, 2, 10, 10, 0], 6, 3)
        self.assertEqual(r["page_count"], 3)
        self.assertEqual(r["min_turn_seconds"], 10)
        self.assertEqual(r["breaks"], [1, 4])

    def test_exact_page_height_float(self):
        r = plan_pages([3.3, 3.3, 3.4], [0, 3, 0], 6.7, 3)
        self.assertEqual(r["page_count"], 2)
        self.assertEqual(r["breaks"], [2])

    def test_full_page_turn_at_threshold(self):
        # 小节1后静默1秒不达标，放满两小节（恰好页高）后静默3秒刚好达标
        r = plan_pages([5, 5, 5], [1, 3, 0], 10, 3)
        self.assertEqual((r["page_count"], r["breaks"]), (2, [2]))

    def test_measure_exceeds_page(self):
        with self.assertRaises(PlanningError) as ctx:
            plan_pages([3, 11, 2], [1, 1, 0], 10, 0)
        self.assertEqual(ctx.exception.code, "measure_exceeds_page")

    def test_no_legal_plan(self):
        with self.assertRaises(PlanningError) as ctx:
            plan_pages([6, 6], [1, 0], 10, 3)
        self.assertEqual(ctx.exception.code, "no_legal_plan")

    def test_invalid_inputs(self):
        with self.assertRaises(PlanningError):
            plan_pages([], [], 10, 1)
        with self.assertRaises(PlanningError):
            plan_pages([1, 2], [1], 10, 1)
        with self.assertRaises(PlanningError):
            plan_pages([1], [0], 0, 1)
        with self.assertRaises(PlanningError):
            plan_pages([-1], [0], 10, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
