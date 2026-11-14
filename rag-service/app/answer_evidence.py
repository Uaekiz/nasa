"""Conservative question coverage, source citations, and extractive answer validation."""

from dataclasses import dataclass
import json
from pathlib import PurePosixPath
import re

from .rag_config import RagError


FIELD_PATTERNS = {
    "Fuel": r"\bfuels?\b",
    "Test end": r"\b(outcomes?|results?|test end|extinction|extinguish\w*|disruption|completion)\b",
    "Test Date": r"\b(dates?|when)\b",
    "Test GMT": r"\bgmt\b",
    "Ambient pressure; mmHg": r"\b(?:ambient )?pressure\b",
    "Droplet initial diameter; mm": r"\b(?:droplet )?initial diameter\b",
    "Visible flame extinction diameter; mm": r"\b(?:visible )?(?:flame )?extinction diameter\b",
    "Burning rate; mm": r"\b(?:burning|burn) rate\b",
    "Burn time; s": r"\b(?:burn|burning) (?:time|duration)\b",
    "FLEX Identifier": r"\b(?:flex )?identifiers?\b",
    "FLEX Test #": r"\btest (?:id|number|no\.?)\b",
}
INTERPRETATION = re.compile(
    r"\b(why|caus\w*|reason\w*|explain\w*|mechanism\w*|affect\w*|influenc\w*|effect\w*|"
    r"because|therefore|recommend\w*|safe\w*|risk\w*|hazard\w*|predict\w*|should|would|"
    r"optimal\w*|prevent\w*|responsible|imply|indicate\w*)\b", re.I,
)
# Unknown scientific attributes, numeric predicates, and instructions fail closed.
GRAMMAR = set("""
a an the and or of for in on at to from with by as is are was were be been being
what which how did does do can you me please tell give show list find retrieve
summarize summarise summary describe report reported recorded raw original source
data evidence record records row rows test tests flex psi used use using had has have
both each these those this that about available examples example some few ended end
ending underwent their its it they them values value fields field details detail
conditions measurements include including provide only also respectively s
""".split())


@dataclass(frozen=True)
class Coverage:
    status: str
    required_fields: tuple[str, ...] = ()
    reason: str = ""


def assess_coverage(question: str, result: dict) -> Coverage:
    """Authorize raw field reporting, never scientific interpretation from proximity."""
    matches = result.get("matches", [])
    if not matches:
        reason = "No source rows match the requested investigation and test filters."
        if result.get("route") not in ("EXACT_ID", "SEMANTIC"):
            reason = result.get("reason") or reason
        return Coverage("INSUFFICIENT_EVIDENCE", reason=reason)
    if INTERPRETATION.search(question):
        return Coverage("INSUFFICIENT_EVIDENCE", reason="The CSV reports test fields, but does not establish the requested explanation, prediction, or recommendation.")
    if all(re.search(r"\b" + fuel + r"\b", question, re.I) for fuel in ("Methanol", "Heptane")):
        return Coverage("INSUFFICIENT_EVIDENCE", reason="Combined-fuel conditions are not implemented. Request one original fuel per question.")
    records = [match["record"] for match in matches]
    outcome_text = re.sub(r"\b(?:visible )?(?:flame )?extinction diameter\b", " ", question, flags=re.I)
    for outcome in ("Extinction", "Disruption", "Completion"):
        if re.search(r"\b" + outcome + r"\b", outcome_text, re.I) and any(
            record["fields"]["Test end"] != outcome for record in records
        ):
            return Coverage("INSUFFICIENT_EVIDENCE", reason="The retrieved rows do not verify the requested reported outcome.")
    headers = set(records[0]["fields"])
    required = []
    remaining = question
    # Match complete original headings before aliases, retaining their original units.
    for header in sorted(headers, key=len, reverse=True):
        if re.search(re.escape(header), remaining, re.I):
            required.append(header)
            remaining = re.sub(re.escape(header), " ", remaining, flags=re.I)
    for header, pattern in FIELD_PATTERNS.items():
        if re.search(pattern, remaining, re.I):
            if header not in headers:
                return Coverage("INSUFFICIENT_EVIDENCE", reason="The requested field is absent from the source.")
            required.append(header)
            remaining = re.sub(pattern, " ", remaining, flags=re.I)
    filters = result.get("filters", {})
    if filters.get("fuel"):
        required.append("Fuel")
    # Removing only explicit selectors prevents an unimplemented numeric condition
    # from being treated as ordinary semantic text.
    selectors = list(filters.get("test_ids", [])) + list(filters.get("flex_identifiers", []))
    selectors += list(filters.get("investigation_ids", []))
    selectors += ["PSI-69", "Methanol", "Heptane"]
    for selector in sorted(set(selectors), key=len, reverse=True):
        remaining = re.sub(r"(?<!\w)" + re.escape(selector) + r"(?!\w)", " ", remaining, flags=re.I)
    tokens = re.findall(r"[a-z0-9]+", remaining.casefold())
    if any(token not in GRAMMAR for token in tokens):
        return Coverage("INSUFFICIENT_EVIDENCE", reason="The question includes an attribute or condition that this CSV answer path cannot verify. Request original test fields or explicit test summaries.")
    if result.get("route") == "SEMANTIC":
        # General definitions and arbitrary nearest rows are not supported answers.
        if not re.search(r"\b(examples?|tests?|records?|rows?)\b", question, re.I) or not re.search(
            r"\b(show|find|list|give|retrieve|which|summariz\w*|summaris\w*)\b", question, re.I
        ):
            return Coverage("INSUFFICIENT_EVIDENCE", reason="Nearest source rows do not establish a general scientific answer.")
        if re.search(r"\b(extinction|extinguish\w*)\b", outcome_text, re.I):
            if filters.get("outcome") != "Extinction" or any(r["fields"]["Test end"] != "Extinction" for r in records):
                return Coverage("INSUFFICIENT_EVIDENCE", reason="The retrieved rows do not verify the requested outcome condition.")
        if any(filters.get("fuel") and r["fields"]["Fuel"] != filters["fuel"] for r in records):
            raise RagError("CORRUPT_INDEX", "A candidate violates the requested fuel condition.")
        status = "PARTIAL"
    else:
        present_tests = {r["sourceTestId"] for r in records}
        present_identifiers = {r["fields"]["FLEX Identifier"] for r in records}
        complete = (
            set(filters.get("test_ids", [])) <= present_tests
            and set(filters.get("flex_identifiers", [])) <= present_identifiers
            and result.get("eligibleRecordCount") == len(records)
        )
        status = "ANSWERED" if complete else "PARTIAL"
    if not required or re.search(r"\b(summariz\w*|summaris\w*|summary|details?|both records)\b", question, re.I):
        required += ["Fuel", "Test end", "Burn time; s", "Burning rate; mm"]
    required = tuple(dict.fromkeys(required))
    if any(header not in headers for header in required):
        raise RagError("INVALID_EVIDENCE", "A required original CSV field is unavailable.")
    missing = any(not r["fields"][header].strip() or r["fields"][header] in ("–", "-") for r in records for header in required)
    return Coverage("PARTIAL" if missing else status, required)


def build_sources(records: list[dict]) -> list[dict]:
    return [{
        "citationId": f"S{index}", "sourceId": record["sourceId"],
        "investigationId": record["investigationId"], "experimentId": None,
        "sourceType": record["sourceType"], "title": PurePosixPath(record["sourceFile"]).name,
        "pdfPage": None, "printedPage": None, "table": None, "chunkId": None,
        "sheetName": None, "rowNumber": record["rowNumber"],
        "sourceTestId": record["sourceTestId"], "sourceFile": record["sourceFile"],
    } for index, record in enumerate(records, 1)]


def generation_input(question: str, records: list[dict], required_fields: tuple[str, ...]) -> tuple[str, dict]:
    citations = [f"S{i}" for i in range(1, len(records) + 1)]
    record_schema = {
        "type": "object", "additionalProperties": False, "required": list(required_fields),
        "properties": {header: {"type": "string"} for header in required_fields},
    }
    schema = {
        "type": "object", "additionalProperties": False, "required": ["records"],
        "properties": {"records": {
            "type": "object", "additionalProperties": False, "required": citations,
            "properties": {citation: record_schema for citation in citations},
        }},
    }
    prompt = (
        "Answer the English question by extracting the required original fields for each evidence row. "
        "Return JSON following the schema: records maps EACH citation ID to its required field/value pairs. "
        "Copy cell strings EXACTLY, including empty strings, qualifiers, decimal formatting, and units in headings. "
        "Do not return prose, calculations, causes, recommendations, filenames, or row numbers. "
        "The service will validate every value and format a concise English answer.\n"
        + json.dumps({"question": question, "requiredFields": required_fields,
                      "evidence": [{"citationId": f"S{i}", "sourceTestId": record["sourceTestId"],
                                    "fields": record["fields"]} for i, record in enumerate(records, 1)],
                      "responseSchema": schema}, ensure_ascii=False)
    )
    return prompt, schema


def render_validated_answer(content: str, records: list[dict], required_fields: tuple[str, ...]) -> tuple[str, list[dict]]:
    """No free model prose or values cross the boundary into a scientific answer."""
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Repeated JSON property")
            result[key] = value
        return result

    try:
        data = json.loads(content, object_pairs_hook=unique_object)
        if not isinstance(data, dict) or set(data) != {"records"} or not isinstance(data["records"], dict):
            raise ValueError("Invalid generated record object")
        expected = {f"S{i}": record for i, record in enumerate(records, 1)}
        if set(data["records"]) != set(expected):
            raise ValueError("Unknown or omitted citation")
        for citation, fields in data["records"].items():
            if not isinstance(fields, dict) or set(fields) != set(required_fields):
                raise ValueError("Missing or unknown original fields")
            if any(not isinstance(value, str) or value != expected[citation]["fields"][header] for header, value in fields.items()):
                raise ValueError("A generated value differs from its cited source cell")
    except (ValueError, TypeError, KeyError) as error:
        raise RagError("GENERATION_VALIDATION_FAILED", "The model's field values or citation IDs could not be validated against the supplied evidence.") from error
    lines, warnings = [], []
    missing = ambiguous = False
    for citation, record in expected.items():
        pairs = []
        for header in required_fields:
            value = record["fields"][header]
            missing |= not value.strip() or value in ("–", "-")
            ambiguous |= header == "Burning rate; mm"
            pairs.append(f"{header}: {value if value else '(empty source cell)'}")
        lines.append(f"FLEX test {record['sourceTestId']} (FLEX Identifier {record['fields']['FLEX Identifier']}): " + "; ".join(pairs) + f". [{citation}]")
    answer = "\n".join(lines)
    if set(re.findall(r"\[(S\d+)\]", answer)) != set(expected):
        raise RagError("GENERATION_VALIDATION_FAILED", "Rendered citations do not match the source records.")
    if missing:
        warnings.append({"code": "SOURCE_MISSING_VALUE", "message": "Empty source cells and dash markers are preserved; no missing measurement was inferred."})
    if ambiguous:
        warnings.append({"code": "AMBIGUOUS_SOURCE_UNIT", "message": "The original heading 'Burning rate; mm' has an ambiguous unit and is reported without reinterpretation."})
    return answer, warnings
