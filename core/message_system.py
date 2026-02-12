#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Унифицированная система сообщений для всего приложения.
Сообщения передаются между Backend -> Controller -> Frontend через очередь.
"""
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional
from datetime import datetime


class MessageLevel(Enum):
    """Уровни сообщений с визуальным приоритетом."""
    DEBUG = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    
    @property
    def prefix(self) -> str:
        """Префикс для отображения в логе."""
        return {
            MessageLevel.DEBUG: "🐛 DEBUG",
            MessageLevel.INFO: "ℹ️ INFO",
            MessageLevel.WARNING: "⚠️ WARNING",
            MessageLevel.ERROR: "❌ ERROR",
        }[self]
    
    @property
    def should_popup(self) -> bool:
        """Должно ли сообщение показываться как всплывающее окно."""
        return self in (MessageLevel.ERROR, MessageLevel.WARNING)
    
    @property
    def tk_tag(self) -> str:
        """Тег для подсветки в Tkinter Text."""
        return {
            MessageLevel.DEBUG: "debug",
            MessageLevel.INFO: "info",
            MessageLevel.WARNING: "warning",
            MessageLevel.ERROR: "error",
        }[self]


@dataclass(frozen=True)
class AppMessage:
    """
    Неизменяемое сообщение для передачи между компонентами.
    Содержит текст, уровень, источник и временную метку.
    """
    text: str
    level: MessageLevel = MessageLevel.INFO
    timestamp: datetime = None
    source: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', datetime.now())
    
    @classmethod
    def info(cls, text: str, source: str = None) -> 'AppMessage':
        """Создаёт информационное сообщение."""
        return cls(text, MessageLevel.INFO, source=source)
    
    @classmethod
    def warning(cls, text: str, source: str = None) -> 'AppMessage':
        """Создаёт предупреждение."""
        return cls(text, MessageLevel.WARNING, source=source)
    
    @classmethod
    def error(cls, text: str, source: str = None) -> 'AppMessage':
        """Создаёт сообщение об ошибке."""
        return cls(text, MessageLevel.ERROR, source=source)
    
    @classmethod
    def debug(cls, text: str, source: str = None) -> 'AppMessage':
        """Создаёт отладочное сообщение."""
        return cls(text, MessageLevel.DEBUG, source=source)
    
    @property
    def formatted(self) -> str:
        """Форматированное сообщение для вывода в консоль/лог."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        source_str = f"[{self.source}]" if self.source else ""
        return f"{time_str} {self.level.prefix}{source_str}: {self.text}"
    
    @property
    def plain_text(self) -> str:
        """Только текст сообщения (без префиксов)."""
        return self.text
    
    def __str__(self) -> str:
        return self.formatted