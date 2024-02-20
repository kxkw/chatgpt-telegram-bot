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

After the first launch in script directory will automatically create file `data.json`, which contains all necessary data.

After the next launch script will read data from a previously created file.
File updating as work progresses.

By default, every new user has 30k tokens, which can be used for messages to the bot (API request).

Using the referrals link to start work with the bot allows you to get an additional bonus of 20k tokens for you and your friend who invited you.

### Communication with bot
Communication with the bot works in the format "one question - one answer", but if you reply to the bot`s message, the next answer will contain the context of this message.
It allows us to continue a conversation on one subject without having to provide context in every message.

By default bot uses a standard system prompt for every request - `"You are a helpful assistant"`,
but users can change the main prompt using the command `/prompt`.

Come back standard system prompt by default user can use the command `/reset_prompt`. 

Language model by default - `gpt-3.5-turbo-1106`, but the user can change it using the command `/switch_model`. For using the premium model `gpt-4-1106-preview` it is necessary to have a positive balance of tokens.
### File `data.json` structure

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
1. `"global"` - general bot`s statistics about the number of requests and used tokens.
2. Admin`s statistics: number of requests, used tokens, infinity tokens balance, and the last message date. 
3. Statistics for every user: number of requests, used tokens, actual balance of tokens, name, @username, and the last message date.

### The commands for users  
`/start` - the start of work: registration is a system and getting the initial balance of tokens;   
`/help` - list available commands;  
`/invite` or `/ref` - getting referral link for inviting new users  
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
