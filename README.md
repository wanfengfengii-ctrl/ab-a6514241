# 航海测深图拼接裁决（depth-chart-adjudicator）

海事博物馆修复被裁成多段的航海测深图：录入各段纸边的深度刻度与刻线类型后，
服务端裁决能否按原航线顺序拼成一条可信的刻度链，并返回拼接顺序、
相邻重叠刻度配对、未配对刻度与总拼接误差。

## 业务规则

- 每段图纸**恰使用一次**，所有段按某一排列依次拼接；
- 相邻两段仅用**类型相同**的刻度做**一对一**配对，且配对**保持各自原始顺序**
  （刻度严格递增 + 平移量一致时，保序与一对一自动成立）；
- 同一相邻边界内所有配对的**平移量**（右刻度 − 左刻度）**必须一致**；
- 裁决目标依次（字典序）：
  1. **最大化**全部边界的配对总数；
  2. **最小化**各边界 |平移量| 的总和（总拼接误差）；
  3. 仍持平时，按**原录入编号序列**字典序稳定决胜；
  4. 边界内部：配对数最大的平移量中，先取 |平移量| 较小者，再取代数值较小者。
- 任一边界没有合法配对（两段没有任何同类型刻度）即整体无解，返回 422；
- 录入的刻度、类型、编号不合法时返回 400 与**首个**原因，页面清除旧方案并展示该原因。

## 录入约束

| 项 | 约束 |
| --- | --- |
| 段数 | 3–6 段 |
| 每段刻度数 | 4–10 个 |
| 刻度 | 严格递增整数 |
| 刻线类型 | `major` / `intermediate` / `minor` |
| 编号 | 正整数，段间唯一 |

## API

- `GET /api/health` → `{"status": "ok", ...}`
- `GET /api/meta` → 录入约束与合法刻线类型
- `POST /api/adjudicate`

请求：

```json
{
  "segments": [
    {"id": 1, "scales": [100, 110, 120, 130, 140],
     "types": ["major", "minor", "intermediate", "minor", "major"]},
    {"id": 2, "scales": [105, 115, 125, 135, 150],
     "types": ["minor", "intermediate", "minor", "major", "major"]},
    {"id": 3, "scales": [98, 108, 118, 128, 138],
     "types": ["intermediate", "minor", "major", "minor", "intermediate"]}
  ]
}
```

成功响应（200）：`order`（拼接顺序）、`boundaries`（每边界的 `delta`、
`pairs` 配对明细、`pairCount`）、`unpaired`（逐段未配对刻度）、
`totalPairs`、`totalError`。

失败响应：

| 状态码 | 场景 | 响应体 |
| --- | --- | --- |
| 400 | 刻度/类型/编号等首个不合法处 | `{"error": {"code", "message", "field"}}` |
| 422 | 任何排列下均存在无合法配对的边界 | `{"error": {"code": "NO_FEASIBLE_CHAIN", ...}}` |

页面（`GET /`）展示的全部结果证据均来自上述 API 响应，前端不做任何求解。

## 运行

### 本地（Python 3.11+，无第三方依赖）

```bash
python3 -m app.server          # 默认 0.0.0.0:8000，可用 PORT 环境变量覆盖
python3 -m unittest discover -s tests -t .   # 运行测试
```

### Docker Compose

```bash
cp .env.example .env           # 可选：修改 HOST_PORT（默认 8000）
docker compose up --build app  # 启动服务，宿主机端口由 HOST_PORT 配置
```

`app` 服务内置健康检查（`GET /api/health`）。

### 一次性验收服务 verify

`verify` 服务依次完成**代码测试**（unittest）、**构建检查**
（字节码编译 + 模块导入）、**API 冒烟**（健康检查、meta、成功裁决、
400 首个原因、422 无可行链），随后自行退出并以退出码报告结果：

```bash
docker compose up --build --exit-code-from verify --abort-on-container-exit verify
echo $?   # 0 = 验收通过，非 0 = 失败
```

## 算法说明

段数 ≤ 6，枚举全部排列（至多 720 种）。对每一有序相邻段对，
统计所有候选平移量可配的对数（同类型且值对齐），取对数最大、
|平移量| 最小的配对方案；排列可行当且仅当每个边界至少有一对合法配对，
再按上述三重目标选出最优排列。未配对刻度 = 该段在两个相邻边界中
均未参与配对的刻度。

## 项目结构

```
app/
  server.py       HTTP 服务（API + 静态页面）
  solver.py       拼接求解器（纯函数）
  validation.py   录入校验（首个原因）
  static/         录入与裁决页面
tests/            求解器与 API 测试
verify/run.py     一次性验收服务入口
Dockerfile / docker-compose.yml / .env.example
```
