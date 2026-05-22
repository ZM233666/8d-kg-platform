# 8d-d4-root-cause-extraction

这个模块专门约束 D4 根因抽取，但**最终输出必须兼容当前 runtime**。

## 当前 runtime 下 D4 可直接落的结构

可直接输出：

- `CauseItem`
- `FailureMode`
- 条件性 `Organization`
- `EightDReport -> ROOT_CAUSE -> CauseItem`
- `CauseItem -> RELATED_FAILURE_MODE -> FailureMode`
- `EightDReport -> RESPONSIBLE_ORG -> Organization`

当前 runtime **暂不直接支持**：

- `LEADS_TO`
- `CauseItem -> RELATED_PART`
- `CauseItem -> RELATED_EVENT`
- `CauseItem -> RELATED_SERIAL`
- `Person`
- 规范时间辅助结构

因此这些信息如果很重要，应保留在：

- `d4_root_cause_summary`
- `CauseItem.evidence`
- `CauseItem.title`

## CauseItem 创建规则

只有当文本满足以下至少一项时，才创建 `CauseItem`：

- 明确被报告认定为原因
- 被证据链强支持，且语义上属于因果解释的一部分
- 被明确列为直接原因 / 中间原因 / 根本原因

以下情况不要创建 `CauseItem`：

- 纯现象描述
- 纯检测结果但没有因果解释
- 被明确排除的假设原因
- 只有弱猜测且无后续支持

## 原因拆分规则

默认采用“中等偏保守”的拆分粒度：

- 每个子句如果可以独立回答“为什么发生”，就可以拆成一个 `CauseItem`
- 如果只是同一个原因的补充限定，不要拆成多个 CauseItem

例如：

- `O 型圈硬度低于图纸要求，且来料检验未覆盖硬度项`
  - 可拆两个 `CauseItem`
- `O 型圈硬度低于图纸要求，导致密封失效`
  - 前半句是原因，后半句更像结果/失效，不要机械拆成两个原因

## cause_type 默认策略

- 文本明确写“直接原因 / 中间原因 / 根本原因”时，照原文归类
- 如果只给出一个最终原因结论，默认记为 `根本原因`
- 如果仍不确定，优先选最保守但可解释的类型，不要凭空造层级

## Evidence 写法

`CauseItem.evidence` 适合承载：

- 检测结果
- 试验结论
- 对比证据
- 当前 runtime 暂时不支持结构化表示的因果顺序
- 无法落为关系的对象指向或时间短语

例如：

- `硬度检测结果 52HA，低于图纸要求 70HA`
- `装机三个月后出现裂纹`
- `供应商热处理批次 2026-05 异常`

## FailureMode 规则

只有在文本明确出现失效模式时，才输出 `FailureMode`。

适合来源：

- 章节标题
- 结论句里的标准化失效术语
- 检测/结论中的故障名称

不要只因为“看起来像故障”就创造新的失效模式。

## Organization 规则

只有在 D4 文本明确把责任归到组织主体时，才输出 `Organization`。

典型例子：

- `供应商热处理参数失控`
- `质量部检验规范未覆盖关键硬度项`
- `客户现场维护流程不当`
- `运营商现场维护流程不当`

当前 runtime 推荐做法：

- 输出 `Organization`
- 运营主体优先标记 `org_type="运营商"`
- 如果明确是报告责任归属，可补：
  - `EightDReport -> RESPONSIBLE_ORG -> Organization`

如果只是模糊流程短语，不要强行建 `Organization`。

## 与措施的边界

如果一句话同时包含原因和措施：

- 原因部分留在 D4
- 措施部分不要写成 `ActionItem`
- 可把原因保留在 `CauseItem.title / evidence`

例如：

- `由于来料检验未覆盖硬度项，后续增加硬度全检`
  - D4 只保留前半句原因

## 与未来 v0.3 的兼容策略

如果你识别到：

- 隐含因果链
- 原因与零件/事件/批次的细粒度绑定
- 重要时间顺序

但当前 runtime 没有对应结构，请遵循：

1. 不输出不被支持的关系
2. 不输出 schema 之外字段
3. 把关键信息尽量压缩到 `d4_root_cause_summary` 或 `CauseItem.evidence`

这样后续升级到更完整的 v0.3 schema 时，至少语义不会在本阶段丢掉。
