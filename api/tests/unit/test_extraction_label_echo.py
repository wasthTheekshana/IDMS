from app.services.extraction import _discard_label_echoes


def test_discards_value_that_exactly_echoes_its_own_label() -> None:
    fields = [{"key": "proof_of_delivery_note", "label": "PROOF OF DELIVERY NOTE"}]
    data = {"proof_of_delivery_note": "PROOF OF DELIVERY NOTE"}

    _discard_label_echoes(data, fields)

    assert data["proof_of_delivery_note"] is None


def test_discards_case_insensitively_and_ignores_surrounding_whitespace() -> None:
    fields = [{"key": "invoice_no", "label": "Invoice Number"}]
    data = {"invoice_no": "  invoice number  "}

    _discard_label_echoes(data, fields)

    assert data["invoice_no"] is None


def test_keeps_a_real_extracted_value() -> None:
    fields = [{"key": "proof_of_delivery_note", "label": "PROOF OF DELIVERY NOTE"}]
    data = {"proof_of_delivery_note": "1808350"}

    _discard_label_echoes(data, fields)

    assert data["proof_of_delivery_note"] == "1808350"


def test_leaves_non_string_and_already_null_values_untouched() -> None:
    fields = [
        {"key": "weight", "label": "Weight"},
        {"key": "no_of_pks", "label": "No. of Pks"},
    ]
    data = {"weight": None, "no_of_pks": 3}

    _discard_label_echoes(data, fields)

    assert data["weight"] is None
    assert data["no_of_pks"] == 3
