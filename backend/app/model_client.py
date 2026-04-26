import base64
import json
import os
import re
from io import BytesIO

import requests
from PIL import Image


CLASSIFY_PROMPT = """
Classify the visible dosage form of the object in the image as one of:
tablet, capsule, soft capsule, caplet, unknown.
Return JSON only:
{"dosage_form": ""}
""".strip()


FEATURE_PROMPT_TEMPLATE = """
Use this dosage form as fixed:
{fixed_dosage_form_json}
Do not reclassify dosage_form.
You are a pharmaceutical visual annotation assistant.
Your task is to analyze a single medicine unit shown in the image and extract ONLY directly visible appearance features for a soft capsule.
Important:
- Do NOT identify the medicine, active ingredient, strength, manufacturer, or medical use.
- Do NOT guess hidden or uncertain properties.
- If a feature is not clearly visible, return "unknown" or "unclear".
- Return JSON only.
- Do not output markdown.
- Do not add explanations outside the JSON.
Return a valid JSON object with exactly these fields:
{
  "dosage_form": "",
  "color_primary": "",
  "color_secondary": "",
  "shape": "",
  "shell_material": "",
  "surface": "",
  "translucency": "",
  "contents_visible": "",
  "contents_color": "",
  "imprint_present": "",
  "imprint_text": "",
  "symbol_or_logo": "",
  "side_visible": "",
  "edges": "",
  "estimated_size_relative": "",
  "confidence": "",
  "free_description_en": ""
}
Rules:
1. Annotate only what is directly visible in the image.
2. Use "unknown" when a feature cannot be determined confidently.
3. Use "unclear" only when something may be present but cannot be confirmed.
4. Use "none" only when absence is visually clear.
5. Do not confuse shell material with surface appearance.
6. Do not infer shell material unless visually obvious.
7. Prefer "soft capsule" over "tablet" for translucent, glossy, soft-shell objects.
8. Do not use "film-coated" for soft capsules.
9. Do not invent imprint text unless it is clearly visible.
10. free_description_en must be a single short sentence and must not introduce any feature not already present in the structured fields.
11. Use only allowed canonical values.
12. Do not invent new wording.
Allowed canonical values:
- shape: round, oval, oblong, capsule-shaped, irregular, unknown
- shell_material: gelatin, unknown, none
- surface: smooth, glossy, matte, rough, speckled, unknown
- translucency: opaque, translucent, transparent, unknown
- side_visible: one side, both sides, unclear
- edges: rounded, beveled, sharp, unknown
- estimated_size_relative: small, standard, large, unknown
- symbol_or_logo: none, unclear, or visible symbol text
- confidence: low, medium, high
Field guidance:
- dosage_form: must be "{dosage_form}"
- color_primary: main visible shell color
- color_secondary: secondary tint or "none"
- shape: choose one canonical value only
- shell_material: use "gelatin" only if visually justified, otherwise "unknown"
- surface: use one or two short canonical descriptors, such as "smooth, glossy"
- translucency: describe the shell visually
- contents_visible: use true, false, or "unclear"
- contents_color: visible internal fill color if clearly observable; otherwise "unknown" or "none"
- imprint_present: use true, false, or "unclear"
- imprint_text: readable text only; otherwise "none" or "unclear"
- symbol_or_logo: visible symbol/logo only; otherwise "none" or "unclear"
- side_visible: use a canonical value only
- edges: use a canonical value only
- estimated_size_relative: use a canonical value only
- confidence: use a canonical value only
Consistency rules:
- If imprint_present is false, imprint_text must be "none".
- If imprint_present is "unclear", imprint_text must be "unclear".
- If contents_visible is false, contents_color must be "none".
- If contents_visible is "unclear", contents_color should usually be "unknown".
- free_description_en must use only information already present in the JSON fields.
Example style for free_description_en:
"Red translucent oval soft capsule with a smooth glossy surface and a visible imprint."
"Translucent oval soft capsule with rounded edges and no clearly readable imprint."
Before producing the final JSON, internally verify:
- Is each field directly visible?
- Is any field inferred rather than observed?
- Is wording canonical?
If a field is inferred or uncertain, replace it with "unknown" or "unclear".
Now analyze the image and return JSON only.
""".strip()


VALIDATOR_PROMPT_TEMPLATE = """
You are a pharmaceutical annotation validator and normalizer.
Your task is to validate, correct, and normalize a JSON annotation for a soft capsule based only on the provided JSON.
Do not add new observations that are not supported by the existing fields.
Be conservative.
Important:
- Return JSON only.
- Do not output markdown.
- Do not add explanations.
- Keep the same schema and the same field order.
- Remove unsupported inferences.
- Normalize wording to canonical values only.
The JSON schema is:
{
  "dosage_form": "",
  "color_primary": "",
  "color_secondary": "",
  "shape": "",
  "shell_material": "",
  "surface": "",
  "translucency": "",
  "contents_visible": "",
  "contents_color": "",
  "imprint_present": "",
  "imprint_text": "",
  "symbol_or_logo": "",
  "side_visible": "",
  "edges": "",
  "estimated_size_relative": "",
  "confidence": "",
  "free_description_en": ""
}
Allowed canonical values:
- dosage_form: soft capsule
- shape: round, oval, oblong, capsule-shaped, irregular, unknown
- shell_material: gelatin, unknown, none
- translucency: opaque, translucent, transparent, unknown
- side_visible: one side, both sides, unclear
- edges: rounded, beveled, sharp, unknown
- estimated_size_relative: small, standard, large, unknown
- confidence: low, medium, high
Allowed boolean-style values:
- contents_visible: true, false, or "unclear"
- imprint_present: true, false, or "unclear"
Allowed surface descriptors:
- smooth
- glossy
- matte
- rough
- speckled
- unknown
Surface normalization rules:
- Keep only allowed surface descriptors.
- If two descriptors are present, use comma-separated canonical form, for example:
  "smooth, glossy"
- Remove unsupported extra wording.
Normalization rules:
- replace "Yes" with true
- replace "No" with false
- replace "Ellipsoidal/Oval" with "oval"
- replace "ellipsoidal" with "oval"
- replace "One side face (anterior view)" with "one side"
- replace "Single face view (one side)" with "one side"
- replace "No distinct symbol or logo visible" with "none"
- replace "None visible" with "none"
- replace "Smooth, rounded" with "rounded" for edges
- keep only allowed canonical values
- simplify wording whenever possible
Validation rules:
1. dosage_form must be "soft capsule"
2. Do not change the dosage form.
3. If shell_material contains non-canonical wording like "polymeric", replace with "unknown" unless it is exactly "gelatin".
4. If contents_visible is false, contents_color must be "none".
5. If contents_visible is "unclear", contents_color should usually be "unknown".
6. If imprint_present is false, imprint_text must be "none".
7. If imprint_present is "unclear", imprint_text must be "unclear".
8. If symbol_or_logo is not clearly identified, use "none" or "unclear".
9. free_description_en must be one short sentence.
10. free_description_en must use only information already present in the structured fields.
11. free_description_en must not mention tablet, film coating, or any unsupported inference.
12. If a value is not canonical and cannot be normalized safely, replace it with "unknown".
Style rules for free_description_en:
- short
- formal
- pharmaceutical
- no speculation
- no new information
- use "soft capsule", not "tablet"
Now validate and normalize the following JSON.
Return corrected JSON only:
{raw_json}
""".strip()


MOCK_OUTPUT = {
    "dosage_form": "soft capsule",
    "color_primary": "white",
    "color_secondary": "none",
    "shape": "capsule-shaped",
    "shell_material": "unknown",
    "surface": "smooth, glossy",
    "translucency": "opaque",
    "contents_visible": False,
    "contents_color": "none",
    "imprint_present": True,
    "imprint_text": "none",
    "symbol_or_logo": "none",
    "side_visible": "one side",
    "edges": "rounded",
    "estimated_size_relative": "small",
    "confidence": "medium",
    "free_description_en": "White opaque soft capsule with a smooth glossy surface and no readable imprint.",
}


def image_to_data_url(image_bytes: bytes, filename: str) -> str:
    mime = "image/jpeg"
    lower = filename.lower()
    if lower.endswith(".png"):
        mime = "image/png"
    elif lower.endswith(".webp"):
        mime = "image/webp"

    # Быстро приводим огромные фото к более удобному размеру для VLM.
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        img.thumbnail((1280, 1280))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=90)
        image_bytes = buf.getvalue()
        mime = "image/jpeg"
    except Exception:
        pass

    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def extract_json_from_text(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError(f"Model returned non-JSON text: {text[:500]}")
        return json.loads(match.group(0))


def _chat_completion_text(prompt: str, image_data_url: str | None = None, max_tokens: int = 900) -> str:
    base_url = os.getenv("MODEL_BASE_URL", "http://host.docker.internal:1234/v1").rstrip("/")
    model_name = os.getenv("MODEL_NAME", "qwen2.5-vl-7b-instruct")
    timeout = int(os.getenv("MODEL_TIMEOUT_SEC", "180"))
    temperature = float(os.getenv("MODEL_TEMPERATURE", "0.0"))

    if image_data_url:
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]
    else:
        content = prompt

    payload = {
        "model": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }

    response = requests.post(f"{base_url}/chat/completions", json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def _normalize_dosage_form(value: str | None) -> str:
    value = (value or "unknown").strip().lower().replace("_", "-")
    aliases = {
        "soft-capsule": "soft capsule",
        "soft_capsule": "soft capsule",
        "softgel": "soft capsule",
        "gel capsule": "soft capsule",
        "hard capsule": "capsule",
        "hard-capsule": "capsule",
        "capsule-shaped tablet": "caplet",
    }
    return aliases.get(value, value)


def analyze_image_with_steps(image_bytes: bytes, filename: str) -> dict:
    mode = os.getenv("MODEL_MODE", "mock").lower().strip()
    if mode == "mock":
        return {
            "final_json": MOCK_OUTPUT,
            "steps": {
                "stage_1_dosage_form": {"dosage_form": "soft capsule"},
                "stage_2_raw_features": MOCK_OUTPUT,
                "stage_3_validated_json": MOCK_OUTPUT,
            },
        }

    if mode != "lmstudio":
        raise ValueError("MODEL_MODE must be mock or lmstudio")

    data_url = image_to_data_url(image_bytes, filename)

    # 1) Быстрая классификация формы.
    stage_1_text = _chat_completion_text(CLASSIFY_PROMPT, image_data_url=data_url, max_tokens=120)
    stage_1_json = extract_json_from_text(stage_1_text)
    dosage_form = _normalize_dosage_form(stage_1_json.get("dosage_form"))

    # Для текущего baseline валидатор заточен под soft capsule.
    # Если первая стадия не уверена, но фото похоже на капсулу, оставляем ответ модели как fixed.
    fixed_json = {"dosage_form": dosage_form}

    # 2) Извлечение признаков с фиксированной формой.
    feature_prompt = (
        FEATURE_PROMPT_TEMPLATE
        .replace("{fixed_dosage_form_json}", json.dumps(fixed_json, ensure_ascii=False))
        .replace("{dosage_form}", dosage_form)
    )
    stage_2_text = _chat_completion_text(feature_prompt, image_data_url=data_url, max_tokens=1100)
    stage_2_json = extract_json_from_text(stage_2_text)

    # 3) Валидация и нормализация только по JSON второй стадии.
    validator_prompt = VALIDATOR_PROMPT_TEMPLATE.replace(
        "{raw_json}", json.dumps(stage_2_json, ensure_ascii=False, indent=2)
    )
    stage_3_text = _chat_completion_text(validator_prompt, image_data_url=None, max_tokens=900)
    stage_3_json = extract_json_from_text(stage_3_text)

    return {
        "final_json": stage_3_json,
        "steps": {
            "stage_1_dosage_form": {"raw": stage_1_json, "normalized": fixed_json},
            "stage_2_raw_features": stage_2_json,
            "stage_3_validated_json": stage_3_json,
        },
    }


def analyze_image(image_bytes: bytes, filename: str) -> dict:
    return analyze_image_with_steps(image_bytes, filename)["final_json"]
