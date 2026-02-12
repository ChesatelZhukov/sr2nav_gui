#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Контекст приложения — единый источник истины о путях и ресурсах.
Работает одинаково в режиме скрипта и скомпилированного EXE.
"""

import sys
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union


@dataclass(frozen=True)
class AppContext:
    """
    Неизменяемый контекст приложения.
    
    Все пути вычисляются один раз при инициализации и не меняются
    в течение всей работы программы. Это гарантирует консистентность.
    
    Пример:
        >>> ctx = AppContext()
        >>> ctx.results_dir
        WindowsPath('C:/SR2NAV/results')
    """
    
    # ============ БАЗОВЫЕ ПУТИ ============
    
    base_dir: Path = field(default_factory=lambda: AppContext._locate_base_dir())
    working_dir: Path = field(init=False)  # Устанавливается в __post_init__
    
    def __post_init__(self) -> None:
        """
        Инициализирует зависимые пути и создаёт необходимые директории.
        
        Важно: используется object.__setattr__ для обхода frozen=True
        """
        object.__setattr__(self, 'working_dir', self.base_dir)
        object.__setattr__(self, 'results_dir', self.working_dir / "results")
        object.__setattr__(self, 'tbl_dir', self.working_dir / "tbl")
        
        self._ensure_directories()
    
    @staticmethod
    def _locate_base_dir() -> Path:
        """
        Определяет корневую директорию приложения.
        
        Приоритет:
            1. Директория скомпилированного EXE (PyInstaller)
            2. Родительская директория текущего файла (разработка)
        """
        if getattr(sys, 'frozen', False):
            # Скомпилированное приложение
            return Path(sys.executable).parent.absolute()
        
        # Режим разработки — поднимаемся из core/ в корень проекта
        return Path(__file__).parent.parent.absolute()
    
    def _ensure_directories(self) -> None:
        """
        Создаёт необходимые директории с проверкой прав доступа.
        В случае frozen-режима ошибки игнорируются (read-only).
        """
        for dir_path in [self.results_dir, self.tbl_dir]:
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                if getattr(sys, 'frozen', False):
                    # В скомпилированном приложении может быть read-only
                    continue
                raise
            except OSError:
                if getattr(sys, 'frozen', False):
                    continue
                raise
    
    # ============ ДИРЕКТОРИИ ============
    
    results_dir: Path = field(init=False)
    """Директория для выходных файлов обработки."""
    
    tbl_dir: Path = field(init=False)
    """Директория для трансформированных TBL-файлов."""
    
    # ============ ФАЙЛЫ ============
    
    @property
    def interval_exe(self) -> Path:
        """Путь к исполняемому файлу Interval.exe."""
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
        """Путь к файлу результатов Interval.exe."""
        return self.working_dir / "interval.txt"
    
    # ============ ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ============
    
    def resolve(self, path: Union[str, Path]) -> Path:
        """
        Преобразует относительный путь в абсолютный относительно working_dir.
        
        Args:
            path: Относительный или абсолютный путь
        
        Returns:
            Абсолютный объект Path
        
        Пример:
            >>> APP_CONTEXT.resolve("Interval.exe")
            WindowsPath('C:/SR2NAV/Interval.exe')
        """
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return (self.working_dir / path_obj).resolve()
    
    def exists_in_working_dir(self, filename: str) -> bool:
        """
        Проверяет существование файла в рабочей директории.
        
        Args:
            filename: Имя файла (относительный путь)
        
        Returns:
            True если файл существует
        """
        return (self.working_dir / filename).exists()
    
    def __repr__(self) -> str:
        """Человекочитаемое представление контекста."""
        return (
            f"AppContext(\n"
            f"  working_dir={self.working_dir},\n"
            f"  results_dir={self.results_dir},\n"
            f"  tbl_dir={self.tbl_dir}\n"
            f")"
        )


# ==================== ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ====================

_APP_CONTEXT_INSTANCE: Optional[AppContext] = None


def get_app_context() -> AppContext:
    """
    Возвращает глобальный экземпляр контекста приложения.
    
    Создаёт его при первом вызове, при последующих возвращает кэшированный.
    """
    global _APP_CONTEXT_INSTANCE
    if _APP_CONTEXT_INSTANCE is None:
        _APP_CONTEXT_INSTANCE = AppContext()
    return _APP_CONTEXT_INSTANCE


# Для обратной совместимости
APP_CONTEXT = get_app_context()