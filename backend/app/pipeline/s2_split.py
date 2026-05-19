"""s2 Splitter: 按章节路径把正文切成可路由的 Chunk。"""

from __future__ import annotations

import re
from datetime import UTC, datetime

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
SPLIT_RE = re.compile(r"[。;\uFF1B]")
BLANK_LINE_RE = re.compile(r"\n\s*\n+")
TOC_RE = re.compile(r"^\s*\d+\s*.+\d+\s*$")
HEADING_PREFIX_RE = re.compile(r"^\s*(?:第?\d+[章节部分篇项节]?|[一二三四五六七八九十]+)[.、]?\s*")
HEADING_SUFFIX_RE = re.compile(r"\s*\d+\s*$")
HEADING_PUNCT_RE = re.compile(r"[。\u0021\uFF01\u003F\uFF1F\u003A\uFF1A\u002C\uFF0C\u003B\uFF1B]")
SUBSECTION_HINTS = (
    "结构",
    "功能",
    "分析",
    "检测",
    "试验",
    "实验",
    "结论",
    "确认",
    "检查",
    "调查",
    "原因",
    "会议",
    "记录",
    "简介",
    "描述",
    "措施",
    "验证",
    "团队",
)


def _classify_role(section_path: list[str], lex: dict) -> str:
    """根据章节路径关键词匹配 ChunkRole。"""
    if not section_path or section_path == ["unknown"]:
        return "unknown"

    overrides = lex.get("sub_section_role_overrides", {})
    sorted_overrides = sorted(overrides.items(), key=lambda item: len(item[0]), reverse=True)
    for segment in reversed(section_path):
        for keyword, role in sorted_overrides:
            if keyword in segment:
                return role

    mapping = lex.get("chapter_role_mapping", {})
    routing = lex.get("chapter_routing", {})
    full = " ".join(section_path)

    for route_key, role in mapping.items():
        keywords = routing.get(route_key, [])
        if any(kw in full for kw in keywords):
            return role
    return "unknown"


def _encode_sentences(encoder: Encoding, text: str) -> list[str]:
    """把长段落按句号或分号切成多个子段落。"""
    if not text.strip():
        return []
    parts = SPLIT_RE.split(text)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        combined = buf + "。" + part if buf else part
        tokens = len(encoder.encode(combined))
        if tokens > 800 and buf:
            # 当前 buf 先封 chunk, 新 part 重新开始累积
            chunks.append(buf.strip())
            buf = part
        else:
            buf = combined
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


def _split_chunk(encoder: Encoding, text: str) -> list[str]:
    """按 token 限制切分段落, 返回子段落列表。"""
    tokens = len(encoder.encode(text))
    if tokens <= 800:
        return [text] if text.strip() else []

    sentences = _encode_sentences(encoder, text)
    results: list[str] = []
    buf = ""

    for sent in sentences:
        if not sent.strip():
            continue
        trial = buf + "。" + sent if buf else sent
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
            # 与下一个小段合并, 降低碎片化
            next_tok = len(encoder.encode(chunks[i + 1]))
            if next_tok < 50:
                combined = cur + " " + chunks[i + 1]
                merged.append(combined)
                i += 2
                continue
        merged.append(cur)
        i += 1
    return merged


def _normalize_heading(text: str) -> str:
    """规整标题文本, 去掉编号和目录页码尾巴。"""
    normalized = text.strip().lstrip("#").strip()
    normalized = HEADING_PREFIX_RE.sub("", normalized)
    normalized = HEADING_SUFFIX_RE.sub("", normalized)
    return normalized.strip(" .、:-")


def _flatten_routing_keywords(lex: dict) -> list[str]:
    """收集词典中的章节路由关键词。"""
    routing = lex.get("chapter_routing", {})
    keywords = {
        keyword.strip() for values in routing.values() for keyword in values if keyword.strip()
    }
    return sorted(keywords, key=len, reverse=True)


def _is_explicit_heading(paragraph: str, keywords: list[str]) -> str | None:
    """识别显式顶层章节标题。"""
    if not paragraph.strip() or TOC_RE.fullmatch(paragraph.strip()):
        return None

    normalized = _normalize_heading(paragraph)
    if not normalized:
        return None
    if len(normalized) > 30:
        return None
    if HEADING_PUNCT_RE.search(normalized):
        return None

    for keyword in keywords:
        if keyword in normalized:
            return normalized
    return None


def _is_subsection_heading(paragraph: str) -> str | None:
    """识别纯文本中的子章节标题。"""
    if TOC_RE.fullmatch(paragraph.strip()):
        return None

    normalized = _normalize_heading(paragraph)
    if not normalized or len(normalized) > 20:
        return None
    if HEADING_PUNCT_RE.search(normalized):
        return None
    if not re.search(r"[\u4e00-\u9fffA-Za-z]", normalized):
        return None
    if re.fullmatch(r"[A-Za-z0-9_-]+", normalized):
        return None
    if any(hint in normalized for hint in SUBSECTION_HINTS):
        return normalized
    return None


def _parse_sections(raw_text: str) -> list[tuple[list[str], str]]:
    """解析 raw_text 中的 [SEC:...] 标记, 返回章节文本块。"""
    sections: list[tuple[list[str], str]] = []
    current_path: list[str] | None = None
    buffer: list[str] = []

    def flush_buffer() -> None:
        nonlocal buffer
        text = "\n".join(buffer).strip()
        if not text:
            buffer = []
            return

        section_path = current_path.copy() if current_path else ["unknown"]
        if sections and sections[-1][0] == section_path:
            prev_path, prev_text = sections[-1]
            sections[-1] = (prev_path, prev_text + "\n\n" + text)
        else:
            sections.append((section_path, text))
        buffer = []

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        marker = SEC_RE.fullmatch(line)
        if marker:
            flush_buffer()
            current_path = [part.strip() for part in marker.group(1).split("/") if part.strip()]
            continue
        buffer.append(raw_line)

    flush_buffer()
    return sections


def _parse_plaintext_sections(raw_text: str, lex: dict) -> list[tuple[list[str], str]]:
    """在没有 [SEC] 标记时, 尝试按纯文本标题切分章节。"""
    paragraphs = [
        paragraph.strip() for paragraph in BLANK_LINE_RE.split(raw_text) if paragraph.strip()
    ]
    if not paragraphs:
        return []

    routing_keywords = _flatten_routing_keywords(lex)
    sections: list[tuple[list[str], str]] = []
    current_path: list[str] | None = None
    buffer: list[str] = []

    def flush_buffer() -> None:
        nonlocal buffer
        text = "\n\n".join(buffer).strip()
        if not text:
            buffer = []
            return

        section_path = current_path.copy() if current_path else ["unknown"]
        if sections and sections[-1][0] == section_path:
            prev_path, prev_text = sections[-1]
            sections[-1] = (prev_path, prev_text + "\n\n" + text)
        else:
            sections.append((section_path, text))
        buffer = []

    for paragraph in paragraphs:
        explicit_heading = _is_explicit_heading(paragraph, routing_keywords)
        if explicit_heading:
            flush_buffer()
            current_path = [explicit_heading]
            continue

        subsection_heading = _is_subsection_heading(paragraph)
        if subsection_heading and current_path:
            flush_buffer()
            current_path = [current_path[0], subsection_heading]
            continue

        buffer.append(paragraph)

    flush_buffer()
    return sections


def _build_chunks_for_section(
    report_id: str,
    section_path: list[str],
    start_para_idx: int,
    text: str,
    lex: dict,
    encoder: Encoding,
) -> list[Chunk]:
    """把同一 section 的正文切成一个或多个 chunk。"""
    sub_chunks = _post_merge_small_chunks(_split_chunk(encoder, text))
    chunks: list[Chunk] = []
    para_idx = start_para_idx
    for sub_text in sub_chunks:
        if not sub_text.strip():
            continue
        chunks.append(_build_chunk(report_id, section_path, para_idx, sub_text, lex, encoder))
        para_idx += 1
    return chunks


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
    now = datetime.now(UTC)

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
    """按章节标记切分正文, 构造带 section_path 的 chunks。"""
    if not ctx.raw_text:
        logger.warning("s2_split.skip_empty_text")
        return ctx

    lex = load_lexicon()
    encoder = tiktoken.get_encoding("cl100k_base")
    report_id = ctx.report_id_hint or "UNKNOWN"

    raw_text = ctx.raw_text.strip()
    if not raw_text:
        logger.warning("s2_split.skip_empty_text")
        return ctx

    has_sec_markers = bool(SEC_RE.search(raw_text))
    if has_sec_markers:
        section_blocks = _parse_sections(raw_text)
    else:
        section_blocks = _parse_plaintext_sections(raw_text, lex)

    if not section_blocks:
        fallback_parts = _post_merge_small_chunks(_split_chunk(encoder, raw_text))
        section_blocks = [(["unknown"], "\n\n".join(fallback_parts))]

    chunks_out: list[Chunk] = []
    para_idx = 0
    for section_path, section_text in section_blocks:
        section_chunks = _build_chunks_for_section(
            report_id=report_id,
            section_path=section_path,
            start_para_idx=para_idx,
            text=section_text,
            lex=lex,
            encoder=encoder,
        )
        chunks_out.extend(section_chunks)
        para_idx += len(section_chunks)

    ctx.chunks = chunks_out
    by_role: dict[str, int] = {}
    for chunk in chunks_out:
        role = chunk.chunk_role or "unknown"
        by_role[role] = by_role.get(role, 0) + 1

    logger.info(
        "s2_split.done",
        total=len(chunks_out),
        by_role=by_role,
    )
    return ctx
