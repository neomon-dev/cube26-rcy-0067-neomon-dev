from .models import EvidenceCheck


CHECK_KEY_MAP = {

    "receiving_quantity_match":
        "quantity_matches_po",

    "receiving_qty_match":
        "quantity_matches_po",

    "receiving_identity_match":
        "identity_matches_po",

    "receiving_carton_damage_none":
        "carton_undamaged",

    "receiving_unit_damage_none":
        "unit_undamaged",

    "prep_polybag_present":
        "polybag_present",

    "prep_polybag_sealed":
        "polybag_sealed",

    "prep_suffocation_warning_present":
        "suffocation_warning_present",

    "prep_suffocation_warning_legible":
        "suffocation_warning_legible",

    "prep_fnsku_label_flat":
        "fnsku_label_flat",

    "prep_fnsku_label_placement":
        "fnsku_label_placement_valid",

    "prep_fnsku_label_placement_valid":
        "fnsku_label_placement_valid",

    "prep_manufacturer_barcode_covered":
        "manufacturer_barcode_covered",

    "prep_expiry_date_legible":
        "expiry_date_legible",

    "prep_handling_marks_present":
        "handling_marks_present",

    "pack_all_items_present":
        "all_items_present",

    "pack_quantity_correct":
        "quantities_correct",

    "pack_quantities_correct":
        "quantities_correct",

    "pack_no_extra_items":
        "no_extra_items",

    "pack_order_line_match":
        "order_matches_manifest",

    "return_identity_match":
        "identity_matches_order",

    "returns_identity_match":
        "identity_matches_order",

    "return_completeness":
        "completeness_verified",

    "returns_completeness":
        "completeness_verified",

    "return_condition_grade":
        "condition_grade",

    "returns_condition_grade":
        "condition_grade",

    "return_disposition":
        "disposition_assigned",

    "returns_disposition":
        "disposition_assigned",
}


OFFICIAL_KEYS = set(
    CHECK_KEY_MAP.values()
)


def normalize_check(
    check: EvidenceCheck,
) -> EvidenceCheck | None:

    original = (
        str(check.check_key)
        .strip()
        .lower()
    )

    if original in OFFICIAL_KEYS:
        normalized = original
    else:
        normalized = CHECK_KEY_MAP.get(
            original
        )

    if not normalized:
        return None

    return EvidenceCheck(
        source=check.source,
        check_key=normalized,
        status=check.status,
        value=check.value,
        reason=check.reason,
        fields=check.fields,
        event_date=check.event_date,
    )


def normalize_checks(
    checks: list[EvidenceCheck],
) -> list[EvidenceCheck]:

    normalized = []

    for check in checks:

        result = normalize_check(
            check
        )

        if result is not None:
            normalized.append(result)

    return normalized