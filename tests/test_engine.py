import pytest

from backend.engine import DataValidationError, compute_baseline, demo_frame, validate_table


def test_demo_has_expected_shape():
    frame = demo_frame()
    assert len(frame) >= 200
    assert frame["date"].nunique() == 30
    assert frame["dish_name"].nunique() >= 3


def test_baseline_is_deterministic_and_bounded():
    frame = demo_frame()
    first = compute_baseline(frame)
    second = compute_baseline(frame)
    assert first == second
    for row in first["dishes"]:
        assert row["baseline_qty"] >= 0


def test_missing_column_returns_row_error():
    frame = demo_frame().drop(columns=["unit_cost"])
    with pytest.raises(DataValidationError) as error:
        validate_table(frame)
    assert error.value.errors[0]["field"] == "unit_cost"


def test_invalid_values_are_rejected():
    frame = demo_frame().head(25).copy()
    frame.loc[0, "sold_qty"] = frame.loc[0, "prepared_qty"] + 1
    with pytest.raises(DataValidationError):
        validate_table(frame)
