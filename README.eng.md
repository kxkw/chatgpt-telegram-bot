# chatgpt-telegram-bot
>*Personal helper working on base model OpenAI GPT-3.5-turbo and GPT-4, which are available in the Telegram app. It processes messages from users, sends them to the OpenAI server, and sends back the answers. 
The bot supports systems of balance tokens for every user, which are used for API-request. Also, there are available referral systems and every user can get bonus tokens.
>Last but not least it is an opportunity to set custom users systems prompt for special answers style. 
**Generated from bot himself**

Bot sends users messages using OpenAI API and returns back generated answer. All requests from users are sent to the admin's personal chat with the bot.
Admin has full control under the bot using special admin's commands.

There are available two main language models:  
- Basic: `gpt-3.5-turbo-1106`, context window 16k tokens;
- Premium: `gpt-4-1106-preview`, context window 128k tokens.     

The `dall-e-3` model is used to generate images.

### Preparation for work

First of all, users must create and fill a file `.env` in the directory of the script with their own value, like in the example:
```env
OPENAI_API_KEY=yourapikey  
TELEGRAM_API_KEY=yourbottoken  
ADMIN_CHAT_ID=123456789
```

In this file:  
1. `OPENAI_API_KEY` - API-key from OpenAI;
2. `TELEGRAM_API_KEY` - API-token from bot in Telegram;
3. `ADMIN_CHAT_ID` - Admin's ID in Telegram;

`example.env` is a template of the `.env` file, which u can find in the repository.
All you need is to replace the value from the file with your value and rename the file.

### Launch bot
`python main.py`  

При первом запуске в директории скрипта будет автоматически создан файл `data.json`, 
в котором будут храниться все необходимые данные.  

При каждом последующем запуске скрипт будет читать данные из ранее созданного файла. 
Обновление файла происходит по мере работы.

Каждому новому пользователю по умолчанию выдается 30к токенов, 
которые можно использовать в сообщениях боту для запросов по API. 

При регистрации по реферальной ссылке начисляется бонус в 20к токенов как пригласившему, так и приглашенному пользователю.

### Общение с ботом
Общение с ботом происходит в формате "один запрос - один ответ", но, если ответить на конкретное сообщение бота (reply), 
то последующий ответ будет включать в себя контекст сообщения, на которое ответил пользователь. 
Это позволяет продолжать беседу, придерживаясь основной темы, без необходимости прописывать контекст в каждом сообщении.

При общении в личных сообщениях бот отправляет ответы в диалог, а 
при общении в групповых чатах - отвечает на конкретное сообщение.

По умолчанию, бот при каждом запросе использует стандартный системный промпт - `"You are a helpful assistant"`, 
но пользователь, при желании, может указать свой собственный системный промпт через команду `/prompt`.  

Вернуть системный промпт по умолчанию можно с помощью команды `/reset_prompt`.  

Модель по умолчанию - `gpt-3.5-turbo-1106`, но пользователь может переключить активную языковую модель через команду `/switch_model`. Для использования премиум модели `gpt-4-1106-preview` необходим положительный баланс премиум токенов.

### Структура файла `data.json`

```json
{
  "global": {
    "requests": 0,
    "tokens": 0
  },
  "admin_id": {
    "requests": 0,
    "tokens": 0,
    "balance": 777777,
    "last_request": "2021-01-01 00:00:00"
  },
  "user1": {
    "requests": 0,
    "tokens": 0,
    "balance": 30000,
    "name": "John",
    "username": "@johndoe",
    "last_request": "2021-01-01 00:00:00",
    "prompt": "You are Marv - a sarcastic reluctant assistant"
  }
}
```
1. `"global"` - общая статистика бота о количестве запросов и использованных токенов  
2. Статистика админа: число запросов, использованных токенов, несгораемый баланс и дата последнего обращения  
3. Статистика каждого из пользователей: число запросов, использованных токенов, баланс, имя, @юзернейм и дата последнего обращения

### Команды для пользователей  
`/start` - начало работы: регистрация в системе и получение стартового баланса токенов  
`/help` - список доступных команд  
`/invite` или `/ref` - получить реферальную ссылку для приглашения новых пользователей  
`/stats` - вывод статистики по количеству запросов и сумме использованных токенов  
`/balance` - текущий баланс обычных и премиум токенов  
`/prompt` или `/p` - установка своего системного промпта  
`/reset_prompt` - сброс системного промпта на стандартный  
`/topup` - плейсхолдер команды для пополнения баланса  
`/ask_favor` - запрос бесплатных токенов у админа  
`/imagine` или `/img` или `/i` - генерация изображения по текстовому описанию  
`/switch_model` или `/switch` или `/sw` - переключение активной языковой модели  
`/pro` или `/prem` или `/gpt4` - сделать быстрый запрос с помощью GPT-4 без переключения активной языковой модели  

### Команды для администратора
`/data` или `/d` - отправить админу копию файла `data.json` или данные конкретного пользователя по его user_id или @username  
`/refill` или `/r` - пополнение баланса пользователя  
`/block` или `/ban` - заблокировать пользователя  
`/stop` - полностью останавливает бота  
`/announce` или `/a` или `/notify` - отправить сообщение всем или выбранным пользователям бота  
`/recent_users` или `/recent` - получить список активных пользователей за последние n дней  
