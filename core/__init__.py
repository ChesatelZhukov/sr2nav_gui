"""Ядро приложения - общие компоненты и контекст."""
from core.app_context import APP_CONTEXT, AppContext
from core.message_system import AppMessage, MessageLevel

__all__ = [
    'APP_CONTEXT',
    'AppContext',
    'AppMessage',
    'MessageLevel',
]