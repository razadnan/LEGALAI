import pytest
from docx import Document

from core.schemas import ClauseNode, ProposedEdit
from document_intelligence.docx_editing import apply_proposed_edits, extract_clause_tree


def make_docx(path, paragraphs):
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(path)
    return path


def test_extracts_clause_tree_with_non_overlapping_paragraph_ranges(tmp_path):
    source = make_docx(
        tmp_path / "agreement.docx",
        [
            "EMPLOYMENT AGREEMENT",
            "1. Compensation",
            "The following terms apply.",
            "1.1 Salary",
            "The Employer shall pay 1000 USD each month.",
            "1.2 Bonus",
            "The annual bonus is discretionary.",
            "2. Governing law",
            "The laws of India govern this agreement.",
        ],
    )

    tree = extract_clause_tree(source)

    assert [node.clause_id for node in tree] == ["1", "2"]
    assert tree[0].paragraph_start == 1
    assert tree[0].paragraph_end == 2
    assert tree[0].text == "1. Compensation\nThe following terms apply."
    assert [node.clause_id for node in tree[0].children] == ["1.1", "1.2"]
    assert (tree[0].children[0].paragraph_start, tree[0].children[0].paragraph_end) == (3, 4)
    assert tree[0].children[0].parent_id == "1"
    assert tree[1].paragraph_start == 7


def test_clause_node_rejects_reversed_paragraph_range():
    with pytest.raises(ValueError, match="paragraph_end"):
        ClauseNode(
            clause_id="1",
            number="1",
            paragraph_start=3,
            paragraph_end=2,
        )


def test_proposed_edit_requires_clause_old_text_and_reason():
    with pytest.raises(ValueError, match="old_text"):
        ProposedEdit(clause_id="1", old_text=" ", new_text="replacement", reason="clarity")
    with pytest.raises(ValueError, match="reason"):
        ProposedEdit(clause_id="1", old_text="existing text", new_text="replacement", reason=" ")
    with pytest.raises(ValueError, match="Extra inputs"):
        ProposedEdit(
            clause_id="1",
            old_text="existing text",
            new_text="replacement",
            reason="clarity",
            approved=True,
        )


def test_apply_proposed_edit_changes_only_target_and_keeps_source_unchanged(tmp_path):
    source = tmp_path / "original.docx"
    document = Document()
    document.add_paragraph("1. Compensation")
    clause_text = document.add_paragraph()
    clause_text.add_run("The Employer shall ")
    clause_text.add_run("pay 1000 USD each month.")
    document.add_paragraph("2. Governing law")
    document.add_paragraph("The laws of India govern this agreement.")
    document.save(source)
    original_bytes = source.read_bytes()
    original_modified_ns = source.stat().st_mtime_ns
    output = tmp_path / "draft.docx"
    edit = ProposedEdit(
        clause_id="1",
        old_text="The Employer shall pay 1000 USD each month.",
        new_text="The Employer shall pay 1200 USD each month.",
        reason="Update the monthly salary.",
    )

    result = apply_proposed_edits(source, [edit], output)

    revised = Document(result)
    original = Document(source)
    assert result == output
    assert source.read_bytes() == original_bytes
    assert source.stat().st_mtime_ns == original_modified_ns
    assert [p.text for p in revised.paragraphs] == [
        "1. Compensation",
        "The Employer shall pay 1200 USD each month.",
        "2. Governing law",
        "The laws of India govern this agreement.",
    ]
    assert [p.text for p in original.paragraphs] == [
        "1. Compensation",
        "The Employer shall pay 1000 USD each month.",
        "2. Governing law",
        "The laws of India govern this agreement.",
    ]


def test_edit_preserves_surrounding_run_formatting(tmp_path):
    source = tmp_path / "original.docx"
    document = Document()
    document.add_paragraph("1. Compensation")
    clause = document.add_paragraph()
    prefix = clause.add_run("The Employer ")
    prefix.italic = True
    target = clause.add_run("shall pay 1000 USD")
    target.bold = True
    suffix = clause.add_run(" each month.")
    suffix.italic = True
    document.save(source)

    output = apply_proposed_edits(
        source,
        [
            ProposedEdit(
                clause_id="1",
                old_text="pay 1000 USD",
                new_text="pay 1200 USD",
                reason="Update salary.",
            )
        ],
        tmp_path / "draft.docx",
    )

    revised_paragraph = Document(output).paragraphs[1]
    assert revised_paragraph.text == "The Employer shall pay 1200 USD each month."
    assert revised_paragraph.runs[0].italic
    assert revised_paragraph.runs[1].bold
    assert revised_paragraph.runs[2].italic


def test_edit_rejects_replacement_spanning_differently_formatted_runs(tmp_path):
    source = tmp_path / "original.docx"
    document = Document()
    document.add_paragraph("1. Compensation")
    clause = document.add_paragraph()
    clause.add_run("The Employer ").italic = True
    clause.add_run("shall pay 1000 USD").bold = True
    document.save(source)
    output = tmp_path / "draft.docx"
    edit = ProposedEdit(
        clause_id="1",
        old_text="The Employer shall pay 1000 USD",
        new_text="The Employer shall pay 1200 USD",
        reason="Update salary.",
    )

    with pytest.raises(ValueError, match="different formatting"):
        apply_proposed_edits(source, [edit], output)

    assert not output.exists()


@pytest.mark.parametrize(
    ("clause_id", "old_text", "error"),
    [
        ("99", "text to replace", "does not exist"),
        ("1", "not present", "found 0 matches"),
        ("1", "Repeated text", "more than once"),
    ],
)
def test_invalid_or_ambiguous_proposal_does_not_write_output(
    tmp_path, clause_id, old_text, error
):
    source = make_docx(
        tmp_path / "original.docx",
        ["1. Terms", "Some terms.", "Repeated text and Repeated text."],
    )
    output = tmp_path / "draft.docx"
    edit = ProposedEdit(
        clause_id=clause_id,
        old_text=old_text,
        new_text="replacement",
        reason="Test proposal.",
    )

    with pytest.raises(ValueError, match=error):
        apply_proposed_edits(source, [edit], output)

    assert not output.exists()


def test_multiple_edits_to_one_clause_fail_explicitly(tmp_path):
    source = make_docx(
        tmp_path / "original.docx",
        ["1. Terms", "Notice is 30 days. Payment is 30 days."],
    )
    output = tmp_path / "draft.docx"
    edits = [
        ProposedEdit(
            clause_id="1",
            old_text="Notice is 30 days.",
            new_text="Notice is 60 days.",
            reason="Revise notice.",
        ),
        ProposedEdit(
            clause_id="1",
            old_text="Payment is 30 days.",
            new_text="Payment is 60 days.",
            reason="Revise payment.",
        ),
    ]

    with pytest.raises(ValueError, match="Only one proposed edit per clause"):
        apply_proposed_edits(source, edits, output)

    assert not output.exists()


def test_docx_editing_rejects_pdf_source_and_prevents_overwrite(tmp_path):
    pdf = tmp_path / "agreement.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(ValueError, match="DOCX files only"):
        extract_clause_tree(pdf)

    source = make_docx(tmp_path / "agreement.docx", ["1. Terms", "Existing terms."])
    edit = ProposedEdit(
        clause_id="1",
        old_text="Existing terms.",
        new_text="Revised terms.",
        reason="Clarify terms.",
    )
    with pytest.raises(ValueError, match="cannot be overwritten"):
        apply_proposed_edits(source, [edit], source)
    existing_draft = make_docx(tmp_path / "existing.docx", ["Existing draft"])
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        apply_proposed_edits(source, [edit], existing_draft)
