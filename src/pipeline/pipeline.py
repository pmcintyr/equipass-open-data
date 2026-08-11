"""
FEI Equine Digital Passport — Open Data Pipeline
==================================================

Proof-of-concept pipeline that ingests raw passport records, cleans and
validates them, and publishes an Open Data–compliant dataset (CSV + JSON,
with a companion data dictionary) plus a machine-readable data-quality
report used by the dashboard prototype (see 02-data-quality-dashboard/).

Design goals for this demo:
  - No exotic dependencies: pandas + standard library only.
  - Deterministic, idempotent, re-runnable on any raw extract with the
    same column layout.
  - Every cleaning decision is logged and quantified, not silently applied,
    because for an Open Data publication the quality of the data is the
    product.

Usage:
    python pipeline.py --input data/raw/equine_passports_raw.csv --outdir output/

Author: Paul (candidate prep for FEI Junior Data Analyst — Equipass)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("equipass-pipeline")

REQUIRED_COLUMNS = [
    "passport_id", "horse_name", "breed", "date_of_birth", "country_of_birth",
    "owner_name", "owner_country", "microchip_number", "vaccination_status",
    "last_vaccination_date", "discipline", "fei_id", "sex", "colour",
    "sire", "dam", "status",
]

VALID_VACCINATION_STATUSES = {"Valid", "Expired", "Unknown"}
VALID_DISCIPLINES = {"Jumping", "Dressage", "Eventing", "Driving", "Endurance", "Vaulting"}
MICROCHIP_PATTERN = re.compile(r"^\d{15}$")  # ISO 11784/11785 format


@dataclass
class QualityIssue:
    rule: str
    severity: str  # "critical" | "warning"
    count: int
    description: str


@dataclass
class QualityReport:
    generated_at: str
    source_file: str
    rows_in: int
    rows_out: int
    duplicates_removed: int
    issues: list = field(default_factory=list)
    field_completeness: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "source_file": self.source_file,
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "duplicates_removed": self.duplicates_removed,
            "issues": [i.__dict__ for i in self.issues],
            "field_completeness": self.field_completeness,
            "overall_quality_score": self.overall_score(),
        }

    def overall_score(self) -> float:
        """Simple composite score: mean field completeness minus a
        penalty per critical issue category. Kept transparent on purpose
        rather than a black-box score, since this feeds a dashboard an
        analyst has to be able to explain to stakeholders."""
        if not self.field_completeness:
            return 0.0
        completeness = sum(self.field_completeness.values()) / len(self.field_completeness)
        penalty = 0.03 * sum(1 for i in self.issues if i.severity == "critical")
        return round(max(0.0, min(1.0, completeness - penalty)) * 100, 1)


def load_raw(path: Path) -> pd.DataFrame:
    log.info("Loading raw extract: %s", path)
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    missing_cols = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing_cols:
        raise ValueError(f"Raw file is missing expected columns: {missing_cols}")
    log.info("Loaded %d rows / %d columns", len(df), len(df.columns))
    return df


def _parse_date_flexible(value):
    """Attempt several known FEI/national date formats before giving up.
    Returns ISO date string or None (never raises)."""
    if pd.isna(value) or not str(value).strip():
        return None
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            d = datetime.strptime(value, fmt).date()
            if d > date.today() or d.year < 1990:
                return None  # implausible date, treat as invalid rather than guess
            return d.isoformat()
        except ValueError:
            continue
    return None  # unparseable, e.g. "2019-13-45"


def clean(df: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    df = df.copy()

    # 1. Deduplicate on passport_id (exact duplicate rows in this extract)
    before = len(df)
    df = df.drop_duplicates(subset=["passport_id"], keep="first")
    report.duplicates_removed = before - len(df)
    if report.duplicates_removed:
        log.info("Removed %d duplicate passport_id rows", report.duplicates_removed)

    # 2. Normalise whitespace / empty-string -> NaN across all text fields
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"": None, "nan": None, "None": None})

    # 3. Parse and validate dates
    df["date_of_birth_clean"] = df["date_of_birth"].apply(_parse_date_flexible)
    invalid_dob = df["date_of_birth_clean"].isna() & df["date_of_birth"].notna()
    if invalid_dob.any():
        report.issues.append(QualityIssue(
            rule="invalid_date_of_birth",
            severity="critical",
            count=int(invalid_dob.sum()),
            description="date_of_birth could not be parsed against known FEI/national formats "
                        "(e.g. '2019-13-45') — flagged for manual correction, not guessed.",
        ))

    df["last_vaccination_date_clean"] = df["last_vaccination_date"].apply(_parse_date_flexible)

    # 4. Validate microchip format (ISO 11784/11785 — 15 digits)
    chip_missing = df["microchip_number"].isna()
    chip_present = ~chip_missing
    chip_invalid = chip_present & ~df["microchip_number"].fillna("").str.match(MICROCHIP_PATTERN)
    if chip_missing.any():
        report.issues.append(QualityIssue(
            rule="missing_microchip_number",
            severity="critical",
            count=int(chip_missing.sum()),
            description="Records without a microchip number cannot be reliably deduplicated "
                        "across national federations — critical for Open Data publication.",
        ))
    if chip_invalid.any():
        report.issues.append(QualityIssue(
            rule="invalid_microchip_format",
            severity="warning",
            count=int(chip_invalid.sum()),
            description="Microchip number does not match the expected 15-digit ISO 11784/11785 format.",
        ))

    # 5. Validate controlled vocabularies
    bad_vacc = df["vaccination_status"].notna() & ~df["vaccination_status"].isin(VALID_VACCINATION_STATUSES)
    bad_disc = df["discipline"].notna() & ~df["discipline"].isin(VALID_DISCIPLINES)
    if bad_vacc.any():
        report.issues.append(QualityIssue(
            rule="unrecognised_vaccination_status", severity="warning",
            count=int(bad_vacc.sum()),
            description="vaccination_status outside controlled vocabulary {Valid, Expired, Unknown}.",
        ))
    if bad_disc.any():
        report.issues.append(QualityIssue(
            rule="unrecognised_discipline", severity="warning",
            count=int(bad_disc.sum()),
            description="discipline outside FEI's seven recognised disciplines.",
        ))

    # 6. Flag missing horse_name / owner_name (required for public dataset)
    for field_name in ("horse_name", "owner_name"):
        n_missing = df[field_name].isna().sum()
        if n_missing:
            report.issues.append(QualityIssue(
                rule=f"missing_{field_name}",
                severity="critical",
                count=int(n_missing),
                description=f"{field_name} missing — record excluded from the public Open Data export "
                             "(PII/identification minimum not met) but retained in the internal log.",
            ))

    # 7. Derive a computed 'age_years' field — useful, cheap, and a nice
    #    demonstration of value-add transformation beyond pure cleaning.
    def _age(iso_date):
        if not iso_date or (isinstance(iso_date, float) and pd.isna(iso_date)):
            return None
        d = datetime.strptime(iso_date, "%Y-%m-%d").date()
        today = date.today()
        return today.year - d.year - ((today.month, today.day) < (d.month, d.day))

    df["age_years"] = df["date_of_birth_clean"].apply(_age)

    # 8. Compute field completeness for the report
    for col in REQUIRED_COLUMNS:
        report.field_completeness[col] = round(1 - df[col].isna().mean(), 3)

    return df


def split_public_vs_internal(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Open Data publication rule: a record only goes into the public
    export if it has the minimum identification fields. Everything else
    stays in an internal log for the data team to chase up — this mirrors
    a real Open Data governance workflow rather than silently dropping rows."""
    minimum_ok = df["horse_name"].notna() & df["owner_name"].notna() & df["fei_id"].notna()
    return df[minimum_ok].copy(), df[~minimum_ok].copy()


PUBLIC_COLUMNS = [
    "fei_id", "passport_id", "horse_name", "breed", "date_of_birth_clean", "age_years",
    "sex", "colour", "country_of_birth", "discipline", "vaccination_status",
    "last_vaccination_date_clean", "status",
]


def write_open_data(public_df: pd.DataFrame, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    export = public_df[PUBLIC_COLUMNS].rename(columns={
        "date_of_birth_clean": "date_of_birth",
        "last_vaccination_date_clean": "last_vaccination_date",
    })

    csv_path = outdir / "equine_passports_open_data.csv"
    json_path = outdir / "equine_passports_open_data.json"
    export.to_csv(csv_path, index=False)
    export.to_json(json_path, orient="records", indent=2, date_format="iso")
    log.info("Published Open Data export: %s (%d rows)", csv_path.name, len(export))
    log.info("Published Open Data export: %s (%d rows)", json_path.name, len(export))

    dictionary = {
        "fei_id": "FEI-issued unique identifier for the horse (national federation + number).",
        "passport_id": "Unique identifier of this digital passport record.",
        "horse_name": "Registered name of the horse.",
        "breed": "Declared breed / studbook.",
        "date_of_birth": "ISO-8601 date of birth, validated against known source formats.",
        "age_years": "Computed age in years as of the export date.",
        "sex": "Stallion / Mare / Gelding.",
        "colour": "Coat colour as declared on the passport.",
        "country_of_birth": "ISO 3166-1 alpha-3 country code.",
        "discipline": "FEI discipline the horse is registered to compete in.",
        "vaccination_status": "Valid / Expired / Unknown as of last recorded check.",
        "last_vaccination_date": "ISO-8601 date of the last recorded vaccination.",
        "status": "Active / Inactive registration status.",
        "_licence": "CC-BY 4.0 (demo) — mirrors FEI Open Data publication conventions.",
        "_update_frequency": "Daily, via automated pipeline run.",
    }
    with open(outdir / "data_dictionary.json", "w") as f:
        json.dump(dictionary, f, indent=2)
    log.info("Published data dictionary: data_dictionary.json")


def write_quality_report(report: QualityReport, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "data_quality_report.json"
    with open(path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)
    log.info("Published data-quality report: %s (score: %s/100)", path.name, report.overall_score())


def write_internal_log(internal_df: pd.DataFrame, outdir: Path) -> None:
    if internal_df.empty:
        return
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "records_pending_review.csv"
    internal_df.to_csv(path, index=False)
    log.info("Logged %d record(s) pending manual review: %s", len(internal_df), path.name)


def run(input_path: Path, outdir: Path) -> QualityReport:
    report = QualityReport(
        generated_at=datetime.now().isoformat() + "Z",
        source_file=str(input_path),
        rows_in=0, rows_out=0, duplicates_removed=0,
    )
    raw = load_raw(input_path)
    report.rows_in = len(raw)

    cleaned = clean(raw, report)
    public_df, internal_df = split_public_vs_internal(cleaned)
    report.rows_out = len(public_df)

    write_open_data(public_df, outdir / "public")
    write_internal_log(internal_df, outdir / "internal")
    write_quality_report(report, outdir)

    log.info(
        "Pipeline complete: %d/%d records published (%.0f%%), quality score %s/100",
        report.rows_out, report.rows_in,
        100 * report.rows_out / report.rows_in if report.rows_in else 0,
        report.overall_score(),
    )
    return report


def main():
    parser = argparse.ArgumentParser(description="FEI Equine Digital Passport Open Data pipeline")
    parser.add_argument("--input", type=Path, default=Path("data/raw/equine_passports_raw.csv"))
    parser.add_argument("--outdir", type=Path, default=Path("output"))
    args = parser.parse_args()
    run(args.input, args.outdir)


if __name__ == "__main__":
    main()
