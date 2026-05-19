# Codex Regression Fixtures

这个目录用于存放 **Codex 抽取回归基线** 的 fixture。

目标不是保存“完美答案”，而是沉淀一批能反复验证高风险抽取场景的样本。

## 目录定位

- `test_codex_regression.py` 会消费这里的场景文件
- 每个 JSON 文件描述一个“脱敏后的 8D 报告风格场景”
- 当前以 synthetic / 真实风格脱敏样本为主
- 后续拿到真实 8D 报告后，优先把它们加工成这里的 fixture 再纳入回归

## 文件结构

每个 fixture 必须至少包含：

```json
{
  "name": "unique_case_name",
  "context": {
    "minio_key": "documents/fs-reg-xxx.docx",
    "report_id_hint": "FS-REG-XXX",
    "chunks": [
      {
        "chunk_id": "FS-REG-XXX#D2#1",
        "report_id": "FS-REG-XXX",
        "section_path": ["D2", "问题描述"],
        "para_idx": 1,
        "chunk_role": "evidence",
        "text": "脱敏后的报告文本片段",
        "token_count": 20
      }
    ]
  },
  "llm_result": {
    "report": {
      "business_key": "FS-REG-XXX",
      "report_no": "FS-REG-XXX",
      "issue_title": "..."
    },
    "relationships": []
  }
}
```

可选字段：

- `source_kind`: 例如 `synthetic` / `real_derived`
- `source_document`: 若该 fixture 由真实文档脱敏改写而来，可记录原始来源路径
- `deidentification`: 说明做了哪些脱敏处理

## 编写原则

1. 优先保留“真实错误模式”，而不是追求场景过于整洁。
2. 所有样本都必须脱敏：
   - 真名替换为化名或角色
   - 序列号、批次号、客户号做改写
   - 公司名如需保留类型特征，可改成“某供应商”“某客户”或内部约定代号
3. 每个 fixture 只聚焦 1 到 2 个高风险点，不要把所有问题混在一个样本里。
4. `llm_result` 代表“模拟 LLM / Codex 可能产出的结构化结果”，可以故意保留一些脏边或保守留空，用于验证 runtime 纠偏。
5. 若来源于 `docs_for_test/` 下的真实报告，建议保留 `source_document`，并在 `deidentification` 中说明如何去掉项目名、客户名、序列号、人名等敏感信息。

## 当前建议覆盖的风险类型

- `reporter_name` 中人名 / 公司 / 部门混淆
- D2 / D4 / D5 同句或同文共存
- 模糊时间表达
- 明确业务时间表达（发生时间 / 措施完成时间 / 报告关闭时间）
- symptom-only，不应创造 `FailureMode`
- 多组织并存，不应把客户误挂成 `RESPONSIBLE_ORG`
- 关系方向错误，必须被 runtime 过滤

## 引入真实样本的建议流程

1. 先对真实 8D 报告做脱敏和切片
2. 把关键段落整理成 `context.chunks`
3. 写出“预期的 LLM 风格输出”到 `llm_result`
4. 在 `test_codex_regression.py` 中补对应断言
5. 运行：

```bash
.venv/bin/pytest backend/tests/test_codex_regression.py
```

## 注意

当前 runtime 仍然是 **v0.3 目标层之下的兼容子集**。因此 fixture 中即使反映了 `Person`、raw 时间字段或更细关系语义，最终也不要直接把这些结构塞进当前 `llm_result`，除非对应 schema / writer / rel_type 已经升级。
