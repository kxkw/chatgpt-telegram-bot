import telebot
import openai
from dotenv.main import load_dotenv
import json
import os


prompt = "You are a helpful assistant."  # "You are Marv - a sarcastic reluctant assistant."
price_1k = 0.002  # price per 1k rokens in USD


# File with global token usage data
filename = "data.json"
default_data = {"requests": 0, "tokens": 0}  # Default values for the JSON file

# Check if the file exists
if os.path.isfile(filename):
    # Read the contents of the file
    with open(filename, "r") as file:
        data = json.load(file)
else:
    # Create the file with default values
    with open(filename, "w") as file:
        json.dump(default_data, file)
    data = default_data


# load .env file with secrets
load_dotenv()

# Load OpenAI API credentials from .env file
openai.api_key = os.getenv("OPENAI_API_KEY")

# Create a new Telebot instance
bot = telebot.TeleBot(os.getenv("TELEGRAM_API_KEY"))

# Получаем чат_айди админа, которому в лс будут приходить логи
admin_chat_id = int(os.getenv("ADMIN_CHAT_ID"))

price_cents = price_1k / 10

# Session token and request counters
session_tokens = 0
request_number = 0


# Define the handler for the /start command
@bot.message_handler(commands=["start"])
def handle_stop_command(message):
    bot.send_message(message.chat.id, "Привет, я Магдыч!")


# Define the handler for the /stop command
@bot.message_handler(commands=["stop"])
def handle_stop_command(message):
    if message.chat.id == admin_chat_id:
        bot.reply_to(message, "Stopping the script...")
        bot.stop_polling()
    else:
        bot.reply_to(message, "Только админ может останавливать бота")


# Define the message handler for incoming messages
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    global session_tokens, request_number, prompt, data

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
    data["tokens"] += request_tokens
    data["requests"] += 1

    # Записываем инфу о количестве запросов и токенах в файл
    with open(filename, "w") as f:
        json.dump(data, f)

    # Считаем стоимость запроса в центах
    request_price = request_tokens * price_cents

    # формируем лог работы для юзера
    user_log = f"\n\n\nТокены: {request_tokens} за ¢{round(request_price, 3)}. " \
               f"\nОбщая стоимость сессии: ¢{round(session_tokens * price_cents, 3)}"

    # Send the response back to the user
    bot.send_message(message.chat.id, response.choices[0].message.content + user_log)

    # Формируем лог работы для админа
    admin_log = (f"Запрос {request_number}: {request_tokens} за ¢{round(request_price, 3)}\n"
                 f"Сессия: {session_tokens} за ¢{round(session_tokens * price_cents, 3)}\n"
                 f"Юзер: {message.chat.first_name} {message.chat.last_name} @{message.chat.username} {message.chat.id}"
                 f"\n{data} ¢{round(data['tokens'] * price_cents, 3)}")

    # Пишем лог работы в консоль
    print("\n" + admin_log)

    # Отправляем лог работы админу в тг
    if message.chat.id != admin_chat_id:
        bot.send_message(admin_chat_id, admin_log)


# Start the bot
print("---работаем---")
bot.infinity_polling()

# Уведомляем админа об успешном завершении работы
bot.send_message(admin_chat_id, "Бот остановлен")
