"""
ЧИСТОЕ ПРЕДСТАВЛЕНИЕ - Графический интерфейс пользователя.
ТОЛЬКО UI, НИКАКОЙ БИЗНЕС-ЛОГИКИ!

ИСПРАВЛЕНО v2.1: добавлен UIPersistence в __all__
"""
from view.themes import Theme
from view.widgets import ModernButton, FileEntryWidget, CollapsibleFrame, InteractiveZoom
from view.dialogs import GPSExclusionDialog, TransformFileDialog
from view.main_window import MainWindow, UIPersistence  # Импортируем UIPersistence
from view.analysis_windows.velocity_window import VelocityAnalysisWindow
from view.analysis_windows.gps_window import GPSAnalysisWindow

__all__ = [
    # Themes
    'Theme',
    
    # Widgets
    'ModernButton',
    'FileEntryWidget',
    'CollapsibleFrame',
    'InteractiveZoom',
    
    # Dialogs
    'GPSExclusionDialog',
    'TransformFileDialog',
    
    # Windows
    'MainWindow',
    'UIPersistence',  # <-- ДОБАВЛЕНО
    'VelocityAnalysisWindow',
    'GPSAnalysisWindow',
]