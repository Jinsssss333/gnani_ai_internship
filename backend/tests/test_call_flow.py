from app.call_flow import FINAL_REVIEW, allowed_action, next_question


def test_visit_done_branches_to_age_or_reason() -> None:
    assert next_question("visit_done", True) == "age"
    assert next_question("visit_done", False) == "not_done_reason"


def test_followup_branch_skips_date_when_not_needed() -> None:
    assert next_question("followup_needed", False) == "notes"
    assert next_question("followup_needed", True) == "followup_date"


def test_optional_question_can_be_skipped() -> None:
    assert allowed_action("symptoms", "skip")
    assert not allowed_action("age", "skip")
    assert next_question("notes", "anything") == FINAL_REVIEW
