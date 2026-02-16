#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТОЕ ПРЕДСТАВЛЕНИЕ - Утилиты для сохранения состояния UI.
НИКАКОЙ БИЗНЕС-ЛОГИКИ, только хранение состояния между вызовами!
"""
import os
from typing import Optional


class UIPersistence:
    """
    Хранит состояние интерфейса между вызовами диалогов.
    ТОЛЬКО ДЛЯ UI - никакой бизнес-логики!
    """
    _last_browse_dir: str = ""
    
    @classmethod
    def get_last_dir(cls) -> str:
        """Возвращает последнюю использованную папку."""
        return cls._last_browse_dir
    
    @classmethod
    def set_last_dir(cls, path: str) -> None:
        """Сохраняет последнюю использованную папку."""
        if path and os.path.exists(os.path.dirname(path)):
            cls._last_browse_dir = os.path.dirname(path)
    
    @classmethod
    def update_from_path(cls, path: str) -> None:
        """Обновляет последнюю папку из выбранного файла."""
        if path and os.path.exists(path):
            cls._last_browse_dir = os.path.dirname(path)