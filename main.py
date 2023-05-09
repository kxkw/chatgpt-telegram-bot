import telebot
import openai
from dotenv.main import load_dotenv
import json
import os
import datetime


prompt = "You are a helpful assistant."  # "You are Marv - a sarcastic reluctant assistant."
price_1k = 0.002  # price per 1k rokens in USD
date_format = "%d-%m-%Y %H:%M:%S"  # date format %d.%m.%Y %H:%M:%S


# load .env file with secrets
load_dotenv()

# Load OpenAI API credentials from .env file
openai.api_key = os.getenv("OPENAI_API_KEY")

# Create a new Telebot instance
bot = telebot.TeleBot(os.getenv("TELEGRAM_API_KEY"))

# Получаем айди админа, которому в лс будут приходить логи
admin_id = int(os.getenv("ADMIN_ID"))

# File with users and global token usage data
datafile = "data.json"


"""======================FUNCTIONS======================="""


# Function to check if the user is in the data file
def is_user_exists(user_id: int) -> bool:
    if user_id in data:
        return True
    else:
        return False


# Function to add new user to the data file
def add_new_user(user_id: int) -> None:
    data[user_id] = default_data.copy()


# Function to update the JSON file with relevant data
def update_json_file(new_data) -> None:
    with open(datafile, "w") as file:
        json.dump(new_data, file, indent=4)


"""======================SOME_CODE======================="""  # kek


# Check if the file exists
if os.path.isfile(datafile):
    # Read the contents of the file
    with open(datafile, "r") as f:
        data = json.load(f)

    # Convert keys to integers (except for the first key)
    for key in list(data.keys())[1:]:
        data[int(key)] = data.pop(key)
else:
    data = {"global": {"requests": 0, "tokens": 0},
            admin_id: {"requests": 0, "tokens": 0, "balance": 777777, "lastdate": "07-05-2023 00:00:00"}}
    # Create the file with default values
    update_json_file(data)

# Default values for new users, who are not in the data file
default_data = {"requests": 0, "tokens": 0, "balance": 30000, "lastdate": "07-05-2023 00:00:00"}


# Calculate the price per token in cents
price_cents = price_1k / 10

# Session token and request counters
session_tokens, request_number = 0, 0


"""=======================HANDLERS======================="""


# Define the handler for the /start command
@bot.message_handler(commands=["start"])
def handle_start_command(message):
    user_id = message.from_user.id

    # Если юзер уже есть в базе, то просто здороваемся и выходим, иначе добавляем его в базу
    if is_user_exists(user_id):
        bot.send_message(message.chat.id, "Магдыч готов к работе 💪")  # мб выдавать случайное приветствие из пула
        return
    else:
        add_new_user(user_id)
        update_json_file(data)

        welcome_string = f"{message.from_user.first_name}, с подключением 🤝\n\n" \
                         f"На твой баланс зачислено 30к токенов 🤑\n\n" \
                         f"Полезные команды: \n/balance - баланс\n/stats - статистика\n"
        bot.send_message(message.chat.id, welcome_string)

        new_user_string = f"\nНовый пользователь: {message.from_user.full_name} " \
                          f"@{message.from_user.username} {message.from_user.id}"
        print(new_user_string)
        bot.send_message(admin_id, new_user_string)


# Define the handler for the /stop command
@bot.message_handler(commands=["stop"])
def handle_stop_command(message):
    if message.from_user.id == admin_id:
        bot.reply_to(message, "Stopping the script...")
        bot.stop_polling()
    else:
        bot.reply_to(message, "Только админ может останавливать бота")


# Define the handler for the /balance command
@bot.message_handler(commands=["balance"])
def handle_balance_command(message):
    if message.from_user.id not in data:
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start")
        return
    balance = data[message.from_user.id]["balance"]
    bot.reply_to(message, f"Ваш баланс: {balance} токенов")


# Define the handler for the /stats command
@bot.message_handler(commands=["stats"])
def handle_stats_command(message):
    if message.from_user.id not in data:
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start")
        return
    user_stats = data[message.from_user.id]["requests"], \
        data[message.from_user.id]["tokens"], data[message.from_user.id]["lastdate"]
    bot.reply_to(message, f"Запросов: {user_stats[0]}\n"
                          f"Токенов использовано: {user_stats[1]}\n"
                          f"Последний запрос: {user_stats[2]}")


# Define the message handler for incoming messages
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    global session_tokens, request_number, prompt, data

    # Если пользователя нет в базе, то добавляем его с дефолтными значениями
    if message.from_user.id not in data:
        data[message.from_user.id] = default_data.copy()
        new_user_string = f"\nНовый пользователь: {message.from_user.full_name} " \
                          f"@{message.from_user.username} {message.from_user.id}"
        print(new_user_string)
        bot.send_message(admin_id, new_user_string)
        # Записываем инфу о новом пользователе в файл
        with open(datafile, "w") as f:
            json.dump(data, f, indent=4)

    # Проверяем, есть ли у пользователя токены на балансе
    if data[message.from_user.id]["balance"] <= 0:
        bot.send_message(message.chat.id, "У вас закончились токены. Пополните баланс")
        return

    # Send the user's message to OpenAI API and get the response. System message is for chat context (in the future)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            max_tokens=3000,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": message.text},
            ]
        )
    except openai.error.RateLimitError:
        print("\nЛимит запросов!")
        bot.send_message(message.chat.id, "Превышен лимит запросов. Пожалуйста, попробуйте секунд через 20")
        return

    # Получаем стоимость запроса по АПИ в токенах
    request_tokens = response["usage"]["total_tokens"]  # same: response.usage.total_tokens
    session_tokens += request_tokens
    request_number += 1

    # Обновляем глобальную статистику по количеству запросов и использованных токенов
    data["global"]["tokens"] += request_tokens
    data["global"]["requests"] += 1

    # Если юзер не админ, то списываем токены с баланса
    if message.from_user.id != admin_id:
        data[message.from_user.id]["balance"] -= request_tokens

    # Обновляем данные юзера по количеству запросов, использованных токенов и дате последнего запроса
    data[message.from_user.id]["tokens"] += request_tokens
    data[message.from_user.id]["requests"] += 1
    data[message.from_user.id]["lastdate"] = datetime.datetime.now().strftime(date_format)

    # Записываем инфу о количестве запросов и токенах в файл
    with open(datafile, "w") as f:
        json.dump(data, f, indent=4)

    # Считаем стоимость запроса в центах
    request_price = request_tokens * price_cents

    # формируем лог работы для юзера
    user_log = f"\n\n\nТокены: {request_tokens} за ¢{round(request_price, 3)}. " \
               f"\nОбщая стоимость сессии: ¢{round(session_tokens * price_cents, 3)}"

    # Send the response back to the user
    if message.chat.type == "private":
        bot.send_message(message.chat.id, response.choices[0].message.content + user_log)
    else:
        bot.reply_to(message, response.choices[0].message.content + user_log)

    # Формируем лог работы для админа
    admin_log = (f"Запрос {request_number}: {request_tokens} за ¢{round(request_price, 3)}\n"
                 f"Сессия: {session_tokens} за ¢{round(session_tokens * price_cents, 3)}\n"
                 f"Юзер: {message.from_user.full_name} "
                 f"@{message.from_user.username} {message.from_user.id}\n"
                 f"Чат: {message.chat.title} {message.chat.id}"
                 f"\n{data['global']} ¢{round(data['global']['tokens'] * price_cents, 3)}")

    # Пишем лог работы в консоль
    print("\n" + admin_log)

    # Отправляем лог работы админу в тг
    if message.chat.id != admin_id:
        bot.send_message(admin_id, admin_log)


# Start the bot
print("---работаем---")
bot.infinity_polling()

# Уведомляем админа об успешном завершении работы
bot.send_message(admin_id, "Бот остановлен")
