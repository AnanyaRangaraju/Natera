"""
parser_837.py
-------------
Parses ANSI X12 837P EDI claim files into structured Python dictionaries.
Supports 005010X222A1 transaction set.

Author: Built for Natera front-end claim validation project
"""

from datetime import datetime


def parse_837(raw_text: str) -> dict:
    """
    Parse a raw 837 EDI string into a structured claim dictionary.

    Args:
        raw_text: Raw 837 EDI file content as a string

    Returns:
        dict with parsed claim fields and metadata
    """
    raw_text = raw_text.strip().replace("\n", "").replace("\r", "")
    segments = [s.strip() for s in raw_text.split("~") if s.strip()]

    claim = {
        "raw_segments": segments,
        "interchange": {},
        "billing_provider": {},
        "subscriber": {},
        "claim": {},
        "diagnosis_codes": [],
        "service_lines": [],
        "rendering_provider": {},
        "ordering_provider": {},
        "parse_errors": [],
    }

    current_hl = None

    for seg in segments:
        elements = seg.split("*")
        seg_id = elements[0]

        try:
            # --- Interchange envelope ---
            if seg_id == "ISA":
                claim["interchange"]["sender_id"] = elements[6].strip() if len(elements) > 6 else ""
                claim["interchange"]["receiver_id"] = elements[8].strip() if len(elements) > 8 else ""
                claim["interchange"]["date"] = elements[9].strip() if len(elements) > 9 else ""
                claim["interchange"]["control_number"] = elements[13].strip() if len(elements) > 13 else ""

            # --- Billing provider name + NPI ---
            elif seg_id == "NM1":
                entity_code = elements[1] if len(elements) > 1 else ""

                if entity_code == "85":  # Billing provider
                    claim["billing_provider"]["name"] = elements[3].strip() if len(elements) > 3 else ""
                    claim["billing_provider"]["npi"] = elements[9].strip() if len(elements) > 9 else ""
                    claim["billing_provider"]["id_qualifier"] = elements[8].strip() if len(elements) > 8 else ""

                elif entity_code == "IL":  # Subscriber / patient
                    claim["subscriber"]["last_name"] = elements[3].strip() if len(elements) > 3 else ""
                    claim["subscriber"]["first_name"] = elements[4].strip() if len(elements) > 4 else ""
                    claim["subscriber"]["member_id"] = elements[9].strip() if len(elements) > 9 else ""

                elif entity_code == "82":  # Rendering provider
                    claim["rendering_provider"]["last_name"] = elements[3].strip() if len(elements) > 3 else ""
                    claim["rendering_provider"]["first_name"] = elements[4].strip() if len(elements) > 4 else ""
                    claim["rendering_provider"]["npi"] = elements[9].strip() if len(elements) > 9 else ""

                elif entity_code == "DN":  # Ordering / referring provider
                    claim["ordering_provider"]["last_name"] = elements[3].strip() if len(elements) > 3 else ""
                    claim["ordering_provider"]["first_name"] = elements[4].strip() if len(elements) > 4 else ""
                    claim["ordering_provider"]["npi"] = elements[9].strip() if len(elements) > 9 else ""

                elif entity_code == "PR":  # Payer
                    claim["claim"]["payer_name"] = elements[3].strip() if len(elements) > 3 else ""
                    claim["claim"]["payer_id"] = elements[9].strip() if len(elements) > 9 else ""

            # --- Claim information ---
            elif seg_id == "CLM":
                claim["claim"]["claim_id"] = elements[1].strip() if len(elements) > 1 else ""
                claim["claim"]["total_charge"] = float(elements[2]) if len(elements) > 2 and elements[2] else 0.0
                pos_composite = elements[5].split(":") if len(elements) > 5 else []
                claim["claim"]["place_of_service"] = pos_composite[0] if pos_composite else ""
                claim["claim"]["assignment_of_benefits"] = elements[6].strip() if len(elements) > 6 else ""
                claim["claim"]["release_of_info"] = elements[8].strip() if len(elements) > 8 else ""

            # --- Date of service ---
            elif seg_id == "DTP" and len(elements) > 3:
                qualifier = elements[1]
                if qualifier == "472":  # Date of service
                    raw_date = elements[3].strip()
                    try:
                        claim["claim"]["date_of_service"] = datetime.strptime(raw_date, "%Y%m%d").date()
                    except ValueError:
                        claim["parse_errors"].append(f"Invalid DOS format: {raw_date}")
                        claim["claim"]["date_of_service"] = None

            # --- Prior auth reference ---
            elif seg_id == "REF" and len(elements) > 2:
                qualifier = elements[1].strip()
                if qualifier == "D9":  # Prior authorization number
                    claim["claim"]["prior_auth_number"] = elements[2].strip()

            # --- Diagnosis codes (HI segment) ---
            elif seg_id == "HI":
                for element in elements[1:]:
                    if element:
                        parts = element.split(":")
                        qualifier = parts[0] if parts else ""
                        code = parts[1] if len(parts) > 1 else ""
                        if code:
                            claim["diagnosis_codes"].append({
                                "qualifier": qualifier,
                                "code": code,
                                "principal": (qualifier in ["ABK", "ABF"])
                            })

            # --- Service lines ---
            elif seg_id == "SV1":
                composite = elements[1].split(":") if len(elements) > 1 else []
                procedure_code = composite[1] if len(composite) > 1 else ""
                modifier = composite[2] if len(composite) > 2 else ""
                try:
                    charge = float(elements[2]) if len(elements) > 2 and elements[2] else 0.0
                except ValueError:
                    charge = 0.0
                try:
                    units = float(elements[4]) if len(elements) > 4 and elements[4] else 1.0
                except ValueError:
                    units = 1.0

                claim["service_lines"].append({
                    "procedure_code": procedure_code,
                    "modifier": modifier,
                    "charge": charge,
                    "units": units,
                    "unit_basis": elements[3].strip() if len(elements) > 3 else "UN",
                })

            # --- Subscriber information ---
            elif seg_id == "SBR":
                claim["subscriber"]["payer_responsibility"] = elements[1].strip() if len(elements) > 1 else ""
                claim["subscriber"]["relationship_code"] = elements[2].strip() if len(elements) > 2 else ""
                claim["subscriber"]["group_number"] = elements[3].strip() if len(elements) > 3 else ""
                claim["subscriber"]["insurance_type"] = elements[9].strip() if len(elements) > 9 else ""

            # --- Patient demographics ---
            elif seg_id == "DMG":
                claim["subscriber"]["dob"] = elements[2].strip() if len(elements) > 2 else ""
                claim["subscriber"]["gender"] = elements[3].strip() if len(elements) > 3 else ""

        except (IndexError, ValueError) as e:
            claim["parse_errors"].append(f"Segment {seg_id}: {str(e)}")

    return claim
