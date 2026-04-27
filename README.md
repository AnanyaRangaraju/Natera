# Natera 837 Front-End Claim Validation Suite

A Python-based tool that parses ANSI X12 837P EDI claim files and runs them through a front-end billing validation rules engine — catching errors before submission to clearinghouses and payers.

Built to mirror the real-world work of a front-end Revenue Cycle Analyst at a high-volume lab or genetic testing company.

---

## What it does

Most claim rejections are preventable. This tool catches them before the claim leaves the building.

The validation engine checks each 837 claim against 11 rule categories:

| Category | Rules |
|---|---|
| NPI Validation | Format, length, Luhn check digit (billing, rendering, ordering) |
| Eligibility | Member ID present and non-empty |
| Diagnosis Codes | ICD-10-CM format validation |
| Service Lines | CPT / HCPCS code format validation |
| Charge Integrity | Non-zero charge amounts at line and claim level |
| Place of Service | Lab billing POS 81 requirement |
| Timely Filing | Days elapsed vs. payer-specific filing window |
| LCD / Medical Necessity | Diagnosis-to-procedure compatibility per CMS LCD policy |
| Prior Authorization | Auth number present for payers and CPTs that require it |

---

## Why this matters

At a genetic testing company like Natera, every claim that goes out wrong costs time and money:

- **Rejection** at the clearinghouse = fix it and resubmit, losing days
- **Denial** for medical necessity = file an appeal, losing weeks
- **Missed timely filing** = permanent write-off, no recovery possible

This tool runs checks in seconds that would otherwise surface as rejections 5-10 business days later.

---

## Natera-specific coverage

The LCD rules engine includes real coverage policies for Natera's core test portfolio:

| CPT / HCPCS | Test | Supported Diagnoses | Auth Required |
|---|---|---|---|
| 81479 | Unlisted molecular pathology | C, D3-D5, Z15, Z80, Z85 | Yes (all major payers) |
| 0172U | Signatera (tumor-informed ctDNA) | C18, C19, C20, C34, C50, C61, C64, Z85 | Yes |
| 81519 | Oncotype DX Breast | C50 | Yes |
| 81420 | Panorama / NIPT | O09, O28, Z13, Z34-Z36 | No |
| 81525 | Oncotype DX Colon | C18, C19, C20 | Yes |

Timely filing windows are payer-specific:

| Payer | Window |
|---|---|
| Aetna | 180 days |
| Cigna | 180 days |
| BCBS | 365 days |
| United Health | 365 days |
| Medicare / Medicaid | 365 days |

---

## Project structure

```
natera_claim_validator/
├── main.py               # Entry point — runs batch or single-file validation
├── parser_837.py         # ANSI X12 837P segment parser
├── validator.py          # Validation rules engine (11 rule categories)
├── reporter.py           # Terminal report formatter + CSV exporter
├── sample_data/          # 5 sample 837 claims with realistic errors
│   ├── claim_01_clean.837              # Aetna oncology — ICD-10 format error + NPI errors
│   ├── claim_02_npi_dx_errors.837      # Aetna — multiple NPI failures + LCD mismatch
│   ├── claim_03_timely_filing.837      # BCBS — timely filing exceeded + missing auth
│   ├── claim_04_pos_memberid_errors.837 # United — wrong POS + missing member ID
│   └── claim_05_clean_panorama.837     # Cigna — Panorama prenatal, NPI errors
└── output/               # Generated CSV reports
```

---

## Setup and usage

**Requirements:** Python 3.10+ — no third-party libraries needed.

```bash
# Clone the repo
git clone https://github.com/yourusername/natera_claim_validator.git
cd natera_claim_validator

# Validate all sample claims
python main.py

# Validate all sample claims and export CSV
python main.py --csv

# Validate a single 837 file
python main.py --file path/to/your_claim.837

# Validate a single file and export CSV
python main.py --file path/to/your_claim.837 --csv
```

---

## Sample output

```
========================================================================
  NATERA 837 CLAIM VALIDATION SUITE
  2024-01-15 09:30:00
========================================================================

  CLAIM VALIDATION REPORT
  Claim ID   : CLAIM002
  Subscriber : MARY JONES
  Payer      : AETNA
  DOS        : 2023-04-08
  Charge     : $3,200.00
  Risk Level : !! HIGH RISK !!
------------------------------------------------------------------------
  Rules run: 12  |  Passed: 4  |  Failed: 8  |  Warnings: 0
------------------------------------------------------------------------

  [NPI Validation]
    [FAIL]  Billing provider NPI format and check digit
           Detail: NPI '123456789' is 9 digits — must be exactly 10
    [FAIL]  Ordering/referring provider NPI format and check digit
           Detail: NPI 'ABCD1234567' contains non-numeric characters

  [LCD / Medical Necessity]
    [FAIL]  Diagnosis supports CPT 0172U per LCD policy
           Detail: CPT 0172U (Signatera) requires diagnosis from: ['C18','C19','C20'...].
           Found: ['J329']. Payer will deny for medical necessity.

  [Prior Authorization]
    [FAIL]  Prior auth number present for CPT 0172U
           Detail: CPT 0172U requires prior authorization from AETNA.
           No REF*D9 auth number found — claim will deny CO-97.
```

---

## CSV export

The `--csv` flag exports a flat file with one row per rule result, ready for import into Excel or Power BI:

| claim_id | payer | subscriber | dos | charge | risk_level | category | rule_id | status | detail | segment |
|---|---|---|---|---|---|---|---|---|---|---|
| CLAIM002 | AETNA | MARY JONES | 2023-04-08 | 3200 | HIGH RISK | NPI Validation | NPI-001 | FAIL | NPI '123456789' is 9 digits | NM1*85 |

This structure allows rejection trend analysis by category, payer, and date — matching the reporting work a front-end analyst would do in production.

---

## How this maps to real analyst work

| This tool does | Real analyst does |
|---|---|
| Parse 837 segments | Read clearinghouse rejection files |
| Run NPI Luhn validation | Investigate NPI-related rejections in payer portal |
| Check LCD diagnosis mapping | Research payer coverage policies for molecular tests |
| Flag timely filing risk | Monitor days-to-resubmission against payer windows |
| Export CSV rejection report | Build rejection trend dashboard in Excel / Power BI |

---

## Author

Ananya Rangaraju  
Master of Engineering Management, Dartmouth College  
[LinkedIn](https://www.linkedin.com/in/ananya-rangaraju/)

Background: 2+ years implementing ANSI X12 revenue cycle systems at Oracle Health (formerly Cerner) for federal healthcare clients including VA and DoD.
