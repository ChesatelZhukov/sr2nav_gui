#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Контекст приложения - единый источник истины о директориях.
Корректно работает как в режиме скрипта, так и в собранном EXE.
"""
import sys
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class AppContext:
    """
    Неизменяемый контекст приложения.
    Все пути определяются здесь и используются во всём приложении.
    
    Особенности:
        - Работает в .py и .exe режимах
        - Все пути - Path объекты (pathlib)
        - Автоматически создаёт нужные директории
    """
    
    @staticmethod
    def _get_base_dir() -> Path:
        """Определяет базовую директорию приложения."""
        if getattr(sys, 'frozen', False):
            # Запуск как собранного EXE файла (PyInstaller)
            return Path(sys.executable).parent
        else:
            # Запуск как скрипта Python
            return Path(__file__).parent.parent
    
    # ========== Основные директории ==========
    base_dir: Path = _get_base_dir()
    working_dir: Path = base_dir  # Рабочая директория = директория с EXE
    
    # ========== Поддиректории ==========
    results_dir: Path = working_dir / "results"
    tbl_dir: Path = working_dir / "tbl"
    
    def __post_init__(self):
        """Создаёт необходимые директории при инициализации."""
        self.results_dir.mkdir(exist_ok=True)
        self.tbl_dir.mkdir(exist_ok=True)
    
    # ========== Методы для получения путей к файлам ==========
    
    def resolve(self, path: str | Path) -> Path:
        """
        Преобразует относительный путь в абсолютный относительно working_dir.
        
        Пример:
            >>> APP_CONTEXT.resolve("Interval.exe")
            WindowsPath('C:/Programs/SR2NAV/Interval.exe')
        """
        return self.working_dir / Path(path)
    
    @property
    def interval_exe(self) -> Path:
        """Путь к Interval.exe."""
        return self.working_dir / "Interval.exe"
    
    @property
    def sr2nav_cfg(self) -> Path:
        """Путь к SR2Nav.cfg."""
        return self.working_dir / "SR2Nav.cfg"
    
    @property
    def mask_ang(self) -> Path:
        """Путь к Mask.Ang."""
        return self.working_dir / "Mask.Ang"
    
    @property
    def exclude_svs(self) -> Path:
        """Путь к Exclude.svs."""
        return self.working_dir / "Exclude.svs"
    
    @property
    def interval_txt(self) -> Path:
        """Путь к interval.txt (результат работы Interval.exe)."""
        return self.working_dir / "interval.txt"
    
    # ========== Вспомогательные методы ==========
    
    def __repr__(self) -> str:
        return (
            f"AppContext(\n"
            f"  working_dir={self.working_dir},\n"
            f"  results_dir={self.results_dir},\n"
            f"  tbl_dir={self.tbl_dir}\n"
            f")"
        )


# Глобальный экземпляр контекста (синглтон)
APP_CONTEXT = AppContext()