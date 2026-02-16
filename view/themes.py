#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Светлая цветовая тема для интерфейса.

ИСПРАВЛЕНО v2.1: исправлена опечатка в комментарии
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """
    Светлая цветовая тема.
    Все цвета в формате HEX.
    """
    
    # Основные фоны
    BG_PRIMARY: str = "#f8f9fa"
    BG_SECONDARY: str = "#ffffff"
    BG_TERTIARY: str = "#e9ecef"
    
    # Текст
    FG_PRIMARY: str = "#212529"
    FG_SECONDARY: str = "#6c757d"
    FG_DISABLED: str = "#adb5bd"
    
    # Границы
    BORDER: str = "#dee2e6"
    
    # Акцентные цвета
    ACCENT_BLUE: str = "#0d6efd"
    ACCENT_GREEN: str = "#198754"
    ACCENT_RED: str = "#dc3545"
    ACCENT_ORANGE: str = "#fd7e14"
    ACCENT_PURPLE: str = "#6f42c1"
    ACCENT_CYAN: str = "#0dcaf0"
    
    # Статусы (исправлена опечатка в комментарии)
    SUCCESS: str = "#212529"
    WARNING: str = "#E7D10A"
    ERROR: str = "#dc3545"
    INFO: str = "#212529"
    DEBUG: str = "#212529"
    
    # Состояния
    HOVER: str = "#e9ecef"
    SELECTED: str = "#cfe2ff"
    DISABLED: str = "#e9ecef"


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