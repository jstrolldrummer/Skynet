"""Tiny pure-function utilities. Kept dependency-free to avoid import cycles."""


def normalize_phone(raw: str) -> str:
    cleaned = "".join(c for c in raw if c.isdigit() or c == "+")
    if cleaned.startswith("+"):
        return cleaned
    if len(cleaned) == 10:
        return "+1" + cleaned
    if len(cleaned) == 11 and cleaned.startswith("1"):
        return "+" + cleaned
    return cleaned


def first_name(full_name: str) -> str:
    parts = full_name.strip().split()
    return parts[0] if parts else ""
