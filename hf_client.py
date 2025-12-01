#!/usr/bin/env python3
# Simple synchronous client for Hugging Face Inference API.
# Uses HF_API_TOKEN and model names HF_TEXT_MODEL, HF_IMAGE_MODEL from env.
import os
import requests
import json

HF_API_TOKEN = os.getenv("HF_API_TOKEN")
HF_TEXT_MODEL = os.getenv("HF_TEXT_MODEL", "facebook/bart-large-mnli")
HF_IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "microsoft/trocr-small-printed")
# Optional: comma-separated labels for zero-shot classification
HF_ZERO_SHOT_LABELS = os.getenv("HF_ZERO_SHOT_LABELS", "")

HEADERS = {}
if HF_API_TOKEN:
    HEADERS["Authorization"] = f"Bearer {HF_API_TOKEN}"


def _post_json_model(model: str, payload: dict, timeout: int = 60):
    url = f"https://api-inference.huggingface.co/models/{model}"
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=timeout)
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            return resp.text
    except requests.HTTPError as e:
        text = resp.text if 'resp' in locals() else str(e)
        raise RuntimeError(f"HF API error: {e} - {text}")


def classify_text(text: str, model: str = None):
    """
    If HF_ZERO_SHOT_LABELS is set (comma separated), run zero-shot classification.
    model parameter overrides default.
    """
    model_to_use = model or HF_TEXT_MODEL
    if HF_ZERO_SHOT_LABELS and "mnli" in model_to_use:
        labels = [l.strip() for l in HF_ZERO_SHOT_LABELS.split(";") if l.strip()]
        payload = {"inputs": text, "parameters": {"candidate_labels": labels}}
        return _post_json_model(model_to_use, payload, timeout=60)
    else:
        payload = {"inputs": text}
        return _post_json_model(model_to_use, payload, timeout=60)


def process_image_file(file_path: str, model: str = None):
    """
    Sends image bytes to HF image model (e.g., TrOCR for OCR).
    model parameter overrides default.
    """
    model_to_use = model or HF_IMAGE_MODEL
    url = f"https://api-inference.huggingface.co/models/{model_to_use}"
    try:
        with open(file_path, "rb") as f:
            data = f.read()
        resp = requests.post(url, headers=HEADERS, data=data, timeout=120)
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            return resp.text
    except requests.HTTPError as e:
        text = resp.text if 'resp' in locals() else str(e)
        raise RuntimeError(f"HF Image API error: {e} - {text}")

