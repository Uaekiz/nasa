"""Recognize source-record inventories, never scientific interpretations.

These are composable metadata concepts, not whole-question allowlists. Only
metadata wording is consumed; unknown attributes, numbers and instructions stay
in the remainder for coverage to reject. Original header/value validation is
independent of this language layer.
"""
from dataclasses import dataclass
import re


INVENTORY_OBJECT = r"(?:fields?|cells?|values?|entries|parameters?|conditions?|measurements?|readings?|data|information)"
OBJECTS = re.compile(r"\b" + INVENTORY_OBJECT + r"\b", re.I)
ALL_OBJECTS = re.compile(r"\b(?:all|every)\s+(?:(?:source|original|recorded|reported|available)\s+)*" + INVENTORY_OBJECT + r"\b", re.I)
CATEGORIES = re.compile(r"\b(?:conditions|measurements|parameters)\s*(?:and|,|or)\s*(?:conditions|measurements|parameters)\b", re.I)
OVERVIEW = re.compile(
    r"\b(?:overview|inventory|(?:full|complete|detailed|entire)\s+"
    r"(?:(?:source|original|test|sample)\s+)*(?:record|row|entry|summary|details?|data))\b", re.I)
MISSINGNESS = re.compile(
    r"\b(?:missing|blank|empty|absent|unreported|unrecorded|unavailable|unspecified|gaps?)\b|"
    r"\bnot\s+(?:recorded|reported|provided|available|specified|given|present)\b|"
    r"\bno\s+(?:values?|data|entries|measurements?)\b", re.I)
PRESENCE = re.compile(r"\b(?:recorded|reported|provided|available|present|given|specified|logged)\b", re.I)
TABLE_CONTENT = re.compile(r"\b(?:(?:source|original)\s+)?(?:table|record|row|entry)\s+(?:contain|hold|show|give|provide|include|list)s?\b", re.I)
RECORD_CONTEXT = re.compile(r"\b(?:records?|rows?|tests?|samples?|sources?|table|entry)\b", re.I)
LIST_ALL_FIELDS = re.compile(
    r"\blist\s+all(?=\s+(?:(?:original|source|recorded|reported|available|missing|blank|empty)\s+)*"
    + INVENTORY_OBJECT + r"\b)", re.I)


@dataclass(frozen=True)
class RecordQuestion:
    all_fields: bool
    inspect_missing: bool
    remainder: str


def record_question(remainder: str, *, named_fields: bool) -> RecordQuestion:
    """Called after actual source headers and record selectors are recognized."""
    objects = bool(OBJECTS.search(remainder))
    overview = bool(OVERVIEW.search(remainder))
    missing = bool(MISSINGNESS.search(remainder))
    contents = bool(TABLE_CONTENT.search(remainder))
    context = objects or overview or contents or named_fields or bool(RECORD_CONTEXT.search(remainder))
    if not context:
        return RecordQuestion(False, False, remainder)
    all_fields = (overview or bool(ALL_OBJECTS.search(remainder)) or bool(CATEGORIES.search(remainder))
                  or (objects and (not named_fields or missing)) or (contents and not named_fields))
    # "What is missing from this test?" is an inventory too; a named-field
    # question such as "Is Primary aging time blank?" stays narrowly scoped.
    all_fields |= missing and not named_fields
    remaining = OVERVIEW.sub(" ", remainder)
    remaining = TABLE_CONTENT.sub("record", remaining)
    remaining = MISSINGNESS.sub(" ", remaining)
    remaining = PRESENCE.sub(" ", remaining)
    remaining = OBJECTS.sub(" ", remaining)
    remaining = re.sub(r"\b(?:all|every|any|identify|note|highlight|mention|outline|table)\b|\bpoint\s+out\b", " ", remaining, flags=re.I)
    return RecordQuestion(all_fields, missing, remaining)


def inventory_analysis_text(question: str, *, has_record_selector: bool) -> str:
    # Only field inventories bound to selected records bypass the old "list all"
    # shortcut. All numeric words/operators and "list all tests" remain intact.
    return LIST_ALL_FIELDS.sub("list", question) if has_record_selector else question
