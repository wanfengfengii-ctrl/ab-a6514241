"""航海测深图刻度链拼接求解器。

业务规则：
- 每段图纸恰使用一次，所有段按某一排列依次拼接；
- 相邻两段之间用"类型相同"的刻度做一对一配对，且配对保持各自原始顺序；
- 同一边界内所有配对的平移量（右刻度 - 左刻度）必须一致；
- 由于每段刻度严格递增，平移量一致时顺序保持与一对一自动成立；
- 优化目标依次：全部边界配对总数最大 → 各边界 |平移量| 总和最小 →
  按原录入编号序列字典序稳定决胜；
- 任一边界找不到合法配对（即两段没有任何同类型刻度）时整体无解。
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Optional


@dataclass(frozen=True)
class Mark:
    value: int
    type: str


@dataclass(frozen=True)
class Segment:
    id: int
    marks: tuple  # tuple[Mark, ...]，value 严格递增


@dataclass(frozen=True)
class Pair:
    left_value: int
    right_value: int
    type: str


@dataclass(frozen=True)
class Boundary:
    left_id: int
    right_id: int
    delta: int
    pairs: tuple  # tuple[Pair, ...]


@dataclass(frozen=True)
class Solution:
    order: tuple  # tuple[int, ...] 拼接后的段编号序列
    boundaries: tuple  # tuple[Boundary, ...]
    total_pairs: int
    total_error: int
    unpaired: tuple  # tuple[tuple[int, tuple[Mark, ...]], ...] 按拼接顺序逐段列出


def best_boundary(left: Segment, right: Segment) -> Optional[Boundary]:
    """计算两段相邻时的最优配对。

    平移量 delta 相同是边界内一致性的要求；在刻度严格递增的前提下，
    同一 delta 下所有"值对齐且类型相同"的刻度天然构成保序的一对一配对，
    因此对该 delta 直接取全部可配对刻度即为配对数最大。
    多个 delta 配对数相同时，先取 |delta| 较小者，再取代数值较小者以保证确定性。
    两段没有任何同类型刻度时返回 None（该边界无合法配对）。
    """
    right_type_by_value = {mark.value: mark.type for mark in right.marks}
    counts: dict[int, int] = {}
    for mark in left.marks:
        for rmark in right.marks:
            if rmark.type == mark.type:
                delta = rmark.value - mark.value
                counts[delta] = counts.get(delta, 0) + 1
    if not counts:
        return None
    top = max(counts.values())
    delta = min((d for d, c in counts.items() if c == top),
                key=lambda d: (abs(d), d))
    pairs = tuple(
        Pair(mark.value, mark.value + delta, mark.type)
        for mark in left.marks
        if right_type_by_value.get(mark.value + delta) == mark.type
    )
    return Boundary(left.id, right.id, delta, pairs)


def solve(segments: list) -> Optional[Solution]:
    """枚举全部排列，按三重目标选出最优拼接方案；无可行排列时返回 None。"""
    best_key = None
    best = None
    for perm in permutations(range(len(segments))):
        boundaries = []
        total_pairs = 0
        total_error = 0
        feasible = True
        for a, b in zip(perm, perm[1:]):
            boundary = best_boundary(segments[a], segments[b])
            if boundary is None:
                feasible = False
                break
            boundaries.append(boundary)
            total_pairs += len(boundary.pairs)
            total_error += abs(boundary.delta)
        if not feasible:
            continue
        key = (-total_pairs, total_error,
               tuple(segments[i].id for i in perm))
        if best_key is None or key < best_key:
            best_key = key
            best = (perm, tuple(boundaries), total_pairs, total_error)
    if best is None:
        return None
    perm, boundaries, total_pairs, total_error = best

    paired_values = [set() for _ in perm]
    for k, boundary in enumerate(boundaries):
        for pair in boundary.pairs:
            paired_values[k].add(pair.left_value)
            paired_values[k + 1].add(pair.right_value)
    unpaired = []
    for pos, seg_index in enumerate(perm):
        segment = segments[seg_index]
        rest = tuple(m for m in segment.marks
                     if m.value not in paired_values[pos])
        unpaired.append((segment.id, rest))
    return Solution(
        order=tuple(segments[i].id for i in perm),
        boundaries=boundaries,
        total_pairs=total_pairs,
        total_error=total_error,
        unpaired=tuple(unpaired),
    )
