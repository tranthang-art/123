#!/usr/bin/env python3
# bot.py - обновлён: логирование, удаление webhook на старте, on_startup
import os
import uuid
import logging
import redis
from rq import Queue
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DATA_DIR = os.getenv("DATA_DIR", "/data")

DEFAULT_TEXT_MODEL = os.getenv("HF_TEXT_MODEL", "facebook/bart-large-mnli")
DEFAULT_IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "microsoft/trocr-small-printed")

if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN not set - exiting")
    raise RuntimeError("TELEGRAM_TOKEN must be set")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

# Try connecting to Redis but don't crash hard if not available immediately
try:
    redis_conn = redis.from_url(REDIS_URL, socket_connect_timeout=5)
    # quick ping to detect issues early
    redis_conn.ping()
    logger.info("Connected to Redis")
except Exception as e:
    redis_conn = None
    logger.warning("Cannot connect to Redis at start: %s", e)

q = Queue("default", connection=redis_conn) if redis_conn else None

# --- menu / models (same as before) ---
TEXT_MODELS = [
    ("Zero-shot (bart-large-mnli)", "facebook/bart-large-mnli"),
    ("Sentiment (distilbert-sst-2)", "distilbert-base-uncased-finetuned-sst-2-english"),
    ("Summarization (bart-large-cnn)", "facebook/bart-large-cnn"),
    ("Generation (gpt2)", "gpt2")
]
IMAGE_MODELS = [
    ("OCR (trocr-small-printed)", "microsoft/trocr-small-printed"),
    ("OCR (trocr-base-printed)", "microsoft/trocr-base-printed")
]


def _make_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("Выбрать текстовую модель", callback_data="menu:text"))
    kb.add(InlineKeyboardButton("Выбрать модель для изображений", callback_data="menu:image"))
    kb.add(InlineKeyboardButton("Показать текущие настройки", callback_data="menu:show"))
    kb.add(InlineKeyboardButton("Помощь", callback_data="menu:help"))
    return kb


def _make_models_keyboard(kind: str):
    kb = InlineKeyboardMarkup(row_width=1)
    if kind == "text":
        for name, model in TEXT_MODELS:
            kb.add(InlineKeyboardButton(name, callback_data=f"set:text:{model}"))
    else:
        for name, model in IMAGE_MODELS:
            kb.add(InlineKeyboardButton(name, callback_data=f"set:image:{model}"))
    kb.add(InlineKeyboardButton("Назад", callback_data="menu:back"))
    return kb


async def on_startup(dp):
    logger.info("Bot starting up: deleting webhook (if any) and skipping old updates")
    try:
        await bot.delete_webhook()
        logger.info("Webhook deleted (if it existed)")
    except Exception as e:
        logger.warning("Failed to delete webhook: %s", e)


@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    try:
        text = (
            "👋 Привет! Это бот для обработки текста и изображений через Hugging Face.\n\n"
            "Выбери модель из меню ниже или отправь текст/файл — задача попадёт в очередь.\n\n"
            "Нажми на кнопку, чтобы выбрать модель."
        )
        await message.reply(text, reply_markup=_make_menu())
    except Exception as e:
        logger.exception("Error in /start handler: %s", e)
        # best-effort response
        try:
            await message.reply("Извините, произошла ошибка. Попробуйте ещё раз позже.")
        except Exception:
            pass


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("menu:"))
async def menu_handler(callback: types.CallbackQuery):
    try:
        data = callback.data.split(":")[-1]
        if data == "text":
            await callback.message.edit_text("Выберите текстовую модель:", reply_markup=_make_models_keyboard("text"))
        elif data == "image":
            await callback.message.edit_text("Выберите модель для изображений:", reply_markup=_make_models_keyboard("image"))
        elif data == "show":
            chat_id = str(callback.from_user.id)
            tm = redis_conn.get(f"chat:{chat_id}:text_model") if redis_conn else None
            im = redis_conn.get(f"chat:{chat_id}:image_model") if redis_conn else None
            tm = tm.decode() if tm else DEFAULT_TEXT_MODEL
            im = im.decode() if im else DEFAULT_IMAGE_MODEL
            await callback.message.edit_text(f"Текущие модели:\n\nТекст: {tm}\nИзображения: {im}", reply_markup=_make_menu())
        elif data == "help":
            await callback.message.edit_text(
                "Как пользоваться:\n"
                "- /start — меню выбора моделей\n"
                "- Отправь текст или файл — он попадёт в очередь\n"
                "- /status <job_id> — узнать статус задачи\n"
                "- /models — узнать текущие модели",\n                reply_markup=_make_menu()
            )
        elif data == "back":
            await callback.message.edit_text("Главное меню:", reply_markup=_make_menu())
        await callback.answer()
    except Exception as e:
        logger.exception("Error in menu_handler: %s", e)
        try:
            await callback.answer("Ошибка при обработке меню", show_alert=True)
        except Exception:
            pass


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("set:"))
async def set_model_handler(callback: types.CallbackQuery):
    try:
        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer("Неверные данные", show_alert=True)
            return
        kind, model = parts[1], parts[2]
        chat_key = str(callback.from_user.id)
        if redis_conn:
            if kind == "text":
                redis_conn.set(f"chat:{chat_key}:text_model", model)
                await callback.answer(f"Текстовая модель изменена на {model}")
                await callback.message.edit_text(f"Текстовая модель установлена: {model}", reply_markup=_make_menu())
            else:
                redis_conn.set(f"chat:{chat_key}:image_model", model)
                await callback.answer(f"Модель для изображений изменена на {model}")
                await callback.message.edit_text(f"Модель для изображений установлена: {model}", reply_markup=_make_menu())
        else:
            await callback.answer("Хранилище недоступно, модель не сохранена", show_alert=True)
    except Exception as e:
        logger.exception("Error in set_model_handler: %s", e)
        try:
            await callback.answer("Ошибка при сохранении модели", show_alert=True)
        except Exception:
            pass


@dp.message_handler(commands=["models"])
async def cmd_models(message: types.Message):
    chat_id = str(message.from_user.id)
    text_model = redis_conn.get(f"chat:{chat_id}:text_model") if redis_conn else None
    image_model = redis_conn.get(f"chat:{chat_id}:image_model") if redis_conn else None
    text_model = text_model.decode() if text_model else DEFAULT_TEXT_MODEL
    image_model = image_model.decode() if image_model else DEFAULT_IMAGE_MODEL
    await message.reply(f"Text model: {text_model}\nImage model: {image_model}")


@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_text(message: types.Message):
    try:
        job_uuid = str(uuid.uuid4())
        os.makedirs(DATA_DIR, exist_ok=True)
        fname = f"{job_uuid}.txt"
        path = os.path.join(DATA_DIR, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(message.text)

        chat_key = str(message.from_user.id)
        selected_model = redis_conn.get(f"chat:{chat_key}:text_model") if redis_conn else None
        model_name = selected_model.decode() if selected_model else DEFAULT_TEXT_MODEL

        if q:
            job = q.enqueue("tasks.process_job", message.chat.id, fname, message.text, job_uuid, model_name, None, timeout=600)
            await message.reply(f"Задача поставлена в очередь. job_id: {job.get_id()}")
        else:
            await message.reply("Очередь недоступна — свяжитесь с админом")
    except Exception as e:
        logger.exception("Error in handle_text: %s", e)
        try:
            await message.reply("Ошибка при приёме сообщения. Попробуйте позже.")
        except Exception:
            pass


@dp.message_handler(content_types=[types.ContentType.DOCUMENT, types.ContentType.PHOTO])
async def handle_file(message: types.Message):
    try:
        await message.reply("Принял файл, сохраняю и ставлю в очередь...")
        os.makedirs(DATA_DIR, exist_ok=True)
        if message.document:
            ext = os.path.splitext(message.document.file_name)[1] or ""
            local_name = f"{uuid.uuid4().hex}{ext}"
            target = os.path.join(DATA_DIR, local_name)
            await message.document.download(destination_file=target)
        else:
            photo = message.photo[-1]
            local_name = f"{uuid.uuid4().hex}.jpg"
            target = os.path.join(DATA_DIR, local_name)
            await photo.download(destination_file=target)

        chat_key = str(message.from_user.id)
        selected_model = redis_conn.get(f"chat:{chat_key}:image_model") if redis_conn else None
        model_name = selected_model.decode() if selected_model else DEFAULT_IMAGE_MODEL

        if q:
            job = q.enqueue("tasks.process_job", message.chat.id, local_name, "", None, model_name, timeout=1800)
            await message.reply(f"Файл сохранён. Задача поставлена в очередь. job_id: {job.get_id()}")
        else:
            await message.reply("Очередь недоступна — свяжитесь с админом")
    except Exception as e:
        logger.exception("Error in handle_file: %s", e)
        try:
            await message.reply("Ошибка при загрузке файла. Попробуйте позже.")
        except Exception:
            pass


@dp.message_handler(commands=["status"])
async def cmd_status(message: types.Message):
    try:
        args = message.get_args().strip()
        if not args:
            await message.reply("Использование: /status <job_id>")
            return
        job_id = args
        from rq.job import Job
        if not redis_conn:
            await message.reply("Redis недоступен")
            return
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
    except Exception as e:
        logger.exception("Error in /status handler: %s", e)
        try:
            await message.reply("Ошибка при получении статуса")
        except Exception:
            pass


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)