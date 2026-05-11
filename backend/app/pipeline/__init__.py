"""Pipeline 流水线模块。

6 个 stage 按顺序执行：
  s1_parse → s2_split → s3_table → s4_extract → s5_vectorize → s6_write
"""

from app.pipeline.context import PipelineContext, StageMetric
from app.pipeline.base import Stage, stage, run_pipeline

__all__ = [
    "PipelineContext",
    "StageMetric",
    "Stage",
    "stage",
    "run_pipeline",
]