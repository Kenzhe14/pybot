import telebot
import os
import json
import subprocess
import fcntl
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
LOCK_FILE = "bot.lock"
DATA_FILE = "data.json"

def load_services():
    """Загружает список сервисов из файла конфигурации"""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            services = data.get('services', {})
            print(f"Загружено {len(services)} сервисов:")
            for service_name, service_data in services.items():
                status = service_data.get('expected_status', 'N/A')
                print(f"- {service_name} (Status: {status})")
            return services
    except Exception as e:
        print(f"Ошибка при загрузке сервисов: {e}")
        return {}

def acquire_lock():
    """Пытается получить блокировку для единственного экземпляра бота"""
    try:
        lock_file = open(LOCK_FILE, 'w')
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except IOError:
        return None

def load_subscriptions():
    if os.path.exists(SUBSCRIPTIONS_FILE):
        with open(SUBSCRIPTIONS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    return {}

def save_subscriptions(subscriptions):
    with open(SUBSCRIPTIONS_FILE, "w", encoding="utf-8") as file:
        json.dump(subscriptions, file, indent=4)

def check_subscription(user_id):
    subscriptions = load_subscriptions()
    if str(user_id) in subscriptions:
        expires_at = datetime.strptime(
            subscriptions[str(user_id)]["expires_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() < expires_at:
            return True
    return False

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

try:
    bot = telebot.TeleBot(TOKEN)
    services = load_services()
    print(f"Бот успешно инициализирован")
    print(f"Доступно сервисов: {len(services)}")
except Exception as e:
    print(f"Ошибка при инициализации бота: {e}")
    raise

@bot.message_handler(commands=['start'])
def start(message):
    services_count = len(load_services())
    bot.send_message(
        message.chat.id,
        f"Привет! Отправь мне номер и время в формате: +7XXXXXXXXXX XX\n"
        f"Доступно сервисов: {services_count}")

@bot.message_handler(commands=['buy'])
def buy_subscription(message):
    bot.send_message(
        message.chat.id,
        f"Для покупки подписки напишите администратору: {ADMIN_USERNAME}")

@bot.message_handler(commands=['check'])
def check_subscription_status(message):
    if check_subscription(message.chat.id):
        bot.send_message(message.chat.id, "✅ У вас есть активная подписка!")
    else:
        bot.send_message(message.chat.id,
                         "❌ У вас нет подписки. Купите через /buy")

@bot.message_handler(commands=['addsub'])
def add_subscription_admin(message):
    if str(message.chat.id) != ADMIN_ID:
        bot.send_message(message.chat.id,
                         "❌ У вас нет прав для выполнения этой команды")
        return

    try:
        args = message.text.split()
        if len(args) != 3:
            raise ValueError("Неверный формат")

        user_id = args[1]
        days = int(args[2])

        subscriptions = load_subscriptions()
        expires_at = (datetime.now() +
                      timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        subscriptions[user_id] = {"expires_at": expires_at, "days": days}
        save_subscriptions(subscriptions)

        bot.send_message(
            message.chat.id,
            f"✅ Подписка на {days} дней добавлена пользователю {user_id}")
        bot.send_message(
            int(user_id),
            f"✅ Администратор активировал вам подписку на {days} дней!")

    except ValueError as e:
        bot.send_message(
            message.chat.id,
            "❌ Ошибка! Используйте формат: /addsub user_id количество_дней")

@bot.message_handler(commands=['addwhite'])
def add_to_whitelist(message):
    if str(message.chat.id) != ADMIN_ID:
        bot.send_message(message.chat.id,
                         "❌ Эта команда доступна только администратору")
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
            bot.send_message(message.chat.id, "❗️ Этот номер уже в белом списке")
            return

        whitelist.append(phone_number)
        save_whitelist(whitelist)
        bot.send_message(message.chat.id,
                         f"✅ Номер {phone_number} добавлен в белый список")

    except ValueError as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    except Exception as e:
        bot.send_message(message.chat.id,
                         "❌ Произошла ошибка при добавлении номера")

@bot.message_handler(commands=['services'])
def list_services(message):
    services = load_services()
    service_list = "\n".join([f"- {name}" for name in services.keys()])
    bot.send_message(
        message.chat.id,
        f"Доступные сервисы ({len(services)}):\n{service_list}")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        print(f"Обработка сообщения от пользователя {message.chat.id}: {message.text}")
        if not check_subscription(message.chat.id):
            bot.send_message(message.chat.id,
                             "❌ У вас нет подписки! Купите через /buy")
            return

        data = message.text.split()
        if len(data) != 2:
            raise ValueError("Неверный формат")

        phone_number, time_duration = data
        if not phone_number.startswith("+7") or not phone_number[1:].isdigit():
            raise ValueError("Неверный номер")
        if not time_duration.isdigit():
            raise ValueError("Неверное время")

        if is_whitelisted(phone_number):
            bot.send_message(
                message.chat.id,
                "❌ Этот номер находится в белом списке и защищен от спама")
            return

        process = None  # Initialize process variable
        try:
            print(f"Запуск спама для номера {phone_number} на {time_duration} секунд")
            # Запускаем скрипт spam.py с параметрами
            process = subprocess.Popen(
                ["python", "spam.py", phone_number, time_duration],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)

            # Отправляем сообщение о начале спама
            bot.send_message(
                message.chat.id,
                f"⏳ Начинаю спам для номера {phone_number} на {time_duration} секунд"
            )

            # Ждем завершения процесса
            stdout, stderr = process.communicate(timeout=int(time_duration) + 10)

            # Проверяем результат
            if process.returncode == 0:
                bot.send_message(message.chat.id, "✅ Спам успешно завершен!")
            else:
                error_msg = stderr.decode() if stderr else "Неизвестная ошибка"
                print(f"Ошибка при выполнении спама: {error_msg}")  # Add error logging
                bot.send_message(
                    message.chat.id,
                    f"❌ Ошибка при выполнении спама: {error_msg}")

        except subprocess.TimeoutExpired:
            if process:  # Check if process exists before killing
                process.kill()
            bot.send_message(message.chat.id,
                             "❌ Превышено время ожидания. Спам остановлен.")
        except Exception as e:
            print(f"Критическая ошибка при запуске спама: {str(e)}")  # Add error logging
            bot.send_message(
                message.chat.id,
                f"❌ Произошла ошибка при запуске спама: {str(e)}")

    except ValueError as e:
        bot.send_message(
            message.chat.id,
            "❌ Ошибка: неверный формат ввода. Используйте: +7XXXXXXXXXX XX")

if __name__ == "__main__":
    # Проверяем, не запущен ли уже бот
    lock = acquire_lock()
    if not lock:
        print("Бот уже запущен в другом процессе")
        exit(1)

    try:
        services = load_services()
        print("Бот запущен...")
        print(f"Загружено {len(services)} сервисов")
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        raise
    finally:
        # Освобождаем блокировку при завершении
        if lock:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()
            try:
                os.remove(LOCK_FILE)
            except:
                pass