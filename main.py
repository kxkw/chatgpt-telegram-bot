from dotenv.main import load_dotenv
import telebot
import openai
import static
import json
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


# Define the message handler for incoming messages
@bot.message_handler(func=lambda message: True)
def handle_message(message):
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
    static.session_tokens += request_tokens
    static.request_number += 1

    data["tokens"] += request_tokens
    data["requests"] += 1

    # записываем инфу о количестве запросов и токенах
    with open(filename, "w") as f:
        json.dump(data, f)

    request_price = request_tokens * static.price_cents
    # формируем лог работы для юзера
    user_log = f"\n\n\nТокены: {request_tokens} за ¢{round(request_price, 4)}. " \
               f"\nОбщая стоимость сессии: ¢{round(static.session_tokens * static.price_cents, 4)}"

    # Send the response back to the user
    bot.send_message(message.chat.id, response.choices[0].message.content + user_log)

    # формируем лог работы для админа
    admin_log = (f"Запрос {static.request_number}: {request_tokens} токенов за ¢{round(request_price, 4)},"
                 f" всего {static.session_tokens} за ¢{round(static.session_tokens * static.price_cents, 4)},"
                 f" {message.chat.first_name} {message.chat.last_name} @{message.chat.username} {message.chat.id}"
                 f"\n{data}, ¢{round(data['tokens']*static.price_cents, 4)}")

    # пишем лог работы в консоль
    print(admin_log)

    # отправляем лог работы админу в тг
    if message.chat.id != admin_chat_id:
        bot.send_message(admin_chat_id, admin_log)


if __name__ == "__main__":
    # Start the bot
    print("Started")
    bot.infinity_polling()
