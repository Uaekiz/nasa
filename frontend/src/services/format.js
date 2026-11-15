// Format normalized UI values only. Original source cells remain verbatim.
export function formatNumber(value, options = {}) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "Not reported";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 6, ...options }).format(value);
}

export function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not reported";
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit", timeZoneName: "short",
  }).format(date);
}

export function investigationDescription(investigation) {
  const descriptions = {
    "PSI-69": "FLEX droplet experiments. Original fuel, ambient conditions and reported outcomes.",
    "PSI-25": "BASS-II solid specimens. CSV and workbook records retain their separate source cells.",
    "PSI-100": "SAFFIRE-III sample and airflow conditions. This table contains no measured burning outcomes.",
    "PSI-101": "SAME-R sample, inlet flow and aging records. These are not treated as open-flame experiments.",
  };
  return descriptions[investigation.investigationId] || "Open the source records to review available fields and provenance.";
}

export function warningText(warning) {
  // Import-time messages are stored in the existing database. Translate their
  // application-owned explanation without rewriting source cells or the DB.
  const messages = {
    BURNING_RATE_UNIT_AMBIGUOUS: "The source heading 'Burning rate; mm' has an ambiguous rate unit. No mm/s conversion was inferred.",
    VALUE_REQUIRES_REVIEW: "This source value needs review and is excluded from verified numerical comparisons. The raw cell is preserved.",
    DISPLAY_UNIT_UNSPECIFIED: "The source display setting has no verified physical unit. It is not interpreted as an airflow speed.",
    NEGATIVE_REPORTED_VALUE: "The negative value is preserved as reported and excluded from verified comparisons.",
    NO_NUMERIC_MEASUREMENTS: "This source provides conditions and qualitative fields, with no numerical burning-outcome measurements.",
    NO_VERIFIED_MEASUREMENTS: "No verified numerical outcome measurement is available for this record. Original source fields remain available.",
    DATA_EXCLUDED: "Missing or unverified values were excluded from the numerical comparison.",
    NOT_COMPARABLE: "The records do not provide comparable verified values for this field.",
  };
  return messages[warning.code] || warning.message;
}
