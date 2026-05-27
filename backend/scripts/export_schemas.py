"""导出 4 份 JSON Schema 文件到 backend/app/schemas/exported/。

用法：cd backend && python -m scripts.export_schemas
"""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas.concept import (
    ActionTypeConcept,
    FailureModeConcept,
    FractographicFeatureConcept,
    MetallurgicalDefectConcept,
    RootCauseConcept,
)
from app.schemas.entity import (
    ActionEvent,
    Chunk,
    ClosureEvent,
    Customer,
    DefectOccurrence,
    EightDReport,
    Equipment,
    Experiment,
    Finding,
    InspectionEvent,
    Laboratory,
    LeadsToEdge,
    Material,
    Measurement,
    Operator,
    Part,
    Person,
    Process,
    Project,
    RiskAssessment,
    RootCause,
    Standard,
    Supplier,
    Team,
    TestMethod,
    Vehicle,
    VerificationEvent,
)

OUTPUT_DIR = Path(__file__).parent.parent / "app" / "schemas" / "exported"

ENTITY_CORE = [
    EightDReport,
    Project,
    Customer,
    Operator,
    Part,
    Material,
    Standard,
    TestMethod,
    Process,
    Equipment,
]

EVENT_MODELS = [
    DefectOccurrence,
    InspectionEvent,
    Experiment,
    ActionEvent,
    VerificationEvent,
    ClosureEvent,
]

CONCEPT_MODELS = [
    FailureModeConcept,
    FractographicFeatureConcept,
    MetallurgicalDefectConcept,
    RootCauseConcept,
    ActionTypeConcept,
]

AUXILIARY_MODELS = [
    Vehicle,
    Laboratory,
    Person,
    Team,
    Supplier,
    Measurement,
    Finding,
    RootCause,
    RiskAssessment,
    Chunk,
    LeadsToEdge,
]


def _export(group_name: str, models: list) -> dict:
    return {m.__name__: m.model_json_schema() for m in models}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    groups = {
        "entity_schemas.json": ENTITY_CORE,
        "event_schemas.json": EVENT_MODELS,
        "concept_schemas.json": CONCEPT_MODELS,
        "auxiliary_schemas.json": AUXILIARY_MODELS,
    }
    for filename, models in groups.items():
        out = OUTPUT_DIR / filename
        data = _export(filename, models)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"✓ {filename}: {len(models)} models, {out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
