"""ABC-XYZ rules: the boundaries stated in app/services/analytics/classify.py and CLAUDE.md."""

import statistics
from datetime import date

import pytest

from app.services.analytics import classify


def test_the_product_crossing_80_percent_is_still_a():
    # Cumulative share before each: 0, 50, 75, 90, 96 -> A A A B C
    assert classify.abc_classes({"p1": 50, "p2": 25, "p3": 15, "p4": 6, "p5": 4}) == {
        "p1": "A", "p2": "A", "p3": "A", "p4": "B", "p5": "C"}


def test_a_dominant_product_is_a_and_the_next_one_b():
    assert classify.abc_classes({"big": 85, "mid": 10, "small": 5}) == {"big": "A", "mid": "B", "small": "C"}


def test_exact_boundaries_belong_to_the_lower_class():
    # Before p3: exactly 80% -> B; before p4: exactly 95% -> C.
    assert classify.abc_classes({"p1": 40, "p2": 40, "p3": 15, "p4": 5}) == {
        "p1": "A", "p2": "A", "p3": "B", "p4": "C"}


def test_ties_rank_by_key_and_no_revenue_means_no_class():
    assert classify.abc_classes({"b": 10, "a": 10}) == {"a": "A", "b": "A"}
    assert classify.abc_classes({"a": 0, "b": 0}) == {"a": None, "b": None}


@pytest.mark.parametrize(("cv", "expected"), [
    (0.0, "X"), (0.4999, "X"), (0.5, "Y"), (1.0, "Y"), (1.0001, "Z"), (None, None)])
def test_xyz_thresholds(cv, expected):
    assert classify.xyz_class(cv) == expected


def test_cv_is_the_sample_standard_deviation_over_the_mean():
    weeks = [10, 12, 8, 30, 0, 9, 11, 10, 10, 12, 8, 11, 9]
    assert classify.coefficient_of_variation(weeks) == pytest.approx(statistics.stdev(weeks) / statistics.fmean(weeks))


def test_under_13_weeks_or_no_sales_is_not_classifiable():
    assert classify.coefficient_of_variation([5] * 12) is None
    assert classify.coefficient_of_variation([0] * 20) is None
    assert classify.coefficient_of_variation([5] * 13) == 0.0


def test_xyz_window_is_52_full_weeks_ending_on_or_before_date_to():
    weeks = classify.xyz_weeks(date(2026, 10, 8), data_first=date(2023, 10, 9), data_last=date(2026, 10, 8))
    assert len(weeks) == 52
    assert weeks[-1] == date(2026, 9, 28)  # the week ending Sunday 4 Oct; 5-8 Oct is not a full week
    assert weeks[0] == date(2025, 10, 6)


def test_xyz_window_stays_inside_the_history():
    weeks = classify.xyz_weeks(date(2024, 1, 31), data_first=date(2023, 10, 11), data_last=date(2026, 10, 8))
    assert weeks[0] == date(2023, 10, 16)  # the first full week of history
    assert weeks[-1] == date(2024, 1, 22)


def test_only_weeks_starting_on_or_after_launch_count():
    weeks = [date(2026, 2, 2), date(2026, 2, 9), date(2026, 2, 16)]
    assert classify.weeks_since_launch(weeks, date(2026, 2, 8)) == [date(2026, 2, 9), date(2026, 2, 16)]
