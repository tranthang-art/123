#!/usr/bin/env python3
# aiogram Telegram bot that enqueues jobs into Redis/RQ (Hugging Face integration via worker)
import os
import uuid
import redis
from rq import Queue
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DATA_DIR = os.getenv("DATA_DIR", "/data")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN must be set")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

redis_conn = redis.from_url(REDIS_URL)
q = Queue("default", connection=redis_conn)


@dp.message_handler(commands=["start", "help"])
async def cmd_start(message: types.Message):
    await message.reply(
        "Привет! Отправь текст или изображение/документ — я поставлю задачу в очереди и обработаю через Hugging Face.\n"
        "Команды:\n"
        "/status <job_id> - проверить статус задачи\n"
        "/models - показать текущие модели"
    )


@dp.message_handler(commands=["models"])
async def cmd_models(message: types.Message):
    from os import getenv
    text_model = getenv("HF_TEXT_MODEL", "<не задано>")
    image_model = getenv("HF_IMAGE_MODEL", "<не задано>")
    labels = getenv("HF_ZERO_SHOT_LABELS", "<не заданы>")
    await message.reply(f"Text model: {text_model}\nImage model: {image_model}\nZero-shot labels: {labels}")


@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_text(message: types.Message):
    job_uuid = str(uuid.uuid4())
    os.makedirs(DATA_DIR, exist_ok=True)
    fname = f"{job_uuid}.txt"
    path = os.path.join(DATA_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(message.text)

    job = q.enqueue("tasks.process_job", message.chat.id, fname, message.text, job_uuid, timeout=600)
    await message.reply(f"Задача поставлена в очередь. job_id: {job.get_id()}")


@dp.message_handler(content_types=[types.ContentType.DOCUMENT, types.ContentType.PHOTO])
async def handle_file(message: types.Message):
    await message.reply("Принял файл, сохраняю и ставлю в очередь...")
    os.makedirs(DATA_DIR, exist_ok=True)
    # Получаем файл и сохраняем в DATA_DIR
    if message.document:
        ext = os.path.splitext(message.document.file_name)[1] or ""
        local_name = f"{uuid.uuid4().hex}{ext}"
        target = os.path.join(DATA_DIR, local_name)
        await message.document.download(destination_file=target)
    else:
        # Для фото берем последний (наибольший)
        photo = message.photo[-1]
        local_name = f"{uuid.uuid4().hex}.jpg"
        target = os.path.join(DATA_DIR, local_name)
        await photo.download(destination_file=target)

    job = q.enqueue("tasks.process_job", message.chat.id, local_name, "", None, timeout=1800)
    await message.reply(f"Файл сохранён. Задача поставлена в очередь. job_id: {job.get_id()}")


@dp.message_handler(commands=["status"])
async def cmd_status(message: types.Message):
    args = message.get_args().strip()
    if not args:
        await message.reply("Использование: /status <job_id>")
        return
    job_id = args
    from rq.job import Job
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        await message.reply("Задача не найдена.")
        return
    response = f"job_id: {job.get_id()}\nStatus: {job.get_status()}\n"
    if job.is_finished:
        response += f"Результат: {job.result}\n"
    elif job.is_failed:
        response += f"Ошибка: {job.exc_info}\n"
    await message.reply(response)


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
