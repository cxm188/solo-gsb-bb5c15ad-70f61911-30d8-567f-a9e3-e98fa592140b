"""请求 / 响应数据模型。"""
from __future__ import annotations

import math

from pydantic import BaseModel, Field, field_validator

_EPS = 1e-12


class Vec2(BaseModel):
    x: float
    y: float

    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


class InterfaceIn(BaseModel):
    """一个界面：线上一点、指向下一介质的法线、下一介质折射率。"""

    point: Vec2
    normal: Vec2
    n_next: float = Field(gt=0, description="下一介质折射率，必须为正")

    @field_validator("normal")
    @classmethod
    def normal_nonzero(cls, v: Vec2) -> Vec2:
        if math.hypot(v.x, v.y) < _EPS:
            raise ValueError("法线不能为零向量")
        return v


class TraceRequest(BaseModel):
    start: Vec2
    direction: Vec2
    n_start: float = Field(gt=0, description="起始介质折射率，必须为正")
    interfaces: list[InterfaceIn] = Field(default_factory=list)

    @field_validator("direction")
    @classmethod
    def direction_nonzero(cls, v: Vec2) -> Vec2:
        if math.hypot(v.x, v.y) < _EPS:
            raise ValueError("方向不能为零向量")
        return v


class BeamRequest(BaseModel):
    """光束评估请求：以中心方向为 0°，在 [-half_angle_deg, +half_angle_deg] 扇形采样。"""

    start: Vec2
    center_direction: Vec2
    half_angle_deg: float = Field(
        gt=0, lt=90, description="对称半角（度），必须满足 0 < a < 90"
    )
    samples: int = Field(ge=2, le=101, description="采样光线数（2～101，含两个端点）")
    n_start: float = Field(gt=0, description="起始介质折射率，必须为正")
    interfaces: list[InterfaceIn] = Field(default_factory=list)
    observation_point: Vec2 = Field(description="观察线上一点")
    observation_normal: Vec2 = Field(description="观察线法线（定义前向方向，不必单位化）")

    @field_validator("center_direction", "observation_normal")
    @classmethod
    def vector_nonzero(cls, v: Vec2) -> Vec2:
        if math.hypot(v.x, v.y) < _EPS:
            raise ValueError("向量不能为零向量")
        return v


class BeamRayOut(BaseModel):
    """光束中一条采样光线的评估结果。"""

    launch_angle_deg: float = Field(description="相对中心方向的发射角（度，逆时针为正）")
    status: str
    reason: str | None
    observation_hit: Vec2 | None = Field(
        description="完成追迹后与观察线的前向交点；未完成、平行或在反向时为 null"
    )


class BeamStats(BaseModel):
    hit_count: int = Field(description="观察线上取得非空交点的光线数")
    centroid: Vec2 | None = Field(description="非空交点的质心；无命中时为 null")
    rms_radius: float | None = Field(
        description="交点到质心距离平方均值的平方根；无命中时为 null"
    )


class BeamOut(BaseModel):
    center_direction: Vec2
    half_angle_deg: float
    samples: int
    rays: list[BeamRayOut]
    stats: BeamStats


class SegmentOut(BaseModel):
    seg_index: int
    origin: Vec2
    direction: Vec2
    n_medium: float
    hit_point: Vec2 | None
    event: str | None
    n_after: float | None


class TraceOut(BaseModel):
    id: int
    start: Vec2
    direction: Vec2
    n_start: float
    status: str
    reason: str | None
    created_at: str
    segments: list[SegmentOut]


class TraceSummary(BaseModel):
    id: int
    status: str
    reason: str | None
    n_start: float
    created_at: str
