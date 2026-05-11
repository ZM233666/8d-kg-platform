"""s2 Splitter：将 raw_text 按章节+段落切分为 list[Chunk]。"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import structlog
import tiktoken
from tiktoken import Encoding

from app.lexicon import load_lexicon
from app.pipeline.base import stage
from app.pipeline.context import PipelineContext
from app.schemas.entity import Chunk

logger = structlog.get_logger(__name__)

# Section marker pattern
SEC_RE = re.compile(r"\[SEC:([^\]]+)\]")
# Sentence splitter
SPLIT_RE = re.compile(r"[。；；]")


def _classify_role(section_path: list[str], lex: dict) -> str:
    """根据章节路径关键词匹配 ChunkRole。"""
    mapping = lex.get("chapter_role_mapping", {})
    routing = lex.get("chapter_routing", {})
    full = " ".join(section_path)

    for route_key, role in mapping.items():
        keywords = routing.get(route_key, [])
        if any(kw in full for kw in keywords):
            return role
    return "unknown"


def _encode_sentences(encoder: Encoding, text: str) -> list[str]:
    """把长段落按句号/分号切成多个子段落。"""
    if not text.strip():
        return []
    parts = SPLIT_RE.split(text)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if buf:
            combined = buf + "。" + part
        else:
            combined = part
        tokens = len(encoder.encode(combined))
        if tokens > 800 and buf:
            # 当前 buf 封chunk，新 part 开始
            chunks.append(buf.strip())
            buf = part
        else:
            buf = combined
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


def _split_chunk(encoder: Encoding, text: str) -> list[str]:
    """按 token 限制切分段落，返回子段落列表。"""
    tokens = len(encoder.encode(text))
    if tokens <= 800:
        return [text] if text.strip() else []

    sentences = _encode_sentences(encoder, text)
    results: list[str] = []
    buf = ""

    for sent in sentences:
        if not sent.strip():
            continue
        if buf:
            trial = buf + "。" + sent
        else:
            trial = sent
        if len(encoder.encode(trial)) > 800 and buf:
            results.append(buf.strip())
            buf = sent
        else:
            buf = trial

    if buf.strip():
        results.append(buf.strip())

    return results


def _post_merge_small_chunks(chunks: list[str]) -> list[str]:
    """合并 token<50 的段落与下一个同章节段落。"""
    encoder = tiktoken.get_encoding("cl100k_base")
    merged: list[str] = []
    i = 0
    while i < len(chunks):
        cur = chunks[i].strip()
        if not cur:
            i += 1
            continue
        tok = len(encoder.encode(cur))
        if tok < 50 and i + 1 < len(chunks):
            # 与下一个合并
            next_tok = len(encoder.encode(chunks[i + 1]))
            if next_tok < 50:
                combined = cur + " " + chunks[i + 1]
                merged.append(combined)
                i += 2
                continue
        merged.append(cur)
        i += 1
    return merged


def _build_chunk(
    report_id: str,
    section_path: list[str],
    para_idx: int,
    text: str,
    lex: dict,
    encoder: Encoding,
) -> Chunk:
    """构建单个 Chunk。"""
    role = _classify_role(section_path, lex)
    token_count = len(encoder.encode(text))
    chunk_id = f"{report_id}#{'/'.join(section_path)}#{para_idx}"
    now = datetime.now(timezone.utc)

    return Chunk(
        chunk_id=chunk_id,
        report_id=report_id,
        section_path=section_path,
        para_idx=para_idx,
        chunk_role=role,
        text=text,
        token_count=token_count,
        is_table=False,
        is_placeholder=False,
        has_referenced_image=False,
        created_at=now,
    )


@stage("s2_split")
async def run(ctx: PipelineContext) -> PipelineContext:
    """把 ctx.raw_text 按章节+段落切分为 ctx.chunks。"""
    if not ctx.raw_text:
        logger.warning("s2_split.skip_empty_text")
        return ctx

    lex = load_lexicon()
    encoder = tiktoken.get_encoding("cl100k_base")
    report_id = ctx.report_id_hint or "UNKNOWN"

    sections_raw = SEC_RE.split(ctx.raw_text)
    # SEC_RE.split 返回 [pre, path1, content1, path2, content2, ...]
    chunks_out: list[Chunk] = []
    para_idx = 0
    i = 1
    while i < len(sections_raw):
        path_str = sections_raw[i].strip()
        content = sections_raw[i + 1] if (i + 1) < len(sections_raw) else ""
        i += 2

        section_path = path_str.split("/") if path_str else []
        # 按空行（\n\n）切段落，strip 掉空部分
        paragraphs = [p.strip() for p in content.split("\n\n")]
        for para in paragraphs:
            if not para:
                continue
            sub_texts = _split_chunk(encoder, para)
            sub_texts = _post_merge_small_chunks(sub_texts)
            for st in sub_texts:
                st = st.strip()
                if not st:
                    continue
                chunk = _build_chunk(report_id, section_path, para_idx, st, lex, encoder)
                chunks_out.append(chunk)
                para_idx += 1

    ctx.chunks = chunks_out

    from collections import Counter

    role_dist = Counter(c.chunk_role for c in chunks_out)
    logger.info(
        "s2_split.done",
        total=len(chunks_out),
        by_role=dict(role_dist),
    )
    return ctx