"""二维介质光线追迹 API。

POST /api/traces                      提交光线与界面序列，返回追迹结果并保存
GET  /api/traces                      列出所有已保存的追迹（摘要）
GET  /api/traces/{trace_id}           按编号查询完整追迹（含各段交点与方向）
GET  /api/traces/{trace_id}/segments/{seg_index}  按编号查询某一段
POST /api/beam-evaluation             扇形光束采样追迹，返回观察线交点、质心与 RMS 半径
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from . import db
from .geometry import evaluate_beam, trace_ray
from .schemas import (
    BeamOut,
    BeamRequest,
    SegmentOut,
    TraceOut,
    TraceRequest,
    TraceSummary,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()  # 启动时建库建表
    yield


app = FastAPI(
    title="2D Medium Ray Tracing API",
    version="1.0.0",
    description="二维介质光线追迹：按斯涅尔定律折射，遇全反射停止并返回原因。",
    lifespan=lifespan,
)


@app.get("/")
def root() -> dict:
    return {
        "service": "2d-ray-tracing",
        "docs": "/docs",
        "api": "/api/traces",
        "beam_evaluation": "/api/beam-evaluation",
    }


@app.post("/api/traces", response_model=TraceOut, status_code=201)
def create_trace(req: TraceRequest) -> dict:
    interfaces = [
        (itf.point.as_tuple(), itf.normal.as_tuple(), itf.n_next)
        for itf in req.interfaces
    ]
    segments, status, reason = trace_ray(
        req.start.as_tuple(), req.direction.as_tuple(), req.n_start, interfaces
    )
    trace_id = db.insert_trace(
        req.start.as_tuple(),
        req.direction.as_tuple(),
        req.n_start,
        status,
        reason,
        segments,
    )
    return db.get_trace(trace_id)


@app.get("/api/traces", response_model=list[TraceSummary])
def list_traces() -> list[dict]:
    return db.list_traces()


@app.get("/api/traces/{trace_id}", response_model=TraceOut)
def get_trace(trace_id: int) -> dict:
    trace = db.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"追迹 {trace_id} 不存在")
    return trace


@app.get("/api/traces/{trace_id}/segments/{seg_index}", response_model=SegmentOut)
def get_segment(trace_id: int, seg_index: int) -> dict:
    segment = db.get_segment(trace_id, seg_index)
    if segment is None:
        raise HTTPException(
            status_code=404, detail=f"追迹 {trace_id} 的第 {seg_index} 段不存在"
        )
    return segment


@app.post("/api/beam-evaluation", response_model=BeamOut)
def evaluate_beam_endpoint(req: BeamRequest) -> dict:
    """以中心方向为 0° 在对称半角内等间距采样，逐条复用追迹并评估观察线光斑。"""
    interfaces = [
        (itf.point.as_tuple(), itf.normal.as_tuple(), itf.n_next)
        for itf in req.interfaces
    ]
    rays, centroid, rms, hit_count = evaluate_beam(
        req.start.as_tuple(),
        req.center_direction.as_tuple(),
        req.half_angle_deg,
        req.samples,
        req.n_start,
        interfaces,
        req.observation_point.as_tuple(),
        req.observation_normal.as_tuple(),
    )
    return {
        "center_direction": req.center_direction,
        "half_angle_deg": req.half_angle_deg,
        "samples": req.samples,
        "rays": [
            {
                "launch_angle_deg": r.launch_angle_deg,
                "status": r.status,
                "reason": r.reason,
                "observation_hit": (
                    None if r.observation_hit is None else
                    {"x": r.observation_hit[0], "y": r.observation_hit[1]}
                ),
            }
            for r in rays
        ],
        "stats": {
            "hit_count": hit_count,
            "centroid": None if centroid is None else {"x": centroid[0], "y": centroid[1]},
            "rms_radius": rms,
        },
    }
