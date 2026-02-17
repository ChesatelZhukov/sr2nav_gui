#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Базовый класс для всех анализаторов данных.

Определяет единый интерфейс для анализа файлов в пакете model.analyzers.
Все конкретные анализаторы должны наследоваться от BaseAnalyzer и реализовывать
абстрактные методы find_files и analyze_file.

Архитектура:
    BaseAnalyzer (ABC)
    ├── find_files() - абстрактный, определяет какие файлы анализировать
    ├── analyze_file() - абстрактный, реализует логику анализа
    └── analyze_all() - шаблонный метод, orchestrates the analysis flow

Результаты анализа сохраняются в AnalysisResult и могут содержать
произвольные данные в поле data.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AnalysisResult:
    """
    Базовый контейнер для результатов анализа одного файла.
    
    Содержит общую для всех анализаторов информацию: имя файла, путь,
    временную метку, статус выполнения. Специфичные для конкретного
    анализа данные хранятся в поле data.
    
    Attributes:
        filename: Имя файла (без пути)
        filepath: Полный путь к файлу
        timestamp: Время выполнения анализа
        success: Флаг успешности анализа
        error: Сообщение об ошибке (если success=False)
        data: Специфичные для анализатора данные в свободном формате
    
    Example:
        >>> result = AnalysisResult(
        ...     filename="rover_2023.jps",
        ...     filepath=Path("/data/rover_2023.jps"),
        ...     timestamp=datetime.now(),
        ...     success=True,
        ...     data={"mean_velocity": 1.23, "max_velocity": 4.56}
        ... )
    """
    filename: str
    filepath: Path
    timestamp: datetime
    success: bool
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class BaseAnalyzer(ABC):
    """
    Абстрактный базовый класс для всех анализаторов данных.
    
    Определяет контракт, который должны реализовать конкретные анализаторы.
    Предоставляет готовую реализацию пакетного анализа через метод analyze_all.
    
    Анализаторы, наследующие этот класс, должны:
        1. Реализовать find_files() для определения набора входных файлов
        2. Реализовать analyze_file() для логики обработки одного файла
        3. При необходимости переопределить другие методы
    
    Attributes:
        _results: Внутреннее хранилище результатов анализа (кэш)
    
    Example:
        >>> class MyAnalyzer(BaseAnalyzer):
        ...     def find_files(self, directory):
        ...         return list(Path(directory).glob("*.dat"))
        ...     
        ...     def analyze_file(self, filepath):
        ...         # логика анализа
        ...         return AnalysisResult(...)
    """
    
    def __init__(self):
        """Инициализирует анализатор с пустым кэшем результатов."""
        self._results: Dict[str, AnalysisResult] = {}
    
    @abstractmethod
    def find_files(self, directory: str) -> List[str]:
        """
        Находит все файлы в директории, подлежащие анализу.
        
        Этот метод должен быть реализован в конкретном анализаторе
        и определять, какие именно файлы нужны для анализа (по расширению,
        по шаблону имени, по содержимому и т.д.).
        
        Args:
            directory: Путь к директории для поиска файлов
            
        Returns:
            Список абсолютных или относительных путей к файлам для анализа
            
        Note:
            Метод может возвращать как строки, так и объекты Path,
            но в интерфейсе указан List[str] для совместимости.
        """
        pass
    
    @abstractmethod
    def analyze_file(self, filepath: str) -> Optional[AnalysisResult]:
        """
        Анализирует один файл и возвращает результат.
        
        Основной метод, содержащий логику анализа. Должен быть реализован
        в каждом конкретном анализаторе.
        
        Args:
            filepath: Путь к файлу для анализа
            
        Returns:
            AnalysisResult если анализ успешен, None если файл не подходит
            для анализа (но это не ошибка)
            
        Raises:
            Различные исключения в зависимости от реализации. Исключения
            будут перехвачены в analyze_all и преобразованы в результат
            с success=False.
        """
        pass
    
    def analyze_all(self, directory: str) -> Dict[str, AnalysisResult]:
        """
        Выполняет пакетный анализ всех найденных файлов.
        
        Этот метод реализует шаблон "Template Method":
            1. Находит все файлы через find_files()
            2. Для каждого файла вызывает analyze_file()
            3. Собирает результаты, обрабатывая исключения
            4. Возвращает словарь с результатами
        
        Args:
            directory: Директория с файлами для анализа
            
        Returns:
            Словарь, где ключ — имя файла, значение — результат анализа
            
        Note:
            Результаты также сохраняются во внутреннем кэше _results
            и могут быть получены позже через get_results().
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
        """
        Возвращает копию всех результатов анализа.
        
        Returns:
            Словарь с результатами последнего вызова analyze_all()
        """
        return self._results.copy()
    
    def get_result(self, filename: str) -> Optional[AnalysisResult]:
        """
        Возвращает результат анализа для конкретного файла.
        
        Args:
            filename: Имя файла (без пути)
            
        Returns:
            Результат анализа или None, если файл не анализировался
        """
        return self._results.get(filename)
    
    def clear_results(self) -> None:
        """Очищает внутренний кэш результатов анализа."""
        self._results.clear()