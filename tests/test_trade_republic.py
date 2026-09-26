import pytest

from patrimoine.sources.trade_republic import LoginRequired, normalize_phone


@pytest.mark.parametrize("raw", ["06 12 34 56 78", "0612345678", "+33 6 12 34 56 78", "0033612345678", "06.12.34.56.78"])
def test_phone_is_put_in_international_format(raw):
    assert normalize_phone(raw) == "+33612345678"


def test_foreign_number_is_kept():
    assert normalize_phone("+49 151 1234 5678") == "+4915112345678"


@pytest.mark.parametrize("raw", ["", "abc", "+33"])
def test_bad_phone_is_rejected(raw):
    with pytest.raises(LoginRequired):
        normalize_phone(raw)
