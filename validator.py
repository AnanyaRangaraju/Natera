"""
validator.py
------------
Front-end claim validation rules engine for Natera 837P claims.
Mirrors real-world clearinghouse and payer edit logic.

Rule categories:
  - NPI format and completeness
  - Member ID / eligibility fields
  - Diagnosis code format and LCD compliance
  - Procedure code (CPT/HCPCS) validation
  - Place of service
  - Timely filing
  - Prior authorization requirements
  - Charge integrity

Author: Built for Natera front-end claim validation project
"""

import re
from datetime import date, datetime
from typing import Optional


# ---------------------------------------------------------------------------
# LCD rules: which ICD-10 diagnosis codes support each molecular test CPT
# Based on CMS LCD L38043 (MolDX) and common commercial payer policies
# ---------------------------------------------------------------------------
LCD_COVERAGE_RULES = {
    # Unlisted molecular pathology - general oncology codes
    "81479": {
        "description": "Unlisted molecular pathology procedure",
        "supported_dx_prefixes": ["C", "D3", "D4", "D5", "Z15", "Z80", "Z85"],
        "requires_prior_auth": True,
        "payers_requiring_auth": ["AETNA", "BCBS", "UNITED HEALTH", "CIGNA"],
    },
    # Signatera (tumor-informed ctDNA) - solid tumor recurrence monitoring
    "0172U": {
        "description": "Signatera - tumor-informed ctDNA",
        "supported_dx_prefixes": ["C18", "C19", "C20", "C34", "C50", "C61", "C64", "Z85"],
        "requires_prior_auth": True,
        "payers_requiring_auth": ["AETNA", "BCBS", "UNITED HEALTH", "CIGNA"],
    },
    # Oncotype DX Breast - early stage breast cancer
    "81519": {
        "description": "Oncotype DX Breast Recurrence Score",
        "supported_dx_prefixes": ["C50"],
        "requires_prior_auth": True,
        "payers_requiring_auth": ["AETNA", "BCBS", "UNITED HEALTH"],
    },
    # Panorama NIPT - fetal chromosomal aneuploidy
    "81420": {
        "description": "Fetal chromosomal aneuploidy (NIPT/Panorama)",
        "supported_dx_prefixes": ["O28", "O09", "Z34", "Z36", "Z13", "Z35"],
        "requires_prior_auth": False,
        "payers_requiring_auth": [],
    },
    # Oncotype DX Colon
    "81525": {
        "description": "Oncotype DX Colon Recurrence Score",
        "supported_dx_prefixes": ["C18", "C19", "C20"],
        "requires_prior_auth": True,
        "payers_requiring_auth": ["AETNA", "BCBS"],
    },
}

# Timely filing windows by payer (days from DOS)
TIMELY_FILING_WINDOWS = {
    "AETNA": 180,
    "BCBS": 365,
    "UNITED HEALTH": 365,
    "CIGNA": 180,
    "MEDICARE": 365,
    "MEDICAID": 365,
    "DEFAULT": 365,
}

# Valid place of service codes for lab billing
VALID_LAB_POS = {"81"}  # 81 = Independent Laboratory
COMMON_POS = {
    "11": "Office",
    "21": "Inpatient Hospital",
    "22": "Outpatient Hospital",
    "81": "Independent Laboratory",
    "23": "Emergency Room",
}


# ---------------------------------------------------------------------------
# NPI validation (Luhn algorithm mod 10 check)
# ---------------------------------------------------------------------------
def validate_npi(npi: str) -> tuple[bool, str]:
    """Validate NPI format and Luhn check digit."""
    if not npi:
        return False, "NPI is missing"
    npi_clean = npi.strip()
    if not npi_clean.isdigit():
        return False, f"NPI '{npi_clean}' contains non-numeric characters"
    if len(npi_clean) != 10:
        return False, f"NPI '{npi_clean}' is {len(npi_clean)} digits — must be exactly 10"

    # Luhn check: prepend 80840 per CMS spec, then run standard Luhn
    full = "80840" + npi_clean
    total = 0
    for i, digit in enumerate(reversed(full)):
        n = int(digit)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    if total % 10 != 0:
        return False, f"NPI '{npi_clean}' fails Luhn check digit validation"

    return True, "Valid"


def validate_icd10(code: str) -> tuple[bool, str]:
    """Basic ICD-10-CM format validation."""
    if not code:
        return False, "Diagnosis code is empty"
    pattern = re.compile(r"^[A-Z][0-9]{2}(\.[A-Z0-9]{1,4})?$")
    if not pattern.match(code.upper()):
        return False, f"ICD-10 code '{code}' does not match expected format (e.g. C18.9, Z15.82)"
    return True, "Valid"


def validate_cpt(code: str) -> tuple[bool, str]:
    """
    Basic CPT/HCPCS format validation.

    Formats handled:
      - CPT:       5 digits              e.g. 81479, 81519
      - HCPCS:     letter + 4 digits     e.g. G0001, A4550
      - PLA codes: 4 digits + letter     e.g. 0172U, 0001U
        PLA (Proprietary Laboratory Analyses) codes were introduced by AMA
        in 2018 for lab-specific tests. They follow a different pattern from
        standard HCPCS and are heavily used in molecular/genetic billing.
    """
    if not code:
        return False, "Procedure code is missing"
    code_upper = code.upper().strip()
    # Standard CPT: exactly 5 digits
    if re.match(r"^\d{5}$", code_upper):
        return True, "Valid CPT code"
    # Standard HCPCS Level II: letter + 4 digits (optional trailing letter)
    if re.match(r"^[A-Z]\d{4}[A-Z]?$", code_upper):
        return True, "Valid HCPCS Level II code"
    # PLA codes: 4 digits + single letter (e.g. 0172U, 0001U)
    if re.match(r"^\d{4}[A-Z]$", code_upper):
        return True, f"Valid PLA (Proprietary Laboratory Analyses) code — {code_upper} is a lab-specific HCPCS"
    return False, f"Procedure code '{code}' is not a valid CPT, HCPCS, or PLA code format"


def get_timely_filing_window(payer_name: str) -> int:
    """Return timely filing window in days for a given payer."""
    payer_upper = (payer_name or "").upper().strip()
    for key, window in TIMELY_FILING_WINDOWS.items():
        if key in payer_upper:
            return window
    return TIMELY_FILING_WINDOWS["DEFAULT"]


# ---------------------------------------------------------------------------
# Main validation engine
# ---------------------------------------------------------------------------
def validate_claim(claim: dict) -> dict:
    """
    Run all front-end validation rules against a parsed 837 claim.

    Returns a results dict with:
      - findings: list of individual rule results
      - summary: aggregate pass/fail/warning counts
      - risk_level: overall risk assessment
    """
    findings = []
    today = date.today()

    def add_finding(rule_id, category, description, status, detail, segment=None):
        findings.append({
            "rule_id": rule_id,
            "category": category,
            "description": description,
            "status": status,       # PASS / FAIL / WARNING
            "detail": detail,
            "segment": segment or "",
        })

    # --- Rule 1: Billing Provider NPI ---
    bp_npi = claim["billing_provider"].get("npi", "")
    valid, msg = validate_npi(bp_npi)
    add_finding(
        "NPI-001", "NPI Validation",
        "Billing provider NPI format and check digit",
        "PASS" if valid else "FAIL",
        msg if not valid else f"NPI {bp_npi} is valid",
        "NM1*85"
    )

    # --- Rule 2: Rendering Provider NPI ---
    rp_npi = claim["rendering_provider"].get("npi", "")
    valid, msg = validate_npi(rp_npi)
    add_finding(
        "NPI-002", "NPI Validation",
        "Rendering provider NPI format and check digit",
        "PASS" if valid else "FAIL",
        msg if not valid else f"NPI {rp_npi} is valid",
        "NM1*82"
    )

    # --- Rule 3: Ordering Provider NPI ---
    op_npi = claim["ordering_provider"].get("npi", "")
    valid, msg = validate_npi(op_npi)
    add_finding(
        "NPI-003", "NPI Validation",
        "Ordering/referring provider NPI format and check digit",
        "PASS" if valid else "FAIL",
        msg if not valid else f"NPI {op_npi} is valid",
        "NM1*DN"
    )

    # --- Rule 4: Member ID present ---
    member_id = claim["subscriber"].get("member_id", "").strip()
    add_finding(
        "ELIG-001", "Eligibility",
        "Patient member ID present",
        "PASS" if member_id else "FAIL",
        f"Member ID: {member_id}" if member_id else "Member ID is missing — claim will reject at payer intake",
        "NM1*IL"
    )

    # --- Rule 5: Diagnosis codes present and formatted correctly ---
    dx_codes = claim.get("diagnosis_codes", [])
    if not dx_codes:
        add_finding(
            "DX-001", "Diagnosis Codes",
            "At least one diagnosis code present",
            "FAIL",
            "No diagnosis codes found in HI segment — required for all claims",
            "HI"
        )
    else:
        for dx in dx_codes:
            code = dx.get("code", "")
            valid, msg = validate_icd10(code)
            add_finding(
                "DX-001", "Diagnosis Codes",
                f"ICD-10 format: {code}",
                "PASS" if valid else "FAIL",
                msg,
                "HI"
            )

    # --- Rule 6: Service lines present ---
    service_lines = claim.get("service_lines", [])
    if not service_lines:
        add_finding(
            "SVC-001", "Service Lines",
            "At least one service line present",
            "FAIL",
            "No SV1 service lines found — claim has no billable procedure",
            "SV1"
        )
    else:
        for i, line in enumerate(service_lines):
            code = line.get("procedure_code", "")
            valid, msg = validate_cpt(code)
            add_finding(
                f"SVC-00{i+1}", "Service Lines",
                f"CPT/HCPCS format: {code}",
                "PASS" if valid else "FAIL",
                msg,
                "SV1"
            )

            # --- Rule 7: Charge amount > 0 ---
            charge = line.get("charge", 0)
            add_finding(
                f"CHG-00{i+1}", "Charge Integrity",
                f"Service line charge amount > 0",
                "PASS" if charge > 0 else "FAIL",
                f"Charge: ${charge:,.2f}" if charge > 0 else "Zero charge amount — claim will reject",
                "SV1"
            )

    # --- Rule 8: Place of service ---
    pos = claim["claim"].get("place_of_service", "").strip()
    pos_name = COMMON_POS.get(pos, f"Unknown ({pos})")
    if pos in VALID_LAB_POS:
        add_finding(
            "POS-001", "Place of Service",
            "Place of service appropriate for lab billing",
            "PASS",
            f"POS {pos} = {pos_name} — correct for independent lab billing",
            "CLM"
        )
    elif pos in COMMON_POS:
        add_finding(
            "POS-001", "Place of Service",
            "Place of service appropriate for lab billing",
            "WARNING",
            f"POS {pos} = {pos_name} — lab claims typically require POS 81 (Independent Laboratory). "
            f"Incorrect POS may cause payer-specific rejection or payment reduction.",
            "CLM"
        )
    else:
        add_finding(
            "POS-001", "Place of Service",
            "Place of service appropriate for lab billing",
            "FAIL",
            f"POS '{pos}' is missing or unrecognized",
            "CLM"
        )

    # --- Rule 9: Timely filing ---
    dos = claim["claim"].get("date_of_service")
    payer_name = claim["claim"].get("payer_name", "")
    if dos:
        days_elapsed = (today - dos).days
        window = get_timely_filing_window(payer_name)
        days_remaining = window - days_elapsed

        if days_elapsed > window:
            add_finding(
                "TF-001", "Timely Filing",
                "Claim within timely filing deadline",
                "FAIL",
                f"DOS: {dos} | Days elapsed: {days_elapsed} | Payer window: {window} days | "
                f"EXCEEDED by {abs(days_remaining)} days — permanent write-off risk",
                "DTP*472"
            )
        elif days_remaining <= 30:
            add_finding(
                "TF-001", "Timely Filing",
                "Claim within timely filing deadline",
                "WARNING",
                f"DOS: {dos} | Days elapsed: {days_elapsed} | {days_remaining} days remaining to file — "
                f"URGENT: resubmit immediately",
                "DTP*472"
            )
        else:
            add_finding(
                "TF-001", "Timely Filing",
                "Claim within timely filing deadline",
                "PASS",
                f"DOS: {dos} | {days_remaining} days remaining within {window}-day window",
                "DTP*472"
            )
    else:
        add_finding(
            "TF-001", "Timely Filing",
            "Claim within timely filing deadline",
            "FAIL",
            "Date of service not parseable — cannot assess timely filing",
            "DTP*472"
        )

    # --- Rule 10: LCD compliance + prior auth check ---
    for line in service_lines:
        cpt = line.get("procedure_code", "").upper()
        if cpt in LCD_COVERAGE_RULES:
            rule = LCD_COVERAGE_RULES[cpt]
            supported_prefixes = rule["supported_dx_prefixes"]
            dx_code_values = [d["code"].upper() for d in dx_codes]

            # Check if any diagnosis supports this CPT
            lcd_supported = any(
                any(dx.startswith(prefix) for prefix in supported_prefixes)
                for dx in dx_code_values
            )

            if lcd_supported:
                add_finding(
                    "LCD-001", "LCD / Medical Necessity",
                    f"Diagnosis supports CPT {cpt} per LCD policy",
                    "PASS",
                    f"CPT {cpt} ({rule['description']}) | Diagnosis codes {dx_code_values} | "
                    f"Covered prefixes: {supported_prefixes}",
                    "HI + SV1"
                )
            else:
                add_finding(
                    "LCD-001", "LCD / Medical Necessity",
                    f"Diagnosis supports CPT {cpt} per LCD policy",
                    "FAIL",
                    f"CPT {cpt} ({rule['description']}) requires diagnosis from: {supported_prefixes}. "
                    f"Found: {dx_code_values}. Payer will deny for medical necessity — fix diagnosis code before submission.",
                    "HI + SV1"
                )

            # Prior auth check
            if rule["requires_prior_auth"]:
                auth_number = claim["claim"].get("prior_auth_number", "").strip()
                payer_upper = payer_name.upper()
                payer_needs_auth = any(p in payer_upper for p in rule["payers_requiring_auth"])

                if payer_needs_auth and not auth_number:
                    add_finding(
                        "AUTH-001", "Prior Authorization",
                        f"Prior auth number present for CPT {cpt}",
                        "FAIL",
                        f"CPT {cpt} requires prior authorization from {payer_name}. "
                        f"No REF*D9 auth number found — claim will deny CO-97 (auth required).",
                        "REF*D9"
                    )
                elif auth_number:
                    add_finding(
                        "AUTH-001", "Prior Authorization",
                        f"Prior auth number present for CPT {cpt}",
                        "PASS",
                        f"Auth number {auth_number} found in REF*D9 segment",
                        "REF*D9"
                    )
                else:
                    add_finding(
                        "AUTH-001", "Prior Authorization",
                        f"Prior auth number present for CPT {cpt}",
                        "WARNING",
                        f"CPT {cpt} may require prior auth — verify payer requirements for {payer_name or 'this payer'}",
                        "REF*D9"
                    )

    # --- Rule 11: Total charge > 0 ---
    total_charge = claim["claim"].get("total_charge", 0)
    add_finding(
        "CHG-000", "Charge Integrity",
        "CLM total charge amount > 0",
        "PASS" if total_charge > 0 else "FAIL",
        f"Total charge: ${total_charge:,.2f}" if total_charge > 0 else "Zero total charge in CLM segment",
        "CLM"
    )

    # --- Build summary ---
    pass_count = sum(1 for f in findings if f["status"] == "PASS")
    fail_count = sum(1 for f in findings if f["status"] == "FAIL")
    warn_count = sum(1 for f in findings if f["status"] == "WARNING")

    if fail_count > 0:
        risk_level = "HIGH RISK"
    elif warn_count > 0:
        risk_level = "MEDIUM RISK"
    else:
        risk_level = "LOW RISK"

    return {
        "claim_id": claim["claim"].get("claim_id", "UNKNOWN"),
        "payer": claim["claim"].get("payer_name", "UNKNOWN"),
        "subscriber": f"{claim['subscriber'].get('first_name', '')} {claim['subscriber'].get('last_name', '')}".strip(),
        "total_charge": claim["claim"].get("total_charge", 0),
        "date_of_service": str(claim["claim"].get("date_of_service", "N/A")),
        "findings": findings,
        "summary": {
            "total_rules": len(findings),
            "passed": pass_count,
            "failed": fail_count,
            "warnings": warn_count,
        },
        "risk_level": risk_level,
        "parse_errors": claim.get("parse_errors", []),
    }
