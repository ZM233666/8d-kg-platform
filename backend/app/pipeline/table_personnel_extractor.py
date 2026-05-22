"""从结构化表格中提取团队成员、编写人和核对人。"""

from __future__ import annotations

import re

from app.pipeline.context import PipelineContext
from app.schemas.entity import Person
from app.schemas.extraction import ExtractionResult, RelationTriple

_TEAM_NAME_KEYS = ("姓名", "name")
_TEAM_DEPARTMENT_KEYS = ("部门", "角色", "职能")
_TEAM_EMAIL_KEYS = ("邮件地址", "邮箱地址", "邮箱", "邮件", "email", "e-mail")
_AUTHOR_KEYS = ("编写", "작성", "author")
_REVIEWER_KEYS = ("核对", "审核", "review", "checker")
_EMPTY_VALUES = {"", "-", "/", "n/a", "none", "null", "姓名", "日期"}


def _normalize_text(value: str | None) -> str:
    return (value or "").strip()


def _normalized_compact(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.strip().lower()
    return re.sub(r"[\s\-_()\uFF08\uFF09,.\uFF0C:\uFF1A;\uFF1B]+", "", lowered)


def _first_chunk_id(ctx: PipelineContext) -> str | None:
    return ctx.chunks[0].chunk_id if ctx.chunks else None


def _first_supporting_chunks(ctx: PipelineContext) -> list[str]:
    first_chunk_id = _first_chunk_id(ctx)
    return [first_chunk_id] if first_chunk_id else []


def _find_value_by_keys(row: dict, keys: tuple[str, ...]) -> str:
    for key, value in row.items():
        normalized_key = _normalized_compact(key)
        if any(_normalized_compact(candidate) in normalized_key for candidate in keys):
            text = _normalize_text(str(value))
            if text:
                return text
    return ""


def _is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered in _EMPTY_VALUES


def _looks_like_email(value: str) -> bool:
    return "@" in value and "." in value


def _normalize_email(value: str | None) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    return re.sub(r"\s+", "", text)


def _build_person_business_key(report_key: str, person_name: str, email: str | None) -> str:
    normalized_email = _normalize_email(email).lower()
    if _looks_like_email(normalized_email):
        return f"PER::{normalized_email}"
    compact_name = _normalized_compact(person_name) or person_name.strip()
    return f"PER-LOCAL::{report_key}::{compact_name}"


def _iter_table_like_cells(table: dict) -> list[str]:
    values: list[str] = []
    for header in table.get("headers", []):
        text = _normalize_text(str(header))
        if text:
            values.append(text)
    for row in table.get("rows", []):
        if isinstance(row, dict):
            for key, value in row.items():
                key_text = _normalize_text(str(key))
                value_text = _normalize_text(str(value))
                if key_text:
                    values.append(key_text)
                if value_text:
                    values.append(value_text)
    return values


def _looks_like_team_table(table: dict) -> bool:
    cells = [_normalized_compact(cell) for cell in _iter_table_like_cells(table)]
    has_name = any("姓名" in cell or cell == "name" for cell in cells)
    has_department = any("部门" in cell or "角色" in cell for cell in cells)
    has_email = any("邮件地址" in cell or "邮箱" in cell or "email" in cell for cell in cells)
    return has_name and has_department and has_email


def _looks_like_author_reviewer_table(table: dict) -> bool:
    cells = [_normalized_compact(cell) for cell in _iter_table_like_cells(table)]
    return any(
        any(candidate in cell for candidate in ("编写", "author")) for cell in cells
    ) and any(any(candidate in cell for candidate in ("核对", "审核", "review")) for cell in cells)


def _extract_name_from_column(row_values: list[str]) -> str:
    for value in row_values:
        normalized = _normalize_text(value)
        if not normalized or _is_placeholder(normalized):
            continue
        if any(token in normalized for token in ("编写", "核对", "日期")):
            continue
        return normalized
    return ""


def _extract_people_from_team_table(
    ctx: PipelineContext,
    er: ExtractionResult,
    table: dict,
    seen_people: dict[str, Person],
) -> None:
    report_key = er.report.business_key if er.report else (ctx.report_id_hint or "UNKNOWN")
    supporting_chunks = _first_supporting_chunks(ctx)

    for row in table.get("rows", []):
        if not isinstance(row, dict):
            continue
        name = _find_value_by_keys(row, _TEAM_NAME_KEYS)
        if not name or _is_placeholder(name):
            continue

        department = _find_value_by_keys(row, _TEAM_DEPARTMENT_KEYS) or None
        email = _normalize_email(_find_value_by_keys(row, _TEAM_EMAIL_KEYS)) or None
        business_key = _build_person_business_key(report_key, name, email)

        normalized_name = _normalized_compact(name)
        person = next(
            (
                existing
                for existing in seen_people.values()
                if _normalized_compact(existing.person_name) == normalized_name
            ),
            None,
        )
        if person is None:
            person = Person(
                business_key=business_key,
                person_id=business_key,
                person_name=name,
                department=department,
                email=email,
                supporting_chunks=list(supporting_chunks),
            )
            er.persons.append(person)
            seen_people[business_key] = person
        else:
            old_key = person.business_key
            if email and old_key != business_key:
                person.business_key = business_key
                person.person_id = business_key
                for relation in er.relationships:
                    if relation.to_label == "Person" and relation.to_key == old_key:
                        relation.to_key = business_key
                seen_people.pop(old_key, None)
                seen_people[business_key] = person
            if department and not person.department:
                person.department = department
            if email and not person.email:
                person.email = email
            person.supporting_chunks = list(
                dict.fromkeys(person.supporting_chunks + list(supporting_chunks))
            )

        relation = RelationTriple(
            from_label="EightDReport",
            from_key=report_key,
            to_label="Person",
            to_key=business_key,
            rel_type="INVOLVES_PERSON",
        )
        if relation not in er.relationships:
            er.relationships.append(relation)


def _extract_person_from_author_reviewer_table(
    ctx: PipelineContext,
    er: ExtractionResult,
    table: dict,
    seen_people: dict[str, Person],
) -> None:
    if er.report is None:
        return

    report_key = er.report.business_key
    supporting_chunks = _first_supporting_chunks(ctx)
    headers = [str(header) for header in table.get("headers", [])]
    rows = [row for row in table.get("rows", []) if isinstance(row, dict)]

    role_specs = [
        (_AUTHOR_KEYS, "编写", "AUTHORED_BY_PERSON"),
        (_REVIEWER_KEYS, "核对", "REVIEWED_BY_PERSON"),
    ]

    for key_candidates, _title, rel_type in role_specs:
        matched_headers = [
            header
            for header in headers
            if any(
                _normalized_compact(candidate) in _normalized_compact(header)
                for candidate in key_candidates
            )
        ]
        for header in matched_headers:
            column_values = [str(row.get(header, "")) for row in rows]
            name = _extract_name_from_column(column_values)
            if not name:
                continue

            normalized_name = _normalized_compact(name)
            person = next(
                (
                    existing
                    for existing in seen_people.values()
                    if _normalized_compact(existing.person_name) == normalized_name
                ),
                None,
            )
            business_key = (
                person.business_key
                if person is not None
                else _build_person_business_key(report_key, name, None)
            )
            if person is None:
                person = Person(
                    business_key=business_key,
                    person_id=business_key,
                    person_name=name,
                    supporting_chunks=list(supporting_chunks),
                )
                er.persons.append(person)
                seen_people[business_key] = person
            else:
                person.supporting_chunks = list(
                    dict.fromkeys(person.supporting_chunks + list(supporting_chunks))
                )

            relation = RelationTriple(
                from_label="EightDReport",
                from_key=report_key,
                to_label="Person",
                to_key=business_key,
                rel_type=rel_type,
            )
            if relation not in er.relationships:
                er.relationships.append(relation)
            break


def enrich_personnel_from_tables(ctx: PipelineContext, er: ExtractionResult) -> ExtractionResult:
    """将团队表、编写人和核对人信息补到 ExtractionResult。"""
    if er.report is None or not ctx.raw_tables:
        return er

    seen_people = {person.business_key: person for person in er.persons}
    for table in ctx.raw_tables:
        if _looks_like_team_table(table):
            _extract_people_from_team_table(ctx, er, table, seen_people)
        if _looks_like_author_reviewer_table(table):
            _extract_person_from_author_reviewer_table(ctx, er, table, seen_people)

    return er
