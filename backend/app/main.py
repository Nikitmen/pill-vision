import os
import uuid
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

from .db import list_drugs, save_qc_check, search_drugs
from .model_client import analyze_image_with_steps

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/pill_uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": os.getenv("CORS_ORIGINS", "*")}})


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/drugs")
def drugs_catalog():
    q = request.args.get("q", "")
    dosage_form = request.args.get("dosage_form", "")
    limit = int(request.args.get("limit", 200))
    return jsonify(list_drugs(q=q, dosage_form=dosage_form, limit=limit))


@app.post("/api/search-json")
def search_json():
    payload = request.get_json(force=True, silent=False) or {}
    top_k = int(request.args.get("top_k", 5))
    search_result = search_drugs(payload, top_k=top_k)
    return jsonify({
        "extracted_json": payload,
        "normalized_query": search_result["normalized_query"],
        "results": search_result["results"],
    })


@app.post("/api/analyze")
def analyze():
    if "image" not in request.files:
        return jsonify({"error": "Field 'image' is required"}), 400

    image = request.files["image"]
    image_bytes = image.read()
    if not image_bytes:
        return jsonify({"error": "Empty image"}), 400

    safe_name = f"{uuid.uuid4().hex}_{image.filename or 'pill.jpg'}"
    image_path = UPLOAD_DIR / safe_name
    image_path.write_bytes(image_bytes)

    try:
        analysis_result = analyze_image_with_steps(image_bytes, image.filename or "pill.jpg")
        extracted = analysis_result["final_json"]
        search_result = search_drugs(extracted, top_k=5)
        save_qc_check(str(image_path), extracted, search_result["results"], os.getenv("MODEL_NAME", "mock"))

        return jsonify({
            "image_name": image.filename,
            "model_mode": os.getenv("MODEL_MODE", "mock"),
            "extracted_json": extracted,
            "model_steps": analysis_result.get("steps"),
            "normalized_query": search_result["normalized_query"],
            "results": search_result["results"],
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
