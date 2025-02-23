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
WHITELIST_FILE = "whitelist.json"  # Новый файл для белого списка

# Добавляем обработку ошибок при инициализации бота
try:
    bot = telebot.TeleBot(TOKEN)
    print(f"Бот успешно инициализирован")
except Exception as e:
    print(f"Ошибка при инициализации бота: {e}")
    raise


def load_subscriptions():
    if os.path.exists(SUBSCRIPTIONS_FILE):
        with open(SUBSCRIPTIONS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    return {}


def save_subscriptions(subscriptions):
    with open(SUBSCRIPTIONS_FILE, "w", encoding="utf-8") as file:
        json.dump(subscriptions, file, indent=4)


def add_subscription(user_id, days):
    subscriptions = load_subscriptions()
    expires_at = (datetime.now() +
                  timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    subscriptions[str(user_id)] = {"expires_at": expires_at, "days": days}
    save_subscriptions(subscriptions)



def check_subscription(user_id):
    subscriptions = load_subscriptions()
    if str(user_id) in subscriptions:
        expires_at = datetime.strptime(
            subscriptions[str(user_id)]["expires_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() < expires_at:
            return True
    return False


def notify_expired_subscriptions():
    subscriptions = load_subscriptions()
    expired_users = []

    for user_id, data in subscriptions.items():
        expires_at = datetime.strptime(data["expires_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expires_at:
            try:
                bot.send_message(
                    int(user_id),
                    "❌ Ваша подписка истекла! Купите новую через /buy")
            except telebot.apihelper.ApiTelegramException as e:
                print(f"Ошибка отправки сообщения пользователю {user_id}: {e}")

            expired_users.append(user_id)

    # Удаляем подписки после уведомления
    for user_id in expired_users:
        del subscriptions[user_id]

    save_subscriptions(subscriptions)


def load_whitelist():
    if os.path.exists(WHITELIST_FILE):
        with open(WHITELIST_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    return []


def save_whitelist(whitelist):
    with open(WHITELIST_FILE, "w", encoding="utf-8") as file:
        json.dump(whitelist, file, indent=4)


def is_whitelisted(phone_number):
    whitelist = load_whitelist()
    return phone_number in whitelist


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

    except ValueError as e:
        bot.send_message(
            message.chat.id,
            "❌ Ошибка! Используйте формат: /addsub user_id количество_дней")


@bot.message_handler(commands=['addwhite'])
def add_to_whitelist(message):
    if str(message.chat.id) != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Эта команда доступна только администратору бота.")
        return

    try:
        args = message.text.split()
        if len(args) != 2:
            raise ValueError("Неверный формат. Используйте: /addwhite +7XXXXXXXXXX")

        phone_number = args[1]
        if not phone_number.startswith("+7") or not phone_number[1:].isdigit():
            raise ValueError("Неверный формат номера")

        whitelist = load_whitelist()
        if phone_number in whitelist:
            bot.send_message(message.chat.id, "❗️ Этот номер уже в белом списке.")
            return

        whitelist.append(phone_number)
        save_whitelist(whitelist)
        bot.send_message(message.chat.id, f"✅ Номер {phone_number} добавлен в белый список.")

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

        # Проверка на белый список
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
        notify_expired_subscriptions()
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        raise