from kopi_keys.components.price_display import flat_label, money, period_label, price_answer, town_label
from kopi_keys.schemas import PriceFilters, PriceResult

# Toa Payoh 5-room, Nov 2025 to Oct 2026, as returned by the price tool and checked against the raw CSV.
PRICE = PriceResult(
    query_id="price-36090aa3d523",
    filters=PriceFilters(town="TOA PAYOH", flat_type="5 ROOM", start_month="2025-11", end_month="2026-10"),
    volume=143, mean="1079268.31", median="1050000.00", iqr="432500.00", minimum="510000", maximum="1588000",
)
VERIFIED = """Mean: SGD 1,079,268.31
Median: SGD 1,050,000.00
IQR: SGD 432,500.00
Range: SGD 510,000.00 to SGD 1,588,000.00
Volume: 143 transactions"""


def test_answer_leads_with_the_median_and_keeps_every_verified_figure():
    text = price_answer(VERIFIED, PRICE)
    assert text.startswith("**5-room flats in Toa Payoh** sold for a median of **$1,050,000**")
    assert "(Nov 2025 to Oct 2026, 143 sales)" in text
    for figure in ("$1,079,268.31", "$432,500", "$510,000 to $1,588,000"):
        assert figure in text
    assert "price-36090aa3d523" not in text and "SGD" not in text


def test_labels():
    assert money("1,050,000.00") == "$1,050,000" and money("650000.13") == "$650,000.13"
    assert flat_label("EXECUTIVE") == "Executive" and flat_label("3 ROOM") == "3-room"
    assert town_label("KALLANG/WHAMPOA") == "Kallang/Whampoa"
    assert period_label(PriceFilters(town="X", flat_type="4 ROOM", start_month="2025-01", end_month="2025-01")) == "Jan 2025"


def test_one_sale_is_singular_and_unexpected_layout_falls_back_to_the_verified_lines():
    one = VERIFIED.replace("143 transactions", "1 transactions")
    text = price_answer(one, PRICE)
    assert "only 1 matching sale" in text and "median" not in text
    fallback = price_answer("Median: SGD 1,050,000.00", PRICE)
    assert "- Median: SGD 1,050,000.00" in fallback


def test_fewer_than_five_sales_lists_sales_instead_of_a_median():
    few = VERIFIED.replace("143 transactions", "4 transactions")
    text = price_answer(few, PRICE)
    assert "only 4 matching sales" in text and "too few for a reliable summary" in text
    assert "$510,000 to $1,588,000" in text and "median" not in text
    assert "median of" in price_answer(VERIFIED.replace("143 transactions", "5 transactions"), PRICE)
