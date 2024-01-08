from typing import Optional

import telebot
import openai
from dotenv.main import load_dotenv
import json
import os
from datetime import datetime, timedelta
import time

from telebot.util import extract_arguments
from telebot import types



MODEL = "gpt-3.5-turbo-1106"  # 16k
PREMIUM_MODEL = "gpt-4-1106-preview"  # 128k tokens context window
MAX_REQUEST_TOKENS = 3000  # max output tokens for one request (not including input tokens)
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant named Магдыч."

PRICE_1K = 0.002  # price per 1k tokens in USD
PREMIUM_PRICE_1K = 0.02  # price per 1k tokens in USD for premium model

DATE_FORMAT = "%d.%m.%Y %H:%M:%S"  # date format for logging
UTC_HOURS_DELTA = 3  # time difference between server and local time in hours (UTC +3)

NEW_USER_BALANCE = 20000  # balance for new users
REFERRAL_BONUS = 10000  # bonus for inviting a new user
FAVOR_AMOUNT = 20000  # amount of tokens per granted favor
FAVOR_MIN_LIMIT = 5000  # minimum balance to ask for a favor

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
def call_chatgpt(user_request: str, prev_answer=None, system_prompt=DEFAULT_SYSTEM_PROMPT):
    messages = [{"role": "system", "content": system_prompt}]

    if prev_answer is not None:
        messages.extend([{"role": "assistant", "content": prev_answer},
                         {"role": "user", "content": user_request}])
        # print("\nЗапрос с контекстом 🤩")
    else:
        messages.append({"role": "user", "content": user_request})
        # print("\nЗапрос без контекста")

    return openai.ChatCompletion.create(
        model=MODEL,
        max_tokens=MAX_REQUEST_TOKENS,
        messages=messages
    )


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


# Function to get user current model
def get_user_model(user_id: int) -> str:
    if data[user_id].get("lang_model") is None:
        return MODEL
    else:
        model = str(data[user_id]["lang_model"])
        if model == "premium":
            return PREMIUM_MODEL
        else:
            return MODEL


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
            ADMIN_ID: {"requests": 0, "tokens": 0, "balance": 777777,
                       "name": "АДМИН", "username": "@admin", "lastdate": "01-05-2023 00:00:00"}}
    # Create the file with default values
    update_json_file(data)


# Calculate the price per token in cents
PRICE_CENTS = PRICE_1K / 10
PREMIUM_PRICE_CENTS = PREMIUM_PRICE_1K / 10

# Session token and request counters
session_tokens, request_number = 0, 0


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

    if "images" in data[target_user_id]:
        images_line = f"images: {data[target_user_id]['images']}\n"
    else:
        images_line = ""

    if data[target_user_id].get("premium_balance") is not None:
        premium_string = (f"premium tokens: {data[target_user_id].get('premium_tokens', 0)}\n"
                          f"premium balance: {data[target_user_id]['premium_balance']}\n\n")
    else:
        premium_string = ""

    # Если юзер был успешно найден, то формируем здесь сообщение с его статой
    user_data_string = f"id {target_user_id}\n" \
                       f"{data[target_user_id]['name']} " \
                       f"{data[target_user_id]['username']}\n\n" \
                       f"requests: {data[target_user_id]['requests']}\n" \
                       f"tokens: {data[target_user_id]['tokens']}\n" \
                       f"{images_line}" \
                       f"balance: {data[target_user_id]['balance']}\n\n" \
                       f"{premium_string}" \
                       f"last request: {data[target_user_id]['lastdate']}\n"

    # Calculate user cost in cents and round it to 3 digits after the decimal point
    user_cost_cents = round(data[target_user_id]['tokens'] * PRICE_CENTS, 3)
    user_data_string += f"user cost: ¢{user_cost_cents}\n\n"

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

    bot.reply_to(message, answer)


# Define the handler for the admin /refill command
@bot.message_handler(commands=["r", "refill"])
def handle_refill_command(message):
    wrong_input_string = ("Укажите @username/id пользователя и сумму пополнения после команды.\n"
                          "Допишите `premium` последним аргументом, чтобы пополнить баланс премиум токенов.\n\n"
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

    # Определяем тип баланса для пополнения в зависимости от третьего аргумента (обычный или премиум)
    balance_type = args[2] if len(args) > 2 else None
    if balance_type is None:
        balance_type = "balance"
        prefix = ""  # префикс для сообщений
    elif balance_type in ["premium", "prem", "p"]:
        balance_type = "premium_balance"
        success_string = "ПРЕМИУМ " + success_string
        prefix = "премиум "
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
            log = f"✉️ Сообщение отправлено в чат {recepients_list[0]}"
        except Exception as e:
            log = f"❌ Ошибка: чат {recepients_list[0]} не найден"
        bot.send_message(ADMIN_ID, log)
        print(log)
        return

    msg_counter = 0
    log = ""
    for user_id in recepients_list:
        try:
            bot.send_message(user_id, announcement_text, parse_mode="HTML")
            msg_counter += 1
            log += f"✉️ {data[user_id]['name']} {data[user_id]['username']} {user_id}" + "\n"
            time.sleep(0.5)
        except Exception as e:
            # print(e)
            log += f"❌ {data[user_id]['name']} {data[user_id]['username']} {user_id}" + "\n"

    log = f"Рассылка завершена!\nОтправлено {msg_counter} из {len(recepients_list)} сообщений." + "\n\nПолучатели:\n" + log
    bot.send_message(ADMIN_ID, log)
    print(log)


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
                  "/balance - баланс токенов\n/stats - статистика запросов\n" \
                  "/ask_favor - запросить эирдроп токенов 🙏\n\n" \
                  "/switch_model или /sw - сменить языковую модель\n\n" \
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

    balance_string = (f"Токены: {balance}\n"
                      f"Премиум токены: {prem_balance}\n\n"
                      f"Используйте команду /switch_model, чтобы переключить используемую языковую модель\n")

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
@bot.message_handler(commands=["stats"])
def handle_stats_command(message):
    user_id = message.from_user.id

    if is_user_blacklisted(user_id):
        return

    if not is_user_exists(user_id):
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start")

    user_data = data[user_id]
    user_data_string = (f"Запросов: {user_data['requests']}\n"
                        f"Токенов использовано: {user_data['tokens']}\n\n")

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

    user_model = get_user_model(user_id)

    # Определяем целевую языковую модель в зависимости от текущей
    if user_model == MODEL:
        target_model_type = "premium"
        target_model = PREMIUM_MODEL
        postfix = "(ПРЕМИУМ)\n\nВнимание! Генерация ответа с данной моделью может занимать до двух минут!"
    elif user_model == PREMIUM_MODEL:
        target_model_type = "default"
        target_model = MODEL
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


# TODO: внедрить фичу для всех пользователей вместе с премиум запросами, пока только пре-релиз для админа
# Define the handler for the /imagine command to generate AI image from text via OpenAi
@bot.message_handler(commands=["i", "img", "image", "imagine"])
def handle_imagine_command(message):
    user = message.from_user

    if is_user_blacklisted(user.id):
        return

    # if not is_user_exists(user.id):
    #     bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start")
    #     return

    # Пока что команда доступна только админу
    if user.id != ADMIN_ID:
        bot.reply_to(message, "платно")
        return

    image_prompt = extract_arguments(message.text)

    if image_prompt == "":
        bot.reply_to(message, "Введите текст для генерации изображения вместе с командой /imagine")
        return

    # bot.reply_to(message, f"{image_prompt}\n\nГенерирую изображение, подождите немного...")

    log_message = f"\nUser {user.full_name} @{user.username} requested image generation with prompt: {image_prompt}"
    print(log_message)
    if user.id != ADMIN_ID:
        bot.send_message(ADMIN_ID, log_message)

    # Симулируем эффект отправки изображения, пока бот получает ответ
    bot.send_chat_action(message.chat.id, "upload_photo")

    try:
        response = openai.Image.create(
            model="dall-e-3",
            prompt=image_prompt,
            size="1024x1024",
            quality="hd"  # hd and standard, hd costs x2
        )
    except openai.error.InvalidRequestError as e:
        # print(e.http_status)
        error_text = ("Произошла ошибка при генерации изображения 😵\n\n"
                      f"Промпт: {image_prompt}\n\n")

        if message.chat.id != ADMIN_ID:
            bot.send_message(message.chat.id, error_text + str(e))
        bot.send_message(ADMIN_ID, error_text + str(e.error))
        print(e.error)
        return

    # image_url = response['data'][0]['url']
    image_url = response.data[0].url
    # revised_prompt = '<span class="tg-spoiler">' + response.data[0].revised_prompt + '</span>'
    revised_prompt = ""

    try:
        bot.send_photo(message.chat.id, image_url, caption=revised_prompt, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        error_text = "Произошла ошибка при отправке изображения 😵\n\n"

        if message.chat.id != ADMIN_ID:
            bot.send_message(message.chat.id, error_text)
        bot.send_message(ADMIN_ID, error_text + str(e))
        print(error_text + str(e))
        return

    if "images" in data[user.id]:
        data[user.id]["images"] += 1
    else:
        data[user.id]["images"] = 1

    # Обновляем глобальную статистику по количеству запросов сгенерированных изображений (режим обратной совместимости)
    if "images" in data["global"]:
        data["global"]["images"] += 1
    else:
        data["global"]["images"] = 1

    update_json_file(data)


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

    # Если пользователя нет в базе, то перенаправляем его на команду /start и выходим
    if not is_user_exists(user.id):
        bot.reply_to(message, "Вы не зарегистрированы в системе. Напишите /start\n\n"
                              "Подсказка: за регистрацию по рефке вы получите на 50% больше токенов!")
        return

    user_model: str = get_user_model(user.id)
    # print("Модель юзера: " + user_model)
    # Проверяем, есть ли у пользователя токены на балансе в зависимости от выбранной языковой модели
    if user_model == MODEL:
        if data[user.id]["balance"] <= 0:
            bot.reply_to(message, 'У вас закончились токены, пополните баланс!\n'
                                  '<span class="tg-spoiler">/help в помощь</span>', parse_mode="HTML")
            return
        balance_type = "balance"
        tokens_type = "tokens"
        current_price_cents = PRICE_CENTS
        admin_log = ""

    elif user_model == PREMIUM_MODEL:
        if data[user.id].get("premium_balance") is None or data[user.id]["premium_balance"] <= 0:
            bot.reply_to(message, 'У вас закончились премиальные токены, пополните баланс!', parse_mode="HTML")
            return
        balance_type = "premium_balance"
        tokens_type = "premium_tokens"
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
        if message.reply_to_message is not None and message.reply_to_message.from_user.id == bot.get_me().id:
            response = call_chatgpt(message.text, message.reply_to_message.text, get_user_prompt(user.id))
        else:
            response = call_chatgpt(message.text, system_prompt=get_user_prompt(user.id))
    except openai.error.RateLimitError:
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
    request_tokens = response["usage"]["total_tokens"]  # same: response.usage.total_tokens
    session_tokens += request_tokens
    request_number += 1

    # Обновляем глобальную статистику по количеству запросов и использованных токенов (режим обратной совместимости с версией без премиум токенов)
    data["global"]["requests"] += 1
    if tokens_type in data["global"]:
        data["global"][tokens_type] += request_tokens
    else:
        data["global"][tokens_type] = request_tokens

    # Если юзер не админ, то списываем токены с баланса
    if user.id != ADMIN_ID:
        data[user.id][balance_type] -= request_tokens

    data[user.id]["requests"] += 1

    # Обновляем данные юзера по количеству использованных токенов (режим обратной совместимости с версией без премиум токенов)
    if tokens_type in data[user.id]:
        data[user.id][tokens_type] += request_tokens
    else:
        data[user.id][tokens_type] = request_tokens

    # получаем текущее время и прибавляем +3 часа
    data[user.id]["lastdate"] = (datetime.now() + timedelta(hours=UTC_HOURS_DELTA)).strftime(DATE_FORMAT)

    # Записываем инфу о количестве запросов и токенах в файл
    update_json_file(data)

    # Считаем стоимость запроса в центах в зависимости от выбранной модели
    request_price = request_tokens * current_price_cents

    # To prevent sending too long messages, we split the response into chunks of 4096 characters
    split_message = telebot.util.smart_split(response.choices[0].message.content, 4096)

    error_text = f"\nОшибка отправки из-за форматирования, отправляю без него.\nТекст ошибки: "
    # Сейчас будет жесткий код
    # Send the response back to the user, but check for `parse_mode` and `message is too long` errors
    if message.chat.type == "private":
        try:
            for string in split_message:
                bot.send_message(message.chat.id, string, parse_mode="Markdown")
        except telebot.apihelper.ApiTelegramException as e:
            print(error_text + str(e))
            for string in split_message:
                bot.send_message(message.chat.id, string)
    else:  # В групповом чате отвечать на конкретное сообщение, а не просто отправлять сообщение в чат
        try:
            for string in split_message:
                bot.reply_to(message, string, parse_mode="Markdown", allow_sending_without_reply=True)
        except telebot.apihelper.ApiTelegramException as e:
            print(error_text + str(e))
            for string in split_message:
                bot.reply_to(message, string, allow_sending_without_reply=True)

    # Если сообщение было в групповом чате, то указать данные о нём
    if message.chat.id < 0:
        chat_line = f"Чат: {message.chat.title} {message.chat.id}\n"
    else:
        chat_line = ""
    # Формируем лог работы для админа
    admin_log = (f"Запрос {request_number}: {request_tokens} за ¢{round(request_price, 3)}\n"
                 f"Сессия: {session_tokens} за ¢{round(session_tokens * PRICE_CENTS, 3)}\n"
                 f"Юзер: {user.full_name} "
                 f"@{user.username} {user.id}\n"
                 f"Баланс: {data[user.id]['balance']}\n"
                 f"{chat_line}"
                 f"{data['global']} ¢{round(data['global']['tokens'] * PRICE_CENTS, 3)}")

    # Пишем лог работы в консоль
    print("\n" + admin_log)

    # Отправляем лог работы админу в тг
    if message.chat.id != ADMIN_ID:
        bot.send_message(ADMIN_ID, admin_log)


# Handler only for bot pinned messages
@bot.message_handler(content_types=["pinned_message"])
def handle_pinned_message(message):
    if message.from_user.id != bot.get_me().id:
        return

    # Удаляем системное сообщение о закрепе
    bot.delete_message(message.chat.id, message.message_id)


# Start the bot
print("---работаем---")
bot.infinity_polling()

# Делаем бэкап бд и уведомляем админа об успешном завершении работы
update_json_file(data, BACKUPFILE)
bot.send_message(ADMIN_ID, "Бот остановлен")
print("\n---работа завершена---")
