# chatgpt-telegram-bot
>*Персональный помощник на основе модели OpenAI GPT-3.5-turbo и GPT-4, работающий в Telegram. Он обрабатывает сообщения пользователей, отправляет их на сервер OpenAI и возвращает сгенерированный ответ. 
Бот поддерживает систему баланса токенов для каждого пользователя, которые используются для запросов к API. Пользователи могут приглашать других пользователей и получать бонусные токены. 
Бот также предоставляет возможность установки пользовательского системного промпта для модификации стиля ответов.*   
**Сгенерировано самим ботом**

Бот отправляет сообщения пользователей по OpenAI API в ChatGPT и возвращает обратно текст ответа. Логи обо всех запросах пользователей приходят админу в личку.
Админ имеет полное управление над ботом с помощью специальных команд администратора.  

Доступно две основные языковые модели:  
- Основная: `gpt-3.5-turbo-1106`, контекстное окно 16k токенов  
- Премиум: `gpt-4-1106-preview`, контекстное окно 128k токенов  

Для генерации изображений используется модель `dall-e-3`.

### Подготовка к работе

Для работы необходимо создать и заполнить файл `.env` в директории скрипта своими значениями следующим образом:
```env
OPENAI_API_KEY=yourapikey  
TELEGRAM_API_KEY=yourbottoken  
ADMIN_CHAT_ID=123456789
```

В данном файле:  
1. `OPENAI_API_KEY` - API-ключ от OpenAI
2. `TELEGRAM_API_KEY` - API-токен от бота в Telegram
3. `ADMIN_CHAT_ID` - ID админа в Telegram

В репозитории находится файл `example.env` - это образец необходимого для работы `.env` файла. 
Достаточно заполнить его своими значениями и переименовать, чтобы не создавать файл самостоятельно.  

### Локальный запуск бота
```shell
pip install -r requirements.txt;
python main.py
```  

При первом запуске в директории скрипта будет автоматически создан файл `data.json`, 
в котором будут храниться все необходимые данные.  

При каждом последующем запуске скрипт будет читать данные из ранее созданного файла. 
Обновление файла происходит по мере работы.

Каждому новому пользователю по умолчанию выдается 30к токенов, 
которые можно использовать в сообщениях боту для запросов по API. 

При регистрации по реферальной ссылке начисляется бонус в 20к токенов как пригласившему, так и приглашенному пользователю.

### Запуск бота через docker (опционально)
Убедитесь что на вашем устройстве установлен и запущен демон докер.
`docker compose up -d` запустит приложение без необходимости настройки локальной среды, установки python, зависимостей, отслеживания здоровья приложения, и других неудобств. \
Чтобы убедиться в успешности запуска, можно выполнить команду `docker logs --tail 100 tg_bot`, или найти имя контейнера с помощью `docker ps -a` при кастомизированном названии корневой папки. \
Остановить бота можно при помощи `docker compose down`

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
