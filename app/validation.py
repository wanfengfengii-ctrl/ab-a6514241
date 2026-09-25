"""录入数据的合法性校验。

按录入顺序逐段、逐字段检查，发现首个问题即抛出 ValidationError，
页面据此"清除旧方案并显示首个原因"。
"""
from __future__ import annotations

from app.solver import Mark, Segment

ALLOWED_TYPES = ("major", "intermediate", "minor")
MIN_SEGMENTS = 3
MAX_SEGMENTS = 6
MIN_MARKS = 4
MAX_MARKS = 10


class ValidationError(Exception):
    def __init__(self, code: str, message: str, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_segments(payload) -> list:
    """把请求 JSON 校验并转换为 Segment 列表；首个不合法处抛 ValidationError。"""
    if not isinstance(payload, dict):
        raise ValidationError("INVALID_BODY", "请求体须为 JSON 对象")
    segments = payload.get("segments")
    if not isinstance(segments, list):
        raise ValidationError("INVALID_SEGMENTS", "请求须包含 segments 数组",
                              "segments")
    if not MIN_SEGMENTS <= len(segments) <= MAX_SEGMENTS:
        raise ValidationError(
            "INVALID_SEGMENT_COUNT",
            f"图纸段数须为 {MIN_SEGMENTS} 至 {MAX_SEGMENTS} 段，"
            f"当前为 {len(segments)} 段",
            "segments")

    seen_ids: set[int] = set()
    result: list[Segment] = []
    for i, raw in enumerate(segments):
        n = i + 1
        prefix = f"segments[{i}]"
        if not isinstance(raw, dict):
            raise ValidationError("INVALID_SEGMENT", f"第 {n} 段须为对象", prefix)

        sid = raw.get("id")
        if not _is_int(sid) or sid < 1:
            raise ValidationError("INVALID_ID",
                                  f"第 {n} 段编号不合法：须为正整数",
                                  f"{prefix}.id")
        if sid in seen_ids:
            raise ValidationError("DUPLICATE_ID",
                                  f"第 {n} 段编号 {sid} 与其他段重复",
                                  f"{prefix}.id")
        seen_ids.add(sid)

        scales = raw.get("scales")
        if not isinstance(scales, list):
            raise ValidationError("INVALID_SCALES", f"第 {n} 段刻度须为数组",
                                  f"{prefix}.scales")
        if not MIN_MARKS <= len(scales) <= MAX_MARKS:
            raise ValidationError(
                "INVALID_SCALE_COUNT",
                f"第 {n} 段刻度数须为 {MIN_MARKS} 至 {MAX_MARKS} 个，"
                f"当前为 {len(scales)} 个",
                f"{prefix}.scales")
        for j, value in enumerate(scales):
            if not _is_int(value):
                raise ValidationError("INVALID_SCALE_VALUE",
                                      f"第 {n} 段第 {j + 1} 个刻度不合法：须为整数",
                                      f"{prefix}.scales[{j}]")
            if j > 0 and value <= scales[j - 1]:
                raise ValidationError(
                    "SCALES_NOT_INCREASING",
                    f"第 {n} 段刻度须严格递增：第 {j + 1} 个刻度 {value} "
                    f"未大于前一刻度 {scales[j - 1]}",
                    f"{prefix}.scales[{j}]")

        types = raw.get("types")
        if not isinstance(types, list):
            raise ValidationError("INVALID_TYPES",
                                  f"第 {n} 段刻线类型须为数组",
                                  f"{prefix}.types")
        if len(types) != len(scales):
            raise ValidationError(
                "TYPE_COUNT_MISMATCH",
                f"第 {n} 段刻线类型数量（{len(types)}）与刻度数量"
                f"（{len(scales)}）不一致",
                f"{prefix}.types")
        for j, t in enumerate(types):
            if not isinstance(t, str) or t not in ALLOWED_TYPES:
                raise ValidationError(
                    "INVALID_TYPE_VALUE",
                    f"第 {n} 段第 {j + 1} 个刻线类型不合法：须为 "
                    f"{' / '.join(ALLOWED_TYPES)} 之一",
                    f"{prefix}.types[{j}]")

        result.append(Segment(sid, tuple(Mark(v, t)
                                         for v, t in zip(scales, types))))
    return result
