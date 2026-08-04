import pytest

from toss_mcp.formatting import compute_change, pick


def test_pick_keeps_only_requested_keys_that_exist():
    row = {"a": 1, "b": 2, "c": 3}

    assert pick(row, "a", "c", "missing") == {"a": 1, "c": 3}


def test_pick_keeps_explicit_nulls():
    """A null timestamp is information: the stock has not traded today."""
    assert pick({"timestamp": None, "x": 1}, "timestamp") == {"timestamp": None}


def test_pick_on_non_dict_returns_empty():
    assert pick(None, "a") == {}
    assert pick(["not", "a", "dict"], "a") == {}


def test_rise():
    assert compute_change("72000", "71000") == {
        "prevClose": "71000",
        "change": "1000",
        "changeRate": "1.41",
    }


def test_fall():
    result = compute_change("70000", "71000")

    assert result["change"] == "-1000"
    assert result["changeRate"] == "-1.41"


def test_flat():
    assert compute_change("71000", "71000") == {
        "prevClose": "71000",
        "change": "0",
        "changeRate": "0.00",
    }


def test_decimal_precision_is_preserved():
    """Floats would turn 0.1 + 0.2 style arithmetic into 3.0000000000000004."""
    result = compute_change("100.30", "100.10")

    assert result["change"] == "0.20"


@pytest.mark.parametrize("prev", ["0", "0.00", "", None, "n/a", "abc"])
def test_unusable_previous_close_yields_nothing(prev):
    assert compute_change("72000", prev) == {}


@pytest.mark.parametrize("last", ["", None, "n/a"])
def test_unusable_last_price_yields_nothing(last):
    assert compute_change(last, "71000") == {}
