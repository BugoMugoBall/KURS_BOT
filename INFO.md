# Описание структуры базы данных EnglishRussianCard

## Таблица `users`

*   `user_id` (SERIAL PRIMARY KEY) - ID пользователя Telegram
*   `telegram_id` (BIGINT UNIQUE NOT NULL) - ID пользователя в Telegram
*   `username` (VARCHAR(255)) - Имя пользователя в Telegram
*   `first_name` (VARCHAR(255)) - Имя
*   `last_name` (VARCHAR(255)) - Фамилия
*   `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP) - Время регистрации

## Таблица `words`

*   `word_id` (SERIAL PRIMARY KEY) - ID слова
*   `english` (VARCHAR(255) UNIQUE NOT NULL) - Слово на английском
*   `russian` (VARCHAR(255) NOT NULL) - Перевод на русский

## Таблица `user_words`

*   `user_word_id` (SERIAL PRIMARY KEY)
*   `user_id` (INTEGER REFERENCES users(user_id)) - ID пользователя
*   `word_id` (INTEGER REFERENCES words(word_id)) - ID слова
*   `added_by_user` (BOOLEAN DEFAULT FALSE) - Добавлено пользователем (TRUE) или из общего списка (FALSE)
*   *UNIQUE (user_id, word_id)* - Чтобы пользователь не мог добавить одно и то же слово несколько раз