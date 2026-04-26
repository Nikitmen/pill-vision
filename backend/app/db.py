import json
import os
from decimal import Decimal

import psycopg2
from psycopg2.extras import RealDictCursor

from .scoring import compute_score, normalize_model_output


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "pillvision"),
        user=os.getenv("POSTGRES_USER", "pilluser"),
        password=os.getenv("POSTGRES_PASSWORD", "pillpass"),
    )


def json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    return str(value) if value is not None else None


def search_drugs(photo_json: dict, top_k: int = 5):
    photo = normalize_model_output(photo_json)

    base_query = """
        WITH normalized_profiles AS (
            SELECT
                id,
                trade_name,
                inn,
                dosage,
                manufacturer,
                CASE
                    WHEN dosage_form ILIKE '%%capsule%%' THEN 'capsule'
                    ELSE dosage_form
                END AS dosage_form,
                shape,
                color_primary,
                color_secondary,
                translucency,
                imprint_present,
                imprint_text,
                surface,
                free_description
            FROM drug_profiles
        )
        SELECT
            id::text,
            trade_name,
            inn,
            dosage,
            manufacturer,
            dosage_form,
            shape,
            color_primary,
            color_secondary,
            translucency,
            imprint_present,
            imprint_text,
            surface,
            free_description
        FROM normalized_profiles
    """

    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            base_query
            + """
            WHERE
                (%s IS NOT NULL AND dosage_form = %s)
                OR
                (%s IS NOT NULL AND shape = %s)
            LIMIT 100
            """,
            (photo.get("dosage_form"), photo.get("dosage_form"), photo.get("shape"), photo.get("shape")),
        )
        rows = cur.fetchall()

        if not rows:
            cur.execute(base_query + " LIMIT 100")
            rows = cur.fetchall()

    results = []
    for row in rows:
        ref = dict(row)
        score = compute_score(photo, ref)
        results.append({"score": score, "score_percent": round(score * 100, 1), "drug": ref})

    results.sort(key=lambda item: item["score"], reverse=True)
    return {"normalized_query": photo, "results": results[:top_k]}


def list_drugs(q: str = "", dosage_form: str = "", limit: int = 200):
    """Return drug profiles for the frontend catalog tab."""
    q = (q or "").strip()
    dosage_form = (dosage_form or "").strip()
    limit = max(1, min(int(limit or 200), 500))

    where = []
    params = []

    if q:
        like = f"%{q}%"
        where.append(
            """
            (
                trade_name ILIKE %s OR
                inn ILIKE %s OR
                dosage ILIKE %s OR
                manufacturer ILIKE %s OR
                free_description ILIKE %s OR
                imprint_text ILIKE %s OR
                color_primary ILIKE %s OR
                shape ILIKE %s
            )
            """
        )
        params.extend([like] * 8)

    if dosage_form:
        where.append("dosage_form = %s")
        params.append(dosage_form)

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    query = f"""
        SELECT
            id::text,
            trade_name,
            inn,
            dosage,
            manufacturer,
            dosage_form,
            shape,
            profile,
            color_primary,
            color_secondary,
            color_notes,
            surface,
            coating,
            translucency,
            capsule_type,
            capsule_size,
            capsule_body_color,
            capsule_cap_color,
            contents_color,
            contents_type,
            imprint_present,
            imprint_text,
            imprint_color,
            imprint_side,
            logo_or_symbol,
            has_score_line,
            score_line_count,
            score_line_side,
            free_description,
            source,
            original_text,
            created_at::text
        FROM drug_profiles
        {where_sql}
        ORDER BY trade_name NULLS LAST, created_at DESC
        LIMIT %s
    """
    select_params = params + [limit]

    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, select_params)
        rows = [dict(row) for row in cur.fetchall()]

        count_query = f"SELECT COUNT(*) AS total FROM drug_profiles {where_sql}"
        cur.execute(count_query, params)
        total = cur.fetchone()["total"]

    return {"total": int(total), "items": rows}


def save_qc_check(image_path: str, extracted_json: dict, results: list, model_name: str):
    if not results:
        return

    best = results[0]
    passed = best["score"] >= 0.65
    fail_reasons = None if passed else "Низкая уверенность совпадения"

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO qc_checks (
                reference_profile_id,
                image_path,
                extracted_json,
                match_score,
                passed,
                fail_reasons,
                model_name
            ) VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s)
            """,
            (
                best["drug"]["id"],
                image_path,
                json.dumps(extracted_json, ensure_ascii=False),
                best["score"],
                passed,
                fail_reasons,
                model_name,
            ),
        )
