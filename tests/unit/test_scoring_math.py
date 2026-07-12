"""Unit tests for the deterministic readiness-score arithmetic (FEAT-054).

compute_score is pure over the Bid aggregate — build detached ORM objects, no DB.
Transparency is the contract: weights sum to 1, every criterion carries its own
detail line, and the total is exactly the weighted sum.
"""

from datetime import UTC, datetime, timedelta

from models.bid import Bid, ChecklistItem, KeyDate
from services.scoring import WEIGHTS, compute_score


def _bid(items: list[ChecklistItem] | None = None, key_dates: list[KeyDate] | None = None) -> Bid:
    bid = Bid(source_ref="unit", title="Unit")
    bid.checklist_items = items or []
    bid.documents = []
    bid.key_dates = key_dates or []
    return bid


def _item(kind: str, req_type: str = "other", status: str = "open", verification: dict | None = None) -> ChecklistItem:
    # Detached ORM objects don't get column defaults — set status explicitly.
    return ChecklistItem(
        criterion_kind=kind, requirement_type=req_type, title=f"{kind} req", status=status, ai_verification=verification
    )


def test_weights_sum_to_one():
    assert round(sum(WEIGHTS.values()), 6) == 1.0


def test_total_is_the_exact_weighted_sum():
    score = compute_score(_bid([_item("formal"), _item("suitability", status="done")]))
    expected = round(sum(c["score"] * c["weight"] for c in score["criteria"]), 1)
    assert score["total"] == expected


def test_every_criterion_is_explained():
    score = compute_score(_bid())
    assert {c["key"] for c in score["criteria"]} == set(WEIGHTS)
    for c in score["criteria"]:
        assert c["detail"], f"criterion {c['key']} must carry a human-readable detail"
        assert c["weight"] == WEIGHTS[c["key"]]
        assert 0.0 <= c["score"] <= 100.0


def test_kind_ratio_counts_done_and_na_as_resolved():
    items = [_item("formal", status="done"), _item("formal", status="n_a"), _item("formal", status="open")]
    score = compute_score(_bid(items))
    formal = next(c for c in score["criteria"] if c["key"] == "formal_readiness")
    assert formal["score"] == round(100.0 * 2 / 3, 1)


def test_no_deadline_is_neutral_50():
    score = compute_score(_bid())
    buffer = next(c for c in score["criteria"] if c["key"] == "deadline_buffer")
    assert buffer["score"] == 50.0
    assert "No submission deadline" in buffer["detail"]


def test_deadline_buffer_caps_at_100_and_floors_at_0():
    far = _bid(key_dates=[KeyDate(kind="submission", date=datetime.now(UTC) + timedelta(days=365))])
    assert next(c for c in compute_score(far)["criteria"] if c["key"] == "deadline_buffer")["score"] == 100.0

    passed = _bid(key_dates=[KeyDate(kind="submission", date=datetime.now(UTC) - timedelta(days=3))])
    assert next(c for c in compute_score(passed)["criteria"] if c["key"] == "deadline_buffer")["score"] == 0.0


def test_naive_deadline_is_treated_as_utc():
    naive = datetime.now() + timedelta(days=10)  # noqa: DTZ005 — deliberately naive
    score = compute_score(_bid(key_dates=[KeyDate(kind="submission", date=naive)]))
    buffer = next(c for c in score["criteria"] if c["key"] == "deadline_buffer")
    assert 0.0 < buffer["score"] < 100.0


def test_document_evidence_counts_only_matched_evidence_requirements():
    items = [
        _item("suitability", "reference", verification={"status": "matched", "detail": "x"}),
        _item("suitability", "certificate"),  # unmatched evidence requirement
        _item("award", "concept"),  # not an evidence-type requirement
    ]
    score = compute_score(_bid(items))
    evidence = next(c for c in score["criteria"] if c["key"] == "document_evidence")
    assert evidence["score"] == 50.0  # 1 of 2 evidence-type requirements
    assert "1/2" in evidence["detail"]


def test_empty_checklist_kinds_score_100_not_crash():
    score = compute_score(_bid())
    for key in ("formal_readiness", "suitability_coverage", "award_preparation"):
        assert next(c for c in score["criteria"] if c["key"] == key)["score"] == 100.0
