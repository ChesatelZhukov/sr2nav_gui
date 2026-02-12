"""
ЧИСТОЕ ПРЕДСТАВЛЕНИЕ - Пакет окон аналитики.
Только UI, данные получают от контроллера!
"""
from view.analysis_windows.velocity_window import VelocityAnalysisWindow
from view.analysis_windows.gps_window import GPSAnalysisWindow

__all__ = [
    'VelocityAnalysisWindow',
    'GPSAnalysisWindow',
]