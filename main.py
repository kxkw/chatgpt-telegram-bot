from typing import Optional

import telebot
import openai
from openai import OpenAI

from dotenv.main import load_dotenv
import json
import os
from datetime import datetime, timedelta
import time

from telebot.util import extract_arguments, extract_command
from telebot import types
import base64
import requests


DEFAULT_MODEL = "gpt-3.5-turbo-0125"  # 16k
PREMIUM_MODEL = "gpt-4-0125-preview"  # 128k tokens context window
MAX_REQUEST_TOKENS = 4000  # max output tokens for one request (not including input tokens)
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant named Магдыч."

PRICE_1K = 0.002  # price per 1k tokens in USD
PREMIUM_PRICE_1K = 0.02  # price per 1k tokens in USD for premium model
IMAGE_PRICE = 0.08  # price per generated image in USD

DATE_FORMAT = "%d.%m.%Y %H:%M:%S"  # date format for logging
UTC_HOURS_DELTA = 3  # time difference between server and local time in hours (UTC +3)

NEW_USER_BALANCE = 30000  # balance for new users
REFERRAL_BONUS = 20000  # bonus for inviting a new user
FAVOR_AMOUNT = 30000  # amount of tokens per granted favor
FAVOR_MIN_LIMIT = 5000  # minimum balance to ask for a favor

# load .env file with secrets
load_dotenv()

# Load OpenAI API credentials from .env file
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Create a new Telebot instance
bot = telebot.TeleBot(os.getenv("TELEGRAM_API_KEY"))

# Получаем айди админа, которому в лс будут приходить логи
ADMIN_ID = int(os.getenv("ADMIN_ID"))


# File with users and global token usage data
DATAFILE = "data.json"
BACKUPFILE = "data-backup.json"

# Default values for new users, who are not in the data file
DEFAULT_NEW_USER_DATA = {"requests": 0, "tokens": 0, "balance": NEW_USER_BALANCE,
                         "name": "None", "username": "None", "lastdate": "01.01.1990 00:00:00"}


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
    data[user_id] = DEFAULT_NEW_USER_DATA.copy()
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


# Function to get user_id by username
def get_user_id_by_username(username: str) -> Optional[int]:
    for user_id in list(data.keys())[1:]:
        if data[user_id]["username"] == username:
            return user_id
    return None


# Function to get the user's prompt
def get_user_prompt(user_id: int) -> str:
    if data[user_id].get("prompt") is None:
        return DEFAULT_SYSTEM_PROMPT
    else:
        return str(data[user_id]["prompt"])


# Function to call the OpenAI API and get the response
def get_chatgpt_response(user_request: str, lang_model=DEFAULT_MODEL, prev_answer=None, system_prompt=DEFAULT_SYSTEM_PROMPT):
    messages = [{"role": "system", "content": system_prompt}]

    if prev_answer is not None:
        messages.extend([{"role": "assistant", "content": prev_answer},
                         {"role": "user", "content": user_request}])
        # print("\nЗапрос с контекстом 🤩")
    else:
        messages.append({"role": "user", "content": user_request})
        # print("\nЗапрос без контекста")

    return client.chat.completions.create(
        model=lang_model,
        max_tokens=MAX_REQUEST_TOKENS,
        messages=messages
    )


# Function to generate image with OpenAI API
def generate_image(image_prompt, model="dall-e-3"):
    response = client.images.generate(
        model=model,
        prompt=image_prompt,
        size="1024x1024",
        quality="hd"  # hd and standard, hd costs x2
    )
    return response


# Function to get all user's referrals
def get_user_referrals(user_id: int) -> list:
    user_referrals = []
    for user in data:
        if data[user].get("ref_id") == user_id:
            user_referrals.append(user)

    return user_referrals


def get_recent_active_users(days: int) -> list:
    recent_active_users = []
    current_date = datetime.now() + timedelta(hours=UTC_HOURS_DELTA)

    for user_id, user_data in data.items():
        if user_id == "global":
            continue

        try:
            last_request_date = datetime.strptime(user_data["lastdate"], DATE_FORMAT)
        # Если дата в неправильном формате, то пропускаем строчку (значит у юзера все равно 0 запросов, а Вы - олд)
        except ValueError:
            continue

        if (current_date - last_request_date).days < days:
            recent_active_users.append((user_id, last_request_date))

    # Sort the list by last_request_date in descending order
    recent_active_users = sorted(recent_active_users, key=lambda x: x[1], reverse=True)

    # Extract only user_id from the sorted list
    recent_active_users = [user_id for user_id, _ in recent_active_users]

    return recent_active_users


# Function to get top users by specified parameter from data.json (requests, tokens, balance, etc.)
def get_top_users_by_data_parameter(max_users: int, parameter: str) -> list:
    top_users = [(user_id, user_data[parameter]) for user_id, user_data in data.items() if user_id != "global" and user_data.get(parameter, 0) > 0]
    top_users = sorted(top_users, key=lambda x: x[1], reverse=True)
    top_users = top_users[:max_users]

    return top_users


# Function to get top users by invited referrals
def get_top_users_by_referrals(max_users: int) -> list:
    top_users = [(user_id, len(get_user_referrals(user_id))) for user_id in list(data.keys())[1:]]
    top_users = [user for user in top_users if user[1] > 0]
    top_users = sorted(top_users, key=lambda x: x[1], reverse=True)
    top_users = top_users[:max_users]

    return top_users


# Function to get top users by cost of their requests
def get_top_users_by_cost(max_users: int) -> list:
    top_users = [(user_id, calculate_cost(data[user_id]['tokens'], data[user_id].get('premium_tokens', 0), data[user_id].get('images', 0))) for user_id in list(data.keys())[1:]]
    top_users = [(user[0], round(user[1], 3)) for user in top_users if user[1] > 0]
    top_users = sorted(top_users, key=lambda x: x[1], reverse=True)
    top_users = top_users[:max_users]

    return top_users


# Function to get user current model
def get_user_active_model(user_id: int) -> str:
    if data[user_id].get("lang_model") is None:
        return DEFAULT_MODEL
    else:
        model = str(data[user_id]["lang_model"])
        if model == "premium":
            return PREMIUM_MODEL
        else:
            return DEFAULT_MODEL


# Function to calculate the cost of the user requests (default + premium) in cents
def calculate_cost(tokens: int, premium_tokens: int = 0, images: int = 0) -> float:
    tokens_cost = tokens * PRICE_CENTS
    premium_tokens_cost = premium_tokens * PREMIUM_PRICE_CENTS
    images_cost = images * IMAGE_PRICE_CENTS
    total_cost = tokens_cost + premium_tokens_cost + images_cost
    return total_cost


def format_cents_to_price_string(price: float) -> str:
    """
    This function formats the price in cents to a string with the dollar or cent sign.

    :param price: The price in cents
    :type price: float

    :return: The formatted price string
    :rtype: str
    """
    if price < 100:
        return f"{round(price, 2)}¢"
    else:
        return f"${round(price / 100, 2)}"


# Function to encode the image
def encode_image_b64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


# Получает на вход новые данные по пользователю по произведенным запросам, потраченным токенам, премиум токенам и изображениям и добавляет их в базу
# Если deduct_tokens = False, то токены не будут списаны с баланса (например, при запросах администратора)
# Вызывать, только если у пользователя положительный баланс используемых токенов!
def update_global_user_data(user_id: int, new_requests: int = 1, new_tokens: int = None, new_premium_tokens: int = None, new_images: int = None, deduct_tokens: bool = True) -> None:

    global data, session_request_counter, session_tokens, premium_session_tokens, session_images  # Глобальные счетчики текущей сессии

    data[user_id]["requests"] += new_requests
    data["global"]["requests"] += new_requests
    session_request_counter += new_requests

    data[user_id]["lastdate"] = (datetime.now() + timedelta(hours=UTC_HOURS_DELTA)).strftime(DATE_FORMAT)

    if new_tokens:
        data[user_id]["tokens"] += new_tokens
        data["global"]["tokens"] += new_tokens
        session_tokens += new_tokens

        if deduct_tokens:
            data[user_id]["balance"] -= new_tokens

    if new_premium_tokens:
        data[user_id]["premium_tokens"] = data[user_id].get("premium_tokens", 0) + new_premium_tokens
        data["global"]["premium_tokens"] = data["global"].get("premium_tokens", 0) + new_premium_tokens
        premium_session_tokens += new_premium_tokens

        if deduct_tokens:
            data[user_id]["premium_balance"] -= new_premium_tokens

    if new_images:
        data[user_id]["images"] = data[user_id].get("images", 0) + new_images
        data["global"]["images"] = data["global"].get("images", 0) + new_images
        session_images += new_images

        if deduct_tokens:
            data[user_id]["image_balance"] -= new_images

    update_json_file(data)


def send_smart_split_message(bot_instance: telebot.TeleBot, chat_id: int, text: str, max_length: int = 4096, parse_mode: str = None, reply_to_message_id: int = None) -> None:
    """
    This function sends a message to a specified chat ID, splitting the message into chunks if it exceeds the maximum length.

    :param bot_instance: The Telebot instance to use for sending the message
    :type bot_instance: telebot.TeleBot

    :param chat_id: The chat ID to send the message to
    :type chat_id: int

    :param text: The text of the message
    :type text: str

    :param max_length: The maximum length of each message chunk
    :type max_length: int

    :param parse_mode: The parse mode of the message (e.g., "MARKDOWN" or "HTML")
    :type parse_mode: str

    :param reply_to_message_id: The message ID to reply to
    :type reply_to_message_id: int

    :return: None
    """
    reply_parameters = None if reply_to_message_id is None else types.ReplyParameters(reply_to_message_id, allow_sending_without_reply=True)

    if len(text) < max_length:
        bot_instance.send_message(chat_id, text, parse_mode=parse_mode, reply_parameters=reply_parameters)
        return

    chunks = telebot.util.smart_split(text, max_length)

    for chunk in chunks:
        bot_instance.send_message(chat_id, chunk, parse_mode=parse_mode, reply_parameters=reply_parameters)
        time.sleep(0.1)  # Introduce a small delay between each message to avoid hitting Telegram's rate limits


def create_request_report(user: telebot.types.User, chat: telebot.types.Chat, request_tokens: int, request_price: float) -> str:
    """
    This function creates a report for the user's request.
    Use `parse_mode="HTML"` to send telegram messages with this content.

    :param user: The user who made the request
    :type user: telebot.types.User

    :param chat: The chat where the request was made
    :type chat: telebot.types.Chat

    :param request_tokens: The number of tokens used for the request
    :type request_tokens: int

    :param request_price: The price of the request in cents
    :type request_price: float

    :return: The report for the user's request
    :rtype: str
    """

    request_info = f"Запрос {session_request_counter}: {request_tokens} за {format_cents_to_price_string(request_price)}\n"

    session_cost_cents = calculate_cost(session_tokens, premium_session_tokens, session_images)
    session_info = f"Сессия: {session_tokens + premium_session_tokens} за {format_cents_to_price_string(session_cost_cents)}\n"

    username = f"@{user.username} " if user.username is not None else ""
    user_info = f"Юзер: {telebot.util.escape(user.full_name)} {username}<code>{user.id}</code>\n"

    balance_info = f"Баланс: {data[user.id]['balance']}; {data[user.id].get('premium_balance', '')}\n"
    chat_info = f"Чат: {telebot.util.escape(chat.title)} {chat.id}\n" if chat.id < 0 else ""  # Если сообщение было в групповом чате, то указать данные о нём

    global_cost_cents = calculate_cost(data['global']['tokens'], data['global'].get('premium_tokens', 0), data['global'].get('images', 0))
    global_info = f"{data['global']} за {format_cents_to_price_string(global_cost_cents)}"

    report = f"{request_info}{session_info}{user_info}{balance_info}{chat_info}{global_info}"
    return report


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
    data = {"global": {"requests": 0, "tokens": 0, "images": 0},
            ADMIN_ID: {"requests": 0, "tokens": 0, "balance": 777777, "premium_balance": 77777, "image_balance": 777,
                       "name": "АДМИН", "username": "@admin", "lastdate": "01-05-2023 00:00:00"}}
    # Create the file with default values
    update_json_file(data)


# Calculate the price per token in cents
PRICE_CENTS = PRICE_1K / 10
PREMIUM_PRICE_CENTS = PREMIUM_PRICE_1K / 10
IMAGE_PRICE_CENTS = IMAGE_PRICE * 100

# Session token and request counters
session_request_counter, session_tokens, premium_session_tokens, session_images = 0, 0, 0, 0


"""====================ADMIN_COMMANDS===================="""


# Define the handler for the admin /data command
@bot.message_handler(commands=["d", "data"])
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
        target_user_id = get_user_id_by_username(target_user_string)
        if target_user_id is None:
            bot.send_message(ADMIN_ID, not_found_string, parse_mode="MARKDOWN")
            return

    elif target_user_string.isdigit():  # Поиск по id пользователя
        target_user_id = int(target_user_string)
        if not is_user_exists(target_user_id):
            bot.send_message(ADMIN_ID, not_found_string, parse_mode="MARKDOWN")
            return

    else:  # Если аргументы были введены неверно, то просим исправиться
        bot.send_message(ADMIN_ID, not_found_string, parse_mode="MARKDOWN")
        return

    if data[target_user_id].get("premium_balance") is not None:
        premium_string = (f"premium tokens: {data[target_user_id].get('premium_tokens', 0)}\n"
                          f"premium balance: {data[target_user_id]['premium_balance']}\n\n")
    else:
        premium_string = ""

    if "image_balance" in data[target_user_id]:
        images_string = (f"images: {data[target_user_id].get('images', 0)}\n"
                         f"image balance: {data[target_user_id]['image_balance']}\n\n")
    else:
        images_string = ""

    # Если юзер был успешно найден, то формируем здесь сообщение с его статой
    user_data_string = f"id {target_user_id}\n" \
                       f"{data[target_user_id]['name']} " \
                       f"{data[target_user_id]['username']}\n\n" \
                       f"requests: {data[target_user_id]['requests']}\n" \
                       f"tokens: {data[target_user_id]['tokens']}\n" \
                       f"balance: {data[target_user_id]['balance']}\n\n" \
                       f"{premium_string}" \
                       f"{images_string}" \
                       f"last request: {data[target_user_id]['lastdate']}\n"

    # Calculate user cost in cents and round it to 3 digits after the decimal point
    user_cost_cents = calculate_cost(data[target_user_id]['tokens'], data[target_user_id].get('premium_tokens', 0), data[target_user_id].get('images', 0))
    user_data_string += f"user cost: ¢{round(user_cost_cents, 3)}\n\n"

    # Если есть инфа о количестве исполненных просьб на пополнение, то выдать ее
    if "favors" in data[target_user_id]:
        user_data_string += f"favors: {data[target_user_id]['favors']}\n\n"

    # Если у пользователя есть промпт, то выдать его
    if "prompt" in data[target_user_id]:
        user_data_string += f"prompt: {data[target_user_id].get('prompt')}\n\n"

    # Если пользователя пригласили по рефке, то выдать информацию о пригласившем
    if "ref_id" in data[target_user_id]:
        referrer = data[target_user_id]["ref_id"]
        user_data_string += f"invited by: {data[referrer]['name']} {data[referrer]['username']} {referrer}\n\n"

    user_referrals_list: list = get_user_referrals(target_user_id)
    if not user_referrals_list:  # Если рефералов нет, то просто отправляем текущие данные по пользователю
        bot.send_message(ADMIN_ID, user_data_string)
        return

    user_data_string += f"{len(user_referrals_list)} invited users:\n"
    for ref in user_referrals_list:
        user_data_string += f"{data[ref]['name']} {data[ref]['username']} {ref}: {data[ref]['requests']}\n"

    bot.send_message(ADMIN_ID, user_data_string)


# Define the handler for the admin /recent_users command to get recent active users in past n days
@bot.message_handler(commands=["recent", "recent_users", "last"])
def handle_recent_users_command(message):
    user = message.from_user
    wrong_input_string = "Укажите целое число дней после команды /recent_users"

    if user.id != ADMIN_ID or message.chat.type != "private":
        return

    # Получаем аргументы команды
    num_of_days = extract_arguments(message.text)

    if num_of_days == "":
        bot.reply_to(message, wrong_input_string)
        return
    elif not num_of_days.isdigit():
        bot.reply_to(message, wrong_input_string)
        return

    num_of_days = int(num_of_days)
    if num_of_days < 1:
        bot.reply_to(message, wrong_input_string)
        return

    recent_active_users: list = get_recent_active_users(num_of_days)
    if not recent_active_users:
        bot.reply_to(message, f"За последние {num_of_days} дней активных пользователей не найдено")
        return

    answer = f"Активные юзеры за последние {num_of_days} дней: {len(recent_active_users)}\n\n"
    for user_id in recent_active_users:
        answer += f"{data[user_id]['name']} {data[user_id]['username']} {user_id}: {data[user_id]['requests']}\n"

    send_smart_split_message(bot, ADMIN_ID, answer, reply_to_message_id=message.message_id)


# Define the handler for the admin /top_users command. we get 2 arguments: number of users and parameter
@bot.message_handler(commands=["top", "top_users"])
def handle_top_users_command(message):
    user = message.from_user
    wrong_input_string = "Укажите целое число пользователей и искомый параметр после команды\n\nПример: `/top 10 requests`"

    if user.id != ADMIN_ID or message.chat.type != "private":
        return

    try:
        max_users, parameter = extract_arguments(message.text).split()
        max_users = int(max_users)
    except (ValueError, IndexError):
        bot.reply_to(message, wrong_input_string, parse_mode="MARKDOWN")
        return

    if max_users < 1:
        bot.reply_to(message, wrong_input_string)
        return

    if parameter in ["requests", "tokens", "balance", "premium_tokens", "premium_balance", "images", "image_balance", "favors", "ref_id"]:
        top_users: list = get_top_users_by_data_parameter(max_users, parameter)
    elif parameter in ["ref", "refs", "referrals", "invites"]:
        top_users: list = get_top_users_by_referrals(max_users)
    elif parameter in ["cost", "price"]:
        top_users: list = get_top_users_by_cost(max_users)
        top_users = [(user[0], f"¢{user[1]}") for user in top_users]
    else:
        bot.reply_to(message, f"Неверный параметр: *{parameter}*\n\n"
                              "Доступные параметры: \n- `requests` \n- `tokens` \n- `balance` \n- `premium_tokens` "
                              "\n- `premium_balance` \n- `images` \n- `image_balance` \n- `favors` \n- `refs` \n- `cost`", parse_mode="MARKDOWN")
        return

    if not top_users:
        bot.reply_to(message, f"Топ пользователей по параметру *{parameter}* не найдено", parse_mode="MARKDOWN")
        return

    user_place = 1
    answer = f"Топ {max_users} пользователей by {parameter}:\n\n"
    for user_id, parameter_value in top_users:
        answer += (f"{user_place}. {data[user_id]['name']} {data[user_id]['username'] if data[user_id]['username'] != 'None' else ''} "
                   f"{user_id}: {parameter_value}\n")
        user_place += 1

    bot.reply_to(message, answer)


# Define the handler for the admin /refill command
@bot.message_handler(commands=["r", "refill"])
def handle_refill_command(message):
    wrong_input_string = ("Укажите @username/id пользователя и сумму пополнения после команды.\n\n"
                          "Допишите `premium` последним аргументом, чтобы пополнить баланс премиум токенов. "
                          "Или `image`, чтобы пополнить баланс для генерации изображений.\n\n"
                          "Пример: `/refill @username 1000`")

    # Проверки на доступность команды
    if message.from_user.id != ADMIN_ID:  # Если пользователь не админ
        bot.reply_to(message, "Команда доступна только админу")
        return
    elif message.chat.type != "private":  # Если команда вызвана не в личке с ботом
        bot.reply_to(message, "Эта команда недоступна в групповых чатах")
        return

    try:
        args = extract_arguments(message.text).split()
        amount = int(args[1])
    except ValueError:
        bot.send_message(ADMIN_ID, wrong_input_string, parse_mode="MARKDOWN")
        return
    except IndexError:
        bot.send_message(ADMIN_ID, wrong_input_string, parse_mode="MARKDOWN")
        return

    target_user = args[0]

    not_found_string = f"Пользователь {target_user} не найден"
    success_string = f"Баланс пользователя {target_user} успешно пополнен на {amount} токенов."

    # Определяем тип баланса для пополнения в зависимости от третьего аргумента (обычный, премиум или генерации изображений)
    balance_type = args[2] if len(args) > 2 else None
    if balance_type is None:
        balance_type = "balance"
        prefix = ""  # префикс для сообщений
    elif balance_type in ["premium", "prem", "p"]:
        balance_type = "premium_balance"
        success_string = "ПРЕМИУМ " + success_string
        prefix = "премиум "
    elif balance_type in ["images", "image", "img", "i"]:
        balance_type = "image_balance"
        success_string = "IMAGE " + success_string
        prefix = "image "
    else:
        bot.send_message(ADMIN_ID, wrong_input_string, parse_mode="MARKDOWN")
        return

    # Находим айди юзера, если он есть в базе, иначе выходим
    if target_user[0] == '@':  # Поиск по @username
        target_user_id = get_user_id_by_username(target_user)

        if target_user_id is None:
            bot.send_message(ADMIN_ID, not_found_string)
            return
    elif target_user.isdigit():  # Поиск по id пользователя
        target_user_id = int(target_user)

        if not is_user_exists(target_user_id):
            bot.send_message(ADMIN_ID, not_found_string)
            return
    else:
        bot.send_message(ADMIN_ID, wrong_input_string, parse_mode="MARKDOWN")
        return

    # Сначала проверяем, есть ли такой тип баланса у юзера (если нет, то создаем), а потом уже пополняем
    if data[target_user_id].get(balance_type) is None:
        data[target_user_id][balance_type] = 0

    data[target_user_id][balance_type] += amount

    update_json_file(data)
    bot.send_message(ADMIN_ID, success_string + f"\nТекущий {prefix}баланс: {data[target_user_id][balance_type]}")
    try:
        if amount > 0:
            bot.send_message(target_user_id, f"Ваш баланс пополнен на {amount} {prefix}токенов!\n"
                                             f"Текущий {prefix}баланс: {data[target_user_id][balance_type]}")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"Ошибка при уведомлении юзера {target_user}, походу он заблочил бота 🤬")
        print(e)


# Define the handler for the admin /block command
@bot.message_handler(commands=["ban", "block"])
def handle_block_command(message):
    target_user = extract_arguments(message.text)
    wrong_input_string = "Укажите @username/id пользователя после команды\n\n" \
                         "Пример: `/block @username`"

    # Проверки на доступность команды
    if message.from_user.id != ADMIN_ID:
        return
    elif message.chat.type != "private":
        bot.reply_to(message, "Эта команда недоступна в групповых чатах")
        return

    if target_user == '':
        bot.send_message(ADMIN_ID, wrong_input_string, parse_mode="MARKDOWN")
        return

    not_found_string = f"Пользователь {target_user} не найден"
    success_string = f"Пользователь {target_user} успешно заблокирован"

    # Находим айди юзера, если он есть в базе, иначе выходим
    if target_user[0] == '@':
        target_user = get_user_id_by_username(target_user)
        if target_user is None:
            bot.send_message(ADMIN_ID, not_found_string)
            return
    elif target_user.isdigit():
        target_user = int(target_user)
        if not is_user_exists(target_user):
            bot.send_message(ADMIN_ID, not_found_string)
            return
    else:
        bot.send_message(ADMIN_ID, wrong_input_string, parse_mode="MARKDOWN")
        return

    data[target_user]["blacklist"] = True
    update_json_file(data)
    bot.send_message(ADMIN_ID, success_string)
    print(success_string)


# Define the handler for the /stop command
@bot.message_handler(commands=["stop"])
def handle_stop_command(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "Stopping the script...")
        bot.stop_polling()


# Define the handler for the /announce command
# Эта команда принимает сообщение от админа и рассылает его между пользователями бота (типа уведомления)
@bot.message_handler(commands=["a", "announce", "alert", "broadcast", "notify"])
def handle_announce_command(message):
    user = message.from_user

    if user.id != ADMIN_ID or message.chat.type != "private":
        return

    # Получаем аргументы команды (текст после /announce)
    user_filter = extract_arguments(message.text)

    if user_filter == "":
        bot.reply_to(message, "Введите тип рассылки после команды /announce\n\n"
                              "Варианты:\n"
                              "all - рассылка всем пользователям\n"
                              "req1 - расылка всем пользователям, кто сделал хотя бы 1 запрос (любое значение)\n"
                              "bal1000 - рассылка всем пользователям с балансом от 1000 токенов (любое значение)\n"
                              "test - рассылка только админу (тест команды)\n\n"
                              "Так же можно уведомить только одного пользователя, написав его user_id или @username")
        return

    bot.reply_to(message, "Введите текст сообщения для рассылки.\nq - отмена")
    bot.register_next_step_handler(message, process_announcement_message_step, user_filter)


def process_announcement_message_step(message, user_filter):
    user = message.from_user

    if user.id != ADMIN_ID or message.chat.type != "private":
        return

    announcement_text = message.html_text
    recepients_list = []

    if announcement_text == "q":
        bot.send_message(user.id, "Рассылка отменена")
        return

    if user_filter == "test":
        recepients_list.append(ADMIN_ID)
        confirmation_text = f"Получатели: тестовый режим, только админ\n\n" \
                            "Отправить данное сообщение? (y/n)\n"

    elif user_filter == "all":
        recepients_list = list(data.keys())[1:]
        confirmation_text = f"Получатели: все пользователи ({len(recepients_list)})\n\n" \
                            "Разослать данное сообщение? (y/n)\n"

    elif user_filter.startswith("req"):
        user_filter = user_filter[3:]
        if not user_filter.isdigit():
            bot.send_message(user.id, "Неверный тип рассылки!\nЖми /announce для справки")
            return

        user_filter = int(user_filter)
        for user_id in list(data.keys())[1:]:
            if data[user_id]["requests"] >= user_filter:
                recepients_list.append(user_id)
        confirmation_text = f"Получатели: юзеры от {user_filter} запросов ({len(recepients_list)})\n\n" \
                            "Разослать данное сообщение? (y/n)\n"

    elif user_filter.startswith("bal"):
        user_filter = user_filter[3:]
        if not user_filter.isdigit():
            bot.send_message(user.id, "Неверный тип рассылки!\nЖми /announce для справки")
            return

        user_filter = int(user_filter)
        for user_id in list(data.keys())[1:]:
            if data[user_id]["balance"] >= user_filter:
                recepients_list.append(user_id)
        confirmation_text = f"Получатели: юзеры с балансом от {user_filter} токенов ({len(recepients_list)})\n\n" \
                            "Разослать данное сообщение? (y/n)\n"

    # Для групповых чатов (id с минусом)
    elif user_filter[0] == "-" and user_filter[1:].isdigit():
        user_filter = int(user_filter)
        recepients_list.append(user_filter)
        confirmation_text = f"Получатели: чат {user_filter}\n\n" \
                            "Отправить данное сообщение? (y/n)\n"

    elif user_filter.isdigit():
        user_filter = int(user_filter)
        if not is_user_exists(user_filter):
            bot.send_message(user.id, f"Пользователь не найден!")
            return

        recepients_list.append(user_filter)
        confirmation_text = f"Получатель: {data[user_filter]['name']} {data[user_filter]['username']} {user_filter}\n\n" \
                            "Разослать данное сообщение? (y/n)\n"

    elif user_filter[0] == "@":
        user_filter = get_user_id_by_username(user_filter)
        if user_filter is None:
            bot.send_message(user.id, "Пользователь не найден!")
            return

        recepients_list.append(user_filter)
        confirmation_text = f"Получатель: {data[user_filter]['name']} {data[user_filter]['username']} {user_filter}\n\n" \
                            "Отправить данное сообщение? (y/n)\n"

    else:
        bot.send_message(user.id, "Неверный тип рассылки!\nЖми /announce для справки")
        return

    announcement_msg = bot.send_message(user.id, announcement_text, parse_mode="HTML")
    time.sleep(0.5)
    bot.reply_to(announcement_msg, confirmation_text)
    bot.register_next_step_handler(announcement_msg, process_announcement_confirmation_step,
                                   recepients_list, announcement_text)


def process_announcement_confirmation_step(message, recepients_list, announcement_text):
    user = message.from_user

    if user.id != ADMIN_ID or message.chat.type != "private":
        return

    if message.text == "y":
        bot.send_message(user.id, "Рассылка запущена")
        print("Рассылка запущена")
    else:
        bot.send_message(user.id, "Рассылка отменена")
        return

    # Если в получателях только один групповой чат
    if len(recepients_list) == 1 and recepients_list[0] < 0:
        try:
            bot.send_message(recepients_list[0], announcement_text, parse_mode="HTML")
            admin_log = f"✉️ Сообщение отправлено в чат {recepients_list[0]}"
        except Exception as e:
            admin_log = f"❌ Ошибка: чат {recepients_list[0]} не найден"
        bot.send_message(ADMIN_ID, admin_log)
        print(admin_log)
        return

    msg_counter = 0
    admin_log = ""
    for user_id in recepients_list:
        try:
            bot.send_message(user_id, announcement_text, parse_mode="HTML")
            msg_counter += 1
            admin_log += f"✉️ {data[user_id]['name']} {data[user_id]['username']} {user_id}" + "\n"
            time.sleep(0.5)
        except Exception as e:
            # print(e)
            admin_log += f"❌ {data[user_id]['name']} {data[user_id]['username']} {user_id}" + "\n"

    admin_log = f"Рассылка завершена!\nОтправлено {msg_counter} из {len(recepients_list)} сообщений." + "\n\nПолучатели:\n" + admin_log

    send_smart_split_message(bot, ADMIN_ID, admin_log)

    print("Рассылка успешно завершена, логи отправлены админу")


"""====================USER_COMMANDS====================="""


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
                  "/invite или /ref - пригласить друга и получить бонус 🎁\n\n" \
                  "/imagine или /img - генерация изображений 🎨\n" \
                  "/balance - баланс токенов\n/stats - статистика запросов\n" \
                  "/ask_favor - запросить эирдроп токенов 🙏\n\n" \
                  "/switch_model или /sw - переключить языковую модель\n" \
                  "/pro или /gpt4 - сделать быстрый премиальный запрос без переключения активной языковой модели\n\n" \
                  "/prompt или /p - установить свой системный промпт\n" \
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

    if not is_user_exists(user_id):
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start")
        return

    # Если юзер есть в базе, то выдаем его баланс
    balance = data[user_id]["balance"]
    prem_balance = data[user_id].get("premium_balance", 0)  # Если поля "premium_balance" нет в БД, то выводим 0
    image_balance = data[user_id].get("image_balance", 0)

    balance_string = (f"Токены: {balance}\n"
                      f"Премиум токены: {prem_balance}\n"
                      f"Генерации изображений: {image_balance}\n\n"
                      f"Используйте команду /switch_model, чтобы переключать используемую языковую модель для запросов. "
                      f"Для генерации изображений используйте команду /imagine\n")

    bot.reply_to(message, balance_string)


# Define the handler for the /topup command
@bot.message_handler(commands=["topup"])
def handle_topup_command(message):
    user_id = message.from_user.id

    if is_user_blacklisted(user_id):
        return

    if is_user_exists(user_id):
        bot.reply_to(message, f"Для пополнения баланса обратитесь к админу")  # Placeholder
    else:
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start")


# Define the handler for the /stats command
@bot.message_handler(commands=["stats", "profile"])
def handle_stats_command(message):
    user_id = message.from_user.id

    if is_user_blacklisted(user_id):
        return

    if not is_user_exists(user_id):
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start")

    user_data = data[user_id]
    user_data_string = (f"Запросов: {user_data['requests']}\n"
                        f"Токенов использовано: {user_data['tokens']}\n"
                        f"Премиум токенов использовано: {user_data.get('premium_tokens', 0)}\n"
                        f"Изображений сгенерировано: {user_data.get('images', 0)}\n\n")

    user_referrals_list: list = get_user_referrals(user_id)
    if user_referrals_list:
        user_data_string += f"Вы пригласили {len(user_referrals_list)} пользователей:\n"
        for ref in user_referrals_list:
            user_data_string += f"{data[ref]['name']} {data[ref]['username']}\n"

    # Если пользователя пригласили по рефке, то выдать информацию о пригласившем
    if "ref_id" in user_data:
        referrer = user_data["ref_id"]
        user_data_string += f"\nВас пригласил: {data[referrer]['name']} {data[referrer]['username']}\n\n"

    bot.reply_to(message, user_data_string)


# Define the handler for the /prompt command
@bot.message_handler(commands=["p", "prompt"])
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


# Define the handler for the /switch_model command to change language model
@bot.message_handler(commands=["sw", "switch", "switch_model", "model"])
def handle_switch_model_command(message):
    user_id = message.from_user.id

    if is_user_blacklisted(user_id):
        return

    if not is_user_exists(user_id):
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start")
        return

    user_model = get_user_active_model(user_id)

    # Определяем целевую языковую модель в зависимости от текущей
    if user_model == DEFAULT_MODEL:
        target_model_type = "premium"
        target_model = PREMIUM_MODEL
        postfix = "(ПРЕМИУМ)\n\nВнимание! Генерация ответа с данной моделью может занимать до двух минут!"
    elif user_model == PREMIUM_MODEL:
        target_model_type = "default"
        target_model = DEFAULT_MODEL
        postfix = "(обычная)"
    else:  # Условие недостижимо, но на всякий случай
        bot.reply_to(message, f"Ошибка при смене модели, перешлите это сообщение админу (+компенсация 50к токенов)\n"
                              f"user_id: {user_id}\nМодель юзера: {user_model}")
        return

    data[user_id]["lang_model"] = target_model_type
    update_json_file(data)

    bot.reply_to(message, f"Языковая модель успешно изменена!\n\n*Текущая модель*: {target_model} {postfix}", parse_mode="Markdown")
    print(f"Модель пользователя {user_id} изменена на {target_model_type}")


# Handler for the /ask_favor command
@bot.message_handler(commands=["ask_favor", "askfavor", "favor"])
def handle_ask_favor_command(message):
    user = message.from_user

    if is_user_blacklisted(user.id):
        return

    if not is_user_exists(user.id):
        return

    if user.id == ADMIN_ID:
        bot.reply_to(message, f"У тебя уже анлимитед саплай токенов, бро")
        return
    elif data[user.id]["balance"] > FAVOR_MIN_LIMIT:
        bot.reply_to(message, f"Не надо жадничать, бро!\nПриходи, когда у тебя будет меньше {FAVOR_MIN_LIMIT} токенов.")
        return
    elif data[user.id].get("active_favor_request"):
        bot.reply_to(message, f"У тебя уже есть активный запрос, бро")
        return
    else:
        bot.reply_to(message, "Ваша заявка отправлена на рассмотрение администратору 🙏\n")
        data[user.id]["active_favor_request"] = True
        update_json_file(data)

        admin_invoice_string = f"Пользователь {user.full_name} @{user.username} {user.id} просит подачку!\n\n" \
                               f"requests: {data[user.id]['requests']}\n" \
                               f"tokens: {data[user.id]['tokens']}\n" \
                               f"balance: {data[user.id]['balance']}\n\n" \
                               f"Оформляем?"

        # add two buttons to the message
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text='Да', callback_data='favor_yes$' + str(user.id)),
                   types.InlineKeyboardButton(text='Нет', callback_data='favor_no$' + str(user.id)))

        admin_message = bot.send_message(ADMIN_ID, admin_invoice_string, reply_markup=markup)
        bot.pin_chat_message(ADMIN_ID, admin_message.message_id, disable_notification=True)


# Favor callback data handler
@bot.callback_query_handler(func=lambda call: True)
def handle_favor_callback(call):
    call_data_list: list = call.data.split("$")

    if call.from_user.id != ADMIN_ID:
        return
    elif len(call_data_list) != 2:
        bot.answer_callback_query(call.id, "Должно быть два аргумента!\n\ncallback_data: " + call.data, True)
        return
    elif not call_data_list[1].isdigit():
        bot.answer_callback_query(call.id, "Второй аргумент должен быть числом!\n\ncallback_data: " + call.data, True)
        return

    call_data_list[1] = int(call_data_list[1])
    user = data[call_data_list[1]]

    if call_data_list[0] == 'favor_yes':
        bot.answer_callback_query(call.id, "Заявка принята")
        bot.unpin_chat_message(ADMIN_ID, call.message.message_id)

        if "favors" in user:
            user["favors"] += 1
        else:
            user["favors"] = 1

        user["balance"] += FAVOR_AMOUNT

        if user.get("active_favor_request"):
            del user["active_favor_request"]
        update_json_file(data)

        bot.send_message(call_data_list[1], f"Ваши мольбы были услышаны! 🙏\n\n"
                                            f"Вам начислено {FAVOR_AMOUNT} токенов!\n"
                                            f"Текущий баланс: {data[int(call_data_list[1])]['balance']}")

        edited_admin_message = f"Заявка от {user['name']} {user['username']} {call_data_list[1]}\n\n" \
                               f"requests: {user['requests']}\n" \
                               f"tokens: {user['tokens']}\n" \
                               f"balance: {user['balance']}\n\n" \
                               f"✅ Оформлено! ✅"
        bot.edit_message_text(chat_id=ADMIN_ID, message_id=call.message.message_id, text=edited_admin_message)

    elif call_data_list[0] == 'favor_no':
        bot.answer_callback_query(call.id, "Заявка отклонена")
        bot.unpin_chat_message(ADMIN_ID, call.message.message_id)

        if user.get("active_favor_request"):
            del user["active_favor_request"]
        update_json_file(data)

        bot.send_message(call_data_list[1], "Вам было отказано в просьбе, попробуйте позже!")

        edited_admin_message = f"Заявка от {user['name']} {user['username']} {call_data_list[1]}\n\n" \
                               f"requests: {user['requests']}\n" \
                               f"tokens: {user['tokens']}\n" \
                               f"balance: {user['balance']}\n\n" \
                               f"❌ Отклонено! ❌"
        bot.edit_message_text(chat_id=ADMIN_ID, message_id=call.message.message_id, text=edited_admin_message)

    else:
        bot.answer_callback_query(call.id, "Что-то пошло не так...\n\ncallback_data: " + call.data, True)


# Define the handler for the /imagine command to generate AI image from text via OpenAi
@bot.message_handler(commands=["i", "img", "image", "imagine"])
def handle_imagine_command(message):
    global session_images, data
    user = message.from_user

    if not is_user_exists(user.id):
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start\n\n"
                              "Подсказка: за регистрацию по рефке вы получите на 50% больше токенов!")
        return
    else:
        if is_user_blacklisted(user.id):
            return

    # Check for user IMAGE balance
    if data[user.id].get("image_balance") is None or data[user.id]["image_balance"] <= 0:
        bot.reply_to(message, 'У вас закончились токены для генерации изображений, пополните баланс!')
        return

    image_prompt = extract_arguments(message.text)
    if image_prompt == "":
        bot.reply_to(message, "Введите текст для генерации изображения моделью *DALL-E 3* после команды /imagine или /img\n\n"
                              "Пример: `/img НЛО похищает Эйфелеву башню`", parse_mode="Markdown")
        return

    wait_message = bot.reply_to(message, f"Генерирую изображение, подождите немного...")

    log_message = f"\nUser {user.id} {user.full_name} has requested image generation"
    print(log_message)

    # Симулируем эффект отправки изображения, пока бот получает ответ
    bot.send_chat_action(message.chat.id, "upload_photo")

    try:
        response = generate_image(image_prompt)
    except openai.BadRequestError as e:
        # print(e.http_status)
        error_text = ("Произошла ошибка при генерации изображения 😵\n\n"
                      f"Промпт: {image_prompt}\n\n")

        if message.chat.id != ADMIN_ID:
            bot.send_message(message.chat.id, error_text + str(e.body['message']))
        bot.send_message(ADMIN_ID, error_text + str(json.dumps(e.body, indent=2)))
        print(e)
        bot.delete_message(wait_message.chat.id, wait_message.message_id)
        return
    except Exception as e:
        if message.chat.id != ADMIN_ID:
            bot.send_message(message.chat.id, "Произошла ошибка при генерации изображения 😵")
        bot.send_message(ADMIN_ID, "Произошла ошибка при генерации изображения 😵\n\n" + str(e))
        return

    image_url = response.data[0].url
    # revised_prompt = '<span class="tg-spoiler">' + response.data[0].revised_prompt + '</span>'

    try:
        bot.send_photo(message.chat.id, image_url)
    except telebot.apihelper.ApiTelegramException as e:
        error_text = "Произошла ошибка при отправке сгенерированного изображения 😵\n\n"

        if message.chat.id != ADMIN_ID:
            bot.send_message(message.chat.id, error_text)
        bot.send_message(ADMIN_ID, error_text + str(e) + f"\n\n{user.id}\n{image_url}")
        print(error_text + str(e))
        return

    # Удалияем сообщение о генерации изображения
    try:
        bot.delete_message(wait_message.chat.id, wait_message.message_id)
    except telebot.apihelper.ApiTelegramException as e:
        pass

    update_global_user_data(
        user.id,
        new_images=1,
        deduct_tokens=True if user.id != ADMIN_ID else False
    )

    print("Image was generated and sent to user")

    # Кидаем картинку с промптом админу в личку, чтобы он тоже окультуривался (но в обезличенном виде)
    if user.id != ADMIN_ID:
        bot.send_photo(ADMIN_ID, image_url, caption=f"{image_prompt}\n\n")


# Define the handler for the /vision command to use `gpt-4-vision-preview` model for incoming images
# @bot.message_handler(func=lambda message: any(command in (message.text or '') or command in (message.caption or '') for command in ["vision", "v", "see"]), content_types=["photo", "text"])
@bot.message_handler(func=lambda message: message.caption is not None, content_types=["photo"])
def handle_vision_command(message: types.Message):
    user = message.from_user
    image_path = "image_for_vision_" + str(user.id) + ".jpg"

    # Если пользователя нет в базе, то перенаправляем его на команду /start и выходим
    if not is_user_exists(user.id):
        if is_user_blacklisted(user.id):
            return
        else:
            bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start\n\n"
                                  "Подсказка: за регистрацию по рефке вы получите на 50% больше токенов!")
        return

    # TODO: или получать аргументы из message.text, если кэпшона к фотке нет (а значит и самой фотки нет, мб она в отвечаемом сообщении)
    user_request = message.caption

    if data[user.id].get("premium_balance") is None or data[user.id]["premium_balance"] <= 0:
        bot.reply_to(message, 'У вас закончились премиальные токены, пополните баланс!', parse_mode="HTML")
        return
    current_price_cents = PREMIUM_PRICE_CENTS
    admin_log = "ВИЖН "

    # if user_request == "":
    #     bot.reply_to(message, "Введите текст после команды /vision или /v для обращения к *GPT-4 Vision*\n\n"
    #                           "Пример: `/v что изображено на картинке?`", parse_mode="Markdown")
    #     return

    # Get the photo
    photo = message.photo[-1]  # get the highest resolution photo

    # Get the file ID
    file_id = photo.file_id

    # Download the photo
    file_info = bot.get_file(file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    # Now `downloaded_file` contains the photo file
    with open(image_path, 'wb') as new_file:
        new_file.write(downloaded_file)
        # print("Картинка получена!")

    # Симулируем эффект набора текста, пока бот получает ответ
    bot.send_chat_action(message.chat.id, "typing")

    # Getting the base64 string
    base64_image = encode_image_b64(image_path)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {client.api_key}"
    }

    payload = {
        "model": "gpt-4-vision-preview",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_request
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 1000
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    response = response.json()
    # print(response.status_code)  # 200
    # print(response.json())

    # Vision requests still use old api response format
    request_tokens = response["usage"]["total_tokens"]
    # print(f"Запрос на {request_tokens} токенов")

    # delete image file
    os.remove(image_path)

    update_global_user_data(
        user.id,
        new_premium_tokens=request_tokens,
        deduct_tokens=True if user.id != ADMIN_ID else False
    )

    # Считаем стоимость запроса в центах
    request_price_cents = request_tokens * current_price_cents
    response_content = response["choices"][0]["message"]["content"]  # Vision requests still use old api response format

    try:  # Send the response back to the user
        send_smart_split_message(bot, message.chat.id, response_content, parse_mode="Markdown", reply_to_message_id=message.message_id)
    except telebot.apihelper.ApiTelegramException as e:
        print(f"\nОшибка отправки из-за форматирования, отправляю без него.\nТекст ошибки: " + str(e))
        send_smart_split_message(bot, message.chat.id, response_content, reply_to_message_id=message.message_id)

    # Формируем лог работы для админа
    admin_log += create_request_report(user, message.chat, request_tokens, request_price_cents)
    print("\n" + admin_log)

    # Отправляем лог работы админу в тг
    if message.chat.id != ADMIN_ID:
        bot.send_message(ADMIN_ID, admin_log, parse_mode="HTML")


# Define the message handler for incoming messages (default and premium requests)
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    global session_tokens, premium_session_tokens, session_request_counter, data
    user = message.from_user

    # Если пользователя нет в базе, то перенаправляем его на команду /start и выходим
    if not is_user_exists(user.id):
        if is_user_blacklisted(user.id):
            return
        else:
            bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start\n\n"
                                  "Подсказка: за регистрацию по рефке вы получите на 50% больше токенов!")
        return

    # Если юзер ответил на ответ боту другого юзера в групповом чате, то выходим, отвечать не нужно (issue #27)
    if message.reply_to_message is not None and message.reply_to_message.from_user.id != bot.get_me().id and not message.text.startswith('/'):
        # print(f"\nUser {user.full_name} @{user.username} replied to another user, skip")
        return

    user_model: str

    if extract_command(message.text) in ["pro", "prem", "premium", "gpt4"]:
        user_model = PREMIUM_MODEL
        message.text = extract_arguments(message.text)
        if message.text == "":
            bot.reply_to(message, "Введите текст после команды /pro или /gpt4 для обращения к *GPT-4* без смены активной языковой модели\n\n"
                                  "Пример: `/pro напиши код калькулятора на python`", parse_mode="Markdown")
            return
    else:
        user_model = get_user_active_model(user.id)

    # Проверяем, есть ли у пользователя токены на балансе в зависимости от выбранной языковой модели
    if user_model == DEFAULT_MODEL:
        if data[user.id]["balance"] <= 0:
            bot.reply_to(message, 'У вас закончились токены, пополните баланс!\n'
                                  '<span class="tg-spoiler">/help в помощь</span>', parse_mode="HTML")
            return
        current_price_cents = PRICE_CENTS
        admin_log = ""

    elif user_model == PREMIUM_MODEL:
        if data[user.id].get("premium_balance") is None or data[user.id]["premium_balance"] <= 0:
            bot.reply_to(message, 'У вас закончились премиальные токены, пополните баланс!', parse_mode="HTML")
            return
        current_price_cents = PREMIUM_PRICE_CENTS
        admin_log = "ПРЕМ "

    else:  # Этого случая не может произойти, но пусть будет описан
        bot.reply_to(message, 'У вас нет доступа к этой модели, обратитесь к админу!')
        print(f"\nUser {user.full_name} @{user.username} has no access to model {user_model}")
        return

    # Симулируем эффект набора текста, пока бот получает ответ
    bot.send_chat_action(message.chat.id, "typing")

    # Send the user's message to OpenAI API and get the response
    # Если юзер написал запрос в ответ на сообщение бота, то добавляем предыдущий ответ бота в запрос
    try:
        if message.reply_to_message is not None:
            prev_answer = message.reply_to_message.caption or message.reply_to_message.text
            response = get_chatgpt_response(message.text, lang_model=user_model, prev_answer=prev_answer,
                                            system_prompt=get_user_prompt(user.id))
        else:
            response = get_chatgpt_response(message.text, lang_model=user_model, system_prompt=get_user_prompt(user.id))
    except openai.RateLimitError:
        print("\nЛимит запросов! Или закончились деньги на счету OpenAI")
        bot.reply_to(message, "Превышен лимит запросов. Пожалуйста, повторите попытку позже")
        return
    except Exception as e:
        print("\nОшибка при запросе по API, OpenAI сбоит!")
        bot.reply_to(message, "Произошла ошибка на серверах OpenAI.\n"
                              "Пожалуйста, попробуйте еще раз или повторите запрос позже")
        print(e)
        return

    # Получаем стоимость запроса по АПИ в токенах
    request_tokens = response.usage.total_tokens  # same: response.usage.total_tokens

    update_global_user_data(
        user.id,
        new_tokens=request_tokens if user_model == DEFAULT_MODEL else None,
        new_premium_tokens=request_tokens if user_model == PREMIUM_MODEL else None,
        deduct_tokens=True if user.id != ADMIN_ID else False
    )

    # Считаем стоимость запроса в центах в зависимости от выбранной модели
    request_price_cents = request_tokens * current_price_cents

    response_content = response.choices[0].message.content

    error_text = f"\nОшибка отправки из-за форматирования, отправляю без него.\nТекст ошибки: "
    # Сейчас будет жесткий код
    # Send the response back to the user, but check for `parse_mode` and `message is too long` errors
    if message.chat.type == "private":
        try:
            send_smart_split_message(bot, message.chat.id, response_content, parse_mode="Markdown")
        except telebot.apihelper.ApiTelegramException as e:
            print(error_text + str(e))
            send_smart_split_message(bot, message.chat.id, response_content)
    else:  # В групповом чате отвечать на конкретное сообщение, а не просто отправлять сообщение в чат
        try:
            send_smart_split_message(bot, message.chat.id, response_content, parse_mode="Markdown", reply_to_message_id=message.message_id)
        except telebot.apihelper.ApiTelegramException as e:
            print(error_text + str(e))
            send_smart_split_message(bot, message.chat.id, response_content, reply_to_message_id=message.message_id)

    # Формируем лог работы для админа
    admin_log += create_request_report(user, message.chat, request_tokens, request_price_cents)
    print("\n" + admin_log)

    # Отправляем лог работы админу в тг
    if message.chat.id != ADMIN_ID:
        bot.send_message(ADMIN_ID, admin_log, parse_mode="HTML")


# Handler only for bot pinned messages
@bot.message_handler(content_types=["pinned_message"])
def handle_pinned_message(message):
    if message.from_user.id != bot.get_me().id:
        return

    # Удаляем системное сообщение о закрепе
    bot.delete_message(message.chat.id, message.message_id)


if __name__ == '__main__':
    print("---работаем---")
    bot.infinity_polling()

    # Делаем бэкап бд и уведомляем админа об успешном завершении работы
    update_json_file(data, BACKUPFILE)
    bot.send_message(ADMIN_ID, "Бот остановлен")
    print("\n---работа завершена---")
