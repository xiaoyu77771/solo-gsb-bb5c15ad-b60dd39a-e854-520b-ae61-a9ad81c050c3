"""请求与响应的数据模型。"""

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlanRequest(BaseModel):
    """翻页点规划请求。"""

    model_config = ConfigDict(extra="forbid")

    measure_heights: List[float] = Field(
        ...,
        min_length=1,
        description="依次排列的各小节高度（单位与页面高度一致）",
    )
    silences: List[float] = Field(
        ...,
        min_length=1,
        description="每个小节之后可供翻页的静默秒数，与小节一一对应；"
        "末项为全曲结束后的静默，不会作为翻页点",
    )
    page_height: float = Field(..., gt=0, description="页面可用高度")
    min_turn_seconds: float = Field(
        ..., ge=0, description="最低翻页时间（静默秒数下限）"
    )

    @field_validator("measure_heights")
    @classmethod
    def _heights_positive(cls, v: List[float]) -> List[float]:
        for idx, h in enumerate(v):
            if h <= 0:
                raise ValueError(f"第 {idx + 1} 个小节的高度必须为正数")
        return v

    @field_validator("silences")
    @classmethod
    def _silences_non_negative(cls, v: List[float]) -> List[float]:
        for idx, s in enumerate(v):
            if s < 0:
                raise ValueError(f"第 {idx + 1} 个小节后的静默时间不能为负数")
        return v


class PageResult(BaseModel):
    page: int = Field(..., description="页码，从 1 开始")
    start_measure: int = Field(..., description="该页起始小节序号（从 1 开始）")
    end_measure: int = Field(..., description="该页结束小节序号（含）")
    turn_after_measure: Optional[int] = Field(
        ..., description="翻页发生在该小节之后；最后一页为 null"
    )
    turn_seconds: Optional[float] = Field(
        ..., description="该翻页点的静默秒数；最后一页为 null"
    )


class PlanResult(BaseModel):
    page_count: int
    min_turn_seconds: Optional[float] = Field(
        ..., description="所有翻页点静默时间的最小值；无翻页点（单页）时为 null"
    )
    breaks: List[int] = Field(..., description="断页序号：翻页发生在这些小节之后")
    pages: List[PageResult]


class PlanEnvelope(BaseModel):
    """统一响应结构。"""

    id: str
    status: Literal["completed", "failed"]
    result: Optional[PlanResult] = None
    error: Optional["ErrorDetail"] = None
    request: Optional[PlanRequest] = None


class ErrorDetail(BaseModel):
    code: str
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    job_count: int


# 前向引用解析（error 字段定义在 PlanEnvelope 之后）。
PlanEnvelope.model_rebuild()


def failed_envelope(job_id: str, code: str, message: str, request: Any) -> PlanEnvelope:
    return PlanEnvelope(
        id=job_id,
        status="failed",
        result=None,
        error=ErrorDetail(code=code, message=message),
        request=request,
    )
