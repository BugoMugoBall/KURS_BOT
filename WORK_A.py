import telebot
from telebot import types
import psycopg2
import random
from config import TOKEN
from config import PARAMS


class DatabaseManager:
    def __init__(self, db_params):
        self.conn = psycopg2.connect(**db_params)
        self.cursor = self.conn.cursor()

    def get_user(self, telegram_id):
        self.cursor.execute("SELECT user_id FROM users WHERE telegram_id = %s", (telegram_id,))
        return self.cursor.fetchone()

    def create_user(self, telegram_id, username, first_name, last_name):
        self.cursor.execute(
            "INSERT INTO users (telegram_id, username, first_name, last_name) VALUES (%s, %s, %s, %s) RETURNING user_id",
            (telegram_id, username, first_name, last_name),
        )
        user_id = self.cursor.fetchone()[0]
        self.conn.commit()
        return user_id

    def get_random_word(self, user_id):
        self.cursor.execute("""
            SELECT word_id, english, russian
            FROM (
                SELECT w.word_id, w.english, w.russian
                FROM words w
                INNER JOIN user_words uw ON w.word_id = uw.word_id
                WHERE uw.user_id = %s
                UNION ALL
                SELECT w.word_id, w.english, w.russian
                FROM words w
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM user_words uw
                    WHERE uw.user_id = %s AND uw.word_id = w.word_id
                )
            ) AS combined_words
            ORDER BY RANDOM()
            LIMIT 1
        """, (user_id, user_id))
        return self.cursor.fetchone()

    def get_word_by_id(self, word_id):
        self.cursor.execute("SELECT word_id, english, russian FROM words WHERE word_id = %s", (word_id,))
        return self.cursor.fetchone()

    def add_word_to_user(self, user_id, english, russian):
        # Сначала проверяем, есть ли такое слово в таблице words
        self.cursor.execute("SELECT word_id FROM words WHERE english = %s", (english,))
        word_data = self.cursor.fetchone()

        if word_data is None:
            # Если слова нет, добавляем его
            self.cursor.execute("INSERT INTO words (english, russian) VALUES (%s, %s) RETURNING word_id",
                                (english, russian))
            word_id = self.cursor.fetchone()[0]
        else:
            word_id = word_data[0]

        # Затем добавляем связь между пользователем и словом в таблицу user_words
        try:
            self.cursor.execute("INSERT INTO user_words (user_id, word_id, added_by_user) VALUES (%s, %s, %s)",
                                (user_id, word_id, True))
            self.conn.commit()
            return True
        except psycopg2.errors.UniqueViolation as e:  # Ловим UniqueViolation
            self.conn.rollback()  # Откатываем транзакцию
            print(f"Слово уже добавлено пользователю: {e}")  # Добавляем вывод ошибки в консоль
            return False  # Возвращаем False, чтобы бот знал, что слово не было добавлено
        except Exception as e:
            self.conn.rollback()  # Откатываем транзакцию
            print(f"Ошибка при добавлении слова: {e}")
            return False

    def delete_word_from_user(self, user_id, word_id):
        self.cursor.execute("DELETE FROM user_words WHERE user_id = %s AND word_id = %s", (user_id, word_id))
        self.conn.commit()

    def get_user_words_count(self, user_id):
        self.cursor.execute("SELECT COUNT(*) FROM user_words WHERE user_id = %s", (user_id,))
        return self.cursor.fetchone()[0]

    def close(self):
        self.cursor.close()
        self.conn.close()


class EnglishCardBot:
    def __init__(self, bot_token, db_params):
        self.bot = telebot.TeleBot(bot_token)
        self.db = DatabaseManager(db_params)
        self.user_states = {}  # Добавим словарь для хранения состояний пользователей

    def register_handlers(self):
        self.bot.message_handler(commands=['start'])(self.start)
        self.bot.message_handler(func=lambda message: True)(self.handle_message)  # Обрабатываем все текстовые сообщения

    def start(self, message):
        user = self.db.get_user(message.from_user.id)
        if not user:
            user_id = self.db.create_user(
                message.from_user.id,
                message.from_user.username,
                message.from_user.first_name,
                message.from_user.last_name,
            )
            self.bot.send_message(
                message.chat.id,
                f"Привет, {message.from_user.first_name}! Добро пожаловать в EnglishCardBot!  Вы новый пользователь, вы зарегистрированы."
            )
        else:
            self.bot.send_message(
                message.chat.id,
                f"Привет, {message.from_user.first_name}! С возвращением в EnglishCardBot!"
            )

        # Создаем reply keyboard
        keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        button1 = types.KeyboardButton("Добавить слово")
        button2 = types.KeyboardButton("Удалить слово")
        button3 = types.KeyboardButton("Начать тренировку")  # Добавим кнопку "Начать тренировку"
        keyboard.add(button1, button2, button3)

        self.bot.send_message(message.chat.id, "Выберите действие:", reply_markup=keyboard)

    def ask_question(self, user_id):
        word = self.db.get_random_word(user_id)
        if not word:
            self.bot.send_message(user_id,
                                  "Похоже, вы выучили все слова! Или в базе данных еще нет слов.  Добавьте новые слова с помощью команды /add.")
            return

        word_id, english, russian = word
        correct_answer = english
        # Получаем три случайных неверных ответа
        incorrect_answers = []
        while len(incorrect_answers) < 3:
            random_word = self.db.get_random_word(user_id)
            if random_word:
                random_word_id, random_english, random_russian = random_word
                if random_english != correct_answer and random_english not in incorrect_answers:
                    incorrect_answers.append(random_english)
            else:
                print("Недостаточно слов в базе данных для генерации вариантов ответа.")
                return  # Или обработайте ситуацию по-другому

        # Формируем варианты ответов
        answers = [correct_answer] + incorrect_answers
        random.shuffle(answers)

        # Создаем клавиатуру
        keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)  # Заменим inline на reply
        for answer in answers:
            button = types.KeyboardButton(answer)  # Вместо callback_data - просто текст
            keyboard.add(button)

        # Добавляем кнопку "Назад"
        back_button = types.KeyboardButton("Назад")
        keyboard.add(back_button)

        self.bot.send_message(user_id, f"Как переводится слово '{russian}'?", reply_markup=keyboard)
        self.user_states[user_id] = {"state": "waiting_answer", "word_id": word_id}  # Сохраняем состояние

    def handle_message(self, message):
        user_id = message.chat.id

        if message.text == "Добавить слово":
            self.add_word_handler(message)  # вызываем обработчик добавления слова
        elif message.text == "Удалить слово":
            self.delete_word_handler(message)  # вызываем обработчик удаления слова
        elif message.text == "Начать тренировку":  # Если пользователь нажал "Начать тренировку"
            self.ask_question(message.chat.id)  # Задаем вопрос
        elif message.text == "Назад":  # Если пользователь нажал "Назад"
            if user_id in self.user_states and self.user_states[user_id]["state"] == "waiting_answer":
                del self.user_states[user_id]  # Удаляем состояние тренировки

            # Создаем reply keyboard с основным меню
            keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
            button1 = types.KeyboardButton("Добавить слово")
            button2 = types.KeyboardButton("Удалить слово")
            button3 = types.KeyboardButton("Начать тренировку")  # Добавим кнопку "Начать тренировку"
            keyboard.add(button1, button2, button3)

            self.bot.send_message(user_id, "Выберите действие:", reply_markup=keyboard)
        elif user_id in self.user_states and self.user_states[user_id]["state"] == "waiting_answer":
            self.check_answer(message)  # Проверяем ответ, если ждем его
        else:
            self.bot.send_message(message.chat.id, "Я не понимаю эту команду.")

    def check_answer(self, message):
        user_id = message.chat.id
        user_state = self.user_states.get(user_id)  # Получаем состояние

        if not user_state or user_state["state"] != "waiting_answer":  # Проверяем, что состояние валидно
            return

        word_id = user_state["word_id"]
        word = self.db.get_word_by_id(word_id)
        if not word:
            self.bot.send_message(user_id, "Слово не найдено.")
            return

        word_id, english, russian = word
        correct_answer = english

        if message.text == correct_answer:
            self.bot.send_message(user_id, "Правильно!",
                                  reply_markup=types.ReplyKeyboardRemove())  # Убираем клавиатуру
            del self.user_states[user_id]  # Удаляем состояние

            # Создаем reply keyboard после правильного ответа
            keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
            button1 = types.KeyboardButton("Добавить слово")
            button2 = types.KeyboardButton("Удалить слово")
            button3 = types.KeyboardButton("Начать тренировку")  # Добавим кнопку "Начать тренировку"
            keyboard.add(button1, button2, button3)

            self.bot.send_message(user_id, "Выберите действие:", reply_markup=keyboard)

        else:
            self.bot.send_message(user_id, "Неправильно. Попробуйте еще раз.")

    def add_word_handler(self, message):
        user_id = message.chat.id
        self.bot.send_message(user_id, "Введите английское слово:",
                              reply_markup=types.ReplyKeyboardRemove())  # Убираем клавиатуру
        self.user_states[user_id] = {"state": "waiting_english"}  # Устанавливаем состояние
        self.bot.register_next_step_handler(message, self.get_english_word)

    def get_english_word(self, message):
        user_id = message.chat.id
        if user_id not in self.user_states or self.user_states[user_id]["state"] != "waiting_english":
            return  # Проверяем состояние
        english_word = message.text.strip()
        self.user_states[user_id] = {"state": "waiting_russian", "english_word": english_word}  # Устанавливаем состояние
        self.bot.send_message(user_id, "Введите русский перевод:")
        self.bot.register_next_step_handler(message, self.get_russian_word)

    def get_russian_word(self, message):
        user_id = message.chat.id
        if user_id not in self.user_states or self.user_states[user_id]["state"] != "waiting_russian":
            return  # Проверяем состояние
        russian_word = message.text.strip()
        english_word = self.user_states[user_id]["english_word"]

        db_user = self.db.get_user(user_id)
        if not db_user:
            self.bot.send_message(message.chat.id, "Пожалуйста, сначала используйте команду /start.")
            return

        user_id = db_user[0]

        if self.db.add_word_to_user(user_id, english_word, russian_word):
            count = self.db.get_user_words_count(user_id)
            self.bot.send_message(message.chat.id, f"Слово '{english_word}' добавлено! Вы изучаете {count} слов.")
        else:
            self.bot.send_message(message.chat.id, f"Слово '{english_word}' уже есть в вашем списке.")

        # Проверяем, существует ли ключ user_id в словаре self.user_states
        if user_id in self.user_states:
            del self.user_states[user_id]  # Удаляем состояние

        # Создаем reply keyboard после добавления слова
        keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        button1 = types.KeyboardButton("Добавить слово")
        button2 = types.KeyboardButton("Удалить слово")
        button3 = types.KeyboardButton("Начать тренировку")  # Добавим кнопку "Начать тренировку"
        keyboard.add(button1, button2, button3)

        self.bot.send_message(message.chat.id, "Выберите действие:", reply_markup=keyboard)

    def delete_word_handler(self, message):
        user_id = message.chat.id

        db_user = self.db.get_user(user_id)
        if not db_user:
            self.bot.send_message(message.chat.id, "Пожалуйста, сначала используйте команду /start.")
            return

        user_id = db_user[0]

        # Получаем все слова пользователя
        self.db.cursor.execute("""
            SELECT w.word_id, w.english
            FROM words w
            INNER JOIN user_words uw ON w.word_id = uw.word_id
            WHERE uw.user_id = %s
        """, (user_id,))
        user_words = self.db.cursor.fetchall()

        if not user_words:
            self.bot.send_message(user_id, "В вашем списке нет слов для удаления.")
            self.ask_question(user_id)
            return

        # Создаем reply keyboard со списком слов
        keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)  # Используем ReplyKeyboardMarkup
        for word_id, english in user_words:
            button = types.KeyboardButton(english)  # Кнопка с текстом слова
            keyboard.add(button)

        cancel_button = types.KeyboardButton("Отмена")  # Кнопка отмены
        keyboard.add(cancel_button)

        self.bot.send_message(user_id, "Выберите слово для удаления:", reply_markup=keyboard)
        self.bot.register_next_step_handler(message, self.delete_word_confirm, user_words)  # Передаем список слов

    def delete_word_confirm(self, message, user_words):  # Принимаем список слов
        user_id = message.chat.id
        selected_word = message.text

        if selected_word == "Отмена":
            self.bot.send_message(user_id, "Удаление отменено.",
                                  reply_markup=types.ReplyKeyboardRemove())  # Убираем клавиатуру
            self.ask_question(user_id)
            return

        word_to_delete = None
        for word_id, english in user_words:
            if english == selected_word:
                word_to_delete = (word_id, english)
                break

        if word_to_delete:
            word_id, english = word_to_delete
            self.db.delete_word_from_user(user_id, word_id)
            self.bot.send_message(user_id, f"Слово '{english}' удалено.",
                                  reply_markup=types.ReplyKeyboardRemove())  # Убираем клавиатуру
        else:
            self.bot.send_message(user_id, "Слово не найдено в вашем списке.",
                                  reply_markup=types.ReplyKeyboardRemove())  # Убираем клавиатуру

        # Создаем reply keyboard после удаления слова
        keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        button1 = types.KeyboardButton("Добавить слово")
        button2 = types.KeyboardButton("Удалить слово")
        button3 = types.KeyboardButton("Начать тренировку")  # Добавим кнопку "Начать тренировку"
        keyboard.add(button1, button2, button3)

        self.bot.send_message(message.chat.id, "Выберите действие:", reply_markup=keyboard)

    def run(self):
        self.bot.infinity_polling()


if __name__ == '__main__':
    # Замените на свои значения
    BOT_TOKEN = TOKEN
    DB_PARAMS = PARAMS

    bot = EnglishCardBot(BOT_TOKEN, DB_PARAMS)
    bot.register_handlers()
    bot.run()