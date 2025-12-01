#!/usr/bin/env python3
# RQ tasks executed by worker. Uses hf_client to call Hugging Face Inference API.
import os
import requests
import json
from typing import Optional
from hf_client import classify_text, process_image_file

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DATA_DIR = os.getenv("DATA_DIR", "/data")


def send_telegram_message(chat_id: int, text: str):
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN not set; cannot send message")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print("Failed to send telegram message:", e)


def send_file_via_telegram(chat_id: int, file_path: str, caption: str = ""):
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN not set; cannot send file")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    with open(file_path, "rb") as f:
        try:
            r = requests.post(url, files={"document": f}, data={"chat_id": chat_id, "caption": caption}, timeout=120)
            r.raise_for_status()
        except Exception as e:
            print("Failed to send document:", e)


def process_job(chat_id: int, file_name: Optional[str], text: str, job_id: Optional[str] = None,
                model_name: Optional[str] = None, image_model: Optional[str] = None):
    """
    process_job signature updated to accept:
      - model_name: for text processing (string)
      - image_model: for image/file processing (string)
    If model_name/image_model is None, hf_client will use its defaults.
    """
    file_path = os.path.join(DATA_DIR, file_name) if file_name else None
    try:
        send_telegram_message(chat_id, "Начинаю обработку вашей задачи через Hugging Face...")
        result_parts = []

        if file_path and os.path.exists(file_path):
            result_parts.append(f"Обрабатываю файл {file_name} через Hugging Face (model={image_model})...")
            hf_res = process_image_file(file_path, model=image_model)
            try:
                result_text = json.dumps(hf_res, ensure_ascii=False, indent=2) if not isinstance(hf_res, str) else hf_res
            except Exception:
                result_text = str(hf_res)
            result_parts.append("Результат HF:\n" + result_text)
        elif text:
            result_parts.append(f"Обрабатываю текст через Hugging Face (model={model_name})...")
            hf_res = classify_text(text, model=model_name)
            try:
                result_text = json.dumps(hf_res, ensure_ascii=False, indent=2) if not isinstance(hf_res, str) else hf_res
            except Exception:
                result_text = str(hf_res)
            result_parts.append("Результат HF:\n" + result_text)
        else:
            result_parts.append("Нет входных данных для обработки")

        final_text = "\n\n".join(result_parts)

        # Если ответ слишком длинный, отправляем как файл
        if len(final_text) > 3500:
            doc_path = os.path.join(DATA_DIR, f"result_{job_id or 'res'}.txt")
            with open(doc_path, "w", encoding="utf-8") as f:
                f.write(final_text)
            send_file_via_telegram(chat_id, doc_path, caption="Результат обработки (файл)")
            try:
                os.remove(doc_path)
            except Exception:
                pass
        else:
            send_telegram_message(chat_id, final_text)

        return {"status": "ok", "summary": "Processed"}
    except Exception as e:
        send_telegram_message(chat_id, f"Ошибка при обработке: {e}")
        print("Exception in process_job:", e)
        raise

