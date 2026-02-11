"""
Пакет анализаторов данных.
Предоставляет классы для анализа VEL файлов и GPS созвездия.
"""

from backend.analyzers.base_analyzer import BaseAnalyzer, AnalysisResult
from backend.analyzers.velocity_analyzer import (
    VelocityFileAnalyzer,
    VelocityAnalysis,
    VelocityStats,
)
from backend.analyzers.gps_constellation_analyzer import (
    GPSConstellationAnalyzer,
    ConstellationAnalysis,
    SatelliteStats,
    SatelliteInterval,
)

__all__ = [
    # Базовый класс
    'BaseAnalyzer',
    'AnalysisResult',
    
    # Анализатор скоростей
    'VelocityFileAnalyzer',
    'VelocityAnalysis',
    'VelocityStats',
    
    # Анализатор GPS созвездия
    'GPSConstellationAnalyzer',
    'ConstellationAnalysis',
    'SatelliteStats',
    'SatelliteInterval',
]