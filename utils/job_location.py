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
    r"\b(?:europe|emea|apac|asia|australia|singapore|japan|tokyo|mexico)\b",
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


_NO_SPONSORSHIP_PATTERNS = (
    r"\b(?:must|should)\s+(?:already\s+)?be\s+(?:legally\s+)?authorized\b.{0,80}\bwithout\b.{0,30}\bsponsorship\b",
    r"\b(?:without|no)\s+(?:current\s+or\s+future\s+)?(?:visa\s+)?sponsorship\b",
    r"\b(?:will|can|does)\s+not\s+(?:provide|offer)\b.{0,25}\bsponsorship\b",
    r"\b(?:unable|not able)\s+to\s+sponsor\b",
)


def assess_sponsorship_language(description: str = "") -> Tuple[bool, str]:
    """Reject postings that explicitly say employment sponsorship is unavailable."""
    text = description or ""
    if _matches_any(text, _NO_SPONSORSHIP_PATTERNS):
        return False, "posting explicitly excludes visa sponsorship"
    return True, "no explicit sponsorship exclusion"
