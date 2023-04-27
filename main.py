from dotenv.main import load_dotenv
import telebot
import _thread
import openai
import static
import json
import time
import os


# API1: $18, 1 June; API2: $5, 1 July
# Load OpenAI API credentials from .env file
load_dotenv()

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


openai.api_key = os.getenv("OPENAI_API_KEY")

# Create a new Telebot instance
bot = telebot.TeleBot(os.getenv("TELEGRAM_API_KEY"))

# получаем чат_айди админа, которому в лс будут приходить логи
admin_chat_id = int(os.getenv("ADMIN_CHAT_ID"))

session_tokens = 0
request_number = 0


@bot.message_handler(commands=["stop"])
def stop(message: telebot.types.Message):
    if message.from_user.id == admin_chat_id:
        bot.send_message(message.from_user.id, "Are you sure you want to turn off the bot?\n/y | /n")
        bot.register_next_step_handler(message, are_you_sure_to_stop)


def are_you_sure_to_stop(message: telebot.types.Message):
    if message.text == "/y":
        bot.send_message(message.from_user.id, "Exited")
        time.sleep(2)
        _thread.interrupt_main()
    elif message.text == "/n":
        bot.send_message(message.from_user.id, "Cancelled")
    else:
        bot.send_message(message.from_user.id, "Unknown answer, cancelled")


# Define the message handler for incoming messages
@bot.message_handler(func=lambda message: True)
def handle_message(message: telebot.types.Message):
    global session_tokens
    global request_number
    global data

    # Send the user's message to OpenAI API and get the response
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        max_tokens=3000,
        messages=[
            {"role": "system", "content": static.prompt},
            {"role": "user", "content": message.text},
        ]
    )

    request_tokens = response["usage"]["total_tokens"]  # same: response.usage.total_tokens
    session_tokens += request_tokens
    request_number += 1

    data["tokens"] += request_tokens
    data["requests"] += 1

    price_cents = static.price_1k / 10

    # записываем инфу о количестве запросов и токенах
    with open(filename, "w") as f:
        json.dump(data, f)

    request_price = request_tokens * price_cents
    # формируем лог работы для юзера
    user_log = f"\n\n\nТокены: {request_tokens} за ¢{round(request_price, 4)}. " \
               f"\nОбщая стоимость сессии: ¢{round(session_tokens * price_cents, 4)}"

    # Send the response back to the user
    bot.send_message(message.chat.id, response.choices[0].message.content + user_log)

    # формируем лог работы для админа
    admin_log = (f"Запрос {request_number}: {request_tokens} токенов за ¢{round(request_price, 4)},"
                 f" всего {session_tokens} за ¢{round(session_tokens * price_cents, 4)},"
                 f" {message.chat.first_name} {message.chat.last_name} @{message.chat.username} {message.chat.id}"
                 f"\n{data}, ¢{round(data['tokens'] * price_cents, 4)}")

    # пишем лог работы в консоль
    print(admin_log)

    # отправляем лог работы админу в тг
    if message.chat.id != admin_chat_id:
        bot.send_message(admin_chat_id, admin_log)


if __name__ == "__main__":
    # Start the bot
    print("Started")
    bot.infinity_polling()
