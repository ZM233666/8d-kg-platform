# 8d-d2-event-extraction

这个模块专门约束 D2 问题描述 / 故障现象 / 客诉 / 异常 / 试验事件抽取，但**最终输出必须兼容当前 runtime**。

## 当前 runtime 下 D2 可直接落的结构

可直接输出：

- `ProductEvent`
- `FailureMode`
- 条件性 `ProductInstance`
- 条件性 `PartSerial`
- 条件性 `Organization`
- 条件性 `Person`
- `ProductEvent -> HAS_8D_REPORT -> EightDReport`
- `ProductEvent -> HAPPENED_ON -> ProductInstance`
- `ProductEvent -> RELATED_SERIAL -> PartSerial`
- `ProductEvent -> RELATED_FAILURE_MODE -> FailureMode`
- 条件性 `ProductEvent -> REPORTED_BY_PERSON -> Person`

当前 runtime **暂不直接支持**：

- `REPORTED_BY_ORG`
- `RELATED_PART`
- `RESPONSIBLE_ORG`
- raw 时间辅助字段
- `timePrecision`

因此这些信息如果重要，应保留在：

- `ProductEvent.reporter_name`
- `ProductEvent.symptom`
- `EightDReport.d2_problem_statement`

## ProductEvent 创建规则

只有当文本满足以下至少一项时，才创建 `ProductEvent`：

- 明确描述了一次故障 / 异常 / 客诉 / 试验事件
- 文本能稳定回答“这份 8D 报告在处理哪件事”
- 出现了清晰的现象、对象或发生事实

以下情况不要创建 `ProductEvent`：

- 纯根因描述
- 纯措施描述
- 只有背景信息，没有事件发生
- 只有检测数值，没有事件语义

## event_type 默认策略

当前 runtime 先收敛到四类：

- `故障`
- `异常`
- `客诉`
- `试验`

推荐映射：

- 现场失效、泄漏、裂纹、功能异常 -> `故障`
- 生产或测试偏差 -> `异常`
- 客户投诉 / 索赔 / 反馈 -> `客诉`
- 台架、验证、出厂、实验失败 -> `试验`

如果仍不确定，选择最保守且最贴近原文的类型，不要强行造新类别。

## symptom 写法

`ProductEvent.symptom` 应尽量：

- 只保留客观现象
- 尽量简短
- 不混入根因和措施

例如：

- `阀门密封面渗油`
- `出厂试验时压力波动超差`
- `装机三个月后弹簧裂纹`

## FailureMode 规则

只有在文本明确出现标准化失效模式时，才输出 `FailureMode`。

适合来源：

- 章节标题
- 客诉或故障清单中的标准失效名称
- 检测或结论中的明确失效术语

如果只是现象，还没形成稳定失效模式：

- 优先保留在 `symptom`
- 不强行创建 `FailureMode`

## ProductInstance / PartSerial 规则

### `ProductInstance`

只有当文本明确给出以下至少一项，且能稳定闭合到当前实体时，才创建：

- 产品序列号
- 资产编码
- 明确的单台设备标识

更偏 `ProductInstance` 的典型线索：

- 车号 / 列车号 / 资产号 / 设备号，例如 `T030`
- 同时出现客户、线路、地点、投运等整机级上下文
- 语义是在说“哪台车 / 哪台设备发生了这次事件”

### `PartSerial`

只有当文本明确给出以下至少一项，且能稳定闭合到当前实体时，才创建：

- 零件序列号
- 批次号
- 明确的零件实例标识

更偏 `PartSerial` 的典型线索：

- 多个相似编码被并列列出
- 出现在拆解、检测、故障件、返工件、库存件、批次件语境里
- 语义是在说“哪些零件样本 / 故障件被检查或更换”

不要因为文本提到“某类阀门”“该批次件”就强行创建实例级对象。

如果 `ProductInstance` 和 `PartSerial` 无法同时满足高置信判别：

- 默认优先保守到 `PartSerial`
- 不要把疑似零件样本编号误建成 `ProductInstance`

## 主线关系规则

### `HAS_8D_REPORT`

只要当前上下文中的 `ProductEvent` 明确是该 8D 报告处理的核心事件，就允许输出：

- `ProductEvent -> HAS_8D_REPORT -> EightDReport`

### `HAPPENED_ON`

只有当文本明确指向唯一 `ProductInstance` 时，才输出：

- `ProductEvent -> HAPPENED_ON -> ProductInstance`

### `RELATED_SERIAL`

只有当文本明确指向唯一 `PartSerial` 时，才输出：

- `ProductEvent -> RELATED_SERIAL -> PartSerial`

### `RELATED_FAILURE_MODE`

只有当失效模式明确且可稳定闭合时，才输出：

- `ProductEvent -> RELATED_FAILURE_MODE -> FailureMode`

## reporter_name / Organization / occurred_at 规则

### `reporter_name`

- 始终先保留原始字符串
- 如果明显是个人，且文本支持稳定，可同时输出：
  - `Person`
  - `ProductEvent -> REPORTED_BY_PERSON -> Person`
- 如果更像公司或部门，不要在当前 runtime 中直接输出 reporter 组织关系

### `Organization`

只有当组织主体本身是事件语义中的核心对象时，才考虑输出 `Organization`。

例如：

- 明确的客户单位
- 明确的供应商单位
- 明确的责任单位

如果组织只是 reporter 或联系人字段中的原始值：

- 优先保留到 `reporter_name`
- 不为了 actor typing 结果额外创建 `Organization`

### `occurred_at`

- 只有高置信日期或日期时间时才写 `occurred_at`
- 对“4 月上旬”“装机三个月后”“次月”这类表达，不要硬写 ISO 时间

### `severity`

- 只有原文明确出现严重级别、风险等级、内部定义等级时才写 `severity`
- 如果只是从风险分析、运营影响、后果描述里间接猜到“严重程度”，不要硬写
- 若原文没有稳定等级词，保持 `severity = null`

## 与 D4 / D5 的边界

如果同一句话同时包含事件、原因、措施：

- 事件现象保留在 D2
- 原因判断交给 D4
- 措施动作交给 D5

## 与未来 v0.3 的兼容策略

如果你识别到：

- reporter 更像 `Person`
- reporter 更像 `Organization`
- 事件与设计件的关系
- 原始时间文本或时间精度

但当前 runtime 不支持，请遵循：

1. 不输出 schema 之外结构
2. 不输出当前白名单外关系
3. 把关键信息尽量压缩到 `reporter_name`、`symptom`、`d2_problem_statement`
