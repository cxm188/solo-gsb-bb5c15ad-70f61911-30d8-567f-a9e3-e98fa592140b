"""二维几何计算与斯涅尔定律折射。

约定：
- 所有方向向量、法线在内部均归一化。
- 界面为一条直线：由线上一点 point 与指向下一介质的法线 normal 定义。
- 光线沿当前方向前进，只接受前向（t > 0）交点。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

EPS = 1e-12
T_MIN = 1e-9  # 交点参数 t 必须大于该值，避免自相交


def _dot(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1]


def normalize(v: tuple[float, float]) -> tuple[float, float]:
    n = math.hypot(v[0], v[1])
    if n < EPS:
        raise ValueError("zero-length vector")
    return (v[0] / n, v[1] / n)


def rotate_deg(v: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    """将二维向量逆时针旋转 angle_deg 度（角度为负表示顺时针）。"""
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    return (c * v[0] - s * v[1], s * v[0] + c * v[1])


def beam_angles(half_angle_deg: float, samples: int) -> list[float]:
    """以中心方向为 0°，在 [-half_angle_deg, +half_angle_deg] 含端点等间距取 samples 个角。"""
    if samples == 1:
        return [0.0]
    span = 2.0 * half_angle_deg
    return [
        -half_angle_deg + (i / (samples - 1)) * span
        for i in range(samples)
    ]


@dataclass
class SegmentResult:
    """一段光线的计算结果。hit_point 为 None 表示光线出射（无后续界面）。"""

    origin: tuple[float, float]
    direction: tuple[float, float]
    n_medium: float
    hit_point: tuple[float, float] | None
    event: str | None  # refraction / total_internal_reflection / no_intersection / None
    n_after: float | None


def _intersect_line(
    origin: tuple[float, float],
    direction: tuple[float, float],
    point: tuple[float, float],
    normal: tuple[float, float],
    t_min: float = T_MIN,
    one_sided: bool = False,
) -> tuple[float, float] | None:
    """光线与直线求交，返回前向交点；平行或交点在身后则返回 None。

    t >= t_min 才算前方命中。界面求交默认要求 t > T_MIN 以避免自相交，且
    one_sided=False：从法线任一侧到达均可（折射时按入射侧翻转法线）。
    观察线传 t_min=0.0、one_sided=True：只接受沿法线正侧到达的光线，
    从法线背面到达视为反向交点。
    """
    denom = _dot(direction, normal)
    if one_sided:
        if denom <= EPS:
            return None  # 平行，或光线打在观察线背面
    elif abs(denom) < EPS:
        return None  # 光线与界面平行
    t = _dot((point[0] - origin[0], point[1] - origin[1]), normal) / denom
    if t < t_min:
        return None  # 交点不在前方
    return (origin[0] + t * direction[0], origin[1] + t * direction[1])


def _refract(
    direction: tuple[float, float],
    normal: tuple[float, float],
    n1: float,
    n2: float,
) -> tuple[float, float] | None:
    """按斯涅尔定律计算折射方向；发生全反射时返回 None。

    若光线从法线背面入射，则翻转法线再计算（折射率仍按给定 n1 -> n2）。
    """
    cos_i = _dot(direction, normal)
    if cos_i < 0.0:
        normal = (-normal[0], -normal[1])
        cos_i = -cos_i
    eta = n1 / n2
    sin2_t = eta * eta * max(0.0, 1.0 - cos_i * cos_i)
    if sin2_t > 1.0:
        return None  # 全反射
    cos_t = math.sqrt(1.0 - sin2_t)
    k = cos_t - eta * cos_i
    return (eta * direction[0] + k * normal[0], eta * direction[1] + k * normal[1])


def trace_ray(
    start: tuple[float, float],
    direction: tuple[float, float],
    n_start: float,
    interfaces: list[tuple[tuple[float, float], tuple[float, float], float]],
) -> tuple[list[SegmentResult], str, str | None]:
    """依次对每个界面做前向求交并折射。

    interfaces: 按顺序排列的 (point, normal, n_next)。
    返回 (segments, status, reason)，status ∈
    completed / total_internal_reflection / no_intersection。
    """
    origin = (float(start[0]), float(start[1]))
    d = normalize(direction)
    n_current = float(n_start)
    segments: list[SegmentResult] = []

    for idx, (point, normal, n_next) in enumerate(interfaces):
        nrm = normalize(normal)
        hit = _intersect_line(origin, d, point, nrm)
        if hit is None:
            reason = (
                f"光线与第 {idx} 个界面平行，或交点位于光线反方向，追迹停止"
            )
            segments.append(SegmentResult(origin, d, n_current, None, "no_intersection", None))
            return segments, "no_intersection", reason

        new_dir = _refract(d, nrm, n_current, n_next)
        if new_dir is None:
            reason = (
                f"在第 {idx} 个界面发生全反射：n1={n_current} -> n2={n_next}，"
                f"入射角超过临界角，追迹停止"
            )
            segments.append(
                SegmentResult(origin, d, n_current, hit, "total_internal_reflection", n_next)
            )
            return segments, "total_internal_reflection", reason

        segments.append(SegmentResult(origin, d, n_current, hit, "refraction", n_next))
        origin = hit
        d = new_dir
        n_current = n_next

    # 穿过所有界面，最后一段出射
    segments.append(SegmentResult(origin, d, n_current, None, None, None))
    return segments, "completed", None


@dataclass
class RayEvaluation:
    """光束中一条光线的评估结果。observation_hit 为 None 表示观察线无有效前向交点。"""

    launch_angle_deg: float
    status: str
    reason: str | None
    observation_hit: tuple[float, float] | None


def evaluate_beam(
    start: tuple[float, float],
    center_direction: tuple[float, float],
    half_angle_deg: float,
    samples: int,
    n_start: float,
    interfaces: list[tuple[tuple[float, float], tuple[float, float], float]],
    observation_point: tuple[float, float],
    observation_normal: tuple[float, float],
) -> tuple[list[RayEvaluation], tuple[float, float] | None, float | None, int]:
    """在对称半角内逐条追迹光线，并与完成追迹后的出射光线求观察线前向交点。

    仅当追迹状态为 completed 时，才用最后一段（出射段）的起点与方向与观察线求交；
    未完成、与观察线平行或交点在反方向时，该条光线的交点记为 None。
    质心与 RMS 半径仅统计非空交点；无任何命中时二者均为 None。

    返回 (rays, centroid, rms_radius, hit_count)。
    """
    center = normalize(center_direction)
    obs_nrm = normalize(observation_normal)
    rays: list[RayEvaluation] = []

    for angle in beam_angles(half_angle_deg, samples):
        direction = rotate_deg(center, angle)
        segments, status, reason = trace_ray(start, direction, n_start, interfaces)
        hit: tuple[float, float] | None = None
        if status == "completed":
            outgoing = segments[-1]
            hit = _intersect_line(
                outgoing.origin, outgoing.direction, observation_point, obs_nrm,
                t_min=0.0, one_sided=True,
            )
        rays.append(RayEvaluation(angle, status, reason, hit))

    hits = [r.observation_hit for r in rays if r.observation_hit is not None]
    if not hits:
        return rays, None, None, 0

    cx = sum(p[0] for p in hits) / len(hits)
    cy = sum(p[1] for p in hits) / len(hits)
    centroid = (cx, cy)
    rms = math.sqrt(sum((p[0] - cx) ** 2 + (p[1] - cy) ** 2 for p in hits) / len(hits))
    return rays, centroid, rms, len(hits)
