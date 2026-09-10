"""The report is a deliverable, so its shape is tested like one.

These assertions exist because `render` was split into per-section helpers
after a complexity gate flagged it; they are what makes that refactor safe to
repeat.
"""

import pytest

from ledger.core import FeePolicy
from ledger.replay import render, replay


@pytest.fixture(scope="module")
def report() -> str:
    return render(replay(policy=FeePolicy.RETROACTIVE), FeePolicy.RETROACTIVE)


def test_a_restated_day_shows_both_views(report: str) -> None:
    assert "  closed at         ACC-001  250.00 AED" in report
    assert (
        "  restated          ACC-001  225.00 AED"
        "  (backdated entries arrived after this close)"
    ) in report


def test_a_fee_names_the_day_it_was_assessed_on(report: str) -> None:
    assert (
        "  fee               ACC-001  -25.00 AED  "
        "(assessed on Day 5, value-dated Day 2)"
    ) in report


def test_authorisation_states_and_errors_are_reported(report: str) -> None:
    assert "  authorisation     Auth-A  SETTLED  (200.00 AED)" in report
    assert "  authorisation     Auth-B  DECLINED  (90.00 AED)" in report
    assert "E6  FORCE_POSTED: no authorisation Auth-Z in the ledger" in report


def test_quiet_days_say_none_rather_than_omitting_the_row(report: str) -> None:
    assert "  fee               none" in report
    assert "  error             none" in report
    assert "  authorisation     none" in report


def test_interest_block_reports_dailies_and_the_credit(report: str) -> None:
    assert "  ACC-001  daily: 0.10  0.09  0.25  0.10  0.08  0.08" in report
    assert "  ACC-001  capitalised on Day 6: 0.70 AED" in report
    assert "  ACC-002  capitalised on Day 6: 0.008 BHD" in report


def test_both_policies_render(report: str) -> None:
    pit = render(replay(policy=FeePolicy.POINT_IN_TIME), FeePolicy.POINT_IN_TIME)
    assert "overdraft-fee policy: point-in-time" in pit
    assert "overdraft-fee policy: retroactive" in report
    assert pit != report


def test_trial_balance_is_grouped_by_currency_and_cancels(report: str) -> None:
    """Structure, not spacing.

    The column widths are tuned to the figures actually shown, so asserting
    exact padding would make this test fail every time the layout improves.
    What must hold is that each currency gets its own block and that the block
    adds up to nothing.
    """
    block = report[report.index("Trial balance") :]
    lines = [line for line in block.splitlines() if line.strip()]

    blocks: dict[str, list[list[str]]] = {}
    current = ""
    for line in lines[2:]:
        if not line.startswith("    "):
            current = line.strip()
            blocks[current] = []
        elif set(line.strip()) != {"-"}:  # skip the rule above each total
            blocks[current].append(line.split())

    assert list(blocks) == ["AED", "BHD"], "one block per currency, in order"

    assert ["ACC-001", "210.70"] in blocks["AED"]
    assert ["SUSPENSE-AED", "180.00"] in blocks["AED"]
    assert ["INCOME-FEES-AED", "75.00"] in blocks["AED"]
    assert blocks["AED"][-1] == ["sum", "0.00"]

    assert ["ACC-002", "10.008"] in blocks["BHD"]
    assert blocks["BHD"][-1] == ["sum", "0.000"]


def test_the_two_currencies_are_never_added_together(report: str) -> None:
    # A single figure summing AED and BHD would be meaningless, and its
    # absence is the point of grouping.
    block = report[report.index("Trial balance") :]
    assert block.count("sum") == 2
