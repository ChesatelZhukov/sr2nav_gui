#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Контекст приложения — единый источник истины о путях и ресурсах.
Работает одинаково в режиме скрипта и скомпилированного EXE.
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
    Неизменяемый контекст приложения.
    
    Все пути вычисляются один раз при инициализации и не меняются
    в течение всей работы программы. Это гарантирует консистентность.
    
    Пример:
        >>> ctx = AppContext()
        >>> ctx.results_dir
        WindowsPath('C:/SR2NAV/имя_ровера')
    """
    
    # ============ БАЗОВЫЕ ПУТИ ============
    
    base_dir: Path = field(default_factory=lambda: AppContext._locate_base_dir())
    working_dir: Path = field(init=False)
    _results_dir_value: Optional[Path] = field(default=None, init=False)
    
    def __post_init__(self) -> None:
        """
        Инициализирует зависимые пути и создаёт необходимые директории.
        """
        object.__setattr__(self, 'working_dir', self.base_dir)
        object.__setattr__(self, 'tbl_dir', self.working_dir / "tbl")
        self._ensure_directories()
    
    @staticmethod
    def _locate_base_dir() -> Path:
        """Определяет корневую директорию приложения."""
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent.absolute()
        return Path(__file__).parent.parent.absolute()
    
    def _ensure_directories(self) -> None:
        """Создаёт необходимые директории."""
        try:
            self.tbl_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            if getattr(sys, 'frozen', False):
                pass
            else:
                raise
    
    # ============ ДИРЕКТОРИИ ============
    
    @property
    def results_dir(self) -> Path:
        """
        Директория для выходных файлов обработки.
        Если не установлена через set_results_dir_from_rover, возвращает "results".
        """
        if self._results_dir_value is None:
            # Используем прямой доступ к атрибуту working_dir
            return self.working_dir / "results"
        return self._results_dir_value
    
    tbl_dir: Path = field(init=False)
    
    # ============ ФАЙЛЫ ============
    
    @property
    def interval_exe(self) -> Path:
        return self.working_dir / "Interval.exe"
    
    @property
    def sr2nav_cfg(self) -> Path:
        return self.working_dir / "SR2Nav.cfg"
    
    @property
    def mask_ang(self) -> Path:
        return self.working_dir / "Mask.Ang"
    
    @property
    def exclude_svs(self) -> Path:
        return self.working_dir / "Exclude.svs"
    
    @property
    def interval_txt(self) -> Path:
        return self.working_dir / "interval.txt"
    
    # ============ МЕТОД ДЛЯ УПРАВЛЕНИЯ ПАПКОЙ РЕЗУЛЬТАТОВ ============
    
    def set_results_dir_from_rover(self, rover_path: Union[str, Path]) -> Path:
        """
        Создаёт папку результатов на основе имени файла ровера.
        
        Args:
            rover_path: Путь к файлу ровера
            
        Returns:
            Path к созданной папке
        """
        if not rover_path:
            fallback = self.working_dir / "results"
            fallback.mkdir(parents=True, exist_ok=True)
            object.__setattr__(self, '_results_dir_value', fallback)
            return fallback
        
        rover_name = Path(rover_path).stem
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', rover_name)
        new_results_dir = self.working_dir / safe_name
        new_results_dir.mkdir(parents=True, exist_ok=True)
        
        object.__setattr__(self, '_results_dir_value', new_results_dir)
        return new_results_dir
    
    # ============ ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ============
    
    def resolve(self, path: Union[str, Path]) -> Path:
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return (self.working_dir / path_obj).resolve()
    
    def exists_in_working_dir(self, filename: str) -> bool:
        return (self.working_dir / filename).exists()
    
    def __repr__(self) -> str:
        results_display = self._results_dir_value.name if self._results_dir_value else "results (default)"
        return (
            f"AppContext(\n"
            f"  working_dir={self.working_dir},\n"
            f"  results_dir={results_display},\n"
            f"  tbl_dir={self.tbl_dir}\n"
            f")"
        )


# ==================== ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ====================

_APP_CONTEXT_INSTANCE: Optional[AppContext] = None


def get_app_context() -> AppContext:
    global _APP_CONTEXT_INSTANCE
    if _APP_CONTEXT_INSTANCE is None:
        _APP_CONTEXT_INSTANCE = AppContext()
    return _APP_CONTEXT_INSTANCE


APP_CONTEXT = get_app_context()