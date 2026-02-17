#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утилиты для сохранения состояния пользовательского интерфейса между сессиями.

Обеспечивает персистентность данных UI, таких как последняя выбранная папка
и выбранная цветовая тема, чтобы при повторных запусках пользователь
возвращался в то же состояние.

Архитектурные принципы:
    - Класс-синглтон с класс-методами (не требует инстанцирования)
    - Не имеет зависимостей от других компонентов
    - Работает с файловой системой только для проверки существования путей
    - Учитывает особенности Windows (длинные пути >260 символов)
    - Сохраняет выбранную тему в конфигурационном файле

На текущий момент хранит:
    - Последнюю использованную директорию для диалогов открытия/сохранения
    - Выбранную цветовую тему приложения

В будущем может быть расширен для сохранения:
    - Размера и положения окон
    - Последних выбранных настроек
    - Состояния сворачиваемых панелей
"""
import os
import sys
import configparser
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from view.themes import ThemeType, get_theme_name

logger = logging.getLogger(__name__)


class UIPersistence:
    """
    Хранилище состояния пользовательского интерфейса.
    
    Использует класс-методы для глобального доступа без необходимости
    создавать экземпляр. Все данные хранятся в класс-атрибутах.
    Сохраняет состояние в ini-файл при изменениях.
    
    Формат файла (user_prefs.ini):
        [LastUsed]
        directory = C:\path\to\last\dir
        theme = DARK
        
        [Window]
        width = 1400
        height = 850
    
    Пример использования:
        >>> # Сохранение после выбора файла
        >>> UIPersistence.set_last_dir("/home/user/data/")
        >>> 
        >>> # Сохранение выбранной темы
        >>> UIPersistence.set_theme(ThemeType.DARK)
        >>> 
        >>> # Восстановление при следующем запуске
        >>> initial_dir = UIPersistence.get_last_dir()
        >>> theme = UIPersistence.get_theme()
    
    Особенности:
        - Для Windows автоматически добавляет префикс '\\\\?\\' для длинных путей
        - Проверяет существование путей перед сохранением
        - Из пути к файлу извлекает директорию
        - Автоматически сохраняет изменения в файл при вызове save()
    """
    
    _CONFIG_FILE = "user_prefs.ini"
    _SECTION_LAST_USED = "LastUsed"
    _SECTION_WINDOW = "Window"
    
    # Ключи для ini-файла
    _KEY_DIRECTORY = "directory"
    _KEY_THEME = "theme"
    _KEY_WIDTH = "width"
    _KEY_HEIGHT = "height"
    
    # Состояние в памяти
    _last_browse_dir: str = ""
    _selected_theme: str = "DARK"  # Храним как строку для совместимости
    _window_width: int = 1400
    _window_height: int = 850
    _config_dir: Optional[Path] = None
    _config: configparser.ConfigParser = None
    _dirty: bool = False
    
    @classmethod
    def initialize(cls, config_dir: Path) -> None:
        """
        Инициализирует хранилище с указанием директории для конфигов.
        
        Должен вызываться при запуске приложения до первого использования.
        
        Args:
            config_dir: Директория для сохранения конфигурационного файла
        """
        cls._config_dir = config_dir
        cls._config = configparser.ConfigParser()
        cls._load()
    
    @classmethod
    def _get_config_path(cls) -> Path:
        """Возвращает полный путь к конфигурационному файлу."""
        if cls._config_dir is None:
            # Если не инициализировано, используем текущую директорию
            cls._config_dir = Path.cwd()
        return cls._config_dir / cls._CONFIG_FILE
    
    @classmethod
    def _load(cls) -> None:
        """Загружает конфигурацию из файла, если он существует."""
        config_path = cls._get_config_path()
        
        if config_path.exists():
            try:
                cls._config.read(config_path, encoding='utf-8')
                logger.debug(f"Конфигурация UI загружена из {config_path}")
                
                # Загружаем последнюю директорию
                if cls._config.has_section(cls._SECTION_LAST_USED):
                    if cls._config.has_option(cls._SECTION_LAST_USED, cls._KEY_DIRECTORY):
                        dir_path = cls._config.get(cls._SECTION_LAST_USED, cls._KEY_DIRECTORY)
                        if dir_path and os.path.exists(dir_path):
                            cls._last_browse_dir = dir_path
                    
                    if cls._config.has_option(cls._SECTION_LAST_USED, cls._KEY_THEME):
                        cls._selected_theme = cls._config.get(cls._SECTION_LAST_USED, cls._KEY_THEME)
                
                # Загружаем размер окна
                if cls._config.has_section(cls._SECTION_WINDOW):
                    if cls._config.has_option(cls._SECTION_WINDOW, cls._KEY_WIDTH):
                        try:
                            cls._window_width = int(cls._config.get(cls._SECTION_WINDOW, cls._KEY_WIDTH))
                        except:
                            pass
                    if cls._config.has_option(cls._SECTION_WINDOW, cls._KEY_HEIGHT):
                        try:
                            cls._window_height = int(cls._config.get(cls._SECTION_WINDOW, cls._KEY_HEIGHT))
                        except:
                            pass
                        
            except Exception as e:
                logger.error(f"Ошибка загрузки конфигурации UI: {e}")
                cls._config = configparser.ConfigParser()
        else:
            logger.info(f"Файл конфигурации UI не найден, будет создан при сохранении")
            cls._config = configparser.ConfigParser()
        
        # Убеждаемся, что секции существуют
        if not cls._config.has_section(cls._SECTION_LAST_USED):
            cls._config.add_section(cls._SECTION_LAST_USED)
        if not cls._config.has_section(cls._SECTION_WINDOW):
            cls._config.add_section(cls._SECTION_WINDOW)
    
    @classmethod
    def save(cls) -> bool:
        """
        Сохраняет текущие настройки в конфигурационный файл, если были изменения.
        
        Returns:
            True, если сохранение прошло успешно или не требовалось, False в случае ошибки.
        """
        if not cls._dirty:
            return True
        
        config_path = cls._get_config_path()
        
        try:
            # Создаем директорию, если её нет
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                cls._config.write(f)
            
            logger.debug(f"Конфигурация UI сохранена в {config_path}")
            cls._dirty = False
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения конфигурации UI: {e}")
            return False
    
    # ==================== УПРАВЛЕНИЕ ДИРЕКТОРИЕЙ ====================
    
    @classmethod
    def get_last_dir(cls) -> str:
        """
        Возвращает последнюю использованную директорию.
        
        Returns:
            Путь к последней директории или пустая строка, если ещё не было выбора.
        """
        return cls._last_browse_dir
    
    @classmethod
    def set_last_dir(cls, path: str) -> None:
        """
        Сохраняет последнюю использованную директорию.
        
        Args:
            path: Путь к файлу или директории, который был выбран пользователем.
        """
        if not path:
            return
        
        # Для Windows путей длиннее 240 символов используем длинный путь
        if sys.platform == 'win32' and len(path) > 240:
            path = '\\\\?\\' + path
        
        # Извлекаем директорию, если передан путь к файлу
        dir_path = os.path.dirname(path) if os.path.isfile(path) else path
        
        # Сохраняем только если директория существует
        if dir_path and os.path.exists(dir_path):
            if cls._last_browse_dir != dir_path:
                cls._last_browse_dir = dir_path
                cls._config.set(cls._SECTION_LAST_USED, cls._KEY_DIRECTORY, dir_path)
                cls._dirty = True
    
    @classmethod
    def update_from_path(cls, path: str) -> None:
        """
        Обновляет последнюю директорию из пути к файлу.
        
        Args:
            path: Путь к файлу, выбранному пользователем.
        """
        cls.set_last_dir(path)
    
    # ==================== УПРАВЛЕНИЕ ТЕМОЙ ====================
    
    @classmethod
    def get_theme(cls) -> ThemeType:
        """
        Возвращает сохранённую тему.
        
        Returns:
            ThemeType: Сохранённая тема или DARK по умолчанию.
        """
        try:
            return ThemeType[cls._selected_theme.upper()]
        except (KeyError, AttributeError):
            return ThemeType.DARK
    
    @classmethod
    def get_theme_name(cls) -> str:
        """
        Возвращает название сохранённой темы для отображения.
        
        Returns:
            str: Название темы
        """
        theme = cls.get_theme()
        return get_theme_name(theme)
    
    @classmethod
    def set_theme(cls, theme_type: ThemeType) -> None:
        """
        Сохраняет выбранную тему.
        
        Args:
            theme_type: Тип темы из ThemeType
        """
        theme_str = theme_type.name
        if cls._selected_theme != theme_str:
            cls._selected_theme = theme_str
            cls._config.set(cls._SECTION_LAST_USED, cls._KEY_THEME, theme_str)
            cls._dirty = True
    
    # ==================== УПРАВЛЕНИЕ РАЗМЕРОМ ОКНА ====================
    
    @classmethod
    def get_window_size(cls) -> tuple[int, int]:
        """
        Возвращает сохранённый размер окна.
        
        Returns:
            tuple[int, int]: (ширина, высота)
        """
        return cls._window_width, cls._window_height
    
    @classmethod
    def set_window_size(cls, width: int, height: int) -> None:
        """
        Сохраняет размер окна.
        
        Args:
            width: Ширина окна
            height: Высота окна
        """
        if cls._window_width != width:
            cls._window_width = width
            cls._config.set(cls._SECTION_WINDOW, cls._KEY_WIDTH, str(width))
            cls._dirty = True
        
        if cls._window_height != height:
            cls._window_height = height
            cls._config.set(cls._SECTION_WINDOW, cls._KEY_HEIGHT, str(height))
            cls._dirty = True
    
    # ==================== ОБЩИЕ МЕТОДЫ ====================
    
    @classmethod
    def get_all_settings(cls) -> Dict[str, Any]:
        """
        Возвращает словарь всех сохранённых настроек.
        
        Returns:
            Dict[str, Any]: Все настройки UI
        """
        return {
            'last_dir': cls._last_browse_dir,
            'theme': cls._selected_theme,
            'window_width': cls._window_width,
            'window_height': cls._window_height,
        }