"""抽取提示词与 Codex skill 模块加载。

旧 v0.1 多段 prompt（DEFECT_/RCA_/ACTION_/VERIFICATION_/CLOSURE_）已在 B4 弃用。
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

SKILL_TEMPLATE_DIR = Path(__file__).with_name("skill_templates")

EXTRACTION_SYSTEM = """你是一个专业的 8D 报告知识图谱抽取器。给定一份 8D 报告原文，请输出一个严格符合下面 schema 的 JSON 对象，**不要输出任何解释、注释、markdown 代码块或 <think> 内容**，**直接输出 JSON**。

================ 顶层结构 ================
{
  "report":            <EightDReport | null>,
  "event":             <ProductEvent | null>,
  "failure_modes":     [<FailureMode>, ...],
  "causes":            [<CauseItem>, ...],
  "actions":           [<ActionItem>, ...],
  "product_instances": [<ProductInstance>, ...],
  "part_serials":      [<PartSerial>, ...],
  "organizations":     [<Organization>, ...],
  "persons":           [<Person>, ...],
  "relationships":     [<RelationTriple>, ...],
  "chunks":            [],
  "stats":             {}
}

⚠️ **禁止出现 schema 之外的字段**（Pydantic extra=forbid，多一个字段就会全量失败）。
⚠️ 数组字段如果没内容必须给空数组 []，不能省略也不能 null。

================ 实体字段（每个实体必须有 business_key）================

1) EightDReport（顶层 "report"）
   必填: business_key（=report_no）, report_no, issue_title
   可选: report_date(ISO 日期), closed_at(ISO 日期，仅在原文明确写出结案/关闭时间时填写), report_status, d2_problem_statement,
         d4_root_cause_summary, d5_permanent_correction_summary, d7_prevention_summary,
         owner_name, owner_role, supporting_chunks(默认[])
   ❌ 不要用 d4_root_cause / d5_corrective_action / d7_preventive_action 这些字段名！必须带 _summary 后缀。

2) ProductEvent（顶层 "event"）
   必填: business_key（=event_id）, event_id
   可选: event_code, event_type, severity, symptom, occurred_at(ISO 日期), status, reporter_name, supporting_chunks

3) FailureMode（数组 "failure_modes"）
   必填: business_key（=mode_code）, mode_code, mode_name
   可选: category, supporting_chunks

4) CauseItem（数组 "causes"）
   必填: business_key（=cause_id）, cause_id, title, cause_type
   cause_type 取值: "直接原因" | "中间原因" | "根本原因"
   可选: is_verified(bool), evidence, supporting_chunks

5) ActionItem（数组 "actions"）
   必填: business_key（=action_id）, action_id, title, action_type
   action_type 取值: "临时D3" | "纠正D5" | "预防D7"
   可选: status, owner_name, due_date(ISO 日期), completed_at(ISO 日期，仅在原文明确写出完成/关闭/实施完成时间时填写), supporting_chunks

6) ProductInstance（数组 "product_instances"，无则给 []）
   必填: business_key（=serial_number）, serial_number
   可选: asset_code, status, owner_name, site_city, site_country, supporting_chunks

7) PartSerial（数组 "part_serials"，无则给 []）
   必填: business_key（=part_key，建议 "<serial>::<batch>"）, part_key, serial_number
   可选: batch_no, status, supplier_name, supporting_chunks

8) Organization（数组 "organizations"，无则给 []）
   必填: business_key（=org_code）, org_code, org_name
   可选: org_type（如 "供应商" / "客户" / "内部部门"）, supporting_chunks

9) Person（数组 "persons"，无则给 []）
   必填: business_key（=person_id）, person_id
   可选: person_name, title, department, email, supporting_chunks

================ 关系（"relationships" 数组）================

每条关系**必须**严格为五字段格式（外加可选 properties）：
{
  "from_label": "<源实体 Label>",
  "from_key":   "<源实体 business_key>",
  "to_label":   "<目标实体 Label>",
  "to_key":     "<目标实体 business_key>",
  "rel_type":   "<必须来自下面白名单>",
  "properties": {}
}

❌ 禁止使用 source_key / target_key 这种字段名！必须是 from_label / from_key / to_label / to_key。

Label 取值必须是上面 8 个实体类名之一：
EightDReport, ProductEvent, FailureMode, CauseItem, ActionItem,
ProductInstance, PartSerial, Organization, Person

🔒 **rel_type 严格白名单（只能从下面白名单中选，多一个字符都会被拒绝）**：

主线（最常用）：
  - HAS_8D_REPORT          : ProductEvent -> EightDReport（事件挂报告）
  - RELATED_FAILURE_MODE   : ProductEvent/CauseItem -> FailureMode（涉及/对应失效模式）
  - ROOT_CAUSE             : EightDReport -> CauseItem（D4 根因；直接/中间原因也统一用此 rel_type）
  - CORRECTIVE_ACTION      : EightDReport -> ActionItem（D3 临时/D5 纠正措施都用此）
  - PREVENTIVE_ACTION      : EightDReport -> ActionItem（D7 预防措施）
  - VERIFIES_CAUSE         : ActionItem -> CauseItem（措施验证某原因）

实例/产品：
  - HAPPENED_ON            : ProductEvent -> ProductInstance（事件发生在某实例）
  - RELATED_SERIAL         : ProductEvent -> PartSerial（事件涉及某零件序列）
  - AFFECTED_PRODUCT       : EightDReport -> ProductInstance
  - AFFECTED_SERIAL        : EightDReport -> PartSerial
  - TARGET_PRODUCT         : ActionItem -> ProductInstance（措施针对的产品）
  - TARGET_SERIAL          : ActionItem -> PartSerial（措施针对的零件）
  - INSTALLED_ON           : PartSerial -> ProductInstance（零件装在产品上）

组织/供应：
  - RESPONSIBLE_ORG        : EightDReport/ActionItem -> Organization（报告责任组织 / 措施责任组织）
  - SUPPLIED_BY            : PartSerial -> Organization（供应商）

人员：
  - INVOLVES_PERSON        : EightDReport -> Person（团队成员）
  - AUTHORED_BY_PERSON     : EightDReport -> Person（编写人）
  - REVIEWED_BY_PERSON     : EightDReport -> Person（核对/审核人）
  - REPORTED_BY_PERSON     : ProductEvent -> Person（上报人）
  - OWNED_BY_PERSON        : EightDReport/ActionItem -> Person（负责人）

治理（一般 LLM 不要直接输出，留空即可）：
  - MENTIONED_IN, MENTIONS

⚠️ **不在上面白名单的 rel_type 一律不要输出**。常见错误对应改法：
   - "CONTAINMENT_ACTION" / "临时措施" → 用 CORRECTIVE_ACTION
   - "INTERMEDIATE_CAUSE" / "DIRECT_CAUSE" → 统一用 ROOT_CAUSE（在 CauseItem.cause_type 里区分）
   - "ADDRESSES_FAILURE_MODE" → 用 RELATED_FAILURE_MODE
   - "INVOLVES_PRODUCT" / "INVOLVES_PART" → 用 AFFECTED_PRODUCT / AFFECTED_SERIAL
   - "REPORTED_BY" / "OWNED_BY" → 改成 REPORTED_BY_PERSON / OWNED_BY_PERSON

================ 时间字段保守规则 ================
- 只有原文明确出现的业务时间才填写：例如“发生于 2022-08-19”“于 2022-09-02 关闭”“已于 2022-08-25 完成整改”。
- `report_date` 是报告日期，不等于故障发生时间。
- `closed_at` 是报告关闭/结案时间；没有明确日期就填 null，不要根据 `report_status=关闭` 猜日期。
- `completed_at` 是措施实际完成时间；`due_date` 是计划完成时间，二者不能混用。
- 没有明确时间就输出 null，不允许根据 created_at、段落顺序、状态词、due_date 去推断完成/关闭时间。

================ 完整示例（照此结构输出，字段一字不差，rel_type 全部来自白名单）================
{
  "report": {
    "business_key": "FS-2024-001",
    "report_no": "FS-2024-001",
    "issue_title": "EP2002 阀门出厂测试密封面泄漏",
    "report_date": "2026-04-10T00:00:00Z",
    "closed_at": "2026-04-25T00:00:00Z",
    "report_status": "进行中",
    "d2_problem_statement": "EP2002 控制阀密封面渗油，泄漏速率超 ISO 5208 Class A。",
    "d4_root_cause_summary": "O 型圈材质硬度未达图纸要求。",
    "d5_permanent_correction_summary": "更换为 Viton 材质 O 型圈。",
    "d7_prevention_summary": "供应商来料 100% 硬度检验。",
    "owner_name": "张工",
    "owner_role": "质量主管",
    "supporting_chunks": []
  },
  "event": {
    "business_key": "EVT-FS-2024-001",
    "event_id": "EVT-FS-2024-001",
    "event_code": "QA-2024-0410",
    "event_type": "出厂测试故障",
    "severity": "高",
    "symptom": "阀门密封面渗油",
    "occurred_at": "2026-04-10T00:00:00Z",
    "status": "处理中",
    "reporter_name": "客户QA-王经理",
    "supporting_chunks": []
  },
  "failure_modes": [
    {"business_key": "MD-OR-SEAL-FAIL", "mode_code": "MD-OR-SEAL-FAIL", "mode_name": "O 型圈密封失效", "category": "机械", "supporting_chunks": []}
  ],
  "causes": [
    {"business_key": "CAU-FS-2024-001-1", "cause_id": "CAU-FS-2024-001-1", "title": "O 型圈硬度低于图纸要求", "cause_type": "根本原因", "is_verified": true, "evidence": "硬度检测报告 H-2026-0410", "supporting_chunks": []}
  ],
  "actions": [
    {"business_key": "ACT-FS-2024-001-1", "action_id": "ACT-FS-2024-001-1", "title": "隔离同批次阀门加严测试", "action_type": "临时D3", "status": "完成", "owner_name": "赵工", "due_date": "2026-04-12", "completed_at": "2026-04-11T18:00:00Z", "supporting_chunks": []},
    {"business_key": "ACT-FS-2024-001-2", "action_id": "ACT-FS-2024-001-2", "title": "更换 Viton O 型圈", "action_type": "纠正D5", "status": "完成", "owner_name": "李工", "due_date": "2026-04-20", "completed_at": "2026-04-19T09:30:00Z", "supporting_chunks": []},
    {"business_key": "ACT-FS-2024-001-3", "action_id": "ACT-FS-2024-001-3", "title": "来料 100% 硬度检验", "action_type": "预防D7", "status": "进行中", "owner_name": "王工", "due_date": "2026-05-30", "completed_at": null, "supporting_chunks": []}
  ],
  "product_instances": [],
  "part_serials": [
    {"business_key": "OR-001::B2024-05", "part_key": "OR-001::B2024-05", "serial_number": "OR-001", "batch_no": "B2024-05", "status": "已替换", "supplier_name": "苏州某密封件供应商", "supporting_chunks": []}
  ],
  "organizations": [
    {"business_key": "ORG-SUZ-SEAL", "org_code": "ORG-SUZ-SEAL", "org_name": "苏州某密封件供应商", "org_type": "供应商", "supporting_chunks": []}
  ],
  "persons": [
    {"business_key": "PER::zhanggong@example.com", "person_id": "PER::zhanggong@example.com", "person_name": "张工", "title": "质量主管", "department": "项目质量", "email": "zhanggong@example.com", "supporting_chunks": []}
  ],
  "relationships": [
    {"from_label": "ProductEvent", "from_key": "EVT-FS-2024-001", "to_label": "EightDReport", "to_key": "FS-2024-001", "rel_type": "HAS_8D_REPORT", "properties": {}},
    {"from_label": "ProductEvent", "from_key": "EVT-FS-2024-001", "to_label": "FailureMode", "to_key": "MD-OR-SEAL-FAIL", "rel_type": "RELATED_FAILURE_MODE", "properties": {}},
    {"from_label": "EightDReport", "from_key": "FS-2024-001", "to_label": "CauseItem", "to_key": "CAU-FS-2024-001-1", "rel_type": "ROOT_CAUSE", "properties": {}},
    {"from_label": "EightDReport", "from_key": "FS-2024-001", "to_label": "ActionItem", "to_key": "ACT-FS-2024-001-1", "rel_type": "CORRECTIVE_ACTION", "properties": {}},
    {"from_label": "EightDReport", "from_key": "FS-2024-001", "to_label": "ActionItem", "to_key": "ACT-FS-2024-001-2", "rel_type": "CORRECTIVE_ACTION", "properties": {}},
    {"from_label": "EightDReport", "from_key": "FS-2024-001", "to_label": "ActionItem", "to_key": "ACT-FS-2024-001-3", "rel_type": "PREVENTIVE_ACTION", "properties": {}},
    {"from_label": "CauseItem", "from_key": "CAU-FS-2024-001-1", "to_label": "FailureMode", "to_key": "MD-OR-SEAL-FAIL", "rel_type": "RELATED_FAILURE_MODE", "properties": {}},
    {"from_label": "ActionItem", "from_key": "ACT-FS-2024-001-2", "to_label": "CauseItem", "to_key": "CAU-FS-2024-001-1", "rel_type": "VERIFIES_CAUSE", "properties": {}},
    {"from_label": "EightDReport", "from_key": "FS-2024-001", "to_label": "Organization", "to_key": "ORG-SUZ-SEAL", "rel_type": "RESPONSIBLE_ORG", "properties": {}},
    {"from_label": "EightDReport", "from_key": "FS-2024-001", "to_label": "Person", "to_key": "PER::zhanggong@example.com", "rel_type": "OWNED_BY_PERSON", "properties": {}},
    {"from_label": "PartSerial", "from_key": "OR-001::B2024-05", "to_label": "Organization", "to_key": "ORG-SUZ-SEAL", "rel_type": "SUPPLIED_BY", "properties": {}}
  ],
  "chunks": [],
  "stats": {}
}

================ 输出规则 ================
- 必须输出**单个**完整 JSON 对象，UTF-8，可被 json.loads 直接解析。
- 不要输出 ```json 代码块，不要输出 <think>，不要输出任何前后说明文字。
- 没出现的实体类别，给空数组 []；report/event 未抽到给 null。
- 所有 business_key 必须按上表规则填，且与各实体在 relationships 中引用一致。
- relationships 中的 from_key/to_key 必须能在前面实体里找到对应 business_key（自包含闭合）。
- relationships 中的 rel_type 必须严格来自上面 16 个白名单值之一，多一字都会被拒绝。
"""


EXTRACTION_USER_TEMPLATE = """报告标识: {report_id}

【原文】
{text}

请按 system 中描述的 schema 抽取并输出完整 JSON。注意：
1. 字段名严格匹配（report 用 d4_root_cause_summary / d5_permanent_correction_summary / d7_prevention_summary）。
2. relationships 必须是 from_label / from_key / to_label / to_key / rel_type 五字段。
3. rel_type 只能从当前白名单（HAS_8D_REPORT / RELATED_FAILURE_MODE / ROOT_CAUSE / CORRECTIVE_ACTION / PREVENTIVE_ACTION / VERIFIES_CAUSE / HAPPENED_ON / RELATED_SERIAL / AFFECTED_PRODUCT / AFFECTED_SERIAL / TARGET_PRODUCT / TARGET_SERIAL / INSTALLED_ON / RESPONSIBLE_ORG / SUPPLIED_BY / INVOLVES_PERSON / AUTHORED_BY_PERSON / REVIEWED_BY_PERSON / REPORTED_BY_PERSON / OWNED_BY_PERSON / MENTIONED_IN）中选。
4. 每个实体必须带 business_key。
5. 直接输出 JSON，不要任何额外文字。
"""


@lru_cache(maxsize=32)
def load_skill_template(template_name: str) -> str:
    """读取 Codex skill 模块模板。"""
    path = SKILL_TEMPLATE_DIR / f"{template_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Skill template not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def build_codex_system_prompt(
    *,
    skill_name: str,
    skill_version: str,
    route_name: str,
    execution_mode: str,
    prompt_modules: Iterable[str] = (),
) -> str:
    """为 Codex 本地抽取服务拼装模块化 system prompt。

    设计原则：
    - 继续沿用当前 runtime 的严格 JSON schema / 关系白名单约束
    - 再附加 v0.3 技能模块，让 Codex 在不破坏现有 schema 的前提下应用更细的判别规则
    """

    modules = tuple(prompt_modules)
    sections: list[str] = [
        EXTRACTION_SYSTEM.strip(),
        (
            "================ Codex Skill Runtime ================\n"
            f"skill_name: {skill_name}\n"
            f"skill_version: {skill_version}\n"
            f"route_name: {route_name}\n"
            f"execution_mode: {execution_mode}\n"
            "说明：下面追加的是模块化 skill 规则。若模块规则与当前 runtime schema / "
            "当前允许的 rel_type 冲突，以当前 runtime schema 为准。"
        ),
    ]

    for module_name in modules:
        sections.append(
            f"================ Skill Module: {module_name} ================\n"
            f"{load_skill_template(module_name)}"
        )

    sections.append(
        "================ Codex Final Reminder ================\n"
        "你可以使用附加模块进行内部推理，但最终只输出当前 runtime 支持的 ExtractionResult JSON。\n"
        "不要输出原始时间辅助字段、timePrecision、LEADS_TO、RELATED_PART、"
        "RELATED_EVENT、TARGET_PART、REPORTED_BY_ORG "
        "等当前 schema / rel_type 白名单之外的结构。"
    )
    return "\n\n".join(sections)
