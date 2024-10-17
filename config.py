import os
from dotenv import load_dotenv
import telebot


DEFAULT_MODEL = "gpt-4o-mini"  # 128k input, 16k output tokens context window
PREMIUM_MODEL = "gpt-4o"  # 128k
MAX_REQUEST_TOKENS = 4000  # max output tokens for one request (not including input tokens)
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant named Магдыч."

# Актуальные цены можно взять с сайта https://openai.com/pricing
PRICE_1K = 0.0006  # price per 1k tokens in USD (gpt4-o-mini)
PREMIUM_PRICE_1K = 0.015  # price per 1k tokens in USD for premium model
IMAGE_PRICE = 0.08  # price per generated image in USD
WHISPER_MIN_PRICE = 0.006  # price per 1 minute of audio transcription in USD

NEW_USER_BALANCE = 30000  # balance for new users
REFERRAL_BONUS = 20000  # bonus for inviting a new user
FAVOR_AMOUNT = 30000  # amount of tokens per granted favor
FAVOR_MIN_LIMIT = 10000  # minimum balance to ask for a favor

# Позволяет боту "помнить" поледние n символов диалога с пользователем за счет увеличенного расхода токенов
CHAT_CONTEXT_FOLDER = "chat_context/"
DEFAULT_CHAT_CONTEXT_LENGTH = 5000  # default max length of chat context in characters.

DATA_SAVE_INTERVAL = 10  # Time interval in seconds for saving user data to JSON file
DATE_FORMAT = "%d.%m.%Y %H:%M:%S"  # date format for logging

# File with users and global token usage data
DATAFILE = "data.json"
BACKUPFILE = "data-backup.json"
REQUESTS_FILE = "requests.csv"  # этот файл нужен только для внешнего анализа данных, сам бот не использует его содержимое

# Default values for new users, who are not in the data file
DEFAULT_NEW_USER_DATA = {
    "requests": 0,
    "tokens": 0,
    "balance": NEW_USER_BALANCE,
    "name": "None",
    "username": "None",
    "lastdate": "01.01.1990 00:00:00"
}

# load .env file with secrets
load_dotenv()
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # айди начальника бота
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # OpenAI API key from .env file

# Create a new Telebot instance
bot = telebot.TeleBot(os.getenv("TELEGRAM_API_KEY"))