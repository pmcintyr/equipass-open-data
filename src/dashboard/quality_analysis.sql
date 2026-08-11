-- =====================================================================
-- FEI Equine Digital Passport — Data Quality Analysis (SQL)
-- =====================================================================
-- Written against the cleaned table produced by the Python pipeline
-- (01-open-data-pipeline). Portable ANSI SQL, tested against SQLite
-- and directly usable as the source query set for a Power BI dataset
-- (Get Data > Database, or as a DirectQuery/Import source view).
--
-- Assumes a table `passports` with the schema of
-- output/public/equine_passports_open_data.csv, plus the internal
-- log as `passports_pending_review`.
-- =====================================================================

-- 1. FIELD-LEVEL COMPLETENESS
-- Powers the "completeness by field" bar chart in the dashboard.
SELECT
    'vaccination_status' AS field_name,
    COUNT(*) AS total_records,
    SUM(CASE WHEN vaccination_status IS NOT NULL THEN 1 ELSE 0 END) AS populated,
    ROUND(100.0 * SUM(CASE WHEN vaccination_status IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS completeness_pct
FROM passports
UNION ALL
SELECT 'last_vaccination_date', COUNT(*),
       SUM(CASE WHEN last_vaccination_date IS NOT NULL THEN 1 ELSE 0 END),
       ROUND(100.0 * SUM(CASE WHEN last_vaccination_date IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM passports
UNION ALL
SELECT 'microchip_number', COUNT(*),
       SUM(CASE WHEN microchip_number IS NOT NULL THEN 1 ELSE 0 END),
       ROUND(100.0 * SUM(CASE WHEN microchip_number IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM passports;


-- 2. VACCINATION COMPLIANCE BY DISCIPLINE
-- Directly actionable for the Equipass team: which discipline has the
-- weakest vaccination data trail?
SELECT
    discipline,
    COUNT(*) AS horses,
    SUM(CASE WHEN vaccination_status = 'Valid' THEN 1 ELSE 0 END) AS valid_vaccination,
    SUM(CASE WHEN vaccination_status = 'Expired' THEN 1 ELSE 0 END) AS expired_vaccination,
    SUM(CASE WHEN vaccination_status IS NULL OR vaccination_status = 'Unknown' THEN 1 ELSE 0 END) AS unknown_vaccination,
    ROUND(100.0 * SUM(CASE WHEN vaccination_status = 'Valid' THEN 1 ELSE 0 END) / COUNT(*), 1) AS compliance_pct
FROM passports
GROUP BY discipline
ORDER BY compliance_pct ASC;


-- 3. RECORDS FLAGGED FOR VETERINARY FOLLOW-UP
-- Vaccination expired or unknown AND status still Active — these are the
-- horses currently eligible to compete without a confirmed valid record.
SELECT
    fei_id, horse_name, discipline, country_of_birth,
    vaccination_status, last_vaccination_date
FROM passports
WHERE status = 'Active'
  AND (vaccination_status IN ('Expired', 'Unknown') OR vaccination_status IS NULL)
ORDER BY discipline, country_of_birth;


-- 4. DATA QUALITY TREND INPUT (for a time-series visual)
-- In production this would aggregate one row per pipeline run, read
-- from data_quality_report.json (loaded into a `quality_runs` table).
-- Kept here as the query shape the dashboard expects.
SELECT
    run_date,
    overall_quality_score,
    rows_in,
    rows_out,
    ROUND(100.0 * rows_out / rows_in, 1) AS publication_rate_pct
FROM quality_runs
ORDER BY run_date;


-- 5. RECORDS PENDING MANUAL REVIEW — ROOT CAUSE BREAKDOWN
-- Why did a record fail to reach the public Open Data export?
SELECT
    CASE
        WHEN horse_name IS NULL THEN 'Missing horse_name'
        WHEN owner_name IS NULL THEN 'Missing owner_name'
        WHEN fei_id IS NULL THEN 'Missing fei_id'
        ELSE 'Other'
    END AS exclusion_reason,
    COUNT(*) AS record_count
FROM passports_pending_review
GROUP BY exclusion_reason
ORDER BY record_count DESC;


-- 6. COUNTRY COVERAGE — geographic completeness check
-- Useful to spot under-reporting national federations at a glance.
SELECT
    country_of_birth,
    COUNT(*) AS horses_registered,
    SUM(CASE WHEN microchip_number IS NOT NULL THEN 1 ELSE 0 END) AS with_microchip,
    ROUND(100.0 * SUM(CASE WHEN microchip_number IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS microchip_completeness_pct
FROM passports
GROUP BY country_of_birth
ORDER BY horses_registered DESC;
