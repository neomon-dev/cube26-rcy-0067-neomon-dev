from pathlib import Path
import pandas as pd
import shutil

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
FEE = DATA / "fee_report_sample.csv"
UP = DATA / "upstream"

if not FEE.exists():
    raise FileNotFoundError(
        f"Fee report not found: {FEE}"
    )

if not UP.exists():
    raise FileNotFoundError(
        f"Upstream directory not found: {UP}"
    )


# ============================================================
# BACKUP
# ============================================================

backup = DATA / "backup_before_demo_dataset"

if not backup.exists():
    backup.mkdir(parents=True)

for path in [FEE, *UP.glob("*.csv")]:
    destination = backup / path.name

    if not destination.exists():
        shutil.copy2(
            path,
            destination,
        )

print()
print("Backup created at:")
print(backup)


# ============================================================
# FEE REPORT
# ============================================================

fee = pd.read_csv(
    FEE,
    dtype=str,
).fillna("")

print()
print("Fee report columns:")
print(list(fee.columns))


# Your loader uses:
#
# charge_id = charge_id column
#              OR
#              line_id
#
# Therefore support both formats.

if "charge_id" in fee.columns:

    fee_id_column = "charge_id"

elif "line_id" in fee.columns:

    fee_id_column = "line_id"

else:

    raise ValueError(
        "Could not find charge identifier column. "
        f"Found columns: {list(fee.columns)}"
    )


print(
    f"Using '{fee_id_column}' as fee identifier."
)


# ============================================================
# INBOUND DEFECT SUBTYPES
# ============================================================

subtypes = {

    "FEE-0014-1":
        "inbound_defect_unbagged",

    "FEE-0018-1":
        "missing_suffocation_warning",

    "FEE-0026-1":
        "unscannable_barcode",

    "FEE-0035-1":
        "manufacturer_barcode_visible",

    "FEE-0061-1":
        "unplanned_prep_labelling",

    "FEE-0071-1":
        "unplanned_prep_bagging",

    "FEE-0074-1":
        "inbound_defect_unbagged",

    "FEE-0095-1":
        "unplanned_prep_bagging",

    "FEE-0096-1":
        "unscannable_barcode",
}


# ============================================================
# UPDATE FEE ROWS
# ============================================================

for fee_id, subtype in subtypes.items():

    mask = (
        fee[fee_id_column]
        .astype(str)
        .str.strip()
        == fee_id
    )

    if not mask.any():

        print(
            f"WARNING: {fee_id} not found"
        )

        continue

    if "charge_subtype" not in fee.columns:
        fee["charge_subtype"] = ""

    fee.loc[
        mask,
        "charge_subtype"
    ] = subtype

    if "description" in fee.columns:

        fee.loc[
            mask,
            "description"
        ] = subtype


# ============================================================
# POSITIVE CLAIM AMOUNTS
# ============================================================

amounts = {

    "FEE-0014-1": "2.00",
    "FEE-0018-1": "1.00",
    "FEE-0026-1": "1.00",
    "FEE-0035-1": "0.50",
    "FEE-0061-1": "2.00",
    "FEE-0071-1": "1.00",
    "FEE-0074-1": "0.50",
    "FEE-0095-1": "0.50",
    "FEE-0096-1": "2.00",

}


if "amount_usd" not in fee.columns:

    raise ValueError(
        "fee_report_sample.csv does not contain "
        "'amount_usd'."
    )


for fee_id, amount in amounts.items():

    mask = (
        fee[fee_id_column]
        .astype(str)
        .str.strip()
        == fee_id
    )

    if not mask.any():
        continue

    fee.loc[
        mask,
        "amount_usd"
    ] = amount


# Keep optional amount columns synchronized
for column in (
    "amount",
    "amount_total",
    "amount_per_unit",
):

    if column in fee.columns:

        for fee_id, amount in amounts.items():

            mask = (
                fee[fee_id_column]
                .astype(str)
                .str.strip()
                == fee_id
            )

            fee.loc[
                mask,
                column
            ] = amount


fee.to_csv(
    FEE,
    index=False,
)


# ============================================================
# UPSTREAM FILE DISCOVERY
# ============================================================

def find_csv(keyword):

    matches = list(
        UP.glob(
            f"*{keyword}*.csv"
        )
    )

    if not matches:

        raise FileNotFoundError(
            f"No CSV containing '{keyword}' "
            f"found in {UP}"
        )

    return matches[0]


prep_path = find_csv("prep")

prep = pd.read_csv(
    prep_path,
    dtype=str,
).fillna("")


print()
print("Prep file:")
print(prep_path)

print()
print("Prep columns:")
print(list(prep.columns))


# ============================================================
# PREP HELPER
# ============================================================

if "unit_id" not in prep.columns:

    raise ValueError(
        "prep CSV has no unit_id column."
    )


def set_prep(
    unit_id,
    **values,
):

    mask = (
        prep["unit_id"]
        .astype(str)
        .str.strip()
        == unit_id
    )

    if not mask.any():

        raise ValueError(
            f"{unit_id} not found in "
            f"{prep_path.name}"
        )

    for column, value in values.items():

        if column not in prep.columns:

            raise ValueError(
                f"Column '{column}' does not exist "
                f"in {prep_path.name}. "
                f"Available columns: "
                f"{list(prep.columns)}"
            )

        prep.loc[
            mask,
            column
        ] = value


# ============================================================
# CREATE REALISTIC DEMO CASES
# ============================================================

# ------------------------------------------------------------
# CLAIM
# inbound_defect_unbagged
# ------------------------------------------------------------

set_prep(
    "UNIT-0014",
    polybag_present_sealed="no",
)


# ------------------------------------------------------------
# REVIEW / CONTRADICTED
# missing_suffocation_warning
# ------------------------------------------------------------

set_prep(
    "UNIT-0018",
    suffocation_warning="legible",
)


# ------------------------------------------------------------
# CLAIM
# unscannable_barcode
# ------------------------------------------------------------

set_prep(
    "UNIT-0026",
    fnsku_label_placement="invalid",
)


# ------------------------------------------------------------
# CLAIM
# manufacturer barcode visible
# ------------------------------------------------------------

set_prep(
    "UNIT-0035",
    original_barcode_covered="no",
)


# ------------------------------------------------------------
# CLAIM
# unplanned prep labelling
# ------------------------------------------------------------

set_prep(
    "UNIT-0061",
    fnsku_label_placement="missing",
)


# ------------------------------------------------------------
# CLAIM
# unplanned prep bagging
# ------------------------------------------------------------

set_prep(
    "UNIT-0071",
    polybag_present_sealed="no",
)


# ------------------------------------------------------------
# REVIEW / UNCERTAIN
# ------------------------------------------------------------

set_prep(
    "UNIT-0074",
    polybag_present_sealed="uncertain",
)


# ------------------------------------------------------------
# REVIEW / CONTRADICTED
# ------------------------------------------------------------

set_prep(
    "UNIT-0095",
    polybag_present_sealed="yes",
)


# ------------------------------------------------------------
# REVIEW / UNCERTAIN
# ------------------------------------------------------------

set_prep(
    "UNIT-0096",
    fnsku_label_placement="uncertain",
)


# ============================================================
# SAVE PREP
# ============================================================

prep.to_csv(
    prep_path,
    index=False,
)


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 60)
print("DEMO DATASET UPDATED")
print("=" * 60)

print()
print("Fee report:")
print(FEE)

print()
print("Prep evidence:")
print(prep_path)

print()
print("Backup:")
print(backup)

print()
print("Inbound defect mappings:")

for fee_id, subtype in subtypes.items():

    print(
        f"  {fee_id} -> {subtype}"
    )

print()
print("Expected demo behavior:")
print()
print("  CLAIM:")
print("    UNIT-0014")
print("    UNIT-0026")
print("    UNIT-0035")
print("    UNIT-0061")
print("    UNIT-0071")
print()
print("  REVIEW / CONTRADICTED:")
print("    UNIT-0018")
print("    UNIT-0095")
print()
print("  REVIEW / UNCERTAIN:")
print("    UNIT-0074")
print("    UNIT-0096")
print()
print("Now run:")
print()
print("  python -u evaluate.py")
print()