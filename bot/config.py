import os
from typing import Optional

# Получение переменных окружения
def get_env_var(name: str, default: Optional[str] = None, required: bool = True) -> str:
    """
    Получает переменную окружения с проверкой
    
    Args:
        name: Имя переменной окружения
        default: Значение по умолчанию
        required: Обязательная ли переменная
        
    Returns:
        str: Значение переменной
        
    Raises:
        ValueError: Если обязательная переменная не найдена
    """
    value = os.getenv(name, default)
    if required and not value:
        raise ValueError(f"Переменная окружения {name} обязательна для работы бота")
    return value

# Конфигурация бота
BOT_TOKEN = get_env_var("BOT_TOKEN")

# Временная директория для файлов
TEMP_DIR = get_env_var("TEMP_DIR", "/tmp/telegram-audio-bot", required=False)

# Максимальный размер файла (в байтах)
# По умолчанию 50 МБ (Telegram лимит для ботов)
MAX_FILE_SIZE = int(get_env_var("MAX_FILE_SIZE", "52428800", required=False))

# Путь к ffmpeg (если нужно указать конкретный путь)
FFMPEG_PATH = get_env_var("FFMPEG_PATH", "ffmpeg", required=False)

# Логирование
LOG_LEVEL = get_env_var("LOG_LEVEL", "INFO", required=False)

# Дополнительные настройки
CLEANUP_INTERVAL = int(get_env_var("CLEANUP_INTERVAL", "3600", required=False))  # 1 час
PROGRESS_UPDATE_INTERVAL = float(get_env_var("PROGRESS_UPDATE_INTERVAL", "1.0", required=False))  # 1 секунда

# Проверяем наличие обязательных переменных при импорте
if __name__ == "__main__":
    print(f"BOT_TOKEN: {'✓ Установлен' if BOT_TOKEN else '✗ Не найден'}")
    print(f"TEMP_DIR: {TEMP_DIR}")
    print(f"MAX_FILE_SIZE: {MAX_FILE_SIZE // (1024*1024)} МБ")
    print(f"FFMPEG_PATH: {FFMPEG_PATH}")
    print(f"LOG_LEVEL: {LOG_LEVEL}")
