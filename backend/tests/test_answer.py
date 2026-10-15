"""The grounding rules of the answer node, without calling a model."""

from agent.answer import fill, fmt, grounded_text

RESULT = {"columns": ["region", "total_sales"],
          "rows": [["North", 110286000.5], ["West", 100253000.0], ["East", 56551000.0]],
          "truncated": False, "tables": ["orders"]}


def test_placeholders_are_filled_from_the_result():
    text, ok = fill("{{region[0]|text}} led with {{total_sales[0]|inr}} of {{sum:total_sales|inr}}.", RESULT)
    assert ok and text == "North led with ₹11.03 Cr of ₹26.71 Cr."


def test_count_placeholder():
    assert fill("{{count}} regions", RESULT) == ("3 regions", True)


def test_a_number_the_model_typed_is_dropped():
    text, dropped = grounded_text("North led with ₹4.8 Cr. {{region[0]|text}} was first.", RESULT, "sales by region")
    assert text == "North was first." and dropped == 1


def test_an_unknown_placeholder_drops_its_sentence():
    text, dropped = grounded_text("Profit was {{profit[0]|inr}}. {{region[2]|text}} was last.", RESULT, "q")
    assert text == "East was last." and dropped == 1


def test_a_row_out_of_range_drops_its_sentence():
    text, dropped = grounded_text("{{region[9]|text}} is tenth.", RESULT, "q")
    assert text == "" and dropped == 1


def test_numbers_from_the_question_may_be_repeated():
    text, dropped = grounded_text("Orders over ₹50,000 are shown below.", RESULT, "just the ones over ₹50,000")
    assert dropped == 0 and "50,000" in text


def test_years_and_days_are_not_treated_as_figures():
    text, dropped = grounded_text("In March 2025, {{region[0]|text}} led.", RESULT, "march sales")
    assert dropped == 0


def test_formats():
    assert fmt(48215330, "inr") == "₹4.82 Cr"
    assert fmt(250000, "inr") == "₹2.50 L"
    assert fmt(64999, "inr") == "₹64,999"
    assert fmt(1234567, "number") == "12,34,567"
    assert fmt(12.345, "percent") == "12.3%"
    assert fmt(None, "inr") == "no value"
