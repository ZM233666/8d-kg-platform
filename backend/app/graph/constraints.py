"""Neo4j 约束和索引 DDL（SCHEMA.md §8）。"""

CONSTRAINTS = [
    # 核心层 Entity（10 条）
    "CREATE CONSTRAINT report_pk IF NOT EXISTS FOR (n:EightDReport) REQUIRE n.report_id IS UNIQUE",
    "CREATE CONSTRAINT project_pk IF NOT EXISTS FOR (n:Project) REQUIRE n.project_no IS UNIQUE",
    "CREATE CONSTRAINT customer_pk IF NOT EXISTS FOR (n:Customer) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT operator_pk IF NOT EXISTS FOR (n:Operator) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT part_pk IF NOT EXISTS FOR (n:Part) REQUIRE n.part_no IS UNIQUE",
    "CREATE CONSTRAINT material_pk IF NOT EXISTS FOR (n:Material) REQUIRE n.material_grade IS UNIQUE",
    "CREATE CONSTRAINT standard_pk IF NOT EXISTS FOR (n:Standard) REQUIRE n.standard_no IS UNIQUE",
    "CREATE CONSTRAINT testmethod_pk IF NOT EXISTS FOR (n:TestMethod) REQUIRE n.method_name IS UNIQUE",
    "CREATE CONSTRAINT process_pk IF NOT EXISTS FOR (n:Process) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT equipment_pk IF NOT EXISTS FOR (n:Equipment) REQUIRE n.name IS UNIQUE",
    # 次要层 Entity（5 条，用 node_id 兜底唯一）
    "CREATE CONSTRAINT vehicle_pk IF NOT EXISTS FOR (n:Vehicle) REQUIRE n.node_id IS UNIQUE",
    "CREATE CONSTRAINT laboratory_pk IF NOT EXISTS FOR (n:Laboratory) REQUIRE n.node_id IS UNIQUE",
    "CREATE CONSTRAINT person_pk IF NOT EXISTS FOR (n:Person) REQUIRE n.node_id IS UNIQUE",
    "CREATE CONSTRAINT team_pk IF NOT EXISTS FOR (n:Team) REQUIRE n.node_id IS UNIQUE",
    "CREATE CONSTRAINT supplier_pk IF NOT EXISTS FOR (n:Supplier) REQUIRE n.node_id IS UNIQUE",
    # 事件（6 条，用 node_id 作唯一约束）
    "CREATE CONSTRAINT defect_pk IF NOT EXISTS FOR (n:DefectOccurrence) REQUIRE n.node_id IS UNIQUE",
    "CREATE CONSTRAINT inspection_pk IF NOT EXISTS FOR (n:InspectionEvent) REQUIRE n.node_id IS UNIQUE",
    "CREATE CONSTRAINT experiment_pk IF NOT EXISTS FOR (n:Experiment) REQUIRE n.node_id IS UNIQUE",
    "CREATE CONSTRAINT action_pk IF NOT EXISTS FOR (n:ActionEvent) REQUIRE n.node_id IS UNIQUE",
    "CREATE CONSTRAINT verification_pk IF NOT EXISTS FOR (n:VerificationEvent) REQUIRE n.node_id IS UNIQUE",
    "CREATE CONSTRAINT closure_pk IF NOT EXISTS FOR (n:ClosureEvent) REQUIRE n.node_id IS UNIQUE",
    # 辅助（5 条）
    "CREATE CONSTRAINT measurement_pk IF NOT EXISTS FOR (n:Measurement) REQUIRE n.node_id IS UNIQUE",
    "CREATE CONSTRAINT finding_pk IF NOT EXISTS FOR (n:Finding) REQUIRE n.node_id IS UNIQUE",
    "CREATE CONSTRAINT rootcause_pk IF NOT EXISTS FOR (n:RootCause) REQUIRE n.node_id IS UNIQUE",
    "CREATE CONSTRAINT risk_pk IF NOT EXISTS FOR (n:RiskAssessment) REQUIRE n.node_id IS UNIQUE",
    "CREATE CONSTRAINT chunk_pk IF NOT EXISTS FOR (n:Chunk) REQUIRE n.chunk_id IS UNIQUE",
    # 概念层（5 条，按 concept_name 唯一）
    "CREATE CONSTRAINT failuremode_pk IF NOT EXISTS FOR (n:FailureModeConcept) REQUIRE n.concept_name IS UNIQUE",
    "CREATE CONSTRAINT fractographic_pk IF NOT EXISTS FOR (n:FractographicFeatureConcept) REQUIRE n.concept_name IS UNIQUE",
    "CREATE CONSTRAINT metdefect_pk IF NOT EXISTS FOR (n:MetallurgicalDefectConcept) REQUIRE n.concept_name IS UNIQUE",
    "CREATE CONSTRAINT rcconcept_pk IF NOT EXISTS FOR (n:RootCauseConcept) REQUIRE n.concept_name IS UNIQUE",
    "CREATE CONSTRAINT actionconcept_pk IF NOT EXISTS FOR (n:ActionTypeConcept) REQUIRE n.concept_name IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX report_closure_status IF NOT EXISTS FOR (n:EightDReport) ON (n.closure_status)",
    "CREATE INDEX report_date IF NOT EXISTS FOR (n:EightDReport) ON (n.report_date)",
    "CREATE INDEX defect_occurred IF NOT EXISTS FOR (n:DefectOccurrence) ON (n.occurred_at)",
    "CREATE INDEX rootcause_chain IF NOT EXISTS FOR (n:RootCause) ON (n.chain_id)",
    "CREATE INDEX finding_polarity IF NOT EXISTS FOR (n:Finding) ON (n.polarity)",
    "CREATE INDEX action_type IF NOT EXISTS FOR (n:ActionEvent) ON (n.action_type)",
    "CREATE INDEX chunk_report IF NOT EXISTS FOR (n:Chunk) ON (n.report_id)",
]


async def apply_constraints(driver, database: str = "neo4j") -> None:
    """对 driver 执行所有 CONSTRAINTS 和 INDEXES。"""
    async with driver.session(database=database) as session:
        for ddl in CONSTRAINTS + INDEXES:
            await session.run(ddl)
