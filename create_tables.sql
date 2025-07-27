-- Создание таблицы users
CREATE table if not exists users (
    user_id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы words
CREATE table if not exists words (
    word_id SERIAL PRIMARY KEY,
    english VARCHAR(255) UNIQUE NOT NULL,
    russian VARCHAR(255) NOT NULL
);

-- Создание таблицы user_words
CREATE table if not exists user_words (
    user_word_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id),
    word_id INTEGER REFERENCES words(word_id),
    added_by_user BOOLEAN DEFAULT FALSE,
    UNIQUE (user_id, word_id)
);
