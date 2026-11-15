"""Conservative question coverage, source citations, and extractive answer validation."""

from dataclasses import dataclass
import json
from pathlib import PurePosixPath
import re

from .rag_config import RagError
from .record_question import record_question


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
conditions measurements include including provide only also respectively s csv workbook xlsx worksheet sample samples
""".split())


@dataclass(frozen=True)
class Coverage:
    status: str
    required_fields: tuple[str, ...] | dict = ()
    reason: str = ""


def assess_coverage(question: str, result: dict) -> Coverage:
    """Authorize reporting only fields that exist in each cited investigation/source."""
    from .source_catalog import PROFILES, field_value, profile_for
    matches = result.get("matches", [])
    if not matches:
        reason = "No source rows match the selected investigation and test filters."
        if result.get("route") not in {"EXACT_ID", "SEMANTIC"}:
            reason = result.get("reason") or reason
        return Coverage("INSUFFICIENT_EVIDENCE", reason=reason)
    # A polite request is not a hypothetical scientific claim. Strip only the
    # leading request form; "what would happen" remains unsupported.
    question = re.sub(r"^\s*(?:please\s+)?(?:could|would|can)\s+you\b", "", question, flags=re.I)
    if INTERPRETATION.search(question):
        return Coverage("INSUFFICIENT_EVIDENCE", reason="The source tables report fields, but do not establish the requested cause, prediction, risk, or recommendation.")
    records = [m["record"] for m in matches]
    if all(r["investigationId"] == "PSI-100" for r in records) and re.search(r"\b(?:burn time|burning rate|flame|temperature|outcome)\b", question, re.I):
        return Coverage("INSUFFICIENT_EVIDENCE", reason="The SAFFIRE-III table contains sample dimensions, material and airflow conditions, but no measured burning behaviour. It cannot supply the requested burning measurement or outcome.")
    filters = result.get("filters", {})
    if any(filters.get("investigation_ids") and r["investigationId"] not in filters["investigation_ids"] for r in records):
        raise RagError("CORRUPT_INDEX", "A candidate violates the investigation scope.")
    outcome_text = re.sub(r"\b(?:visible )?(?:flame )?extinction diameter\b", " ", question, flags=re.I)
    for outcome in ("Extinction", "Disruption", "Completion"):
        if re.search(r"\b"+outcome+r"\b", outcome_text, re.I) and any(field_value(r, "outcome") != outcome for r in records):
            return Coverage("INSUFFICIENT_EVIDENCE", reason="The selected source rows do not verify the requested reported outcome.")
    selected_fields = {}
    missing = False
    for index, record in enumerate(records, 1):
        profile = profile_for(record)
        headers = set(record["fields"])
        required, remaining = [], question
        for header in sorted(headers, key=len, reverse=True):
            if re.search(re.escape(header), remaining, re.I):
                required.append(header)
                remaining = re.sub(re.escape(header), " ", remaining, flags=re.I)
        for header, pattern in profile["fields"].items():
            if header not in headers: continue
            if re.search(pattern, remaining, re.I):
                required.append(header)
                remaining = re.sub(pattern, " ", remaining, flags=re.I)
        named_fields = bool(required)
        if filters.get("fuel"): required.append(profile["fuel"])
        selectors = list(filters.get("test_ids", [])) + list(filters.get("flex_identifiers", [])) + list(filters.get("investigation_ids", []))
        selectors += [alias for inv in {r["investigationId"] for r in records} for alias in PROFILES[inv]["aliases"]]
        # Authorize material names only when they actually occur in this record.
        selectors += [field_value(record, "fuel")]
        if record["investigationId"] == "PSI-69":
            if all(re.search(r"\b"+v+r"\b", question, re.I) for v in ("Methanol", "Heptane")):
                return Coverage("INSUFFICIENT_EVIDENCE", reason="Combined-fuel conditions are not implemented. Request one original fuel per question.")
        for selector in sorted(set(selectors) - {""}, key=len, reverse=True):
            remaining = re.sub(r"(?<!\w)"+re.escape(selector)+r"(?!\w)", " ", remaining, flags=re.I)
        intent = record_question(remaining, named_fields=named_fields)
        remaining = intent.remainder
        tokens = re.findall(r"[a-z0-9]+", remaining.casefold())
        if any(token not in GRAMMAR for token in tokens):
            return Coverage("INSUFFICIENT_EVIDENCE", reason="The question includes an attribute or condition that the selected source cannot verify. Request original fields or an explicit test summary.")
        if intent.inspect_missing and result.get("route") != "EXACT_ID":
            return Coverage("INSUFFICIENT_EVIDENCE", reason="A missing-field inventory needs an explicit test or source-record ID. No cross-record missingness filter or count was inferred.")
        if intent.all_fields:
            # Use this row's own reviewed headers, including empty cells. Do not
            # fabricate absent columns or merge the CSV/workbook field layouts.
            required = list(record["fields"])
        elif not required or re.search(r"\b(summariz\w*|summaris\w*|summary|details?|both records)\b", question, re.I):
            required += profile["summary"]
        if any(h not in headers for h in required):
            return Coverage("INSUFFICIENT_EVIDENCE", reason="A requested field is absent from this source; no missing measurement was inferred.")
        selected_fields[f"S{index}"] = tuple(dict.fromkeys(required))
        missing |= any(not record["fields"][h].strip() or record["fields"][h].strip().casefold() in {"none", "n/a", "na", "-", "–", "—"} for h in required)
    if result.get("route") == "SEMANTIC":
        if not re.search(r"\b(examples?|tests?|records?|rows?|samples?)\b", question, re.I) or not re.search(r"\b(show|find|list|give|retrieve|which|summariz\w*|summaris\w*)\b", question, re.I):
            return Coverage("INSUFFICIENT_EVIDENCE", reason="Nearest rows do not establish a general scientific answer.")
        if any(filters.get("fuel") and " ".join(field_value(r, "fuel").split()) != filters["fuel"] for r in records):
            raise RagError("CORRUPT_INDEX", "A candidate violates the requested material/fuel condition.")
        status = "PARTIAL"
    else:
        present_tests = {r["sourceTestId"] for r in records}
        identifiers = {field_value(r, "identifier") for r in records}
        complete = (set(filters.get("test_ids", [])) <= present_tests and set(filters.get("flex_identifiers", [])) <= identifiers
            and result.get("eligibleRecordCount") == len(records))
        status = "ANSWERED" if complete else "PARTIAL"
    values = list(selected_fields.values())
    required = values[0] if all(v == values[0] for v in values) else selected_fields
    return Coverage("PARTIAL" if missing else status, required)


def fields_for(required_fields, index):
    return required_fields[f"S{index}"] if isinstance(required_fields, dict) else required_fields


def build_sources(records: list[dict]) -> list[dict]:
    return [{
        "citationId": f"S{index}", "sourceId": record["sourceId"],
        "investigationId": record["investigationId"], "experimentId": None,
        "sourceType": record["sourceType"], "title": PurePosixPath(record["sourceFile"]).name,
        "pdfPage": None, "printedPage": None, "table": None, "chunkId": None,
        "sheetName": record.get("sheetName"), "rowNumber": record["rowNumber"],
        "sourceTestId": record["sourceTestId"], "sourceFile": record["sourceFile"],
    } for index, record in enumerate(records, 1)]


def generation_input(question: str, records: list[dict], required_fields: tuple[str, ...]) -> tuple[str, dict]:
    citations = [f"S{i}" for i in range(1, len(records) + 1)]
    schemas = {}
    for index, citation in enumerate(citations, 1):
        headers = fields_for(required_fields, index)
        schemas[citation] = {"type": "object", "additionalProperties": False, "required": list(headers),
            "properties": {header: {"type": "string", "enum": [records[index - 1]["fields"][header]]} for header in headers}}
    schema = {"type": "object", "additionalProperties": False, "required": ["records"],
        "properties": {"records": {"type": "object", "additionalProperties": False,
            "required": citations, "properties": schemas}}}
    prompt = (
        "Answer the English question by extracting the required original fields for each evidence row. "
        "Return JSON following the schema: records maps EACH citation ID to its required field/value pairs. "
        "Copy cell strings EXACTLY, including empty strings, qualifiers, decimal formatting, and units in headings. "
        "Do not return prose, calculations, causes, recommendations, filenames, or row numbers. "
        "The service will validate every value and compose short, cited English sentences from these cells.\n"
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
            if not isinstance(fields, dict) or set(fields) != set(fields_for(required_fields, int(citation[1:]))):
                raise ValueError("Missing or unknown original fields")
            if any(not isinstance(value, str) or value != expected[citation]["fields"][header] for header, value in fields.items()):
                raise ValueError("A generated value differs from its cited source cell")
    except (ValueError, TypeError, KeyError) as error:
        raise RagError("GENERATION_VALIDATION_FAILED", "The model's field values or citation IDs could not be validated against the supplied evidence.") from error
    from .answer_narrative import render_source_answer
    return render_source_answer(records, required_fields)
