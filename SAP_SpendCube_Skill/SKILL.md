---
name: sap-spendcube-analysis
description: >
  Comprehensive SAP procurement spend cube analysis with maverick deep dive.
  Analyzes full datasets (all companies) or single companies from SAP data
  (RSEG+BSEG+Vendor pre-built CSV or raw BKPF/BSEG files). Generates 8-slide
  PowerPoint, Word document, and maverick CSV extract. Includes Direct/Indirect
  classification, Maverick spend tiers, Three-way match, vendor concentration,
  GL/Cost Center/Profit Center analysis, credit-heavy vendors, single-source risk,
  and savings opportunity assessment.
argument-hint: "[--mode full|company|fi] [--bukrs CODE] [--name NAME] [--doc-types TYPE1 TYPE2...]"
allowed-tools: "Read, Grep, Glob, Bash, Write, Edit"
---

# SAP Procurement Spend Cube Analysis Skill

## Overview

This skill performs comprehensive procurement spend analysis on SAP data.
It processes pre-built comprehensive datasets or raw SAP table exports to
generate spend cubes, maverick spend deep dives, and remediation roadmaps.

## Quick Start

```bash
# Full dataset analysis (all companies, 8-slide deck)
cd "C:\data\Condor HRP 2025\final-output-v3\SAP_SpendCube_Skill"
python run_analysis.py --mode full

# Single company analysis
python run_analysis.py --mode company --bukrs 113 --name "Granada"

# FI document types analysis
python run_analysis.py --mode fi --bukrs 113 --doc-types EC KR KG KE KX --name "Granada"
```

## Analysis Modes

### 1. Full Dataset (`--mode full`)
- Analyzes ALL companies in the pre-built comprehensive CSV
- Generates: 8-slide PPTX, comprehensive DOCX, maverick CSV
- Includes: Country breakdown, compliance by country, extreme risk deep dive
- Output: `SpendCube_Full/` directory

### 2. Single Company (`--mode company`)
- Filters pre-built CSV by BUKRS (company code)
- Generates: 5-slide PPTX, DOCX, filtered CSV
- Requires: `--bukrs` (and optionally `--name`)

### 3. FI Document Types (`--mode fi`)
- Loads raw BKPF + BSEG files for specific document types
- Generates: 5-slide PPTX, DOCX, extracted CSV
- Requires: `--bukrs`, `--doc-types`
- FI docs have No PR/GR by definition (100% maverick expected)

## Company Codes

| BUKRS | Name           | Country |
|-------|----------------|---------|
| 6     | Russia         | RU      |
| 8     | Egypt          | EG      |
| 10    | USA            | US      |
| 21    | Spain (ES01)   | ES      |
| 23    | UK             | GB      |
| 29    | Turkey         | TR      |
| 30    | Germany (HQ)   | DE      |
| 46    | Slovenia       | SI      |
| 78    | South Africa   | ZA      |
| 113   | Granada        | ES      |
| 117   | France         | FR      |

## FI Document Types

| Type | Description            |
|------|------------------------|
| EC   | Invoice Correction     |
| KR   | Vendor Invoice (FI)    |
| KG   | Vendor Credit Memo     |
| KE   | Vendor Credit Note     |
| KX   | Vendor Special Credit  |

## Business Rules

### Direct/Indirect Classification
1. Has PR/PO/GR? → NO → INDIRECT
2. Has Material? → NO → INDIRECT
3. Material digits = 6 → DIRECT
4. Material digits >= 7 → INDIRECT
5. Material digits < 6 → INDIRECT

### Maverick Tiers
- **CRITICAL**: No PR + No GR + No Material (zero controls)
- **HIGH**: No PR + No GR (primary maverick)
- **MEDIUM**: No PR only, or No GR only
- **LOW**: No Material only (data quality)

### SHKZG (Debit/Credit)
- S = Soll (Debit/Expense) → Adds to Gross
- H = Haben (Credit/Reversal) → Reduces Net

### Vendor Risk
- Credit-heavy: >20% credit-to-debit ratio
- Single-source: Material with only 1 vendor
- Pareto: Number of vendors covering 80% spend

## Module Reference

| Module            | Purpose                                    |
|-------------------|--------------------------------------------|
| `config.py`       | ALL rules, mappings, thresholds, colors    |
| `modules/loaders.py` | Data loading (CSV, BSEG split files, LFA1) |
| `modules/classify.py` | Classification, maverick, derived flags    |
| `modules/metrics.py`  | KPI computation, dimensional analysis      |
| `modules/pptx_builder.py` | 8-slide PowerPoint generation          |
| `modules/docx_builder.py` | Word document generation               |
| `run_analysis.py` | CLI orchestrator with argparse             |

## Outputs

### Full Mode (8 Slides)
1. Spend Cube Overview (country + vendor + BSEG coverage)
2. Maverick Scorecard & Three-Way Match
3. Maverick by Country
4. Maverick by GL / Cost Center / Profit Center
5. Maverick Vendor Deep Dive & Credit Risk
6. Maverick Direct vs Indirect Breakdown
7. Extreme Risk Deep Dive
8. Remediation Roadmap & Savings Opportunities

### Company/FI Mode (5 Slides)
1. Executive Overview
2. GL Account & Cost Center
3. Vendor Concentration
4. Maverick Spend Analysis
5. Recommendations & Remediation

## Dependencies

- pandas, numpy
- python-pptx (PowerPoint)
- python-docx (Word)

## Data Requirements

### Pre-built CSV (full/company modes)
- `SAP_Final_Comprehensive_With_BSEG_Vendor.csv` in `final-output-v3/`
- 45 columns including BSEG enrichment (GL, Cost Center, Profit Center)

### Raw Tables (fi mode)
- `HRP_BKPF.csv` (semicolon-delimited, 5.9GB)
- `hrp--BSEG.csv_part001.csv` through `part013` (semicolon, ~1.5GB each)
- `HRP_LFA1.csv` (semicolon, vendor master)
