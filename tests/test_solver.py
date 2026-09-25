import unittest

from app.solver import Mark, Segment, best_boundary, solve


def seg(sid, scales, types):
    return Segment(sid, tuple(Mark(v, t) for v, t in zip(scales, types)))


class BestBoundaryTest(unittest.TestCase):
    def test_pairs_share_single_delta_and_type(self):
        left = seg(1, [10, 20, 30, 40],
                   ["major", "minor", "major", "minor"])
        right = seg(2, [15, 25, 35, 45],
                    ["major", "minor", "major", "minor"])
        boundary = best_boundary(left, right)
        self.assertIsNotNone(boundary)
        self.assertEqual(boundary.delta, 5)
        self.assertEqual(len(boundary.pairs), 4)
        self.assertEqual([(p.left_value, p.right_value, p.type)
                          for p in boundary.pairs],
                         [(10, 15, "major"), (20, 25, "minor"),
                          (30, 35, "major"), (40, 45, "minor")])

    def test_type_mismatch_never_paired(self):
        left = seg(1, [0, 10, 20, 30], ["major"] * 4)
        right = seg(2, [5, 15, 25, 35], ["minor"] * 4)
        self.assertIsNone(best_boundary(left, right))

    def test_delta_tie_prefers_smaller_absolute_then_smaller_value(self):
        # delta=5 与 delta=-5 均可配 2 对，|delta| 相同，取代数值较小者 -5
        left = seg(1, [0, 10, 20, 30], ["major"] * 4)
        right = seg(2, [5, 15, 105, 115], ["major"] * 4)
        boundary = best_boundary(left, right)
        self.assertEqual(boundary.delta, -5)
        self.assertEqual([(p.left_value, p.right_value)
                          for p in boundary.pairs],
                         [(10, 5), (20, 15)])

    def test_max_pairs_wins_over_smaller_delta(self):
        # delta=1 可配 2 对，delta=31 可配 3 对，配对数优先于 |delta|
        left = seg(1, [5, 15, 25, 35], ["major"] * 4)
        right = seg(2, [6, 36, 46, 66], ["major"] * 4)
        boundary = best_boundary(left, right)
        self.assertEqual(boundary.delta, 31)
        self.assertEqual(len(boundary.pairs), 3)

    def test_single_common_type_mark_is_legal(self):
        # 仅一对同类型刻度也构成合法配对（平移量一致性对单对自然成立）
        left = seg(1, [0, 1, 2, 3], ["major", "minor", "minor", "minor"])
        right = seg(2, [10, 20, 21, 22],
                    ["intermediate", "major", "minor", "minor"])
        boundary = best_boundary(left, right)
        self.assertIsNotNone(boundary)
        self.assertGreaterEqual(len(boundary.pairs), 1)


class SolveTest(unittest.TestCase):
    def test_comprehensive_objectives(self):
        # 7 对 > 6 对（配对数最大）；误差 36 < 41；
        # (1,2,3) 与 (3,2,1) 前两项持平，按编号序列决胜取 (1,2,3)
        segments = [
            seg(1, [0, 10, 20, 30], ["major"] * 4),
            seg(2, [5, 15, 25, 35], ["major"] * 4),
            seg(3, [36, 46, 57, 66], ["major"] * 4),
        ]
        solution = solve(segments)
        self.assertEqual(solution.order, (1, 2, 3))
        self.assertEqual(solution.total_pairs, 7)
        self.assertEqual(solution.total_error, 36)
        self.assertEqual([b.delta for b in solution.boundaries], [5, 31])
        unpaired = dict(solution.unpaired)
        self.assertEqual(unpaired[1], ())
        self.assertEqual(unpaired[2], ())
        self.assertEqual([m.value for m in unpaired[3]], [57])

    def test_tie_break_uses_id_values_not_entry_order(self):
        # 录入顺序与编号不一致时，决胜按编号值序列而非录入位置
        segments = [
            seg(2, [0, 10, 20, 30], ["major"] * 4),
            seg(1, [5, 15, 25, 35], ["major"] * 4),
            seg(3, [100, 110, 120, 130], ["major"] * 4),
        ]
        solution = solve(segments)
        self.assertEqual(solution.order, (2, 1, 3))
        self.assertEqual(solution.total_pairs, 8)
        self.assertEqual(solution.total_error, 100)

    def test_each_segment_used_exactly_once(self):
        segments = [
            seg(1, [0, 10, 20, 30], ["major"] * 4),
            seg(2, [5, 15, 25, 35], ["major", "major", "major", "minor"]),
            seg(3, [40, 50, 60, 70], ["minor"] * 4),
            seg(4, [45, 55, 65, 75], ["minor"] * 4),
        ]
        solution = solve(segments)
        self.assertIsNotNone(solution)
        self.assertEqual(sorted(solution.order), [1, 2, 3, 4])
        self.assertEqual(len(solution.boundaries), 3)

    def test_infeasible_when_some_boundary_cannot_pair(self):
        # 段 2 与任何其他段都没有同类型刻度，任何排列都存在无配对边界
        segments = [
            seg(1, [0, 10, 20, 30], ["major"] * 4),
            seg(2, [5, 15, 25, 35], ["minor"] * 4),
            seg(3, [40, 50, 60, 70], ["major"] * 4),
        ]
        self.assertIsNone(solve(segments))

    def test_unpaired_marks_cover_both_boundaries(self):
        # 中段同时参与左右两个边界，未配对刻度需合并两侧配对后计算
        segments = [
            seg(1, [100, 110, 120, 130, 140],
                ["major", "minor", "intermediate", "minor", "major"]),
            seg(2, [105, 115, 125, 135, 150],
                ["minor", "intermediate", "minor", "major", "major"]),
            seg(3, [98, 108, 118, 128, 138],
                ["intermediate", "minor", "major", "minor", "intermediate"]),
        ]
        solution = solve(segments)
        self.assertEqual(solution.order, (1, 2, 3))
        self.assertEqual(solution.total_pairs, 7)
        self.assertEqual(solution.total_error, 22)
        unpaired = dict(solution.unpaired)
        self.assertEqual([m.value for m in unpaired[1]], [100])
        self.assertEqual([m.value for m in unpaired[2]], [150])
        self.assertEqual([m.value for m in unpaired[3]], [128, 138])


if __name__ == "__main__":
    unittest.main()
