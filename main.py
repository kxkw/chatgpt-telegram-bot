import telebot
import openai
from dotenv.main import load_dotenv
import json
import os
import datetime
import time

from telebot.util import extract_arguments


MODEL = "gpt-3.5-turbo"
MAX_REQUEST_TOKENS = 1800
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant named Магдыч."

PRICE_1K = 0.002  # price per 1k tokens in USD
DATE_FORMAT = "%d.%m.%Y %H:%M:%S"  # date format for logging

NEW_USER_BALANCE = 20000  # balance for new users
REFERRAL_BONUS = 10000  # bonus for inviting a new user

# load .env file with secrets
load_dotenv()

# Load OpenAI API credentials from .env file
openai.api_key = os.getenv("OPENAI_API_KEY")

# Create a new Telebot instance
bot = telebot.TeleBot(os.getenv("TELEGRAM_API_KEY"))

# Получаем айди админа, которому в лс будут приходить логи
ADMIN_ID = int(os.getenv("ADMIN_ID"))


# File with users and global token usage data
DATAFILE = "data.json"
BACKUPFILE = "data-backup.json"

# Default values for new users, who are not in the data file
DEFAULT_DATA = {"requests": 0, "tokens": 0, "balance": NEW_USER_BALANCE,
                "name": "None", "username": "None", "lastdate": "11-09-2001 00:00:00"}


"""======================FUNCTIONS======================="""


# Function to check if the user is in the data file
def is_user_exists(user_id: int) -> bool:
    if user_id in data:
        return True
    else:
        return False


# Function to check if the user is in the blacklist
def is_user_blacklisted(user_id: int) -> bool:
    if user_id in data and "blacklist" in data[user_id]:
        return data[user_id]["blacklist"]
    else:
        return False


# Function to add new user to the data file
def add_new_user(user_id: int, name: str, username: str, referrer=None) -> None:
    data[user_id] = DEFAULT_DATA.copy()
    data[user_id]["name"] = name

    if username is not None:
        data[user_id]["username"] = '@'+username
    else:
        data[user_id]["username"] = "None"

    if referrer is not None:
        data[user_id]["balance"] += REFERRAL_BONUS
        data[user_id]["ref_id"] = referrer


# Function to update the JSON file with relevant data
def update_json_file(new_data, file_name=DATAFILE) -> None:
    with open(file_name, "w", encoding='utf-8') as file:
        json.dump(new_data, file, ensure_ascii=False, indent=4)


# Function to get the user's prompt
def get_user_prompt(user_id: int) -> str:
    if data[user_id].get("prompt") is None:
        return DEFAULT_SYSTEM_PROMPT
    else:
        return str(data[user_id]["prompt"])


# Function to call the OpenAI API and get the response
def call_chatgpt(user_request: str, prev_answer=None, system_prompt=DEFAULT_SYSTEM_PROMPT):
    messages = [{"role": "system", "content": system_prompt}]

    if prev_answer is not None:
        messages.extend([{"role": "assistant", "content": prev_answer},
                         {"role": "user", "content": user_request}])
        print("\nЗапрос с контекстом 🤩")
    else:
        messages.append({"role": "user", "content": user_request})
        print("\nЗапрос без контекста")

    return openai.ChatCompletion.create(
        model=MODEL,
        max_tokens=MAX_REQUEST_TOKENS,
        messages=messages
    )


"""========================SETUP========================="""


# Check if the file exists
if os.path.isfile(DATAFILE):
    # Read the contents of the file
    with open(DATAFILE, "r", encoding='utf-8') as f:
        data = json.load(f)

    # Convert keys to integers (except for the first key)
    for key in list(data.keys())[1:]:
        data[int(key)] = data.pop(key)
else:
    data = {"global": {"requests": 0, "tokens": 0},
            ADMIN_ID: {"requests": 0, "tokens": 0, "balance": 777777,
                       "name": "АДМИН", "username": "@admin", "lastdate": "01-05-2023 00:00:00"}}
    # Create the file with default values
    update_json_file(data)


# Calculate the price per token in cents
PRICE_CENTS = PRICE_1K / 10

# Session token and request counters
session_tokens, request_number = 0, 0


"""====================ADMIN_COMMANDS===================="""


# Define the handler for the admin /data command
@bot.message_handler(commands=["data"])
def handle_data_command(message):
    target_user_string = extract_arguments(message.text)
    not_found_string = "Пользователь не найден, либо данные введены неверно.\n" \
                       "Укажите @username или id пользователя после команды `/data`"

    # Проверки на доступность команды
    if message.from_user.id != ADMIN_ID:  # Если пользователь не админ
        bot.reply_to(message, "Команда доступна только админу")
        return
    elif message.chat.type != "private":  # Если команда вызвана не в личке с ботом (чтобы не скомпрометировать данные)
        bot.reply_to(message, "Эта команда недоступна в групповых чатах")
        return

    if target_user_string == '':  # Если аргументов нет, то отправить весь файл
        bot.send_message(ADMIN_ID, f"Копия файла `{DATAFILE}`:", parse_mode="MARKDOWN")
        bot.send_document(ADMIN_ID, open(DATAFILE, "rb"))
        print("\nДанные отправлены админу")
        return

    elif target_user_string[0] == "@":  # Поиск по @username
        for user_id in list(data.keys())[2:]:
            if data[user_id]["username"] == target_user_string:
                bot.send_message(ADMIN_ID, json.dumps(data[user_id], ensure_ascii=False, indent=4))
                return
        bot.send_message(ADMIN_ID, not_found_string, parse_mode="MARKDOWN")

    elif target_user_string.isdigit():  # Поиск по id пользователя
        target_user_string = int(target_user_string)
        if target_user_string in data:
            bot.send_message(ADMIN_ID, json.dumps(data[target_user_string], ensure_ascii=False, indent=4))
            return
        bot.send_message(ADMIN_ID, not_found_string, parse_mode="MARKDOWN")

    else:
        bot.send_message(ADMIN_ID, not_found_string, parse_mode="MARKDOWN")


# Define the handler for the admin /refill command
@bot.message_handler(commands=["refill"])
def handle_refill_command(message):
    wrong_input_string = "Укажите @username/id пользователя и сумму пополнения после команды\n\n" \
                         "Пример: `/refill @username 1000`"

    # Проверки на доступность команды
    if message.from_user.id != ADMIN_ID:  # Если пользователь не админ
        bot.reply_to(message, "Команда доступна только админу")
        return
    elif message.chat.type != "private":  # Если команда вызвана не в личке с ботом
        bot.reply_to(message, "Эта команда недоступна в групповых чатах")
        return

    try:
        target_user, amount = extract_arguments(message.text).split()
        amount = int(amount)
    except ValueError:
        bot.send_message(ADMIN_ID, wrong_input_string, parse_mode="MARKDOWN")
        return

    not_found_string = f"Пользователь {target_user} не найден"
    success_string = f"Баланс пользователя {target_user} успешно пополнен на {amount} токенов"

    if target_user[0] == '@':
        for user_id in list(data.keys())[2:]:
            if data[user_id]["username"] == target_user:
                data[user_id]["balance"] += amount
                update_json_file(data)
                bot.send_message(ADMIN_ID, success_string)
                return
        bot.send_message(ADMIN_ID, not_found_string)

    elif target_user.isdigit():
        if int(target_user) in data:
            data[int(target_user)]["balance"] += amount
            update_json_file(data)
            bot.send_message(ADMIN_ID, success_string)
            return
        bot.send_message(ADMIN_ID, not_found_string)
    else:
        bot.send_message(ADMIN_ID, wrong_input_string, parse_mode="MARKDOWN")


# Define the handler for the /stop command
@bot.message_handler(commands=["stop"])
def handle_stop_command(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "Stopping the script...")
        bot.stop_polling()



"""=======================HANDLERS======================="""


# Define the handler for the /start command
@bot.message_handler(commands=["start"])
def handle_start_command(message):
    user = message.from_user

    if is_user_blacklisted(user.id):
        return

    # Если юзер уже есть в базе, то просто здороваемся и выходим, иначе проверяем рефералку и добавляем его в базу
    if is_user_exists(user.id):
        bot.send_message(message.chat.id, "Магдыч готов к работе 💪💅")  # мб выдавать случайное приветствие
        return

    welcome_string = f"{user.first_name}, с подключением 🤝\n\n" \
                     f"На твой баланс зачислено {NEW_USER_BALANCE//1000}к токенов 🤑\n\n" \
                     f"Полезные команды:\n/help - список команд\n/balance - баланс токенов\n" \
                     f"/stats - статистика запросов\n/prompt - установить системный промпт\n\n" \
                     f"/invite или /ref - пригласить друга и получить бонус 🎁"
    bot.send_message(message.chat.id, welcome_string)

    new_referral_string = ""
    referrer = extract_arguments(message.text)
    if referrer and referrer.isdigit() and is_user_exists(int(referrer)) and not is_user_blacklisted(int(referrer)):
        referrer = int(referrer)
        invited_by_string = f"Ого, тебя пригласил 🤩{data[referrer]['name']}🤩\n\n" \
                            f"На твой баланс дополнительно зачислено +{str(REFERRAL_BONUS)} токенов! 🎉"
        time.sleep(1.5)
        bot.send_message(message.chat.id, invited_by_string)

        data[referrer]["balance"] += REFERRAL_BONUS
        ref_notification_string = f"Ого, по твоей ссылке присоединился 🤩{user.full_name}🤩\n\n" \
                                  f"Это заслуживает лайка и +{str(REFERRAL_BONUS)} токенов на счет! 🎉"
        bot.send_message(referrer, ref_notification_string)

        new_referral_string = f"{data[referrer]['name']} {data[referrer]['username']} пригласил {user.full_name} 🤝\n"
    else:
        referrer = None

    add_new_user(user.id, user.first_name, user.username, referrer)
    update_json_file(data)

    new_user_log = f"\nНовый пользователь: {user.full_name} " \
                   f"@{user.username} {user.id}!"
    print(new_referral_string + new_user_log)
    bot.send_message(ADMIN_ID, new_referral_string + new_user_log)


# Define the handler for the /help command
@bot.message_handler(commands=["help"])
def handle_help_command(message):

    if is_user_blacklisted(message.from_user.id):
        return

    help_string = "Список доступных команд:\n\n" \
                  "/start - регистрация в системе\n/help - список команд (вы здесь)\n" \
                  "/invite - пригласить друга и получить бонус 🎁\n\n" \
                  "/balance - баланс токенов\n/stats - статистика запросов\n\n" \
                  "/prompt - установить свой системный промпт\n" \
                  "/reset_prompt - вернуть промпт по умолчанию\n"
    bot.reply_to(message, help_string)


# Define the handler for the /ref command
@bot.message_handler(commands=["ref", "invite"])
def handle_ref_command(message):
    user_id = message.from_user.id

    if is_user_blacklisted(user_id):
        return

    if is_user_exists(user_id):
        ref_string = f"Пригласи друга по своей уникальной ссылке и раздели с ним 🎁*{REFERRAL_BONUS*2}*🎁 " \
                     f"токенов на двоих!\n\n" \
                     f"*Твоя реферальная ссылка:* \n" \
                     f"`https://t.me/{bot.get_me().username}?start={user_id}`\n\n" \
                     f"Зарабатывать еще никогда не было так легко! 🤑"
        bot.reply_to(message, ref_string, parse_mode="Markdown")
    else:
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start")


# Define the handler for the /balance command
@bot.message_handler(commands=["balance"])
def handle_balance_command(message):
    user_id = message.from_user.id

    if is_user_blacklisted(user_id):
        return

    # Если юзер есть в базе, то выдаем его баланс, иначе просим его зарегистрироваться
    if is_user_exists(user_id):
        balance = data[user_id]["balance"]
        bot.reply_to(message, f"Ваш баланс: {balance} токенов")
    else:
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start")


# Define the handler for the /stats command
@bot.message_handler(commands=["stats"])
def handle_stats_command(message):
    user_id = message.from_user.id

    if is_user_blacklisted(user_id):
        return

    # Если юзер есть в базе, то выдаем его статистику, иначе просим его зарегистрироваться
    if is_user_exists(user_id):
        user_stats = data[user_id]["requests"], data[user_id]["tokens"], data[user_id]["lastdate"]
        bot.reply_to(message, f"Запросов: {user_stats[0]}\n"
                              f"Токенов использовано: {user_stats[1]}")
    else:
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start")


# Define the handler for the /prompt command
@bot.message_handler(commands=["prompt"])
def handle_prompt_command(message):
    user = message.from_user
    answer = ""

    if is_user_blacklisted(user.id):
        return

    # Получаем аргументы команды (текст после /prompt)
    prompt = extract_arguments(message.text)

    # Если юзер есть в базе, то записываем промпт, иначе просим его зарегистрироваться
    if is_user_exists(user.id):
        if prompt:
            data[user.id]["prompt"] = prompt
            update_json_file(data)
            bot.reply_to(message, f"Установлен промпт: `{prompt}`", parse_mode="Markdown")
            print("\nУстановлен промпт: " + prompt)
        else:
            if "prompt" in data[user.id]:
                answer = f"*Текущий промпт:* `{str(data[user.id]['prompt'])}`\n\n"

            answer += "Системный промпт - это специальное указание, которое будет использоваться ботом вместе "\
                      "с каждым запросом для придания определенного поведения и стиля ответа. \n\n"\
                      "Для установки системного промпта напишите команду `/prompt`"\
                      " и требуемый текст одним сообщением, например: \n\n"\
                      "`/prompt Ты YodaGPT - AI модель, "\
                      "которая на все запросы отвечает в стиле Йоды из Star Wars`"

            bot.reply_to(message, answer,  parse_mode="Markdown")
            print("\nNo text provided.")
    else:
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start")


# Define the handler for the /reset_prompt command
@bot.message_handler(commands=["reset_prompt"])
def handle_reset_prompt_command(message):
    user = message.from_user

    if is_user_blacklisted(user.id):
        return

    # Если юзер есть в базе, то сбрасываем промпт, иначе просим его зарегистрироваться
    if is_user_exists(user.id):
        if data[user.id].get("prompt") is not None:
            del data[user.id]["prompt"]
            update_json_file(data)
            bot.reply_to(message, f"Системный промпт сброшен до значения по умолчанию")
            print("\nСистемный промпт сброшен до значения по умолчанию")
        else:
            bot.reply_to(message, f"У вас уже стоит дефолтный промпт!")
            print("\nУ вас уже стоит дефолтный промпт!")
    else:
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start")


# Define the message handler for incoming messages
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    global session_tokens, request_number, data
    user = message.from_user

    if is_user_blacklisted(user.id):
        return

    # Если юзер ответил на ответ боту другого юзера в групповом чате, то выходим, отвечать не нужно (issue #27)
    if message.reply_to_message is not None and message.reply_to_message.from_user.id != bot.get_me().id:
        print(f"\nUser {user.full_name} @{user.username} replied to another user, skip")
        return

    # Если пользователя нет в базе, то добавляем его с дефолтными значениями
    if not is_user_exists(user.id):
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start")
        return

    # Проверяем, есть ли у пользователя токены на балансе
    if data[user.id]["balance"] <= 0:
        bot.reply_to(message, "У вас закончились токены. Пополните баланс")
        return

    # Симулируем эффект набора текста, пока бот получает ответ
    bot.send_chat_action(message.chat.id, "typing")

    # Send the user's message to OpenAI API and get the response
    # Если юзер написал запрос в ответ на сообщение бота, то добавляем предыдущий ответ бота в запрос
    try:
        if message.reply_to_message is not None and message.reply_to_message.from_user.id == bot.get_me().id:
            response = call_chatgpt(message.text, message.reply_to_message.text, get_user_prompt(user.id))
        else:
            response = call_chatgpt(message.text, system_prompt=get_user_prompt(user.id))
    except openai.error.RateLimitError:
        print("\nЛимит запросов!")
        bot.reply_to(message, "Превышен лимит запросов. Пожалуйста, повторите попытку позже")
        return

    # Получаем стоимость запроса по АПИ в токенах
    request_tokens = response["usage"]["total_tokens"]  # same: response.usage.total_tokens
    session_tokens += request_tokens
    request_number += 1

    # Обновляем глобальную статистику по количеству запросов и использованных токенов
    data["global"]["tokens"] += request_tokens
    data["global"]["requests"] += 1

    # Если юзер не админ, то списываем токены с баланса
    if user.id != ADMIN_ID:
        data[user.id]["balance"] -= request_tokens

    # Обновляем данные юзера по количеству запросов, использованных токенов и дате последнего запроса
    data[user.id]["tokens"] += request_tokens
    data[user.id]["requests"] += 1
    data[user.id]["lastdate"] = datetime.datetime.now().strftime(DATE_FORMAT)

    # Записываем инфу о количестве запросов и токенах в файл
    update_json_file(data)

    # Считаем стоимость запроса в центах
    request_price = request_tokens * PRICE_CENTS

    # формируем лог работы для юзера под каждым сообщением
    user_log = ""  # \n\nБип-боп

    # Send the response back to the user, but check for `parse_mode` errors
    if message.chat.type == "private":
        try:
            bot.send_message(message.chat.id, response.choices[0].message.content + user_log, parse_mode="Markdown")
        except telebot.apihelper.ApiTelegramException:
            print(f"\nОшибка отправки из-за форматирования, отправляю без него")
            bot.send_message(message.chat.id, response.choices[0].message.content + user_log)
    else:
        try:
            bot.reply_to(message, response.choices[0].message.content + user_log, parse_mode="Markdown")
        except telebot.apihelper.ApiTelegramException:
            print(f"\nОшибка отправки из-за форматирования, отправляю без него")
            bot.reply_to(message, response.choices[0].message.content + user_log)

    # Формируем лог работы для админа
    admin_log = (f"Запрос {request_number}: {request_tokens} за ¢{round(request_price, 3)}\n"
                 f"Сессия: {session_tokens} за ¢{round(session_tokens * PRICE_CENTS, 3)}\n"
                 f"Юзер: {user.full_name} "
                 f"@{user.username} {user.id}\n"
                 f"Чат: {message.chat.title} {message.chat.id}"
                 f"\n{data['global']} ¢{round(data['global']['tokens'] * PRICE_CENTS, 3)}")

    # Пишем лог работы в консоль
    print("\n" + admin_log)

    # Отправляем лог работы админу в тг
    if message.chat.id != ADMIN_ID:
        bot.send_message(ADMIN_ID, admin_log)


# Start the bot
print("---работаем---")
bot.infinity_polling()

# Делаем бэкап бд и уведомляем админа об успешном завершении работы
update_json_file(data, BACKUPFILE)
bot.send_message(ADMIN_ID, "Бот остановлен")
