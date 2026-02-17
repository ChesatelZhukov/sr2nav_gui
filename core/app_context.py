#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Глобальный контекст приложения — единый источник истины о путях и ресурсах.

Обеспечивает централизованный доступ ко всем файлам и директориям,
используемым в приложении. Пути вычисляются однократно при инициализации
и остаются неизменными, что гарантирует консистентность состояния.

Особенности:
    - Работает одинаково в режиме скрипта и скомпилированного EXE
    - Все пути вычисляются лениво (через свойства) или при инициализации
    - Контекст неизменяем (frozen dataclass) после создания
    - Предоставляет глобальный синглтон APP_CONTEXT для всего приложения

Пример:
    >>> from core.app_context import APP_CONTEXT
    >>> APP_CONTEXT.results_dir
    WindowsPath('C:/SR2NAV/rover_name')
    >>> APP_CONTEXT.interval_exe.exists()
    True
"""

import sys
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union


@dataclass(frozen=True)
class AppContext:
    """
    Неизменяемый контекст приложения, содержащий все пути к ресурсам.
    
    После создания экземпляра все пути фиксируются. Единственное исключение —
    директория результатов (_results_dir_value), которая может быть обновлена
    при выборе файла ровера через set_results_dir_from_rover().
    
    Атрибуты:
        base_dir: Корневая директория приложения (автоопределяется)
        working_dir: Рабочая директория (совпадает с base_dir)
        tbl_dir: Директория для TBL файлов (working_dir/tbl)
        
    Свойства:
        results_dir: Директория для результатов обработки (может меняться)
        interval_exe: Путь к Interval.exe
        sr2nav_cfg: Путь к конфигурационному файлу SR2Nav.cfg
        mask_ang: Путь к файлу маски углов Mask.Ang
        exclude_svs: Путь к файлу исключённых спутников Exclude.svs
        interval_txt: Путь к файлу интервала interval.txt
    """
    
    # ============ БАЗОВЫЕ ПУТИ ============
    
    base_dir: Path = field(default_factory=lambda: AppContext._locate_base_dir())
    working_dir: Path = field(init=False)
    _results_dir_value: Optional[Path] = field(default=None, init=False)
    
    def __post_init__(self) -> None:
        """
        Инициализирует зависимые пути и создаёт необходимые директории.
        
        Вызывается автоматически после создания экземпляра.
        Устанавливает working_dir = base_dir и создаёт директорию tbl.
        """
        object.__setattr__(self, 'working_dir', self.base_dir)
        object.__setattr__(self, 'tbl_dir', self.working_dir / "tbl")
        self._ensure_directories()
    
    @staticmethod
    def _locate_base_dir() -> Path:
        """
        Определяет корневую директорию приложения в зависимости от режима запуска.
        
        Returns:
            Path: Абсолютный путь к корневой директории
            
        Логика определения:
            - В скомпилированном EXE: директория, где находится исполняемый файл
            - В режиме скрипта: родительская директория от core/app_context.py
        """
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent.absolute()
        return Path(__file__).parent.parent.absolute()
    
    def _ensure_directories(self) -> None:
        """
        Создаёт необходимые директории, если они не существуют.
        
        Игнорирует ошибки прав доступа в скомпилированной версии,
        но позволяет им всплывать в режиме разработки для отладки.
        
        Создаваемые директории:
            - tbl_dir: для временных TBL файлов
        """
        try:
            self.tbl_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            if getattr(sys, 'frozen', False):
                # В скомпилированной версии не прерываем работу
                # из-за невозможности создать директорию
                pass
            else:
                # В режиме разработки ошибка должна быть видна
                raise
    
    # ============ ДИРЕКТОРИИ ============
    
    @property
    def results_dir(self) -> Path:
        """
        Директория для выходных файлов обработки.
        
        Возвращает:
            - Если установлена через set_results_dir_from_rover(): путь к именной папке
            - Иначе: working_dir/results (папка по умолчанию)
        
        Note:
            Это свойство, а не атрибут, так как значение может измениться
            при выборе нового файла ровера.
        """
        if self._results_dir_value is None:
            return self.working_dir / "results"
        return self._results_dir_value
    
    tbl_dir: Path = field(init=False)
    
    # ============ ФАЙЛЫ ============
    
    @property
    def interval_exe(self) -> Path:
        """Путь к исполняемому файлу Interval.exe в рабочей директории."""
        return self.working_dir / "Interval.exe"
    
    @property
    def sr2nav_cfg(self) -> Path:
        """Путь к конфигурационному файлу SR2Nav.cfg."""
        return self.working_dir / "SR2Nav.cfg"
    
    @property
    def mask_ang(self) -> Path:
        """Путь к файлу маски углов Mask.Ang."""
        return self.working_dir / "Mask.Ang"
    
    @property
    def exclude_svs(self) -> Path:
        """Путь к файлу исключённых спутников Exclude.svs."""
        return self.working_dir / "Exclude.svs"
    
    @property
    def interval_txt(self) -> Path:
        """Путь к файлу с определённым временным интервалом interval.txt."""
        return self.working_dir / "interval.txt"
    
    # ============ УПРАВЛЕНИЕ ДИРЕКТОРИЕЙ РЕЗУЛЬТАТОВ ============
    
    def set_results_dir_from_rover(self, rover_path: Union[str, Path]) -> Path:
        """
        Создаёт именованную папку результатов на основе имени файла ровера.
        
        Это единственный метод, который может изменить состояние контекста
        после его создания. Папка создаётся в рабочей директории с именем,
        соответствующим имени файла ровера (очищенным от недопустимых символов).
        
        Args:
            rover_path: Путь к файлу ровера (.jps). Может быть пустым.
            
        Returns:
            Path: Путь к созданной (или существующей) директории результатов.
            
        Example:
            >>> APP_CONTEXT.set_results_dir_from_rover("data/rover_2023.jps")
            WindowsPath('C:/SR2NAV/rover_2023')
            
        Note:
            Если rover_path пуст или не указан, создаётся папка "results"
            в рабочей директории.
        """
        if not rover_path:
            fallback = self.working_dir / "results"
            fallback.mkdir(parents=True, exist_ok=True)
            object.__setattr__(self, '_results_dir_value', fallback)
            return fallback
        
        rover_name = Path(rover_path).stem
        # Очищаем имя от символов, недопустимых в именах папок Windows
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', rover_name)
        new_results_dir = self.working_dir / safe_name
        new_results_dir.mkdir(parents=True, exist_ok=True)
        
        # Обновляем значение через object.__setattr__ из-за frozen=True
        object.__setattr__(self, '_results_dir_value', new_results_dir)
        return new_results_dir
    
    # ============ ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ============
    
    def resolve(self, path: Union[str, Path]) -> Path:
        """
        Преобразует относительный путь в абсолютный относительно working_dir.
        
        Args:
            path: Относительный или абсолютный путь
            
        Returns:
            Path: Абсолютный нормализованный путь
            
        Example:
            >>> APP_CONTEXT.resolve("temp/file.txt")
            WindowsPath('C:/SR2NAV/temp/file.txt')
        """
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return (self.working_dir / path_obj).resolve()
    
    def exists_in_working_dir(self, filename: str) -> bool:
        """
        Проверяет существование файла в рабочей директории.
        
        Args:
            filename: Имя файла (или относительный путь)
            
        Returns:
            bool: True если файл существует
            
        Example:
            >>> APP_CONTEXT.exists_in_working_dir("Interval.exe")
            True
        """
        return (self.working_dir / filename).exists()
    
    def __repr__(self) -> str:
        """
        Строковое представление контекста для отладки.
        
        Показывает текущее состояние: рабочую директорию,
        директорию результатов и директорию TBL.
        """
        results_display = self._results_dir_value.name if self._results_dir_value else "results (default)"
        return (
            f"AppContext(\n"
            f"  working_dir={self.working_dir},\n"
            f"  results_dir={results_display},\n"
            f"  tbl_dir={self.tbl_dir}\n"
            f")"
        )


# ==================== ГЛОБАЛЬНЫЙ СИНГЛТОН ====================

_APP_CONTEXT_INSTANCE: Optional[AppContext] = None


def get_app_context() -> AppContext:
    """
    Возвращает глобальный экземпляр контекста приложения (синглтон).
    
    При первом вызове создаёт экземпляр AppContext, при последующих —
    возвращает уже существующий. Это гарантирует, что все компоненты
    приложения используют один и тот же контекст с согласованными путями.
    
    Returns:
        AppContext: Глобальный контекст приложения
        
    Example:
        >>> from core.app_context import get_app_context
        >>> ctx = get_app_context()
        >>> ctx2 = get_app_context()
        >>> ctx is ctx2  # Всегда True
        True
    """
    global _APP_CONTEXT_INSTANCE
    if _APP_CONTEXT_INSTANCE is None:
        _APP_CONTEXT_INSTANCE = AppContext()
    return _APP_CONTEXT_INSTANCE


# Удобный глобальный доступ для всего приложения
APP_CONTEXT = get_app_context()