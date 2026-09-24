"""演出用谱翻页点规划 API。

接口
----
* ``POST /plans``           提交一条规划，同步计算并保存结果，返回结果与 ID
* ``GET  /plans/{job_id}``  按 ID 查询已保存的规划结果
* ``GET  /health``          健康检查
"""

import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .planner import PlanningError, plan_pages
from .schemas import PlanEnvelope, PlanRequest, failed_envelope
from .storage import JobStore


class UTF8JSONResponse(JSONResponse):
    """JSON 响应不转义中文（ensure_ascii=False）。"""

    def render(self, content: object) -> bytes:
        return json.dumps(
            content, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")

DB_PATH = os.environ.get("PLAN_DB_PATH", "/data/plans.db")
store: Optional[JobStore] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 容器启动即完成本地数据库初始化。
    global store
    store = JobStore(DB_PATH)
    yield


app = FastAPI(
    title="演出用谱翻页点规划 API",
    version="1.0.0",
    description="动态规划计算页数最少、翻页点最短静默最大、断页序号字典序最小的翻页方案",
    lifespan=lifespan,
    default_response_class=UTF8JSONResponse,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """统一请求校验失败的错误格式。"""
    messages = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        messages.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
    detail = "；".join(messages)
    return UTF8JSONResponse(
        status_code=400,
        content={"id": None, "status": "failed", "result": None,
                 "error": {"code": "invalid_input", "message": detail}},
    )


@app.post("/plans", status_code=201, response_model=PlanEnvelope)
def submit_plan(payload: PlanRequest) -> JSONResponse:
    job_id = uuid.uuid4().hex
    request_data = payload.model_dump()

    try:
        result = plan_pages(
            heights=payload.measure_heights,
            silences=payload.silences,
            page_height=payload.page_height,
            min_turn_seconds=payload.min_turn_seconds,
        )
    except PlanningError as exc:
        # 失败结果同样落盘，可凭 ID 查询。
        store.save(
            job_id,
            status="failed",
            request=request_data,
            error_code=exc.code,
            error_message=exc.message,
        )
        envelope = failed_envelope(job_id, exc.code, exc.message, payload)
        return UTF8JSONResponse(status_code=400, content=envelope.model_dump())

    store.save(job_id, status="completed", request=request_data, result=result)
    envelope = PlanEnvelope(id=job_id, status="completed", result=result, request=payload)
    return UTF8JSONResponse(status_code=201, content=envelope.model_dump())


@app.get("/plans/{job_id}", response_model=PlanEnvelope)
def get_plan(job_id: str) -> JSONResponse:
    record = store.get(job_id)
    if record is None:
        return UTF8JSONResponse(
            status_code=404,
            content={"detail": f"未找到 ID 为 {job_id} 的规划记录"},
        )

    request_obj = PlanRequest(**record["request"])
    if record["status"] == "completed":
        envelope = PlanEnvelope(
            id=record["id"],
            status="completed",
            result=record["result"],
            request=request_obj,
        )
    else:
        envelope = PlanEnvelope(
            id=record["id"],
            status="failed",
            error=record["error"],
            request=request_obj,
        )
    return UTF8JSONResponse(status_code=200, content=envelope.model_dump())


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "job_count": store.count()}
