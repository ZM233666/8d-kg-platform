"""s5 Vectorizer (noop v0.1)。

v0.1 不做实际向量化，仅占位以保留 6 阶段流水线契约。
v0.2 接入 bge-m3 时实现 chunk-level embedding 写入 pgvector。
"""

from app.pipeline.base import stage
from app.pipeline.context import PipelineContext


@stage("s5_vectorize")
async def run(ctx: PipelineContext) -> PipelineContext:
    # v0.1: noop。chunk.embedding 已在 schema 层定义为 list[float] | None，默认 None。
    # 这里不动 ctx.chunks，也不做任何 IO。
    return ctx
