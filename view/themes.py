#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Централизованное управление цветовыми темами приложения.

Обеспечивает:
    - Единый источник всех цветов для UI
    - Переключение между темами (тёмная, светлая, барби)
    - Сохранение выбранной темы в user_paths.txt
    - Автоматическое применение темы при запуске
    - Валидацию выбранной темы при загрузке

Архитектурные принципы:
    - Все цвета определены как константы в Theme классе
    - Поддержка нескольких тем через ThemeType
    - Функция get_theme() для получения активной темы
    - Функция apply_theme() для рекурсивного применения темы к виджетам
"""
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, Optional
import tkinter as tk


class ThemeType(Enum):
    """Доступные цветовые темы приложения."""
    DARK = auto()       # Тёмная тема (по умолчанию)
    LIGHT = auto()      # Светлая тема
    BARBIE = auto()     # Розовая тема "Барби"


@dataclass(frozen=True)
class ThemeColors:
    """
    Контейнер с цветами для конкретной темы.
    
    Все цвета представлены в формате HEX-строк, которые напрямую
    принимаются Tkinter (например, "#2d2d2d").
    
    Группы цветов:
        - BG_*: фоновые цвета различных уровней
        - FG_*: цвета текста
        - ACCENT_*: акцентные цвета для кнопок и выделения
        - Статусные цвета (SUCCESS, WARNING, ERROR, INFO, DEBUG)
        - Состояния (HOVER, SELECTED, DISABLED)
    """
    
    # ============ ОСНОВНЫЕ ФОНЫ ============
    BG_PRIMARY: str      # Основной фон окна
    BG_SECONDARY: str    # Фон вложенных элементов (панели, карточки)
    BG_TERTIARY: str     # Фон для выделенных областей
    
    # ============ ЦВЕТА ТЕКСТА ============
    FG_PRIMARY: str      # Основной текст
    FG_SECONDARY: str    # Второстепенный текст (подписи, статусы)
    FG_DISABLED: str     # Текст в отключённых элементах
    
    # ============ ГРАНИЦЫ И РАЗДЕЛИТЕЛИ ============
    BORDER: str          # Цвет рамок и разделительных линий
    
    # ============ АКЦЕНТНЫЕ ЦВЕТА ============
    ACCENT_BLUE: str     # Основной акцент (действия)
    ACCENT_GREEN: str    # Успешные операции
    ACCENT_RED: str      # Опасные действия, ошибки
    ACCENT_ORANGE: str   # Предупреждения, внимание
    ACCENT_PURPLE: str   # Дополнительные действия
    ACCENT_CYAN: str     # Информационные элементы
    
    # ============ СТАТУСНЫЕ ЦВЕТА ============
    SUCCESS: str         # Успешное завершение
    WARNING: str         # Предупреждения
    ERROR: str           # Ошибки
    INFO: str            # Информация
    DEBUG: str           # Отладочная информация
    
    # ============ СОСТОЯНИЯ ЭЛЕМЕНТОВ ============
    HOVER: str           # При наведении мыши
    SELECTED: str        # Выбранный элемент
    DISABLED: str        # Отключённый элемент


# ==================== ОПРЕДЕЛЕНИЕ ТЕМ ====================

DARK_THEME = ThemeColors(
    # Основные фоны
    BG_PRIMARY="#1a1b1e",
    BG_SECONDARY="#2c2e33",
    BG_TERTIARY="#3a3c44",
    
    # Цвета текста
    FG_PRIMARY="#e8e9ed",
    FG_SECONDARY="#9a9ca5",
    FG_DISABLED="#5f616a",
    
    # Границы
    BORDER="#40434a",
    
    # Акценты
    ACCENT_BLUE="#5f8ec9",
    ACCENT_GREEN="#6f9e6f",
    ACCENT_RED="#c96b6b",
    ACCENT_ORANGE="#c99a6b",
    ACCENT_PURPLE="#9f8cc9",
    ACCENT_CYAN="#6b9ec9",
    
    # Статусные цвета
    SUCCESS="#8fbc8f",
    WARNING="#e0b080",
    ERROR="#d98c8c",
    INFO="#80b0e0",
    DEBUG="#b0a0d0",
    
    # Состояния
    HOVER="#3e4048",
    SELECTED="#2a4f6e",
    DISABLED="#2a2c30",
)


LIGHT_THEME = ThemeColors(
    # Основные фоны
    BG_PRIMARY="#f5f5f5",
    BG_SECONDARY="#ffffff",
    BG_TERTIARY="#e8e8e8",
    
    # Цвета текста
    FG_PRIMARY="#333333",
    FG_SECONDARY="#666666",
    FG_DISABLED="#999999",
    
    # Границы
    BORDER="#cccccc",
    
    # Акценты
    ACCENT_BLUE="#0066cc",
    ACCENT_GREEN="#2e7d32",
    ACCENT_RED="#c62828",
    ACCENT_ORANGE="#ed6c02",
    ACCENT_PURPLE="#7b1fa2",
    ACCENT_CYAN="#0097a7",
    
    # Статусные цвета
    SUCCESS="#2e7d32",
    WARNING="#ed6c02",
    ERROR="#c62828",
    INFO="#0288d1",
    DEBUG="#7b1fa2",
    
    # Состояния
    HOVER="#e0e0e0",
    SELECTED="#bbdefb",
    DISABLED="#f0f0f0",
)


BARBIE_THEME = ThemeColors(
    # Основные фоны - ВСЁ РОЗОВОЕ!
    BG_PRIMARY="#FFB6C1",      # Светло-розовый
    BG_SECONDARY="#FFC0CB",     # Нежно-розовый
    BG_TERTIARY="#FFA6C9",      # Тёплый розовый
    
    # Цвета текста
    FG_PRIMARY="#000000",       # Белый на розовом
    FG_SECONDARY="#000000",      # Горячий розовый
    FG_DISABLED="#000000",       # Бледно-розовый
    
    # Границы
    BORDER="#FF1493",           # Глубокий розовый
    
    # Акценты - ВСЁ ТОЖЕ РОЗОВОЕ!
    ACCENT_BLUE="#FF69B4",      # Hot Pink
    ACCENT_GREEN="#FF85B3",      # Розовый
    ACCENT_RED="#FF4D6D",        # Ярко-розовый
    ACCENT_ORANGE="#FFA07A",     # Светло-лососевый
    ACCENT_PURPLE="#DA70D6",     # Орхидея
    ACCENT_CYAN="#FFB3C6",       # Бледно-розовый
    
    # Статусные цвета
    SUCCESS="#FFC0CB",          # Розовый
    WARNING="#FFB347",           # Персиковый
    ERROR="#FF6B8B",             # Светло-розово-красный
    INFO="#FFB6C1",              # Светло-розовый
    DEBUG="#FFA6C9",             # Тёплый розовый
    
    # Состояния
    HOVER="#FF1493",            # Глубокий розовый
    SELECTED="#FF69B4",          # Горячий розовый
    DISABLED="#FFB6C1",          # Бледно-розовый
)


# ==================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ТЕМЫ ====================

_THEMES: Dict[ThemeType, ThemeColors] = {
    ThemeType.DARK: DARK_THEME,
    ThemeType.LIGHT: LIGHT_THEME,
    ThemeType.BARBIE: BARBIE_THEME,
}

_ACTIVE_THEME: ThemeType = ThemeType.DARK


def set_active_theme(theme_type: ThemeType) -> None:
    """
    Устанавливает активную тему.
    
    Args:
        theme_type: Тип темы из ThemeType
    """
    global _ACTIVE_THEME
    if theme_type in _THEMES:
        _ACTIVE_THEME = theme_type


def get_active_theme() -> ThemeColors:
    """
    Возвращает цвета активной темы.
    
    Returns:
        ThemeColors: Цвета текущей активной темы
    """
    return _THEMES[_ACTIVE_THEME]


def get_theme_colors(theme_type: Optional[ThemeType] = None) -> ThemeColors:
    """
    Возвращает цвета указанной темы или активной, если тема не указана.
    
    Args:
        theme_type: Тип темы (если None, возвращается активная тема)
        
    Returns:
        ThemeColors: Цвета запрошенной темы
    """
    if theme_type is None:
        return get_active_theme()
    return _THEMES.get(theme_type, get_active_theme())


def get_theme_name(theme_type: ThemeType) -> str:
    """
    Возвращает человекочитаемое название темы.
    
    Args:
        theme_type: Тип темы
        
    Returns:
        str: Название темы для отображения в UI
    """
    names = {
        ThemeType.DARK: "🌙 Тёмная",
        ThemeType.LIGHT: "☀️ Светлая",
        ThemeType.BARBIE: "💖 Барби",
    }
    return names.get(theme_type, "Неизвестная")


def get_all_themes() -> Dict[ThemeType, str]:
    """
    Возвращает словарь всех доступных тем с их названиями.
    
    Returns:
        Dict[ThemeType, str]: Словарь {тип_темы: название}
    """
    return {theme_type: get_theme_name(theme_type) for theme_type in ThemeType}


def apply_theme(widget: tk.Widget, theme_colors: Optional[ThemeColors] = None) -> None:
    """
    Рекурсивно применяет тему к виджету и всем его дочерним элементам.
    
    Функция изменяет фон виджетов, которые используют системные цвета
    по умолчанию ('SystemButtonFace', 'SystemWindow', '#f0f0f0'),
    заменяя их на основной цвет темы (BG_PRIMARY).
    
    Args:
        widget: Виджет Tkinter, к которому применяется тема
        theme_colors: Цвета темы (если None, используется активная тема)
    
    Note:
        - Функция рекурсивно обходит всех потомков виджета
        - Изменяет только фон, цвета текста нужно устанавливать отдельно
        - Не выбрасывает исключения при ошибках применения темы
        - Подходит для применения после создания всех виджетов
    
    Example:
        >>> root = tk.Tk()
        >>> create_all_widgets(root)
        >>> apply_theme(root, get_active_theme())
    """
    if theme_colors is None:
        theme_colors = get_active_theme()
    
    # Получаем текущий цвет фона виджета
    try:
        bg = widget.cget('bg')
    except:
        bg = None
    
    # Если виджет использует системный цвет по умолчанию, меняем его
    if bg in ('SystemButtonFace', 'SystemWindow', '#f0f0f0'):
        try:
            widget.configure(bg=theme_colors.BG_PRIMARY)
        except:
            # Некоторые виджеты могут не поддерживать изменение bg
            pass
    
    # Рекурсивно обрабатываем дочерние виджеты
    try:
        for child in widget.winfo_children():
            apply_theme(child, theme_colors)
    except:
        # Некоторые виджеты могут не иметь winfo_children
        pass


# Для обратной совместимости с существующим кодом
# Эти константы будут возвращать цвета активной темы
@property
def Theme_BG_PRIMARY(self):
    return get_active_theme().BG_PRIMARY

# Создаём класс-обёртку для обратной совместимости
class Theme:
    """
    Класс для обратной совместимости с существующим кодом.
    
    Все атрибуты динамически возвращают цвета из активной темы.
    """
    
    @property
    def BG_PRIMARY(self): return get_active_theme().BG_PRIMARY
    @property
    def BG_SECONDARY(self): return get_active_theme().BG_SECONDARY
    @property
    def BG_TERTIARY(self): return get_active_theme().BG_TERTIARY
    
    @property
    def FG_PRIMARY(self): return get_active_theme().FG_PRIMARY
    @property
    def FG_SECONDARY(self): return get_active_theme().FG_SECONDARY
    @property
    def FG_DISABLED(self): return get_active_theme().FG_DISABLED
    
    @property
    def BORDER(self): return get_active_theme().BORDER
    
    @property
    def ACCENT_BLUE(self): return get_active_theme().ACCENT_BLUE
    @property
    def ACCENT_GREEN(self): return get_active_theme().ACCENT_GREEN
    @property
    def ACCENT_RED(self): return get_active_theme().ACCENT_RED
    @property
    def ACCENT_ORANGE(self): return get_active_theme().ACCENT_ORANGE
    @property
    def ACCENT_PURPLE(self): return get_active_theme().ACCENT_PURPLE
    @property
    def ACCENT_CYAN(self): return get_active_theme().ACCENT_CYAN
    
    @property
    def SUCCESS(self): return get_active_theme().SUCCESS
    @property
    def WARNING(self): return get_active_theme().WARNING
    @property
    def ERROR(self): return get_active_theme().ERROR
    @property
    def INFO(self): return get_active_theme().INFO
    @property
    def DEBUG(self): return get_active_theme().DEBUG
    
    @property
    def HOVER(self): return get_active_theme().HOVER
    @property
    def SELECTED(self): return get_active_theme().SELECTED
    @property
    def DISABLED(self): return get_active_theme().DISABLED


# Создаём глобальный экземпляр для обратной совместимости
Theme = Theme()