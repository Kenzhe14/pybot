import telebot
import os
import json
import subprocess
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

TOKEN = os.getenv("TOKEN")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")  # Укажите имя пользователя администратора
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Укажите Telegram ID администратора
SUBSCRIPTIONS_FILE = "subscriptions.json"

bot = telebot.TeleBot(TOKEN)


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
    expires_at = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    subscriptions[str(user_id)] = {"expires_at": expires_at, "days": days}
    save_subscriptions(subscriptions)


def check_subscription(user_id):
    subscriptions = load_subscriptions()
    if str(user_id) in subscriptions:
        expires_at = datetime.strptime(subscriptions[str(user_id)]["expires_at"], "%Y-%m-%d %H:%M:%S")
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
                bot.send_message(int(user_id), "❌ Ваша подписка истекла! Купите новую через /buy")
            except telebot.apihelper.ApiTelegramException as e:
                print(f"Ошибка отправки сообщения пользователю {user_id}: {e}")

            expired_users.append(user_id)  # Добавляем в список для удаления

    # Удаляем подписки после уведомления
    for user_id in expired_users:
        del subscriptions[user_id]

    save_subscriptions(subscriptions)


@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Привет! Отправь мне номер и время в формате: +7XXXXXXXXXX XX")


@bot.message_handler(commands=['buy'])
def buy_subscription(message):
    bot.send_message(message.chat.id, f"Для покупки подписки напишите администратору: {ADMIN_USERNAME}")


@bot.message_handler(commands=['check'])
def check_subscription_status(message):
    user_id = message.chat.id
    if check_subscription(user_id):
        bot.send_message(message.chat.id, "✅ У вас есть активная подписка!")
    else:
        bot.send_message(message.chat.id, "❌ Ваша подписка истекла. Купите её через /buy")


@bot.message_handler(commands=['addsub'])
def add_subscription_admin(message):
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды.")
        return

    try:
        args = message.text.split()
        if len(args) != 3:
            raise ValueError("Неверный формат. Используйте: /addsub user_id количество_дней")

        user_id = int(args[1])
        days = int(args[2])
        add_subscription(user_id, days)
        bot.send_message(message.chat.id, f"✅ Подписка на {days} дней добавлена пользователю {user_id}")
        bot.send_message(user_id, f"✅ Администратор активировал вам подписку на {days} дней!")

    except ValueError:
        bot.send_message(message.chat.id, "❌ Ошибка! Используйте формат: /addsub user_id количество_дней")


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

        bot.send_message(message.chat.id, f"Спам запущен для {phone_number} на {time} секунд")

        # Запускаем процесс и ждем его завершения
        process = subprocess.run(["python", "spam.py", phone_number, time])

        # После завершения отправляем сообщение
        bot.send_message(message.chat.id, "✅ Успешный спам!")

    except ValueError as e:
        bot.send_message(message.chat.id, "❌ Ошибка: неверный формат ввода. Используйте: +7XXXXXXXXXX XX")


notify_expired_subscriptions()
bot.polling()
