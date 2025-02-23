import telebot
import os
import json
import subprocess
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# Get token from environment variable
TOKEN = "7851000077:AAHE8Pib-c73RZ9EcoDIyGcVhzhKfIaA-vo"

ADMIN_USERNAME = "@kzbomber_admin"
ADMIN_ID = "7379341259"
SUBSCRIPTIONS_FILE = "subscriptions.json"
WHITELIST_FILE = "whitelist.json"

# Кэш для хранения whitelist в памяти
_whitelist_cache = None
_subscriptions_cache = None
_last_cache_update = None
CACHE_TIMEOUT = 300  # 5 минут

# Добавляем обработку ошибок при инициализации бота
try:
    bot = telebot.TeleBot(TOKEN)
    print(f"Бот успешно инициализирован")
except Exception as e:
    print(f"Ошибка при инициализации бота: {e}")
    raise

def _update_cache_if_needed():
    global _whitelist_cache, _subscriptions_cache, _last_cache_update
    current_time = datetime.now()

    if (_last_cache_update is None or 
        (current_time - _last_cache_update).total_seconds() > CACHE_TIMEOUT):
        try:
            if os.path.exists(WHITELIST_FILE):
                with open(WHITELIST_FILE, "r", encoding="utf-8") as file:
                    _whitelist_cache = set(json.load(file))
            else:
                _whitelist_cache = set()

            if os.path.exists(SUBSCRIPTIONS_FILE):
                with open(SUBSCRIPTIONS_FILE, "r", encoding="utf-8") as file:
                    _subscriptions_cache = json.load(file)
            else:
                _subscriptions_cache = {}

            _last_cache_update = current_time
        except Exception as e:
            print(f"Ошибка обновления кэша: {e}")
            # В случае ошибки чтения кэша, сбрасываем его
            _whitelist_cache = set()
            _subscriptions_cache = {}

def save_subscriptions(subscriptions):
    global _subscriptions_cache
    try:
        with open(SUBSCRIPTIONS_FILE, "w", encoding="utf-8") as file:
            json.dump(subscriptions, file, indent=4)
        _subscriptions_cache = subscriptions
    except Exception as e:
        print(f"Ошибка сохранения подписок: {e}")

def add_subscription(user_id, days):
    _update_cache_if_needed()
    expires_at = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    if _subscriptions_cache is None:
        _subscriptions_cache = {}
    _subscriptions_cache[str(user_id)] = {"expires_at": expires_at, "days": days}
    save_subscriptions(_subscriptions_cache)

def check_subscription(user_id):
    _update_cache_if_needed()
    if _subscriptions_cache is None:
        return False

    if str(user_id) in _subscriptions_cache:
        expires_at = datetime.strptime(
            _subscriptions_cache[str(user_id)]["expires_at"], "%Y-%m-%d %H:%M:%S")
        return datetime.now() < expires_at
    return False

def save_whitelist(whitelist):
    global _whitelist_cache
    try:
        with open(WHITELIST_FILE, "w", encoding="utf-8") as file:
            json.dump(list(whitelist), file, indent=4)
        _whitelist_cache = set(whitelist)
    except Exception as e:
        print(f"Ошибка сохранения белого списка: {e}")

def is_whitelisted(phone_number):
    _update_cache_if_needed()
    return phone_number in _whitelist_cache if _whitelist_cache is not None else False

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "Привет! Отправь мне номер и время в формате: +7XXXXXXXXXX XX")

@bot.message_handler(commands=['buy'])
def buy_subscription(message):
    bot.send_message(
        message.chat.id,
        f"Для покупки подписки напишите администратору: {ADMIN_USERNAME}")

@bot.message_handler(commands=['check'])
def check_subscription_status(message):
    user_id = message.chat.id
    if check_subscription(user_id):
        bot.send_message(message.chat.id, "✅ У вас есть активная подписка!")
    else:
        bot.send_message(message.chat.id,
                         "❌ Ваша подписка истекла. Купите её через /buy")

@bot.message_handler(commands=['addsub'])
def add_subscription_admin(message):
    if message.chat.id != int(ADMIN_ID):
        bot.send_message(message.chat.id,
                         "❌ У вас нет прав для выполнения этой команды.")
        return

    try:
        args = message.text.split()
        if len(args) != 3:
            raise ValueError(
                "Неверный формат. Используйте: /addsub user_id количество_дней"
            )

        user_id = int(args[1])
        days = int(args[2])
        add_subscription(user_id, days)
        bot.send_message(
            message.chat.id,
            f"✅ Подписка на {days} дней добавлена пользователю {user_id}")
        bot.send_message(
            user_id,
            f"✅ Администратор активировал вам подписку на {days} дней!")

    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ Ошибка! Используйте формат: /addsub user_id количество_дней")

@bot.message_handler(commands=['addwhite'])
def add_to_whitelist(message):
    if str(message.chat.id) != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Эта команда доступна только администратору бота.")
        print(f"Попытка доступа к админ-команде от пользователя {message.chat.id}")
        return

    try:
        args = message.text.split()
        if len(args) != 2:
            raise ValueError("Неверный формат. Используйте: /addwhite +7XXXXXXXXXX")

        phone_number = args[1]
        if not phone_number.startswith("+7") or not phone_number[1:].isdigit():
            raise ValueError("Неверный формат номера")

        _update_cache_if_needed()
        if _whitelist_cache is None:
            _whitelist_cache = set()

        if phone_number in _whitelist_cache:
            bot.send_message(message.chat.id, "❗️ Этот номер уже в белом списке.")
            return

        _whitelist_cache.add(phone_number)
        save_whitelist(_whitelist_cache)
        bot.send_message(message.chat.id, f"✅ Номер {phone_number} добавлен в белый список.")
        print(f"Администратор добавил номер {phone_number} в белый список")

    except ValueError as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Произошла ошибка при добавлении номера.")
        print(f"Ошибка при добавлении в белый список: {e}")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        user_id = message.chat.id
        if not check_subscription(user_id):
            bot.send_message(message.chat.id, "❌ У вас нет подписки! Купите её через /buy")
            return

        data = message.text.split()
        if len(data) != 2:
            raise ValueError("Неверный формат")

        phone_number, time = data
        if not phone_number.startswith("+7") or not phone_number[1:].isdigit():
            raise ValueError("Неверный номер")
        if not time.isdigit():
            raise ValueError("Неверное время")

        # Проверяем, не в белом ли списке номер
        if is_whitelisted(phone_number):
            bot.send_message(message.chat.id, "❌ Этот номер находится в белом списке и защищен от спама.")
            return

        bot.send_message(message.chat.id, f"Спам запущен для {phone_number} на {time} секунд")

        # Запускаем процесс и ждем его завершения
        process = subprocess.run(["python", "spam.py", phone_number, time])

        # После завершения отправляем сообщение
        bot.send_message(message.chat.id, "✅ Успешный спам!")

    except ValueError as e:
        bot.send_message(
            message.chat.id,
            "❌ Ошибка: неверный формат ввода. Используйте: +7XXXXXXXXXX XX")

if __name__ == "__main__":
    try:
        print("Бот запущен...")
        # Инициализируем кэш при запуске
        _update_cache_if_needed()
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        raise