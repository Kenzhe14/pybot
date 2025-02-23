import telebot
import os
import json
import subprocess
import signal
import queue
import threading
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# Get token from environment variable
TOKEN = os.getenv('TOKEN')
if not TOKEN:
    raise ValueError("Не найден токен бота в переменных окружения")

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', "@kzbomber_admin")
ADMIN_ID = os.getenv('ADMIN_ID', "7379341259")
SUBSCRIPTIONS_FILE = "subscriptions.json"
WHITELIST_FILE = "whitelist.json"

# Константы для оптимизации
MAX_CONCURRENT_TASKS = 50  # Максимальное количество одновременных задач
RATE_LIMIT = 1  # Минимальный интервал между запросами от одного пользователя (в секундах)
CACHE_TIMEOUT = 300  # Время жизни кэша (5 минут)

# Глобальные переменные
bot = None
task_queue = queue.Queue()
user_last_request = {}
subscriptions_cache = {}
whitelist_cache = set()
last_cache_update = None
active_tasks = 0
task_lock = threading.Lock()

def signal_handler(signum, frame):
    print("Получен сигнал завершения, останавливаем бота...")
    if bot:
        bot.stop_polling()
    exit(0)

# Регистрируем обработчик сигналов
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def update_cache():
    global subscriptions_cache, whitelist_cache, last_cache_update
    current_time = datetime.now()

    if not last_cache_update or (current_time - last_cache_update).total_seconds() > CACHE_TIMEOUT:
        try:
            if os.path.exists(SUBSCRIPTIONS_FILE):
                with open(SUBSCRIPTIONS_FILE, "r", encoding="utf-8") as file:
                    subscriptions_cache = json.load(file)

            if os.path.exists(WHITELIST_FILE):
                with open(WHITELIST_FILE, "r", encoding="utf-8") as file:
                    whitelist_cache = set(json.load(file))

            last_cache_update = current_time
        except Exception as e:
            print(f"Ошибка обновления кэша: {e}")

def save_subscriptions():
    try:
        with open(SUBSCRIPTIONS_FILE, "w", encoding="utf-8") as file:
            json.dump(subscriptions_cache, file, indent=4)
    except Exception as e:
        print(f"Ошибка сохранения подписок: {e}")

def save_whitelist():
    try:
        with open(WHITELIST_FILE, "w", encoding="utf-8") as file:
            json.dump(list(whitelist_cache), file, indent=4)
    except Exception as e:
        print(f"Ошибка сохранения белого списка: {e}")

def check_rate_limit(user_id):
    current_time = time.time()
    if user_id in user_last_request:
        time_passed = current_time - user_last_request[user_id]
        if time_passed < RATE_LIMIT:
            return False
    user_last_request[user_id] = current_time
    return True

def process_spam_task(phone_number, duration, chat_id):
    global active_tasks
    try:
        with task_lock:
            active_tasks += 1

        if active_tasks <= MAX_CONCURRENT_TASKS:
            process = subprocess.run(
                ["python", "spam.py", phone_number, duration],
                capture_output=True,
                text=True
            )
            if process.returncode == 0:
                bot.send_message(chat_id, "✅ Успешный спам!")
            else:
                bot.send_message(
                    chat_id,
                    f"❌ Ошибка при выполнении спама: {process.stderr}"
                )
        else:
            bot.send_message(
                chat_id,
                "⏳ Сервер перегружен, попробуйте позже"
            )
    except Exception as e:
        print(f"Ошибка выполнения задачи: {e}")
        bot.send_message(chat_id, "❌ Произошла ошибка при выполнении задачи")
    finally:
        with task_lock:
            active_tasks -= 1

def task_worker():
    while True:
        try:
            task = task_queue.get()
            if task is None:
                break
            phone_number, duration, chat_id = task
            process_spam_task(phone_number, duration, chat_id)
            task_queue.task_done()
        except Exception as e:
            print(f"Ошибка в worker thread: {e}")

# Запускаем worker threads
worker_threads = []
for _ in range(MAX_CONCURRENT_TASKS):
    t = threading.Thread(target=task_worker, daemon=True)
    t.start()
    worker_threads.append(t)

# Инициализация бота
try:
    bot = telebot.TeleBot(TOKEN)
    print(f"Бот успешно инициализирован")
except Exception as e:
    print(f"Ошибка при инициализации бота: {e}")
    raise

@bot.message_handler(commands=['start'])
def start(message):
    if not check_rate_limit(message.chat.id):
        bot.send_message(message.chat.id, "⏳ Подождите немного перед следующим запросом")
        return

    bot.send_message(
        message.chat.id,
        "Привет! Отправь мне номер и время в формате: +7XXXXXXXXXX XX")

@bot.message_handler(commands=['buy'])
def buy_subscription(message):
    if not check_rate_limit(message.chat.id):
        bot.send_message(message.chat.id, "⏳ Подождите немного перед следующим запросом")
        return

    bot.send_message(
        message.chat.id,
        f"Для покупки подписки напишите администратору: {ADMIN_USERNAME}")

@bot.message_handler(commands=['check'])
def check_subscription_status(message):
    if not check_rate_limit(message.chat.id):
        bot.send_message(message.chat.id, "⏳ Подождите немного перед следующим запросом")
        return

    update_cache()
    user_id = str(message.chat.id)

    if user_id in subscriptions_cache:
        expires_at = datetime.strptime(
            subscriptions_cache[user_id]["expires_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() < expires_at:
            bot.send_message(message.chat.id, "✅ У вас есть активная подписка!")
            return

    bot.send_message(message.chat.id, "❌ У вас нет активной подписки. Купите через /buy")

@bot.message_handler(commands=['addsub'])
def add_subscription_admin(message):
    if not check_rate_limit(message.chat.id):
        bot.send_message(message.chat.id, "⏳ Подождите немного перед следующим запросом")
        return

    if str(message.chat.id) != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
        return

    try:
        args = message.text.split()
        if len(args) != 3:
            raise ValueError()

        user_id = str(int(args[1]))
        days = int(args[2])

        update_cache()
        expires_at = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        subscriptions_cache[user_id] = {"expires_at": expires_at, "days": days}
        save_subscriptions()

        bot.send_message(
            message.chat.id,
            f"✅ Подписка на {days} дней добавлена пользователю {user_id}")
        bot.send_message(
            int(user_id),
            f"✅ Администратор активировал вам подписку на {days} дней!")

    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ Ошибка! Используйте формат: /addsub user_id количество_дней")

@bot.message_handler(commands=['addwhite'])
def add_to_whitelist(message):
    if not check_rate_limit(message.chat.id):
        bot.send_message(message.chat.id, "⏳ Подождите немного перед следующим запросом")
        return

    if str(message.chat.id) != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Эта команда доступна только администратору бота")
        return

    try:
        args = message.text.split()
        if len(args) != 2:
            raise ValueError("Неверный формат. Используйте: /addwhite +7XXXXXXXXXX")

        phone_number = args[1]
        if not phone_number.startswith("+7") or not phone_number[1:].isdigit():
            raise ValueError("Неверный формат номера")

        update_cache()
        if phone_number in whitelist_cache:
            bot.send_message(message.chat.id, "❗️ Этот номер уже в белом списке")
            return

        whitelist_cache.add(phone_number)
        save_whitelist()
        bot.send_message(message.chat.id, f"✅ Номер {phone_number} добавлен в белый список")

    except ValueError as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Произошла ошибка при добавлении номера")
        print(f"Ошибка при добавлении в белый список: {e}")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if not check_rate_limit(message.chat.id):
        bot.send_message(message.chat.id, "⏳ Подождите немного перед следующим запросом")
        return

    try:
        update_cache()
        user_id = str(message.chat.id)

        if user_id not in subscriptions_cache:
            bot.send_message(message.chat.id, "❌ У вас нет подписки! Купите через /buy")
            return

        expires_at = datetime.strptime(
            subscriptions_cache[user_id]["expires_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expires_at:
            bot.send_message(message.chat.id, "❌ Ваша подписка истекла! Купите через /buy")
            return

        data = message.text.split()
        if len(data) != 2:
            raise ValueError("Неверный формат")

        phone_number, time = data
        if not phone_number.startswith("+7") or not phone_number[1:].isdigit():
            raise ValueError("Неверный номер")
        if not time.isdigit():
            raise ValueError("Неверное время")

        if phone_number in whitelist_cache:
            bot.send_message(
                message.chat.id,
                "❌ Этот номер находится в белом списке и защищен от спама")
            return

        # Добавляем задачу в очередь
        task_queue.put((phone_number, time, message.chat.id))
        bot.send_message(
            message.chat.id,
            f"⏳ Задача добавлена в очередь. Спам для {phone_number} на {time} секунд")

    except ValueError as e:
        bot.send_message(
            message.chat.id,
            "❌ Ошибка: неверный формат ввода. Используйте: +7XXXXXXXXXX XX")

if __name__ == "__main__":
    try:
        print("Бот запущен...")
        update_cache()  # Инициализируем кэш при запуске
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        raise
    finally:
        # Останавливаем worker threads
        for _ in range(len(worker_threads)):
            task_queue.put(None)
        for t in worker_threads:
            t.join()