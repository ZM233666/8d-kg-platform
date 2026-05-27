"""Pipeline 流水线模块。

6 个 stage 按顺序执行：
  s1_parse → s2_split → s3_table → s4_extract → s5_vectorize → s6_write
"""

from app.pipeline.base import Stage, run_pipeline, stage
from app.pipeline.context import PipelineContext, StageMetric

__all__ = [
    "PipelineContext",
    "Stage",
    "StageMetric",
    "run_pipeline",
    "stage",
]
