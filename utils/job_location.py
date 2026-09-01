"""Deterministic US job-location eligibility checks.

The classifier is intentionally conservative: clearly foreign-only roles are
excluded, while unknown locations remain eligible so incomplete ATS metadata
does not hide valid US openings.
"""
import re
from typing import Tuple


_US_LOCATION_PATTERNS = (
    r"\bunited states(?: of america)?\b",
    r"\busa\b",
    r"\bu\.s\.a\.?(?=\s|$|[,;/])",
    r"\bu\.s\.(?=\s|$|[,;/])",
    r"\bus\b",
    r"\bremote\s*[-–—,(]?\s*us\b",
    r"\bus\s*[-–— ](?:remote|based|only)\b",
    r"\b(?:new york|san francisco|san jose|sunnyvale|mountain view|palo alto|"
    r"seattle|austin|boston|chicago|dallas|denver|atlanta|los angeles|"
    r"washington,? d\.?c\.?|raleigh|miami|portland|philadelphia|pittsburgh)\b",
    r"\b(?:alabama|alaska|arizona|arkansas|california|colorado|connecticut|"
    r"delaware|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|"
    r"kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|"
    r"mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|"
    r"new mexico|new york|north carolina|north dakota|ohio|oklahoma|oregon|"
    r"pennsylvania|rhode island|south carolina|south dakota|tennessee|texas|"
    r"utah|vermont|virginia|washington|west virginia|wisconsin|wyoming)\b",
    r",\s*(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|"
    r"MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|"
    r"TX|UT|VT|VA|WA|WV|WI|WY)(?:\b|\s)",
)

_US_DESCRIPTION_PATTERNS = (
    r"\b(?:this|the)\s+(?:role|position|job|opening)\b.{0,80}\b(?:available|open|based|located|remote)\b.{0,45}\b(?:united states|usa|u\.s\.)\b",
    r"\b(?:available|open|hiring|locations?)\b.{0,55}\b(?:united states|usa|u\.s\.)\b",
    r"\b(?:work authorization|authorized|eligible)\b.{0,45}\b(?:united states|the us|u\.s\.)\b",
)

_GLOBAL_LOCATION_PATTERNS = (
    r"\bglobal\b",
    r"\bworldwide\b",
    r"\bwork from anywhere\b",
    r"\banywhere in the world\b",
)

_GLOBAL_DESCRIPTION_PATTERNS = (
    r"\b(?:this|the)\s+(?:role|position|job|opening)\b.{0,60}\b(?:available|open|remote)\b.{0,35}\b(?:globally|worldwide|anywhere in the world)\b",
    r"\b(?:candidates|applicants)\b.{0,45}\b(?:worldwide|globally)\b",
)

_FOREIGN_LOCATION_PATTERNS = (
    r"\b(?:india|bengaluru|bangalore|hyderabad|pune|gurugram|gurgaon|noida|"
    r"mumbai|chennai|delhi)\b",
    r"\b(?:brazil|brasil|sao paulo|são paulo|rio de janeiro|latam|latin america|"
    r"south america)\b",
    r"\b(?:united kingdom|u\.?k\.?|london|manchester|ireland|dublin)\b",
    r"\b(?:canada|toronto|vancouver|montreal|ottawa)\b",
    r"\b(?:ontario|quebec|alberta|british columbia|nova scotia|manitoba|"
    r"saskatchewan|new brunswick|newfoundland and labrador)\b",
    r"\b(?:europe|emea|apac|asia|australia|new zealand|singapore|japan|tokyo|"
    r"mexico|indonesia|china|netherlands|spain|portugal|germany|france|sweden|"
    r"denmark|finland|norway|switzerland|austria|belgium|poland|czechia|"
    r"czech republic|romania|bulgaria|ukraine|lithuania|south korea|malaysia|"
    r"philippines|thailand|vietnam|taiwan|hong kong|israel|united arab emirates|"
    r"uae|saudi arabia|south africa|turkey|argentina|colombia|chile|peru)\b",
    r"\b(?:berlin|munich|hamburg|frankfurt|amsterdam|stockholm|copenhagen|"
    r"helsinki|oslo|paris|madrid|barcelona|lisbon|porto|prague|warsaw|"
    r"zurich|geneva|vienna|brussels|sofia|bucharest|kyiv|vilnius|seoul)\b",
    r"\b(?:lithuania|south korea|republic of korea)\b",
)

_FOREIGN_DESCRIPTION_PATTERNS = (
    r"\b(?:role|position|job|candidate|applicant)s?\b.{0,45}\b(?:based|located|remote)\b.{0,25}\b(?:india|brazil|brasil|latam|latin america|united kingdom|uk|canada|europe|emea|apac)\b",
    r"\b(?:based|located|remote)\s+(?:in|from|within)\s+(?:india|brazil|brasil|latam|latin america|united kingdom|uk|canada|europe|emea|apac)\b",
)

_CANADIAN_CODE_SEGMENT = re.compile(
    r"(?:^|[;/])\s*[^;/]+,\s*(?:AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT)"
    r"\s*,\s*CA\s*(?=$|[;/])",
    re.IGNORECASE,
)


def _matches_any(text: str, patterns: tuple) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def assess_us_job_location(location: str = "", description: str = "") -> Tuple[bool, str]:
    """Return whether a role may be worked from the US and an audit reason.

    Precedence matters: an explicit US option keeps a multi-country role even
    when India, Brazil, or another country is also listed.
    """
    location = (location or "").strip()
    description = (description or "").strip()

    # ATS country codes make "..., ON, CA" ambiguous with California. Remove
    # Canadian province/country segments before checking whether another
    # segment explicitly offers a US location.
    without_canadian_segments, canadian_segment_count = _CANADIAN_CODE_SEGMENT.subn(
        " ", location
    )
    if canadian_segment_count and not _matches_any(
        without_canadian_segments, _US_LOCATION_PATTERNS
    ):
        return False, "non-US-only location"

    # Country codes can collide with US state codes (for example Berlin, DE).
    # Treat a same-segment foreign city/country + state-code-only US signal as
    # foreign, but retain a separate US segment such as "Bengaluru; Redmond, WA".
    segments = [part.strip() for part in re.split(r"[;/|]", location) if part.strip()]
    ambiguous_foreign_segments = [
        segment
        for segment in segments
        if _matches_any(segment, _FOREIGN_LOCATION_PATTERNS)
        and _matches_any(segment, (_US_LOCATION_PATTERNS[-1],))
        and not _matches_any(segment, _US_LOCATION_PATTERNS[:-1])
    ]
    if ambiguous_foreign_segments:
        other_segments = " ; ".join(
            segment for segment in segments if segment not in ambiguous_foreign_segments
        )
        if not _matches_any(other_segments, _US_LOCATION_PATTERNS):
            return False, "non-US-only location"

    if _matches_any(location, _US_LOCATION_PATTERNS):
        return True, "explicit US availability"

    if _matches_any(location, _GLOBAL_LOCATION_PATTERNS):
        return True, "global/worldwide availability"

    if _matches_any(location, _FOREIGN_LOCATION_PATTERNS):
        return False, "non-US-only location"

    if _matches_any(description, _US_DESCRIPTION_PATTERNS):
        return True, "explicit US availability"

    if _matches_any(description, _FOREIGN_DESCRIPTION_PATTERNS):
        return False, "non-US-only location"

    if _matches_any(description, _GLOBAL_DESCRIPTION_PATTERNS):
        return True, "global/worldwide availability"

    if re.search(r"\b(?:north america|americas)\b", location, re.IGNORECASE):
        return True, "US-inclusive region"

    return True, "location unknown or not explicitly restricted"


def is_us_job_eligible(location: str = "", description: str = "") -> bool:
    """Convenience boolean wrapper for US eligibility checks."""
    return assess_us_job_location(location, description)[0]


_WORK_AUTHORIZATION_EXCLUSIONS = (
    (
        (
            r"\b(?:must|should)\s+(?:already\s+)?be\s+(?:legally\s+)?authorized\b"
            r".{0,80}\bwithout\b.{0,30}\bsponsorship\b|"
            r"\b(?:will|can|does|do)\s+not\s+(?:provide|offer|support)\b.{0,35}\bsponsorship\b|"
            r"\b(?:unable|not able)\s+to\s+(?:sponsor|(?:provide|offer|support)\s+"
            r"(?:visa\s+)?sponsorship)\b|"
            r"\b(?:cannot|can't)\s+(?:sponsor|(?:provide|offer|support)\s+"
            r"(?:visa\s+)?sponsorship)\b|"
            r"\bno\s+(?:visa\s+)?sponsorship\b(?!\s+required)|"
            r"\b(?:visa|immigration|employment)\s+sponsorship\s+(?:is\s+)?"
            r"(?:not available|unavailable|not offered|not provided)|"
            r"\b(?:this|the)\s+(?:role|position|job)\s+(?:is\s+)?not\s+eligible\b"
            r".{0,35}\bsponsorship\b"
        ),
        "posting explicitly excludes visa sponsorship",
    ),
    (
        (
            r"\b(?:u\.?s\.?|united states)\s+citizenship\s+(?:is\s+)?required\b|"
            r"\bmust\s+be\s+(?:a\s+)?(?:u\.?s\.?|united states)\s+citizens?\b|"
            r"\b(?:only|solely)\s+(?:u\.?s\.?|united states)\s+citizens?\b|"
            r"\b(?:u\.?s\.?\s+)?citizens?\s+(?:only|required)\b"
        ),
        "posting requires US citizenship",
    ),
    (
        (
            r"\b(?:green card|lawful permanent resident|permanent resident status)"
            r"\s+(?:is\s+)?required\b|"
            r"\bmust\s+be\b.{0,35}\b(?:green card holder|lawful permanent resident)\b|"
            r"\b(?:citizens?|nationals?|lawful permanent residents?|green card holders?)"
            r"(?:\s*(?:,|or|and)\s*(?:citizens?|nationals?|lawful permanent residents?|"
            r"green card holders?))*\s+only\b|"
            r"\bmust\s+(?:qualify|be eligible)\s+as\s+(?:a\s+)?u\.?s\.?\s+person\b|"
            r"\b(?:u\.?s\.?\s+citizens?|green card holders?)\s+(?:or|and)\s+"
            r"(?:u\.?s\.?\s+citizens?|green card holders?)\b|"
            r"\b(?:must|required\s+to)\s+be\b.{0,100}\b(?:u\.?s\.?\s+person|"
            r"u\.?s\.?\s+national|lawful permanent residents?|protected individual)\b"
        ),
        "posting requires citizenship or permanent-resident status",
    ),
    (
        (
            r"\b(?:active|current|existing)\b.{0,30}\b(?:security\s+)?clearance\b|"
            r"\b(?:top secret|secret|ts/?sci)\b.{0,20}\b(?:security\s+)?clearance\b|"
            r"\b(?:security\s+)?clearance\s+(?:is\s+)?required\b|"
            r"\bmust\s+(?:hold|possess|maintain|obtain)\b.{0,40}\bclearance\b|"
            r"\b(?:ability|eligible|eligibility)\s+to\s+(?:obtain|maintain)\b"
            r".{0,40}\bclearance\b"
        ),
        "posting requires or conditions employment on a security clearance",
    ),
    (
        (
            r"\b(?:do|does|will)\s+not\s+(?:accept|consider|support)\b.{0,35}"
            r"\b(?:stem\s+)?opt\b|"
            r"\b(?:stem\s+)?opt\s+(?:candidates?|holders?)\s+(?:are\s+)?not\b|"
            r"\b(?:stem\s+)?opt(?:/cpt|\s+or\s+cpt)?\s+(?:candidates?|holders?)"
            r"\s+(?:will\s+)?not\s+be\s+(?:accepted|considered)\b|"
            r"\bno\s+(?:stem\s+)?opt(?:\s+or\s+cpt)?\b|"
            r"\b(?:not eligible|ineligible)\b.{0,35}\b(?:stem\s+)?opt\b"
        ),
        "posting explicitly excludes OPT/STEM OPT candidates",
    ),
)

_EXPLICIT_SPONSORSHIP_PATTERNS = (
    r"\b(?:visa|immigration|employment|h-?1b)\s+sponsorship\s+(?:is\s+)?"
    r"(?:available|provided|offered|supported)\b",
    r"\bwe\s+(?:will|can|may)\s+sponsor\b",
    r"\b(?:eligible|considered)\s+for\s+(?:visa|h-?1b)\s+sponsorship\b",
    r"\bh-?1b\s+(?:transfer|sponsorship)\b",
)


def classify_sponsorship_language(
    description: str = "", title: str = ""
) -> Tuple[str, str]:
    """Classify JD work-authorization language for an OPT/STEM OPT candidate.

    DOL history is deliberately absent here. The current posting decides basic
    eligibility; historical filings are presented later as supporting context.
    """
    if re.search(
        r"\b(?:top secret|secret|ts/?sci)\b.{0,25}\bclearance\b|"
        r"\bclearance\b.{0,25}\b(?:required|top secret|secret|ts/?sci)\b",
        title or "",
        flags=re.IGNORECASE,
    ):
        return "excluded", "job title requires or emphasizes a security clearance"

    text = f"{title or ''}\n{description or ''}"
    for pattern, reason in _WORK_AUTHORIZATION_EXCLUSIONS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            return "excluded", reason
    if _matches_any(text, _EXPLICIT_SPONSORSHIP_PATTERNS):
        return "explicit_sponsorship", "posting explicitly indicates sponsorship support"
    return (
        "not_specified",
        "compatible with current OPT/STEM OPT unless the employer confirms otherwise",
    )


def assess_sponsorship_language(
    description: str = "", title: str = ""
) -> Tuple[bool, str]:
    """Return whether the JD is viable for an OPT/STEM OPT candidate."""
    status, reason = classify_sponsorship_language(description, title)
    return status != "excluded", reason
