"""
ЧИСТАЯ МОДЕЛЬ - Бизнес-логика приложения.
НИКАКОГО UI, ТОЛЬКО ФАЙЛОВЫЕ ОПЕРАЦИИ И АЛГОРИТМЫ!
"""
from model.file_manager import FileManager, FileType, TimeInterval
from model.process_runner import ProcessRunner, ProcessType, ProcessStatus
from model.gps_excluder import GPSExcluder
from model.file_transformer import FileTransformer, TransformerFileType

# Анализаторы - чистые алгоритмы, без UI
from model.analyzers.velocity_analyzer import VelocityAnalyzer, VelocityData, VelocityStatistics, VelocityAnalysisResult
from model.analyzers.gps_constellation_analyzer import (
    GPSConstellationAnalyzer,
    SatelliteInterval,
    SatelliteStatistics,
    GPSConstellationData,
    GPSConstellationAnalysisResult
)

__all__ = [
    # File Manager
    'FileManager',
    'FileType',
    'TimeInterval',
    
    # Process Runner
    'ProcessRunner',
    'ProcessType',
    'ProcessStatus',
    
    # GPS Excluder
    'GPSExcluder',
    
    # File Transformer
    'FileTransformer',
    'TransformerFileType',
    
    # Velocity Analyzer
    'VelocityAnalyzer',
    'VelocityData',
    'VelocityStatistics',
    'VelocityAnalysisResult',
    
    # GPS Constellation Analyzer
    'GPSConstellationAnalyzer',
    'SatelliteInterval',
    'SatelliteStatistics',
    'GPSConstellationData',
    'GPSConstellationAnalysisResult',
]