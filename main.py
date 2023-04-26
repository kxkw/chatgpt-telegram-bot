import telebot
import openai
from dotenv.main import load_dotenv
import os

# API1: $18, 1 June; API2: $5, 1 July
# Load OpenAI API credentials from .env file
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Create a new Telebot instance
bot = telebot.TeleBot(os.getenv("TELEGRAM_API_KEY"))

# получаем чат_айди админа, которому в лс будут приходить логи
admin_chat_id = int(os.getenv("ADMIN_CHAT_ID"))

# prompt = "You are Marv - a sarcastic reluctant assistant."
prompt = "You are a helpful assistant."

gross_tokens_used = 0
request_number = 1
price_1k = 0.002

price_cents = price_1k / 10


# Define the message handler for incoming messages
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    global gross_tokens_used
    global request_number
    global price_cents
    global admin_chat_id
    global prompt

    # Send the user's message to OpenAI API and get the response
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        max_tokens=3000,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": message.text},
        ]
    )
    # print(response)

    request_tokens = response.usage.total_tokens  # response["usage"]["total_tokens"] то же самое
    gross_tokens_used += request_tokens

    request_price = request_tokens * price_cents
    # формируем лог работы для юзера
    user_log = f"\n\n\nТокены: {request_tokens} за ¢{round(request_price, 4)}. " \
               f"\nОбщая стоимость сессии: ¢{round(gross_tokens_used * price_cents, 4)}"

    # Send the response back to the user
    bot.send_message(message.chat.id, response.choices[0].message.content + user_log)

    # формируем лог работы для админа
    admin_log = (f"Запрос {request_number}: {request_tokens} токенов за ¢{round(request_price, 4)},"
                 f" {gross_tokens_used} всего за ¢{round(gross_tokens_used * price_cents, 4)}, "
                 f"юзер {message.chat.first_name} {message.chat.last_name} @{message.chat.username} {message.chat.id}")

    # пишем лог работы в консоль
    print(admin_log)

    # отправляем лог работы админу в тг
    if message.chat.id != admin_chat_id:
        bot.send_message(admin_chat_id, admin_log)

    request_number += 1


# Start the bot
bot.polling()
