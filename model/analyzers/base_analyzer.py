#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТАЯ МОДЕЛЬ - Базовый класс для всех анализаторов данных.
Только абстрактные методы, никакой реализации UI!
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class AnalysisResult:
    """Базовый результат анализа."""
    filename: str
    filepath: Path
    timestamp: datetime
    success: bool
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class BaseAnalyzer(ABC):
    """
    Абстрактный базовый анализатор.
    
    Все конкретные анализаторы должны наследоваться от этого класса.
    Только определение интерфейса, никакой реализации!
    """
    
    def __init__(self):
        self._results: Dict[str, AnalysisResult] = {}
    
    @abstractmethod
    def find_files(self, directory: str) -> List[str]:
        """Находит файлы для анализа в указанной директории."""
        pass
    
    @abstractmethod
    def analyze_file(self, filepath: str) -> Optional[AnalysisResult]:
        """Анализирует один файл."""
        pass
    
    def analyze_all(self, directory: str) -> Dict[str, AnalysisResult]:
        """
        Анализирует все найденные файлы.
        
        Args:
            directory: Директория с файлами для анализа
            
        Returns:
            Словарь {имя_файла: результат}
        """
        self._results.clear()
        files = self.find_files(directory)
        
        for filepath in files:
            try:
                result = self.analyze_file(filepath)
                if result:
                    self._results[result.filename] = result
            except Exception as e:
                filename = Path(filepath).name
                self._results[filename] = AnalysisResult(
                    filename=filename,
                    filepath=Path(filepath),
                    timestamp=datetime.now(),
                    success=False,
                    error=str(e),
                )
        
        return self.get_results()
    
    def get_results(self) -> Dict[str, AnalysisResult]:
        """Возвращает все результаты анализа."""
        return self._results.copy()
    
    def get_result(self, filename: str) -> Optional[AnalysisResult]:
        """Возвращает результат анализа по имени файла."""
        return self._results.get(filename)
    
    def clear_results(self) -> None:
        """Очищает результаты анализа."""
        self._results.clear()