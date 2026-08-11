"""Unit tests for the Equipass Open Data pipeline. Run via `pytest tests/ -v`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "pipeline"))

import pandas as pd
import pytest

from pipeline import (
    _parse_date_flexible,
    clean,
    split_public_vs_internal,
    QualityReport,
)


def make_report():
    return QualityReport(
        generated_at="2026-01-01T00:00:00Z",
        source_file="test",
        rows_in=0, rows_out=0, duplicates_removed=0,
    )


class TestDateParsing:
    def test_iso_format(self):
        assert _parse_date_flexible("2015-03-12") == "2015-03-12"

    def test_european_slash_format(self):
        assert _parse_date_flexible("12/08/2016") == "2016-08-12"

    def test_invalid_date_returns_none(self):
        assert _parse_date_flexible("2019-13-45") is None

    def test_empty_returns_none(self):
        assert _parse_date_flexible("") is None
        assert _parse_date_flexible(None) is None

    def test_future_date_rejected(self):
        assert _parse_date_flexible("2099-01-01") is None


class TestClean:
    def test_deduplicates_on_passport_id(self):
        df = pd.DataFrame([
            {"passport_id": "PP-1", "horse_name": "A", "breed": "X", "date_of_birth": "2015-01-01",
             "country_of_birth": "FRA", "owner_name": "O1", "owner_country": "FRA",
             "microchip_number": "1" * 15, "vaccination_status": "Valid", "last_vaccination_date": "2026-01-01",
             "discipline": "Jumping", "fei_id": "FRA1", "sex": "Mare", "colour": "Bay", "sire": "S", "dam": "D", "status": "Active"},
            {"passport_id": "PP-1", "horse_name": "A", "breed": "X", "date_of_birth": "2015-01-01",
             "country_of_birth": "FRA", "owner_name": "O1", "owner_country": "FRA",
             "microchip_number": "1" * 15, "vaccination_status": "Valid", "last_vaccination_date": "2026-01-01",
             "discipline": "Jumping", "fei_id": "FRA1", "sex": "Mare", "colour": "Bay", "sire": "S", "dam": "D", "status": "Active"},
        ])
        report = make_report()
        cleaned = clean(df, report)
        assert len(cleaned) == 1
        assert report.duplicates_removed == 1

    def test_flags_missing_microchip_as_critical(self):
        df = pd.DataFrame([{
            "passport_id": "PP-2", "horse_name": "B", "breed": "X", "date_of_birth": "2015-01-01",
            "country_of_birth": "FRA", "owner_name": "O2", "owner_country": "FRA",
            "microchip_number": None, "vaccination_status": "Valid", "last_vaccination_date": "2026-01-01",
            "discipline": "Jumping", "fei_id": "FRA2", "sex": "Mare", "colour": "Bay", "sire": "S", "dam": "D", "status": "Active",
        }])
        report = make_report()
        clean(df, report)
        rule_names = [i.rule for i in report.issues]
        assert "missing_microchip_number" in rule_names
        issue = next(i for i in report.issues if i.rule == "missing_microchip_number")
        assert issue.severity == "critical"


class TestPublicationSplit:
    def test_excludes_records_missing_minimum_fields(self):
        df = pd.DataFrame([
            {"horse_name": "A", "owner_name": "O1", "fei_id": "FRA1"},
            {"horse_name": None, "owner_name": "O2", "fei_id": "FRA2"},
        ])
        public, internal = split_public_vs_internal(df)
        assert len(public) == 1
        assert len(internal) == 1


class TestQualityScore:
    def test_score_between_0_and_100(self):
        report = make_report()
        report.field_completeness = {"a": 0.9, "b": 0.8}
        assert 0 <= report.overall_score() <= 100

    def test_critical_issues_reduce_score(self):
        clean_report = make_report()
        clean_report.field_completeness = {"a": 1.0, "b": 1.0}
        dirty_report = make_report()
        dirty_report.field_completeness = {"a": 1.0, "b": 1.0}
        dirty_report.issues = [
            __import__("pipeline").QualityIssue("x", "critical", 1, "test")
        ]
        assert dirty_report.overall_score() < clean_report.overall_score()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
