# chatgpt-telegram-bot
Personal ChatGPT Telegram bot

Бот отправляет сообщение пользователя по OpenAI API в ChatGPT и возвращает обратно текст ответа.  

Используемая модель - `gpt-3.5-turbo`, лимит токенов на один запрос - 3000

Для работы необходимо заполнить файл `.env` в директории скрипта своими значениями следующим образом:

`OPENAI_API_KEY` = sk-naborbukvapi  
`TELEGRAM_API_KEY` = naborbukvtgtoken  
`ADMIN_CHAT_ID` = 123456789

### Команды бота  
`/stop` - полностью останавливает бота, доступно только админу
