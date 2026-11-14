"""Structured clause mapping and deterministic draft edits for DOCX files."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Union

from docx import Document as DocxDocument
from docx.document import Document as DocxDocumentObject

from core.schemas import ClauseNode, ProposedEdit
from rag_engine.chunking import match_heading

DocxSource = Union[str, Path, bytes, bytearray]


def _load_docx(source: DocxSource) -> tuple[DocxDocumentObject, Path | None]:
    source_path = None
    if isinstance(source, (str, Path)):
        source_path = Path(source)
        if source_path.suffix.lower() != ".docx":
            raise ValueError("Clause extraction and edits currently support DOCX files only.")
        if not source_path.is_file():
            raise FileNotFoundError(f"DOCX file not found: {source_path}")
        source_data = source_path
    elif isinstance(source, (bytes, bytearray)):
        source_data = io.BytesIO(bytes(source))
    else:
        raise TypeError("source must be a DOCX path or DOCX bytes.")

    try:
        return DocxDocument(source_data), source_path
    except Exception as exc:
        raise ValueError("The supplied content is not a readable DOCX file.") from exc


def _extract_clause_tree(document: DocxDocumentObject) -> list[ClauseNode]:
    paragraphs = document.paragraphs
    headings: list[tuple[int, str, str]] = []
    seen_ids: set[str] = set()

    for index, paragraph in enumerate(paragraphs):
        match = match_heading(paragraph.text.strip())
        if not match:
            continue
        number, heading = match
        if number in seen_ids:
            raise ValueError(f"Duplicate clause number {number!r}; clause IDs must be unique.")
        seen_ids.add(number)
        headings.append((index, number, heading))

    roots: list[ClauseNode] = []
    stack: list[tuple[int, ClauseNode]] = []
    for position, (start, number, heading) in enumerate(headings):
        level = number.count(".") + 1
        while stack and stack[-1][0] >= level:
            stack.pop()

        parent = stack[-1][1] if stack and number.startswith(stack[-1][1].number + ".") else None
        next_heading = headings[position + 1][0] if position + 1 < len(headings) else len(paragraphs)
        end = next_heading - 1
        node = ClauseNode(
            clause_id=number,
            number=number,
            heading=heading,
            text="\n".join(paragraphs[i].text for i in range(start, end + 1)),
            paragraph_start=start,
            paragraph_end=end,
            parent_id=parent.clause_id if parent else None,
        )
        if parent:
            parent.children.append(node)
        else:
            roots.append(node)
        stack.append((level, node))

    return roots


def extract_clause_tree(source: DocxSource) -> list[ClauseNode]:
    """Extract numbered clauses and zero-based indexes into ``Document.paragraphs``.

    Clause ranges are inclusive and stop before the next numbered heading, so a
    parent clause's range does not overlap its child clauses.
    """
    document, _ = _load_docx(source)
    return _extract_clause_tree(document)


def _flatten_clause_tree(nodes: list[ClauseNode]) -> dict[str, ClauseNode]:
    clauses: dict[str, ClauseNode] = {}
    pending = list(nodes)
    while pending:
        node = pending.pop()
        clauses[node.clause_id] = node
        pending.extend(node.children)
    return clauses


def _find_clause_text_paragraphs(
    document: DocxDocumentObject,
    clause: ClauseNode,
    old_text: str,
) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    paragraphs = document.paragraphs
    for index in range(clause.paragraph_start, clause.paragraph_end + 1):
        paragraph = paragraphs[index]
        run_text = "".join(run.text for run in paragraph.runs)
        if paragraph.text != run_text and old_text in paragraph.text:
            raise ValueError(
                f"Clause {clause.clause_id} contains text outside editable DOCX runs."
            )
        first = run_text.find(old_text)
        if first < 0:
            continue
        if run_text.find(old_text, first + 1) >= 0:
            raise ValueError(
                f"old_text occurs more than once in clause {clause.clause_id}."
            )
        matches.append((index, first))
    return matches


def _replace_run_text(
    paragraph,
    old_text: str,
    new_text: str,
    start: int,
    clause_id: str,
) -> None:
    runs = paragraph.runs
    run_ranges: list[tuple[int, int]] = []
    cursor = 0
    for run in runs:
        run_ranges.append((cursor, cursor + len(run.text)))
        cursor += len(run.text)

    end = start + len(old_text)
    start_run = next(
        (i for i, (run_start, run_end) in enumerate(run_ranges) if run_start <= start < run_end),
        None,
    )
    end_run = next(
        (i for i, (run_start, run_end) in enumerate(run_ranges) if run_start < end <= run_end),
        None,
    )
    if start_run is None or end_run is None:
        raise ValueError("The target text could not be mapped to editable DOCX runs.")

    matched_runs = [
        runs[index]
        for index in range(start_run, end_run + 1)
        if run_ranges[index][0] < end and run_ranges[index][1] > start
    ]
    style_signatures = [
        str(run._r.rPr.xml) if run._r.rPr is not None else ""
        for run in matched_runs
    ]
    if len(set(style_signatures)) > 1:
        raise ValueError(
            f"old_text spans runs with different formatting in clause {clause_id}; "
            "submit a proposal that stays within one formatting run."
        )

    for index in range(start_run, end_run + 1):
        run = runs[index]
        run_start, _ = run_ranges[index]
        if index == start_run:
            prefix = run.text[:start - run_start]
            suffix = run.text[end - run_start:] if index == end_run else ""
            run.text = prefix + new_text + suffix
        elif index == end_run:
            run.text = run.text[end - run_start:]
        else:
            run.text = ""


def apply_proposed_edits(
    source: DocxSource,
    edits: list[ProposedEdit | dict],
    output_path: str | Path,
) -> Path:
    """Write an edited DOCX draft without changing or overwriting its source.

    Each proposal must target an existing clause and an exact old-text string
    occurring once in that clause. One proposal per clause is accepted per call.
    """
    document, source_path = _load_docx(source)
    output = Path(output_path)
    if output.suffix.lower() != ".docx":
        raise ValueError("The revised document must have a .docx extension.")
    if source_path and output.resolve() == source_path.resolve():
        raise ValueError("The original DOCX cannot be overwritten.")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing draft: {output}")

    proposals = [ProposedEdit.model_validate(edit) for edit in edits]
    if not proposals:
        raise ValueError("At least one proposed edit is required.")
    clause_ids = [edit.clause_id for edit in proposals]
    if len(set(clause_ids)) != len(clause_ids):
        raise ValueError("Only one proposed edit per clause is allowed in a single draft.")

    clauses = _flatten_clause_tree(_extract_clause_tree(document))
    prepared: list[tuple[ProposedEdit, int, int]] = []
    for edit in proposals:
        clause = clauses.get(edit.clause_id)
        if clause is None:
            raise ValueError(f"Clause {edit.clause_id!r} does not exist in the DOCX.")
        matches = _find_clause_text_paragraphs(document, clause, edit.old_text)
        if len(matches) != 1:
            raise ValueError(
                f"old_text must occur exactly once in clause {edit.clause_id}; found {len(matches)} matches."
            )
        paragraph_index, text_start = matches[0]
        prepared.append((edit, paragraph_index, text_start))

    paragraphs = document.paragraphs
    for edit, paragraph_index, text_start in prepared:
        _replace_run_text(
            paragraphs[paragraph_index],
            edit.old_text,
            edit.new_text,
            text_start,
            edit.clause_id,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(output)
    return output
