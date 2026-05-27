"""ConceptType（概念分类树 SCHEMA.md §5）。

概念是受控词表，v0.1 由 domain_lexicon.yaml 维护初始树，v0.2 由 Aligner 自动扩充。
不从原文抽取生成新节点，只通过 Aligner 链接已有概念。
"""

from pydantic import Field

from app.schemas.base import BaseNode


class FailureModeConcept(BaseNode):
    """失效模式概念树（§5.1）。

    初始树：断裂 / 疲劳断裂 / 脆性断裂 / 应力腐蚀开裂；变形 / 弹性变形超限 / 塑性变形；磨损；腐蚀。
    """

    concept_name: str = Field(..., description="概念名称，如 '疲劳断裂'")
    parent_concept: str | None = Field(None, description="上位概念，如 '断裂'")
    aliases: list[str] = Field(default_factory=list, description="别名列表")
    # TODO: §5.1 字段补充（如有）


class FractographicFeatureConcept(BaseNode):
    """断口特征概念树（§5.2）。"""

    concept_name: str = Field(
        ...,
        description="概念名称，如 '海滩花样'/'韧窝形貌'/'疲劳条带'",
    )
    aliases: list[str] = Field(default_factory=list, description="别名列表")
    # TODO: §5.2 字段补充（如有）


class MetallurgicalDefectConcept(BaseNode):
    """冶金缺陷概念树（§5.3）。"""

    concept_name: str = Field(
        ...,
        description="概念名称，如 '夹杂'/'气孔'/'疏松'/'脱碳'",
    )
    aliases: list[str] = Field(default_factory=list, description="别名列表")
    # TODO: §5.3 字段补充（如有）


class RootCauseConcept(BaseNode):
    """根因分类概念树（§5.4）。"""

    concept_name: str = Field(
        ...,
        description="概念名称，如 '外部过载'/'材料缺陷'/'设计不足'",
    )
    parent_concept: str | None = Field(None, description="上位概念")
    aliases: list[str] = Field(default_factory=list, description="别名列表")


class ActionTypeConcept(BaseNode):
    """对策类型概念树（§5.5）。"""

    concept_name: str = Field(
        ...,
        description="概念名称，如 '100%全检'/'工艺改进'/'模具更换'",
    )
    aliases: list[str] = Field(default_factory=list, description="别名列表")
