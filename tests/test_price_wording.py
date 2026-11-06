"""Exact wording of price answers, labels and the lease note, added to kill surviving mutants.

See docs/testing-price-tool.md. Expected strings are written out in full by hand.
"""

from decimal import Decimal

import pytest

from kopi_keys.components.price_display import lease_note, price_answer, subject_label
from kopi_keys.schemas import BandStat, PriceFilters, PriceResult

FILTERS = PriceFilters(town="TOA PAYOH", flat_type="5 ROOM", start_month="2025-11", end_month="2026-10")
STATS = dict(query_id="price-36090aa3d523", filters=FILTERS, volume=143, mean="1079268.31",
             median="1050000.00", iqr="432500.00", minimum="510000", maximum="1588000")
PRICE = PriceResult(**STATS)
VERIFIED = """Mean: SGD 1,079,268.31
Median: SGD 1,050,000.00
IQR: SGD 432,500.00
Range: SGD 510,000.00 to SGD 1,588,000.00
Volume: 143 transactions"""
SOURCE = ("*Source: HDB resale flat prices (data.gov.sg). "
          "Past sales only, not a valuation of any particular flat.*")


def lease(*bands, storey=()):
    """Breakdown from (band, volume, median) tuples."""
    out = [BandStat(dimension="lease", band=b, volume=v, median=Decimal(m)) for b, v, m in bands]
    return out + [BandStat(dimension="storey", band=b, volume=v, median=Decimal(m)) for b, v, m in storey]


def priced(breakdown, **changes):
    return PriceResult(**{**STATS, "breakdown": breakdown, **changes})


# --- subject labels for every band ------------------------------------------

@pytest.mark.parametrize("bands, text", [
    ({"lease_band": "under_60"}, "5-room flats in Toa Payoh with under 60 years of lease left"),
    ({"lease_band": "60_79"}, "5-room flats in Toa Payoh with 60 to 79 years of lease left"),
    ({"lease_band": "80_plus"}, "5-room flats in Toa Payoh with 80+ years of lease left"),
    ({"storey_band": "low"}, "5-room flats in Toa Payoh on low floors (1 to 6)"),
    ({"storey_band": "mid"}, "5-room flats in Toa Payoh on middle floors (7 to 12)"),
    ({"storey_band": "high"}, "5-room flats in Toa Payoh on high floors (13+)"),
])
def test_subject_label_for_every_band(bands, text):
    assert subject_label(FILTERS.model_copy(update=bands)) == text


# --- lease note -------------------------------------------------------------

THREE_BANDS = lease(("under_60", 5, "600000"), ("60_79", 5, "800000"), ("80_plus", 5, "1000000"),
                    # Floor bands must be ignored; they would give a different (or no) note.
                    storey=[("low", 5, "100000"), ("mid", 5, "200000"), ("high", 5, "5000000")])
THREE_BANDS_NOTE = ("Remaining lease matters here: the median ranges from $600,000 (under 60 years left) "
                    "to $1,000,000 (80+ years left). Use **Narrow it down** below to compare like with like.")


def test_lease_note_names_the_lowest_and_highest_lease_band_medians():
    assert lease_note(priced(THREE_BANDS)) == THREE_BANDS_NOTE


def test_lease_note_counts_bands_with_5_sales_but_not_4():
    # under_60 has 4 sales, so only 60_79 and 80_plus count: 1,000,000 / 800,000 = 1.25 >= 1.1.
    note = lease_note(priced(lease(("under_60", 4, "100000"), ("60_79", 5, "800000"), ("80_plus", 5, "1000000"))))
    assert note == ("Remaining lease matters here: the median ranges from $800,000 (60 to 79 years left) "
                    "to $1,000,000 (80+ years left). Use **Narrow it down** below to compare like with like.")


def test_lease_note_needs_two_bands():
    assert lease_note(priced(lease(("60_79", 5, "800000"), ("80_plus", 4, "1000000")))) is None


@pytest.mark.parametrize("high, shown", [
    ("1100000", True),    # 1,100,000 / 1,000,000 = 1.10 exactly: shown
    ("1050000", False),   # 1.05: too small a gap to mention
])
def test_lease_note_threshold_is_a_gap_of_at_least_10_percent(high, shown):
    note = lease_note(priced(lease(("60_79", 5, "1000000"), ("80_plus", 5, high))))
    assert (note is not None) is shown


def test_no_lease_note_once_a_lease_band_is_chosen():
    chosen = FILTERS.model_copy(update={"lease_band": "80_plus"})
    assert lease_note(priced(THREE_BANDS, filters=chosen)) is None


# --- full answers -----------------------------------------------------------

SUMMARY = ("**5-room flats in Toa Payoh** sold for a median of **$1,050,000** (Nov 2025 to Oct 2026, 143 sales).\n\n"
           "- Average (mean): $1,079,268.31\n"
           "- Middle 50% of prices fall within a $432,500 band\n"
           "- Lowest to highest: $510,000 to $1,588,000\n\n")


def test_summary_answer_exact_text():
    assert price_answer(VERIFIED, PRICE) == SUMMARY + SOURCE


def test_summary_answer_with_the_lease_note():
    assert price_answer(VERIFIED, priced(THREE_BANDS)) == SUMMARY + THREE_BANDS_NOTE + "\n\n" + SOURCE


def test_sales_count_with_a_thousands_separator():
    text = price_answer(VERIFIED.replace("143 transactions", "1,234 transactions"), PRICE)
    assert "(Nov 2025 to Oct 2026, 1,234 sales)" in text


def test_four_sales_exact_text():
    text = price_answer(VERIFIED.replace("143 transactions", "4 transactions"), PRICE)
    assert text == ("**5-room flats in Toa Payoh** had only 4 matching sales (Nov 2025 to Oct 2026): "
                    "too few for a reliable summary, and not a guide to what any particular flat is worth. "
                    "They sold for $510,000 to $1,588,000; each sale is listed below. "
                    "Widen the filters for a summary.\n\n" + SOURCE)


def test_one_sale_exact_text():
    one = ("Mean: SGD 600,000.00\nMedian: SGD 600,000.00\nIQR: SGD 0.00\n"
           "Range: SGD 600,000.00 to SGD 600,000.00\nVolume: 1 transaction")
    assert price_answer(one, PRICE) == (
        "**5-room flats in Toa Payoh** had only 1 matching sale (Nov 2025 to Oct 2026): "
        "too few for a reliable summary, and not a guide to what any particular flat is worth. "
        "It sold for $600,000; each sale is listed below. Widen the filters for a summary.\n\n" + SOURCE)


def test_unexpected_layout_lists_each_verified_line():
    text = price_answer("Median: SGD 1,050,000.00\n\nMean: SGD 1,079,268.31", PRICE)
    assert text == ("**5-room flats in Toa Payoh**, Nov 2025 to Oct 2026\n\n"
                    "- Median: SGD 1,050,000.00\n- Mean: SGD 1,079,268.31")
