from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional
from datetime import datetime
class MessageLevel(Enum):
    DEBUG = auto()
    INFO = auto()
    SUCCESS = auto()                                                         
    WARNING = auto()
    ERROR = auto()
    @property
    def prefix(self) -> str:
        return {            MessageLevel.DEBUG: "🐛 DEBUG",            MessageLevel.INFO: "ℹ️ INFO",            MessageLevel.SUCCESS: "✅ SUCCESS",            MessageLevel.WARNING: "⚠️ WARNING",            MessageLevel.ERROR: "❌ ERROR",        }[self]
    @property
    def should_popup(self) -> bool:
        return self in (MessageLevel.ERROR, MessageLevel.WARNING)
    @property
    def tk_tag(self) -> str:
        return {            MessageLevel.DEBUG: "debug",            MessageLevel.INFO: "info",            MessageLevel.SUCCESS: "success",            MessageLevel.WARNING: "warning",            MessageLevel.ERROR: "error",        }[self]
@dataclass(frozen=True)
class AppMessage:
    text: str
    level: MessageLevel = MessageLevel.INFO
    timestamp: datetime = None
    source: Optional[str] = None
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', datetime.now())
    @classmethod
    def success(cls, text: str, source: str = None) -> 'AppMessage':
        return cls(text, MessageLevel.SUCCESS, source=source)
    @classmethod
    def info(cls, text: str, source: str = None) -> 'AppMessage':
        return cls(text, MessageLevel.INFO, source=source)
    @classmethod
    def warning(cls, text: str, source: str = None) -> 'AppMessage':
        return cls(text, MessageLevel.WARNING, source=source)
    @classmethod
    def error(cls, text: str, source: str = None) -> 'AppMessage':
        return cls(text, MessageLevel.ERROR, source=source)
    @classmethod
    def debug(cls, text: str, source: str = None) -> 'AppMessage':
        return cls(text, MessageLevel.DEBUG, source=source)
    @property
    def formatted(self) -> str:
        time_str = self.timestamp.strftime("%H:%M:%S")
        source_str = f"[{self.source}]" if self.source else ""
        return f"{time_str} {self.level.prefix}{source_str}: {self.text}"
    @property
    def plain_text(self) -> str:
        return self.text
    def __str__(self) -> str:
        return self.formatted