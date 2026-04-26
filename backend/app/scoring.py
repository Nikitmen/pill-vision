EMPTY_VALUES = {"none", "unknown", "n/a", "", "unclear", "null"}


def normalize(value):
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in EMPTY_VALUES:
        return None
    return s.replace(" ", "_").replace("-", "_").replace(",", "").strip("_")


def normalize_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    s = str(value).strip().lower()
    if s in {"true", "yes", "1", "present"}:
        return True
    if s in {"false", "no", "0", "none", "unknown", "unclear", "n/a", ""}:
        return False
    return False


def normalize_imprint_text(value):
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in EMPTY_VALUES:
        return None
    return s


def canonical_dosage_form(value):
    v = normalize(value)
    if not v:
        return None
    if "capsule" in v:
        return "capsule"
    return v


def normalize_model_output(raw: dict) -> dict:
    raw = raw or {}
    imprint_present = normalize_bool(raw.get("imprint_present"))
    return {
        "dosage_form": canonical_dosage_form(raw.get("dosage_form")),
        "shape": normalize(raw.get("shape")),
        "color_primary": normalize(raw.get("color_primary")),
        "color_secondary": normalize(raw.get("color_secondary")),
        "translucency": normalize(raw.get("translucency")),
        "surface": normalize(raw.get("surface")),
        "imprint_present": imprint_present,
        "imprint_text": normalize_imprint_text(raw.get("imprint_text")) if imprint_present else None,
        "free_description": raw.get("free_description_en") or raw.get("free_description"),
    }


COLOR_GROUPS = {
    "white_family": ["white", "off_white", "cream", "beige"],
    "yellow_family": ["light_yellow", "yellow"],
    "brown_family": ["light_brown", "brown", "dark_brown"],
    "red_family": ["red", "crimson", "light_orange", "orange"],
    "blue_family": ["light_blue", "blue", "dark_blue"],
    "green_family": ["light_green", "green"],
    "pink_family": ["pink", "light_pink", "purple"],
    "dark_family": ["gray", "dark_gray", "black"],
}


def same_color_group(a, b):
    if not a or not b:
        return False
    return any(a in group and b in group for group in COLOR_GROUPS.values())


def color_score(photo_color, ref_color):
    if not photo_color or not ref_color:
        return 0.0
    if photo_color == ref_color:
        return 1.0
    if same_color_group(photo_color, ref_color):
        return 0.6
    return 0.0


WEIGHTS = {
    "dosage_form": 30,
    "shape": 20,
    "color_primary": 15,
    "color_secondary": 5,
    "translucency": 10,
    "imprint_text": 30,
    "imprint_present": 5,
}

MAX_SCORE = sum(WEIGHTS.values())


def normalize_imprint_for_compare(value):
    if not value:
        return None
    return str(value).upper().replace(" ", "")


def compute_score(photo: dict, ref: dict) -> float:
    score = 0

    for field in ("dosage_form", "shape", "translucency"):
        if photo.get(field) and ref.get(field) and photo[field] == ref[field]:
            score += WEIGHTS[field]

    score += WEIGHTS["color_primary"] * color_score(photo.get("color_primary"), ref.get("color_primary"))
    score += WEIGHTS["color_secondary"] * color_score(photo.get("color_secondary"), ref.get("color_secondary"))

    if photo.get("imprint_present") == ref.get("imprint_present"):
        score += WEIGHTS["imprint_present"]

    photo_imprint = normalize_imprint_for_compare(photo.get("imprint_text"))
    ref_imprint = normalize_imprint_for_compare(ref.get("imprint_text"))
    if photo_imprint and ref_imprint and photo_imprint == ref_imprint:
        score += WEIGHTS["imprint_text"]

    return round(score / MAX_SCORE, 3)
