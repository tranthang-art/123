# Telegram bot + Hugging Face + очередь (Redis/RQ)

Описание
- Telegram bot (aiogram) принимает текст или файлы и ставит задачи в очередь (Redis/RQ).
- Worker берет задачу и вызывает Hugging Face Inference API для обработки текста или изображений.
- Результат возвращается пользователю в Telegram (сообщение или файл).

Переменные окружения (пример .env):
- TELEGRAM_TOKEN - токен Telegram бота (обязательно)
- REDIS_URL - URL Redis (по умолчанию redis://redis:6379/0)
- DATA_DIR - каталог для временного хранения файлов (по умолчанию /data)
- HF_API_TOKEN - токен Hugging Face (рекомендуется)
- HF_TEXT_MODEL - имя HF модели для текста (по умолчанию facebook/bart-large-mnli)
- HF_IMAGE_MODEL - имя HF модели для изображений (по умолчанию microsoft/trocr-small-printed)
- HF_ZERO_SHOT_LABELS - (опционально) запятая-разделённый список меток для zero-shot классификации

Запуск (локально)
1. pip install -r requirements.txt
2. Создать папку data: mkdir data
3. Создать .env на основе .env.example (НЕ коммитить) и заполнить TELEGRAM_TOKEN и HF_API_TOKEN, при необходимости REDIS_URL и другие переменные.
4. Запустить Redis (локально или в Docker):
   docker run -p 6379:6379 --name redis -d redis:7-alpine
5. В одном терминале запустить worker:
   rq worker -u ${REDIS_URL:-redis://localhost:6379/0} default
6. В другом терминале запустить бота:
   python bot.py

Docker
- В проекте есть docker-compose.yml и Dockerfile.bot/worker. Пример .env.example прилагается.

Примечания по моделям и лимитам
- Для текстовой zero-shot классификации: HF_TEXT_MODEL=facebook/bart-large-mnli и HF_ZERO_SHOT_LABELS="invoice,contract,letter,other".
- Для OCR изображений: HF_IMAGE_MODEL=microsoft/trocr-small-printed (или аналог).
- Проверьте квоты/платёжные лимиты для HF Inference API на вашем токене.
