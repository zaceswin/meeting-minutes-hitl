import pytest

from minutes import export
from minutes.schemas import Session


def test_blocked_until_reviewed(demo):
    with pytest.raises(ValueError) as e:
        export.write_outputs(demo, "/tmp/never")
    assert "reviewer" in str(e.value).lower() and "pending" in str(e.value)


def test_export_contains_quotes_speakers_hashes(demo, tmp_path):
    demo.reviewer = "Secretary"
    demo.speakers["SPEAKER_00"] = "Mr. Otieno"
    for i in demo.items:
        i.status = "accepted"
    out = export.write_outputs(demo, tmp_path)
    md = open(out["minutes"], encoding="utf-8").read()
    assert "it is agreed, the levy is 500 shillings from March" in md
    assert "Mr. Otieno, L005 @ 0:00:31" in md
    assert "Recording SHA-256" in md and "Transcript SHA-256" in md
    assert "Left open (NOT decided)" in md and "Visitors will not pay the gate fee" not in md


def test_rejected_items_never_exported(demo, tmp_path):
    demo.reviewer = "S"
    for i in demo.items:
        i.status = "rejected"
    out = export.write_outputs(demo, tmp_path)
    assert "Monthly water levy" not in open(out["minutes"], encoding="utf-8").read()


def test_manual_mode_exports_transcript_with_banner(tmp_path):
    from minutes.pipeline import assemble_session
    from minutes.schemas import Line
    lines = [Line(id=f"L{i:03d}", start=i, end=i + 1, text=f"noisy line {i}", confidence=0.1) for i in range(1, 4)]
    s = assemble_session(lines, name="n", audio="a")
    s.reviewer = "S"
    md = open(export.write_outputs(s, tmp_path)["minutes"], encoding="utf-8").read()
    assert export.BANNER in md and "noisy line 2" in md


def test_csv_formula_injection_neutralised(demo, tmp_path):
    demo.reviewer = "S"
    demo.items[0].text = "=HYPERLINK(\"http://evil\")"
    for i in demo.items:
        i.status = "accepted"
    csv_text = open(export.write_outputs(demo, tmp_path)["register"], encoding="utf-8").read()
    assert "'=HYPERLINK" in csv_text
