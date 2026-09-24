"""演出用谱翻页点规划：动态规划核心。

问题描述
--------
输入依次排列的小节高度 ``heights``、每小节之后可供翻页的静默秒数
``silences``（与小节一一对应，末项为全曲结束后的静默，不会成为翻页点）、
页面可用高度 ``page_height`` 以及最低翻页时间 ``min_turn_seconds``。

规则：
* 小节不得拆开，同一页上的小节高度之和不得超过页面可用高度；
* 只允许在小节之间的静默处翻页，且该处静默秒数必须不低于最低翻页时间；
  既可以在内容恰好放满（再放一个小节就超高）时翻页，也可以在静默达标时
  主动提前翻页；
* 单小节高度超过页面可用高度，或不存在任何合法分页方案时，抛出
  :class:`PlanningError`。

优化目标（按字典序）：
1. 页数最少；
2. 在页数最少的方案中，最大化所有翻页点静默时间的最小值
   （只有一页、不存在翻页点时，该目标视为最优，取值为 ``None``）；
3. 仍并列时，选断页序号（翻页发生在哪些小节之后）字典序最小的方案。
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple


class PlanningError(Exception):
    """规划失败：输入不合法或不存在合法分页方案。"""

    def __init__(self, message: str, code: str = "no_legal_plan"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class Signature:
    """某个前缀位置上的最优方案签名。

    ``breaks`` 只记录真正发生翻页的位置（翻页发生在该小节之后），
    最后一页收尾位置不计入，因此其长度恒为 ``pages - 1``。
    """

    pages: int
    min_silence: Optional[float]
    breaks: Tuple[int, ...]


def _better(a: Signature, b: Signature) -> bool:
    """按三级优化目标判断签名 ``a`` 是否严格优于 ``b``。"""
    if a.pages != b.pages:
        return a.pages < b.pages

    # 第二目标：翻页点最短静默越大越好；没有翻页点（单页）视为 +inf。
    sa, sb = a.min_silence, b.min_silence
    if sa != sb:
        if sa is None:
            return True
        if sb is None:
            return False
        return sa > sb

    # 第三目标：断页序号字典序最小。
    return a.breaks < b.breaks


def plan_pages(
    heights: List[float],
    silences: List[float],
    page_height: float,
    min_turn_seconds: float,
) -> dict:
    """计算最优翻页规划。

    返回::

        {
            "page_count": int,
            "min_turn_seconds": float | None,
            "breaks": [int, ...],
            "pages": [
                {
                    "page": int,
                    "start_measure": int,
                    "end_measure": int,
                    "turn_after_measure": int | None,
                    "turn_seconds": float | None,
                }, ...
            ],
        }
    """
    n = len(heights)
    if n == 0:
        raise PlanningError("measure_heights 不能为空，至少需要一个小节", "invalid_input")
    if len(silences) != n:
        raise PlanningError(
            f"silences 长度（{len(silences)}）必须与小节数（{n}）一致",
            "invalid_input",
        )
    if page_height <= 0:
        raise PlanningError("page_height 必须为正数", "invalid_input")
    if min_turn_seconds < 0:
        raise PlanningError("min_turn_seconds 不能为负数", "invalid_input")

    for idx, h in enumerate(heights):
        if h <= 0:
            raise PlanningError(
                f"第 {idx + 1} 个小节的高度必须为正数，实际为 {h}", "invalid_input"
            )
        if h > page_height:
            raise PlanningError(
                f"第 {idx + 1} 个小节高度 {h} 超过页面可用高度 {page_height}，"
                "该小节无法放入任何页面",
                "measure_exceeds_page",
            )
    for idx, s in enumerate(silences):
        if s < 0:
            raise PlanningError(
                f"第 {idx + 1} 个小节后的静默时间不能为负数，实际为 {s}",
                "invalid_input",
            )

    # 浮点求和的容差：高度恰好等于页高时应视为放得下。
    eps = 1e-9 * max(1.0, abs(float(page_height)))

    # dp[j]：前 j 个小节的最优方案签名；pred[j]：该方案最后一页的起点前驱
    # （最后一页为小节 pred[j]+1 .. j）。
    # 每个前缀位置只保留一个签名：页数相同的前提下，min_silence 更大或
    # breaks 字典序更小的签名，对任意后续延伸都不会变得更差，因此可以安全剪枝。
    dp: dict[int, Signature] = {0: Signature(0, None, ())}
    pred: dict[int, int] = {}

    for j in range(1, n + 1):
        total = 0.0
        best: Optional[Signature] = None
        best_i: Optional[int] = None

        # 最后一页放小节 i+1 .. j，倒序累加高度，一旦超页即可停止。
        for i in range(j - 1, -1, -1):
            total += heights[i]
            if total > page_height + eps:
                break

            prev = dp.get(i)
            if prev is None:
                continue

            if j < n:
                # 非末页：j 之后必须翻页，静默时长 silences[j-1] 必须达标。
                silence = silences[j - 1]
                if silence < min_turn_seconds:
                    continue
                new_min = silence if prev.min_silence is None else min(
                    prev.min_silence, silence
                )
                new_breaks = prev.breaks + (j,)
            else:
                # 全曲结束：最后一页之后不翻页，不引入翻页点。
                new_min = prev.min_silence
                new_breaks = prev.breaks

            candidate = Signature(prev.pages + 1, new_min, new_breaks)
            if best is None or _better(candidate, best):
                best = candidate
                best_i = i

        if best is not None:
            dp[j] = best
            pred[j] = best_i  # type: ignore[assignment]

    if n not in dp:
        raise PlanningError(
            "在给定的页面高度与最低翻页时间下不存在合法的分页方案："
            "每次换页位置的静默时长均不足，或无法在不拆散小节的前提下排满页面",
            "no_legal_plan",
        )

    final = dp[n]

    # 回溯重建每页的小节范围。
    ranges: List[Tuple[int, int]] = []
    end = n
    while end > 0:
        start = pred[end] + 1
        ranges.append((start, end))
        end = pred[end]
    ranges.reverse()

    pages = []
    for idx, (start, end_measure) in enumerate(ranges):
        is_last = idx == len(ranges) - 1
        pages.append(
            {
                "page": idx + 1,
                "start_measure": start,
                "end_measure": end_measure,
                "turn_after_measure": None if is_last else end_measure,
                "turn_seconds": None if is_last else silences[end_measure - 1],
            }
        )

    return {
        "page_count": final.pages,
        "min_turn_seconds": final.min_silence,
        "breaks": list(final.breaks),
        "pages": pages,
    }
