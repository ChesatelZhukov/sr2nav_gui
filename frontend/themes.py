#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Светлая цветовая тема для интерфейса.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """
    Светлая цветовая тема.
    Все цвета в формате HEX.
    """
    
    # Основные фоны
    BG_PRIMARY: str = "#f8f9fa"      # Светло-серый (основной фон)
    BG_SECONDARY: str = "#ffffff"     # Белый (карточки, панели)
    BG_TERTIARY: str = "#e9ecef"      # Чуть темнее для контраста
    
    # Текст
    FG_PRIMARY: str = "#212529"       # Почти чёрный (основной текст)
    FG_SECONDARY: str = "#6c757d"     # Серый (второстепенный текст)
    FG_DISABLED: str = "#adb5bd"      # Светло-серый (неактивный)
    
    # Границы
    BORDER: str = "#dee2e6"           # Светло-серая граница
    
    # Акцентные цвета
    ACCENT_BLUE: str = "#0d6efd"      # Синий (основной)
    ACCENT_GREEN: str = "#198754"     # Зелёный (успех)
    ACCENT_RED: str = "#dc3545"       # Красный (ошибка)
    ACCENT_ORANGE: str = "#fd7e14"    # Оранжевый (предупреждение)
    ACCENT_PURPLE: str = "#6f42c1"    # Фиолетовый (инструменты)
    ACCENT_CYAN: str = "#0dcaf0"      # Голубой (инфо)
    
    # Статусы
    SUCCESS: str = "#198754"          # Зелёный
    WARNING: str = "#ffc107"          # Жёлтый
    ERROR: str = "#dc3545"           # Красный
    INFO: str = "#0d6efd"           # Синий
    DEBUG: str = "#6c757d"          # Серый
    
    # Состояния
    HOVER: str = "#e9ecef"           # При наведении
    SELECTED: str = "#cfe2ff"        # Выбранный элемент
    DISABLED: str = "#e9ecef"        # Неактивный фон


def apply_theme(widget) -> None:
    """
    Рекурсивно применяет тему к виджету и его дочерним элементам.
    """
    bg = widget.cget('bg')
    
    if bg in ('SystemButtonFace', 'SystemWindow', '#f0f0f0'):
        try:
            widget.configure(bg=Theme.BG_PRIMARY)
        except:
            pass
    
    try:
        for child in widget.winfo_children():
            apply_theme(child)
    except:
        pass