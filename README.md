# 演出用谱翻页点规划 API

为演出电子谱自动规划翻页点的 HTTP 服务（Python 3.11 + FastAPI）。
输入依次排列的**小节高度**、每小节后可供翻页的**静默秒数**、**页面可用高度**
与**最低翻页时间**，服务用动态规划求出最优分页方案：

1. **页数最少**；
2. 页数相同时，**最大化所有翻页点中最短的静默时间**（给实际翻页留出最充裕的余量）；
3. 仍并列时，选**断页序号字典序最小**的方案（倾向尽早确定翻页位置）。

约束：小节不得拆开；每页小节高度之和不得超过页面可用高度；只能在小节之间翻页，
且该处静默秒数必须 ≥ 最低翻页时间（可以在静默达标的位置主动**提前翻页**，
也可以在页面放满后**满页翻页**）。

## 单条命令启动

```bash
docker compose up -d --build
```

启动后服务监听 **http://localhost:8000**

- 在线交互文档（Swagger UI）：http://localhost:8000/docs
- OpenAPI 描述：http://localhost:8000/openapi.json
- 健康检查：http://localhost:8000/health

依赖安装、数据库初始化均在容器启动时自动完成；规划结果保存在容器内
`/data/plans.db`（SQLite），通过 Docker 命名卷 `planner-data` 持久化，
重启/重建容器不丢失。

停止：`docker compose down`（加 `-v` 会同时删除结果数据卷）。

## 必要配置

均为可选，使用默认值即可直接启动。可通过环境变量或 `.env` 文件设置：

| 配置 | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| 宿主机端口 | `APP_PORT` | `8000` |  compose 中映射 `${APP_PORT:-8000}:8000` |
| 结果数据库路径 | `PLAN_DB_PATH` | `/data/plans.db` | 容器内 SQLite 文件路径，父目录由数据卷挂载 |

本地不使用容器运行时：

```bash
pip install -r requirements.txt
PLAN_DB_PATH=./data/plans.db uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API

### `POST /plans` — 提交规划

同步完成计算并保存结果，返回结果与分配的 `id`（HTTP 201）。

请求体：

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `measure_heights` | number[] | 非空、元素 > 0 | 依次排列的各小节高度 |
| `silences` | number[] | 与小节数等长、元素 ≥ 0 | 每个小节之后的静默秒数；末项为全曲结束后的静默，不作为翻页点 |
| `page_height` | number | > 0 | 页面可用高度（与小节高度同单位） |
| `min_turn_seconds` | number | ≥ 0 | 最低翻页时间，翻页点静默必须达到该值 |

```bash
curl -X POST http://localhost:8000/plans \
  -H 'Content-Type: application/json' \
  -d '{
    "measure_heights": [3, 3, 4, 4],
    "silences": [5, 2, 6, 0],
    "page_height": 10,
    "min_turn_seconds": 3
  }'
```

响应（小节 1–3 放第一页，在第 3 小节后 6 秒静默处翻页）：

```json
{
  "id": "3c157ed3bbb94eab9540dbcc2237630b",
  "status": "completed",
  "result": {
    "page_count": 2,
    "min_turn_seconds": 6.0,
    "breaks": [3],
    "pages": [
      {"page": 1, "start_measure": 1, "end_measure": 3,
       "turn_after_measure": 3, "turn_seconds": 6.0},
      {"page": 2, "start_measure": 4, "end_measure": 4,
       "turn_after_measure": null, "turn_seconds": null}
    ]
  },
  "error": null,
  "request": { "...": "回显的原始请求" }
}
```

字段说明：`breaks` 为断页序号（翻页发生在这些小节之后）；每页给出小节范围
`start_measure`–`end_measure`（均含、从 1 开始）以及该页之后的翻页点
`turn_after_measure` / `turn_seconds`（最后一页不翻页，为 `null`）。
全曲只有一页时 `min_turn_seconds` 与 `breaks` 分别为 `null` / `[]`。

### `GET /plans/{id}` — 按 ID 查询结果

```bash
curl http://localhost:8000/plans/3c157ed3bbb94eab9540dbcc2237630b
```

返回与提交时相同的完整记录（`id` 不存在返回 404）。计算失败的记录同样持久化，
可凭 ID 查询到失败原因。

### `GET /health`

返回 `{"status": "ok", "job_count": <已保存记录数>}`。

## 错误处理

错误统一返回 HTTP 400，结构为
`{"id": "...", "status": "failed", "result": null, "error": {"code": ..., "message": ...}}`，
失败记录也会保存：

| `error.code` | 触发条件 |
|---|---|
| `measure_exceeds_page` | 单小节高度超过页面可用高度，任何页面都放不下 |
| `no_legal_plan` | 不存在合法分页方案（所有必需的换页位置静默时长均不足，且无法靠提前/满页翻页避开） |
| `invalid_input` | 数组为空或长度不匹配、数值非法等请求校验错误 |

## 算法说明

对每个前缀小节数 `j` 保留唯一最优签名 `(页数, 翻页点最短静默, 断页序号元组)`，
枚举最后一页起点 `i`（同页高度倒序累加，一旦超页即剪枝）进行转移：
非末页要求 `silences[j-1] ≥ min_turn_seconds` 并把该静默计入最小值，
末页（全曲结束）不引入翻页点。按三级目标（页数↑ → 最短静默↓ → 断页元组字典序）
取优。该剪枝是安全的：页数相同前提下，更优签名对任意后续延伸保持更优。
时间复杂度 O(n²)、空间 O(n)（2000 小节约 0.06 s）。

## 测试

```bash
python tests/test_planner.py        # 无需 pytest
```
