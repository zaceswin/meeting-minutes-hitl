from minutes import trust
from minutes.schemas import Evidence, ExtractedDecision, ExtractionResult, Line, Session


def test_quote_exact_ignores_case_and_punctuation():
    assert trust.quote_ok("it is AGREED the levy is 500 shillings", "Then it is agreed, the levy is 500 shillings.")


def test_one_digit_change_is_rejected():
    # the reason we do NOT use a fuzzy threshold: 500 vs 600 is a 1-character edit
    assert not trust.quote_ok("the levy is 600 shillings", "the levy is 500 shillings")
    assert trust.closeness("the levy is 600 shillings", "the levy is 500 shillings") > 0.9


def test_short_quote_only_if_whole_line():
    assert trust.quote_ok("Yes.", "Yes")
    assert not trust.quote_ok("Yes", "Yes I agree with that")


def test_gate_blocks_over_15_percent():
    lines = [Line(id=f"L{i:03d}", start=i, end=i + 1, text="x y z", confidence=0.9) for i in range(1, 11)]
    for l in lines[:2]:
        l.confidence = 0.3  # 20% bad
    trust.mark_unreliable(lines)
    g = trust.source_gate(lines)
    assert not g.ok and g.ratio == 0.2


def test_gate_passes_at_limit():
    lines = [Line(id=f"L{i:03d}", start=i, end=i + 1, text="x y z", confidence=0.9) for i in range(1, 21)]
    for l in lines[:3]:
        l.confidence = 0.3  # exactly 15%
    trust.mark_unreliable(lines)
    assert trust.source_gate(lines).ok


def test_unscored_lines_are_not_called_unreliable_but_are_flagged():
    lines = [Line(id="L001", start=0, end=1, text="we will pay the contractor", confidence=None)]
    trust.mark_unreliable(lines)
    assert not lines[0].unreliable
    s = Session(name="t", audio="x", lines=lines)
    res = ExtractionResult(decisions=[ExtractedDecision(text="Pay the contractor.", evidence=[Evidence(line_id="L001", quote="we will pay the contractor")])])
    s.items, problems = trust.items_from_extraction(res, s)
    trust.refresh(s)
    assert not problems and "UNSCORED_AUDIO:L001" in s.items[0].flags


def test_demo_drops_fabricated_and_invented(demo):
    kinds = [(i.kind, i.id) for i in demo.items]
    assert ("decision", "D1") in kinds and ("decision", "D2") not in kinds  # fabricated + invented were dropped
    notes = " ".join(demo.notes)
    assert "L099" in notes and "visitors will not pay" in notes


def test_demo_flags(demo):
    d1 = next(i for i in demo.items if i.id == "D1")
    assert "NUMBER_OR_AMOUNT" in d1.flags
    a1 = next(i for i in demo.items if i.id == "A1")
    assert "OWNER_UNCONFIRMED" in a1.flags
    o1 = next(i for i in demo.items if i.id == "O1")
    assert any(f.startswith("UNRELIABLE_AUDIO") for f in o1.flags)  # L008 is 47%


def test_missed_swahili_decision_is_surfaced(demo):
    assert "L009" in trust.uncovered_candidates(demo)


def test_pipeline_manual_mode_when_noisy():
    from minutes.pipeline import assemble_session
    lines = [Line(id=f"L{i:03d}", start=i, end=i + 1, text="blah blah blah", confidence=0.2) for i in range(1, 6)]
    called = []
    s = assemble_session(lines, name="n", audio="a", extractor=lambda ls: called.append(1))
    assert s.mode == "manual_review_required" and not called and not s.items
    assert "MANUAL REVIEW REQUIRED" in " ".join(s.notes)
