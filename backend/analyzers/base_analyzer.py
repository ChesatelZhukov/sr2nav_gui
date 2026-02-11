#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Базовый класс для всех анализаторов данных.
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
    """
    
    def __init__(self, results_dir: Path):
        """
        :param results_dir: Директория с результатами
        """
        self._results_dir = Path(results_dir)
        self._results: Dict[str, AnalysisResult] = {}
    
    @abstractmethod
    def find_files(self) -> List[Path]:
        """Находит файлы для анализа."""
        pass
    
    @abstractmethod
    def analyze_file(self, filepath: Path) -> AnalysisResult:
        """Анализирует один файл."""
        pass
    
    def analyze_all(self) -> Dict[str, AnalysisResult]:
        """
        Анализирует все найденные файлы.
        
        Returns:
            Словарь {имя_файла: результат}
        """
        files = self.find_files()
        
        for filepath in files:
            try:
                result = self.analyze_file(filepath)
                self._results[filepath.name] = result
            except Exception as e:
                self._results[filepath.name] = AnalysisResult(
                    filename=filepath.name,
                    filepath=filepath,
                    timestamp=datetime.now(),
                    success=False,
                    error=str(e),
                )
        
        return self._results
    
    def get_result(self, filename: str) -> Optional[AnalysisResult]:
        """Возвращает результат анализа по имени файла."""
        return self._results.get(filename)
    
    @property
    def all_results(self) -> Dict[str, AnalysisResult]:
        """Все результаты анализа."""
        return self._results.copy()