import re
import unicodedata


_NUMBER_WORDS = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
)
_TENS_WORDS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_SCALE_WORDS = ((1_000_000_000, "billion"), (1_000_000, "million"), (1_000, "thousand"))
_SPOKEN_ABBREVIATIONS = {
    "AI": "A I",
    "API": "A P I",
    "KAM": "K A M",
    "KPI": "K P I",
    "ROI": "R O I",
    "SKU": "S K U",
}


def _integer_to_words(value: int) -> str:
    if value < 20:
        return _NUMBER_WORDS[value]
    if value < 100:
        return _TENS_WORDS[value // 10] + (f"-{_NUMBER_WORDS[value % 10]}" if value % 10 else "")
    if value < 1_000:
        remainder = value % 100
        return f"{_NUMBER_WORDS[value // 100]} hundred" + (f" {_integer_to_words(remainder)}" if remainder else "")
    for scale, name in _SCALE_WORDS:
        if value >= scale:
            remainder = value % scale
            return f"{_integer_to_words(value // scale)} {name}" + (f" {_integer_to_words(remainder)}" if remainder else "")
    return str(value)


def _number_to_words(value: str) -> str:
    normalized = value.replace(",", "")
    if "." in normalized:
        whole, fraction = normalized.split(".", 1)
        whole_words = _integer_to_words(int(whole))
        fraction_words = " ".join(_NUMBER_WORDS[int(digit)] for digit in fraction)
        return f"{whole_words} point {fraction_words}"
    return _integer_to_words(int(normalized))


def _replace_numbers(text: str) -> str:
    def compact_number(match: re.Match[str]) -> str:
        number, suffix = match.group(1), match.group(2).lower()
        scale = {"k": "thousand", "m": "million", "b": "billion"}[suffix]
        return f"{_number_to_words(number)} {scale}"

    def percentage(match: re.Match[str]) -> str:
        return f"{_number_to_words(match.group(1))} percent"

    def currency(match: re.Match[str]) -> str:
        return f"{_number_to_words(match.group(1))} rupees"

    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*([kKmMbB])\b", compact_number, text)
    text = re.sub(r"(?<!\w)(\d+(?:\.\d+)?)\s*%", percentage, text)
    text = re.sub(r"₹\s*(\d+(?:,\d{3})*(?:\.\d+)?)", currency, text)
    text = re.sub(r"\$\s*(\d+(?:,\d{3})*(?:\.\d+)?)", lambda match: f"{_number_to_words(match.group(1))} dollars", text)
    text = re.sub(r"€\s*(\d+(?:,\d{3})*(?:\.\d+)?)", lambda match: f"{_number_to_words(match.group(1))} euros", text)
    text = re.sub(r"£\s*(\d+(?:,\d{3})*(?:\.\d+)?)", lambda match: f"{_number_to_words(match.group(1))} pounds", text)
    return re.sub(r"(?<![\w.])(\d+(?:,\d{3})*(?:\.\d+)?)(?![\w.])", lambda match: _number_to_words(match.group(1)), text)


def _remove_decorative_symbols(text: str) -> str:
    cleaned = []
    for character in text:
        category = unicodedata.category(character)
        if category == "So" or character in "\ufe0e\ufe0f\u200d":
            continue
        cleaned.append(character)
    return "".join(cleaned)


def clean_text_for_speech(text: str) -> str:
    """Convert a formatted assistant response into natural Piper input."""
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-+*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+[.)]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_~]+", "", text)
    text = _replace_numbers(text)
    text = _remove_decorative_symbols(text)
    for abbreviation, spoken in _SPOKEN_ABBREVIATIONS.items():
        text = re.sub(rf"\b{abbreviation}\b", spoken, text)
    text = "".join(
        character
        if character.isalnum() or character.isspace() or unicodedata.category(character).startswith("M") or character in ".,!?:;'’()/%-"
        else " "
        for character in text
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text