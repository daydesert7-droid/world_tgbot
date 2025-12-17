import logging
import sqlite3
import time
import sys
import os
import datetime
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from logging.handlers import RotatingFileHandler
from threading import Thread
import queue

TOKEN = "8132501492:AAFgd3ja9Tre30XQTg5BEiyR7qOyxJ-XZw0"
CREATOR_ID = "2037455253"

LOG_CLEANUP_HOURS = 24  # Очистка логов каждые 24 часа
LOG_RETENTION_DAYS = 7  # Хранить логи 7 дней
HEARTBEAT_INTERVAL = 300  # Проверка состояния каждые 5 минут

os.makedirs('logs', exist_ok=True)
os.makedirs('logs/archive', exist_ok=True)

# Настройка логгера
log_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Основной обработчик логов
main_log_handler = RotatingFileHandler(
    'logs/bot_main.log',
    maxBytes=5*1024*1024,  # 5MB
    backupCount=10
)
main_log_handler.setFormatter(log_formatter)

# Обработчик ошибок
error_log_handler = RotatingFileHandler(
    'logs/bot_errors.log',
    maxBytes=2*1024*1024,  # 2MB
    backupCount=5
)
error_log_handler.setFormatter(log_formatter)
error_log_handler.setLevel(logging.ERROR)

# Консольный обработчик
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

# Настройка корневого логгера
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(main_log_handler)
logger.addHandler(error_log_handler)
logger.addHandler(console_handler)

bot_logger = logging.getLogger(__name__)

class BotMonitor:
    """Мониторинг и обслуживание бота"""

    def __init__(self):
        self.start_time = time.time()
        self.message_count = 0
        self.last_cleanup = time.time()
        self.last_heartbeat = time.time()
        self.running = True
        self.task_queue = queue.Queue()

    def increment_message_count(self):
        self.message_count += 1

    def get_uptime(self):
        uptime = time.time() - self.start_time
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        seconds = int(uptime % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def cleanup_old_logs(self):
        """Очистка старых логов"""
        try:
            current_time = time.time()
            cutoff_time = current_time - (LOG_RETENTION_DAYS * 86400)

            deleted_count = 0
            for filename in os.listdir('logs'):
                if filename.endswith('.log'):
                    filepath = os.path.join('logs', filename)
                    if os.path.getmtime(filepath) < cutoff_time:
                        os.remove(filepath)
                        deleted_count += 1
                        bot_logger.info(f"Удален старый лог: {filename}")

            # Архивируем текущий основной лог если он больше 1MB
            main_log_path = 'logs/bot_main.log'
            if os.path.exists(main_log_path) and os.path.getsize(main_log_path) > 1024*1024:
                archive_name = f"logs/archive/bot_main_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                try:
                    os.rename(main_log_path, archive_name)
                    bot_logger.info(f"Основной лог заархивирован: {archive_name}")
                except OSError as e:
                    bot_logger.error(f"Ошибка при архивации лога: {e}")

            self.last_cleanup = current_time
            bot_logger.info(f"Очистка логов завершена. Удалено: {deleted_count} файлов")

        except Exception as e:
            bot_logger.error(f"Ошибка при очистке логов: {e}", exc_info=True)

    def send_heartbeat(self):
        """Отправка heartbeat для поддержания активности"""
        try:
            uptime = self.get_uptime()
            
            # Проверяем существование файла лога
            log_size = 0
            if os.path.exists('logs/bot_main.log'):
                log_size = os.path.getsize('logs/bot_main.log') / 1024
            
            stats = (f"🤖 Бот работает\n"
                    f"⏱ Время работы: {uptime}\n"
                    f"📊 Сообщений обработано: {self.message_count}\n"
                    f"💾 Лог: {log_size:.1f} KB")

            bot_logger.info(f"Heartbeat: {stats}")
            self.last_heartbeat = time.time()

        except Exception as e:
            bot_logger.error(f"Ошибка heartbeat: {e}", exc_info=True)

    def run_scheduled_tasks(self):
        """Запуск запланированных задач в отдельном потоке"""
        while self.running:
            try:
                current_time = time.time()

                # Проверяем нужно ли очистить логи
                if current_time - self.last_cleanup > (LOG_CLEANUP_HOURS * 3600):
                    self.cleanup_old_logs()

                # Отправляем heartbeat
                if current_time - self.last_heartbeat > HEARTBEAT_INTERVAL:
                    self.send_heartbeat()

                time.sleep(60)  # Проверяем каждую минуту

            except Exception as e:
                bot_logger.error(f"Ошибка в планировщике: {e}", exc_info=True)
                time.sleep(300)

    def start_scheduler(self):
        """Запуск планировщика в отдельном потоке"""
        scheduler_thread = Thread(target=self.run_scheduled_tasks, daemon=True)
        scheduler_thread.start()
        bot_logger.info("Планировщик задач запущен")

# Глобальный монитор
monitor = BotMonitor()

def format_time_remaining(hours, minutes):
    if hours > 0:
        if hours == 1 or hours == 21:
            hours_text = f"{hours} час"
        elif 2 <= hours <= 4 or 22 <= hours <= 24:
            hours_text = f"{hours} часа"
        else:
            hours_text = f"{hours} часов"

    if minutes > 0:
        if minutes == 1 or minutes == 21 or minutes == 31 or minutes == 41 or minutes == 51:
            minutes_text = f"{minutes} минуту"
        elif (2 <= minutes <= 4 or 22 <= minutes <= 24 or
              32 <= minutes <= 34 or 42 <= minutes <= 44 or
              52 <= minutes <= 54):
            minutes_text = f"{minutes} минуты"
        else:
            minutes_text = f"{minutes} минут"

    if hours > 0 and minutes > 0:
        return f"{hours_text} {minutes_text}"
    elif hours > 0:
        return hours_text
    elif minutes > 0:
        return minutes_text
    else:
        return "0 минут"

def init_database():
    """Инициализация базы данных"""
    try:
        conn = sqlite3.connect('user_limits.db')
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_limits (
                user_id INTEGER PRIMARY KEY,
                last_message_time INTEGER
            )
        ''')

        # Создаем индекс для улучшения производительности
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_last_message_time ON user_limits(last_message_time)')
        
        conn.commit()
        conn.close()
        bot_logger.info("База данных инициализирована")
        
    except Exception as e:
        bot_logger.error(f"Ошибка при инициализации базы данных: {e}", exc_info=True)

def can_send_message(user_id):
    """Проверка, может ли пользователь отправить сообщение"""
    try:
        conn = sqlite3.connect('user_limits.db')
        cursor = conn.cursor()

        cursor.execute(
            'SELECT last_message_time FROM user_limits WHERE user_id = ?',
            (user_id,)
        )

        result = cursor.fetchone()
        conn.close()

        if result is None:
            return True

        last_message_time = result[0]
        current_time = int(time.time())

        return (current_time - last_message_time) >= 86400
        
    except Exception as e:
        bot_logger.error(f"Ошибка при проверке лимита сообщений: {e}", exc_info=True)
        return True  # В случае ошибки разрешаем отправку

def save_message_time(user_id):
    """Сохранение времени отправки сообщения"""
    try:
        conn = sqlite3.connect('user_limits.db')
        cursor = conn.cursor()

        current_time = int(time.time())

        cursor.execute('''
            INSERT OR REPLACE INTO user_limits (user_id, last_message_time)
            VALUES (?, ?)
        ''', (user_id, current_time))

        conn.commit()
        conn.close()
        
    except Exception as e:
        bot_logger.error(f"Ошибка при сохранении времени сообщения: {e}", exc_info=True)

def get_time_until_next_message(user_id):
    """Получение времени до следующего сообщения"""
    try:
        conn = sqlite3.connect('user_limits.db')
        cursor = conn.cursor()

        cursor.execute(
            'SELECT last_message_time FROM user_limits WHERE user_id = ?',
            (user_id,)
        )

        result = cursor.fetchone()
        conn.close()

        if result is None:
            return 0, 0

        last_message_time = result[0]
        current_time = int(time.time())
        time_passed = current_time - last_message_time

        if time_passed >= 86400:
            return 0, 0

        time_remaining = 86400 - time_passed

        hours = time_remaining // 3600
        minutes = (time_remaining % 3600) // 60

        if time_remaining % 60 > 0:
            minutes += 1
            if minutes == 60:
                hours += 1
                minutes = 0

        return hours, minutes
        
    except Exception as e:
        bot_logger.error(f"Ошибка при получении времени до следующего сообщения: {e}", exc_info=True)
        return 0, 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    try:
        welcome_text = (
            'Добро пожаловать!\n\n'
            'Отправь мне текстовое сообщение, и оно опубликуется в канал "мир знает, что".\n\n'
            'Лимит: 1 сообщение в сутки.'
        )
        await update.message.reply_text(welcome_text)
    except Exception as e:
        bot_logger.error(f"Ошибка в команде /start: {e}", exc_info=True)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    try:
        user = update.effective_user
        user_id = user.id
        monitor.increment_message_count()

        if not can_send_message(user_id):
            hours, minutes = get_time_until_next_message(user_id)
            time_text = format_time_remaining(hours, minutes)
            limit_text = f"Следующее сообщение можно отправить через:\n{time_text}"
            await update.message.reply_text(limit_text)
            return

        if not update.message.text or update.message.text.strip() == "":
            await update.message.reply_text("Сообщение не может быть пустым.")
            return

        # Сохраняем время отправки
        save_message_time(user_id)

        # Уведомляем пользователя
        await update.message.reply_text("Сообщение отправлено. Опубликуется в порядке очереди.")

        # Отправляем сообщение создателю
        try:
            user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
            message_to_creator = f"Новое сообщение от {user_info}:"
            
            await context.bot.send_message(
                chat_id=CREATOR_ID,
                text=message_to_creator
            )
            
            await context.bot.send_message(
                chat_id=CREATOR_ID,
                text=update.message.text
            )
            
            bot_logger.info(f"Сообщение от {user_info} отправлено создателю")
            
        except Exception as e:
            bot_logger.error(f"Ошибка при отправке сообщения создателю: {e}", exc_info=True)
            await update.message.reply_text("Произошла ошибка при отправке сообщения создателю.")
            
    except Exception as e:
        bot_logger.error(f"Ошибка при обработке текстового сообщения: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при обработке вашего сообщения.")

async def handle_unsupported_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик неподдерживаемых типов сообщений"""
    try:
        await update.message.reply_text("Принимаются только текстовые сообщения.")
    except Exception as e:
        bot_logger.error(f"Ошибка при обработке неподдерживаемого сообщения: {e}", exc_info=True)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    try:
        bot_logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
        
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "Произошла внутренняя ошибка. Пожалуйста, попробуйте позже."
            )
    except Exception as e:
        bot_logger.error(f"Ошибка в глобальном обработчике ошибок: {e}", exc_info=True)

async def post_init(application: Application):
    """Функция инициализации после запуска бота"""
    bot_logger.info("Бот запущен и инициализирован")
    monitor.start_scheduler()

async def post_stop(application: Application):
    """Функция завершения работы бота"""
    bot_logger.info("Бот останавливается")
    monitor.running = False

def main():
    """Основная функция запуска бота"""
    try:
        # Инициализация базы данных
        init_database()
        
        # Оптимизация БД
        try:
            conn = sqlite3.connect('user_limits.db')
            cursor = conn.cursor()
            cursor.execute('PRAGMA journal_mode=WAL')  # Включаем режим WAL для лучшей производительности
            cursor.execute('PRAGMA optimize')
            conn.close()
        except Exception as e:
            bot_logger.error(f"Ошибка при оптимизации БД: {e}", exc_info=True)

        # Создание и настройка приложения
        application = Application.builder()\
            .token(TOKEN)\
            .post_init(post_init)\
            .post_stop(post_stop)\
            .build()

        # Добавление обработчиков команд
        application.add_handler(CommandHandler("start", start))
        
        # Добавление обработчиков сообщений
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text_message
        ))
        
        application.add_handler(MessageHandler(
            ~filters.TEXT & ~filters.COMMAND,
            handle_unsupported_message
        ))
        
        # Добавление глобального обработчика ошибок
        application.add_error_handler(error_handler)

        # Запуск бота
        bot_logger.info("Запуск бота...")
        application.run_polling(
            poll_interval=1.0,
            timeout=30,
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        bot_logger.error(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()