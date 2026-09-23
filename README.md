# 2D 介质光线追迹 API

基于 **Python + FastAPI + SQLite** 的二维光线追迹服务：提交初始光线（起点、方向）、起始介质折射率，以及按顺序排列的界面（界面上一点、指向下一介质的法线、下一介质折射率），服务逐界面计算前向交点并依斯涅尔定律更新方向；遇到全反射（或光线与界面平行 / 交点在反方向）即停止并返回原因。追迹结果保存到 SQLite，可按编号查询各段交点与方向。此外提供光束评估接口：以中心方向为轴在对称半角内等间距采样多条光线并逐条追迹，返回每条光线在观察线上的前向交点以及光斑质心与 RMS 半径（纯计算、不落库）。

## 启动

```bash
docker compose up --build
```

启动时会安装依赖并自动建库建表（SQLite 文件存于命名卷 `raytrace-data` 中）。

- **API 地址**：http://localhost:8000
- **交互式文档（Swagger UI）**：http://localhost:8000/docs
- **端口**：`8000`

本地开发（不用 Docker）：

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/traces` | 提交光线与界面序列，执行追迹、保存并返回完整结果 |
| GET | `/api/traces` | 列出所有已保存追迹的摘要 |
| GET | `/api/traces/{trace_id}` | 按编号查询完整追迹（含各段交点与方向） |
| GET | `/api/traces/{trace_id}/segments/{seg_index}` | 按编号查询某一段的交点与方向 |
| POST | `/api/beam-evaluation` | 扇形光束采样追迹：逐条返回发射角、状态与观察线前向交点，并给出质心与 RMS 半径（不落库） |

### 请求示例

```bash
curl -X POST http://localhost:8000/api/traces \
  -H "Content-Type: application/json" \
  -d '{
    "start": {"x": 0, "y": 0},
    "direction": {"x": 1, "y": 0.5},
    "n_start": 1.0,
    "interfaces": [
      {"point": {"x": 2, "y": 0}, "normal": {"x": 1, "y": 0}, "n_next": 1.5},
      {"point": {"x": 4, "y": 0}, "normal": {"x": 1, "y": 0}, "n_next": 1.0}
    ]
  }'
```

### 响应说明

- `status`：`completed`（穿过所有界面）、`total_internal_reflection`（全反射停止）、`no_intersection`（与界面平行或交点在反方向）
- `reason`：停止原因（完成时为 `null`）
- `segments[]`：每段包含 `origin`（段起点）、`direction`（段方向）、`n_medium`（所在介质折射率）、`hit_point`（与下一界面的交点，出射段为 `null`）、`event`（`refraction` / `total_internal_reflection` / `no_intersection` / `null`）

### 全反射示例

```bash
curl -X POST http://localhost:8000/api/traces \
  -H "Content-Type: application/json" \
  -d '{
    "start": {"x": 0, "y": 0},
    "direction": {"x": 1, "y": 2},
    "n_start": 1.5,
    "interfaces": [
      {"point": {"x": 2, "y": 0}, "normal": {"x": 1, "y": 0}, "n_next": 1.0}
    ]
  }'
# status = "total_internal_reflection"，reason 说明入射角超过临界角
```

## 光束评估 `POST /api/beam-evaluation`

以 `center_direction` 为 0°，在对称半角 `[-half_angle_deg, +half_angle_deg]`（含两端点）等间距生成 `samples` 条方向（逆时针为正），逐条复用同一套追迹逻辑穿过相同界面序列；对**完成追迹**的光线，取其出射段（最后一段）的起点与方向与观察线求**前向**交点。

- `half_angle_deg`：对称半角（度），必须满足 `0 < a < 90`
- `samples`：采样光线数（2～101），第一条/最后一条分别对应 `-a` / `+a`
- `observation_point` + `observation_normal`：观察线上一点与其法线；只接受沿法线正侧到达（`方向·法线 > 0`）且位于出射点前方的交点
- 追迹未完成（全反射 / 无交点）、与观察线平行、或交点在反方向时，该条光线的 `observation_hit` 为 `null`
- 统计仅基于非空交点：`centroid` 为交点坐标均值，`rms_radius` = √(各交点到质心距离平方的均值)；无任何命中时 `hit_count = 0` 且 `centroid`、`rms_radius` 均为 `null`

该接口为纯计算，结果不写入 SQLite。

### 请求示例

```bash
curl -X POST http://localhost:8000/api/beam-evaluation \
  -H "Content-Type: application/json" \
  -d '{
    "start": {"x": 0, "y": 0},
    "center_direction": {"x": 1, "y": 0},
    "half_angle_deg": 10,
    "samples": 5,
    "n_start": 1.0,
    "interfaces": [
      {"point": {"x": 2, "y": 0}, "normal": {"x": 1, "y": 0}, "n_next": 1.5},
      {"point": {"x": 4, "y": 0}, "normal": {"x": 1, "y": 0}, "n_next": 1.0}
    ],
    "observation_point": {"x": 10, "y": 0},
    "observation_normal": {"x": 1, "y": 0}
  }'
```

### 响应结构

```json
{
  "center_direction": {"x": 1.0, "y": 0.0},
  "half_angle_deg": 10.0,
  "samples": 5,
  "rays": [
    {
      "launch_angle_deg": -10.0,
      "status": "completed",
      "reason": null,
      "observation_hit": {"x": 10.0, "y": -1.6437}
    }
  ],
  "stats": {"hit_count": 5, "centroid": {"x": 10.0, "y": 0.0}, "rms_radius": 1.1607}
}
```

- `rays[].launch_angle_deg`：相对中心方向的发射角（度）
- `rays[].status` / `reason`：与 `/api/traces` 相同的追迹状态与停止原因
- `rays[].observation_hit`：观察线前向交点，未命中为 `null`
- `stats`：`hit_count`、`centroid`、`rms_radius`（无命中时后两者为 `null`）

## 项目结构

```
app/
  main.py       FastAPI 路由与生命周期（启动时建库）
  geometry.py   二维求交与斯涅尔折射计算
  db.py         SQLite 持久化（traces / segments 两表）
  schemas.py    Pydantic 请求 / 响应模型
Dockerfile
docker-compose.yml
requirements.txt
```
