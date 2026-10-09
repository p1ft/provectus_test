"""Independent passage facts, including valid paraphrases and unsupported exclusivity."""

import pytest

from scripts.verify_reference_cases import facts_match


@pytest.mark.parametrize("case,text", [
    ("Q1", "No, free-plan users cannot export CSV."),
    ("Q3", "Email support runs Monday through Friday, from 09:00 to 17:00 UTC."),
    ("Q4", "No, live chat is not available."),
    ("Q5", "Users sign in using their email address and password."),
    ("Q6", "Account owners can send team invitations."),
    ("Q7", "Paid subscriptions are billed on a monthly basis."),
    ("Q8", "Account owners can obtain billing invoices."),
    ("Q6", "Account owners are the only users explicitly identified as able to invite team members."),
    ("Q8", "Account owners are the only users explicitly identified as able to download invoices."),
])
def test_reference_facts_accept_meaning_without_exact_phrasing(case, text):
    assert facts_match(case, text)


@pytest.mark.parametrize("case,text", [
    ("Q6", "Only account owners can invite members."),
    ("Q8", "Only account owners can download billing invoices."),
    ("Q3", "Email support runs Monday through Friday, 09:00 to 17:00 PST."),
    ("Q7", "Subscriptions are billed annually."),
])
def test_reference_facts_reject_wrong_or_undocumented_additions(case, text):
    assert not facts_match(case, text)
