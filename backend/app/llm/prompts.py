"""LLM Prompt 模板（v0.1 中文 8D 报告抽取）。

每个 prompt 含：
- SYSTEM：定位 + 输出 schema 描述
- USER 模板：填入 chunk 文本 + 上下文

v0.1 mock 不会真消费 prompt，但保持完整以便切换真 LLM 时直接用。
"""

from __future__ import annotations

from typing import Final

_BASE_SYSTEM = """你是一位精通 8D 报告分析的工业质量专家。
你将收到 8D 报告的局部章节文本，请严格按照给定 JSON Schema 抽取结构化信息。

通用规则：
1. 输出必须是合法 JSON，所有字段名英文小写下划线
2. supporting_chunks 必须填入输入 chunks 的 chunk_id 列表
3. 时间字段用 ISO8601 字符串 (YYYY-MM-DDTHH:MM:SS+00:00)
4. 不确定的字段填 null，不要编造
5. confidence 在 0~1，根据证据强度判定
"""

DEFECT_SYSTEM: Final = _BASE_SYSTEM + """
本次抽取目标：DefectOccurrence（故障发生）列表。
关键字段：defect_description, defect_location, serial_no, operating_mileage_km, detection_context, is_first_occurrence, occurred_at
"""

DEFECT_USER_TEMPLATE: Final = """报告 ID: {report_id}
章节路径: {chapter_path}

【原文】
{text}

请输出 list[DefectOccurrence] JSON。
"""

RCA_SYSTEM: Final = _BASE_SYSTEM + """
本次抽取目标：RootCauseAnalysisOutput（根因分析全套）。
需同时抽取：
- inspection_events: 检测事件
- experiments: 验证型实验
- measurements: 测量值
- findings: 发现/结论（注意 polarity: positive/negative/neutral）
- root_causes: 扁平根因列表（v0.1 不建 LEADS_TO 关系）
- causal_narrative: 完整因果链文本（如 "X→Y→Z"）

关键规则：
- 看到 "未发现 / 未见 / 无 X" 等否定表达，对应 Finding.polarity=negative
- Finding.evidence_strength: direct=断口直接观察 / indirect=间接推断 / ruled_out=否定证据
"""

RCA_USER_TEMPLATE: Final = """报告 ID: {report_id}
章节路径: {chapter_path}

【原文】
{text}

请输出 RootCauseAnalysisOutput JSON。
"""

ACTION_SYSTEM: Final = _BASE_SYSTEM + """
本次抽取目标：ActionEvent 列表，action_type={action_type}。
- containment: 临时措施 (D3)
- corrective: 永久纠正措施 (D5/D6)
- preventive: 预防措施 (D7)

关键字段：action_description, responsible_party (KB/Supplier/Customer/Operator/Other),
responsible_person, deadline, status, verification_result
"""

ACTION_USER_TEMPLATE: Final = """报告 ID: {report_id}
章节路径: {chapter_path}
预期 action_type: {action_type}

【原文】
{text}

请输出 list[ActionEvent] JSON，所有 action_type 字段必须为 {action_type}。
"""

VERIFICATION_SYSTEM: Final = _BASE_SYSTEM + """
本次抽取目标：VerificationEvent 列表（D8 验证）。
关键字段：verification_method, verification_result (passed/failed/inconclusive/tbd), verified_action_id
"""

VERIFICATION_USER_TEMPLATE: Final = """报告 ID: {report_id}
章节路径: {chapter_path}

【原文】
{text}

请输出 list[VerificationEvent] JSON。
"""

CLOSURE_SYSTEM: Final = _BASE_SYSTEM + """
本次抽取目标：ClosureEvent（最终结案事件，至多 1 条）。
关键字段：closure_decision, final_meeting_date, attendees
"""

CLOSURE_USER_TEMPLATE: Final = """报告 ID: {report_id}
章节路径: {chapter_path}

【原文】
{text}

请输出 ClosureEvent JSON。若本章节未发现结案信息，返回 null。
"""