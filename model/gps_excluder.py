#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТАЯ МОДЕЛЬ - Управление исключением спутников GPS.
ТОЛЬКО ФАЙЛОВЫЕ ОПЕРАЦИИ, НИКАКОГО UI!
"""
from pathlib import Path
from typing import Set, Optional, List

from core.app_context import AppContext


class GPSExcluder:
    """
    ЧИСТАЯ МОДЕЛЬ - Менеджер исключения спутников GPS.
    
    Только:
        - Загрузка списка исключённых спутников из Exclude.svs
        - Сохранение списка в Exclude.svs
        - Никакого UI, никаких диалогов!
    """
    
    ALL_SATELLITES = [f"G{i:02d}" for i in range(1, 33)]
    
    def __init__(self, context: AppContext):
        self._ctx = context
        self._exclude_file = self._ctx.exclude_svs
        
        # ИСПРАВЛЕНО: Создаём пустой файл при первом обращении к классу
        self._ensure_file_exists()
    
    def _ensure_file_exists(self) -> None:
        """
        Гарантирует существование файла Exclude.svs.
        SR2Nav.exe ожидает, что файл существует, даже если он пустой.
        """
        if not self._exclude_file.exists():
            try:
                self._exclude_file.write_text("", encoding='utf-8')
            except Exception as e:
                print(f"Предупреждение: не удалось создать Exclude.svs: {e}")
    
    def load_excluded(self) -> Set[str]:
        """Загружает список исключённых спутников из файла."""
        self._ensure_file_exists()  # На всякий случай
        
        excluded = set()
        if not self._exclude_file.exists():
            return excluded
        
        try:
            content = self._exclude_file.read_text(encoding='utf-8')
            for line in content.splitlines():
                sat = line.strip()
                if sat in self.ALL_SATELLITES:
                    excluded.add(sat)
        except Exception as e:
            print(f"Ошибка загрузки Exclude.svs: {e}")
        
        return excluded
    
    def save_excluded(self, excluded: Set[str]) -> bool:
        """Сохраняет список исключённых спутников в файл."""
        try:
            sorted_sats = sorted(excluded, key=lambda x: int(x[1:]))
            content = "\n".join(sorted_sats)
            self._exclude_file.write_text(content, encoding='utf-8')
            return True
        except Exception as e:
            print(f"Ошибка сохранения Exclude.svs: {e}")
            return False
    
    def get_excluded_count(self) -> int:
        """Возвращает количество исключённых спутников."""
        return len(self.load_excluded())
    
    def is_excluded(self, satellite: str) -> bool:
        """Проверяет, исключён ли спутник."""
        return satellite in self.load_excluded()
    
    def get_excluded_list(self) -> List[str]:
        """Возвращает отсортированный список исключённых спутников."""
        excluded = self.load_excluded()
        return sorted(excluded, key=lambda x: int(x[1:]))