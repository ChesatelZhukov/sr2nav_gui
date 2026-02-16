#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТОЕ ПРЕДСТАВЛЕНИЕ - Утилиты для сохранения состояния UI.
"""
import os, sys
from typing import Optional


class UIPersistence:
    """
    Хранит состояние интерфейса между вызовами диалогов.
    """
    _last_browse_dir: str = ""
    
    @classmethod
    def get_last_dir(cls) -> str:
        """Возвращает последнюю использованную папку."""
        return cls._last_browse_dir
    
    @classmethod
    def set_last_dir(cls, path: str) -> None:
        """Сохраняет последнюю использованную папку."""
        if path:
            # Для Windows путей длиннее 260 символов
            if sys.platform == 'win32' and len(path) > 240:
                path = '\\\\?\\' + path
            
            dir_path = os.path.dirname(path) if os.path.isfile(path) else path
            if dir_path and os.path.exists(dir_path):
                cls._last_browse_dir = dir_path
    
    @classmethod
    def update_from_path(cls, path: str) -> None:
        """Обновляет последнюю папку из выбранного файла."""
        if path and os.path.exists(path):
            cls._last_browse_dir = os.path.dirname(path)