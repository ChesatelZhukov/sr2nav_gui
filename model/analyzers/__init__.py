"""
Пакет анализаторов данных для обработки навигационных измерений.

Содержит чистые модели (бизнес-логику) для различных видов анализа:
- Анализ скоростей (VelocityAnalyzer)
- Анализ GPS созвездия (GPSConstellationAnalyzer)

Все анализаторы следуют единому интерфейсу BaseAnalyzer и возвращают
результаты в формате AnalysisResult или его специализированных наследников.

Архитектура:
    BaseAnalyzer (абстрактный базовый класс)
    ├── VelocityAnalyzer
    │   ├── VelocityData - сырые данные скоростей
    │   ├── VelocityStatistics - статистические показатели
    │   └── VelocityAnalysisResult - объединённый результат
    └── GPSConstellationAnalyzer
        ├── SatelliteInterval - интервалы видимости спутников
        ├── SatelliteStatistics - статистика по спутнику
        ├── GPSConstellationData - данные о созвездии
        └── GPSConstellationAnalysisResult - полный результат анализа

Все классы в этом пакете не имеют зависимостей от UI и могут использоваться
в любом контексте (консольные утилиты, веб-сервисы, GUI приложения).
"""
from model.analyzers.base_analyzer import BaseAnalyzer, AnalysisResult
from model.analyzers.velocity_analyzer import (
    VelocityAnalyzer,
    VelocityData,
    VelocityStatistics,
    VelocityAnalysisResult
)
from model.analyzers.gps_constellation_analyzer import (
    GPSConstellationAnalyzer,
    SatelliteInterval,
    SatelliteStatistics,
    GPSConstellationData,
    GPSConstellationAnalysisResult
)

__all__ = [
    # Базовые классы
    'BaseAnalyzer',
    'AnalysisResult',
    
    # Компоненты анализа скоростей
    'VelocityAnalyzer',
    'VelocityData',
    'VelocityStatistics',
    'VelocityAnalysisResult',
    
    # Компоненты анализа GPS созвездия
    'GPSConstellationAnalyzer',
    'SatelliteInterval',
    'SatelliteStatistics',
    'GPSConstellationData',
    'GPSConstellationAnalysisResult',
]
