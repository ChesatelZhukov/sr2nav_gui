#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Управление исключением спутников GPS через файл Exclude.svs.

Обеспечивает чтение и запись списка исключённых спутников в формате,
ожидаемом программой SR2Nav.exe. Каждый спутник представлен строкой
с PRN номером (G01...G32).

Файл Exclude.svs:
    - Простой текстовый формат: один спутник на строку
    - Пустой файл означает "все спутники включены"
    - Файл должен существовать даже при отсутствии исключений
    - SR2Nav.exe игнорирует неверные имена спутников

Пример содержимого:
    G05
    G12
    G24
"""
from pathlib import Path
from typing import Set, Optional, List

from core.app_context import AppContext


class GPSExcluder:
    """
    Менеджер исключения спутников GPS.

    Отвечает за:
        - Загрузку списка исключённых спутников из Exclude.svs
        - Сохранение списка в Exclude.svs
        - Проверку статуса отдельных спутников
        - Подсчёт количества исключений

    Класс не содержит UI-логики и может использоваться в любом контексте.
    Все операции с файлами безопасны: при ошибках возвращаются пустые множества
    или False, исключения не выбрасываются наружу.

    Архитектурное замечание:
        Файл Exclude.svs создаётся при первом обращении к классу,
        так как SR2Nav.exe ожидает его существования даже при пустом списке.

    Example:
        >>> excluder = GPSExcluder(app_context)
        >>> # Загрузка текущих исключений
        >>> excluded = excluder.load_excluded()
        >>> print(f"Исключено: {len(excluded)} спутников")
        >>> 
        >>> # Добавление спутника
        >>> excluded.add("G12")
        >>> excluder.save_excluded(excluded)
        >>> 
        >>> # Проверка статуса
        >>> if excluder.is_excluded("G05"):
        ...     print("Спутник G05 исключён")
    """
    
    ALL_SATELLITES = [f"G{i:02d}" for i in range(1, 33)]
    
    def __init__(self, context: AppContext):
        """
        Инициализация менеджера исключений.
        
        Args:
            context: Контекст приложения, содержащий путь к Exclude.svs
        """
        self._ctx = context
        self._exclude_file = self._ctx.exclude_svs
        
        # Гарантируем существование файла при первом обращении
        self._ensure_file_exists()
    
    def _ensure_file_exists(self) -> None:
        """
        Создаёт пустой файл Exclude.svs, если он не существует.
        
        SR2Nav.exe ожидает, что файл существует, даже если он пустой.
        При ошибке создания выводит предупреждение в консоль, но не
        прерывает выполнение программы.
        """
        if not self._exclude_file.exists():
            try:
                self._exclude_file.write_text("", encoding='utf-8')
            except Exception as e:
                print(f"Предупреждение: не удалось создать Exclude.svs: {e}")
    
    def load_excluded(self) -> Set[str]:
        """
        Загружает список исключённых спутников из файла.
        
        Читает файл построчно, фильтрует только валидные имена спутников
        (G01...G32). Пустые строки и неверные форматы игнорируются.
        
        Returns:
            Множество PRN номеров исключённых спутников (например, {"G05", "G12"})
            Пустое множество, если файл не существует, пуст или повреждён.
        """
        self._ensure_file_exists()  # На всякий случай, если файл был удалён
        
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
        """
        Сохраняет список исключённых спутников в файл.
        
        Args:
            excluded: Множество PRN номеров для сохранения
                     (невалидные имена будут отфильтрованы)
        
        Returns:
            True при успешной записи, False при ошибке
        
        Note:
            Спутники автоматически сортируются по номеру перед записью.
            Пустое множество создаёт пустой файл (все спутники включены).
        """
        try:
            # Фильтруем только валидные спутники и сортируем
            valid_sats = {sat for sat in excluded if sat in self.ALL_SATELLITES}
            sorted_sats = sorted(valid_sats, key=lambda x: int(x[1:]))
            content = "\n".join(sorted_sats)
            self._exclude_file.write_text(content, encoding='utf-8')
            return True
        except Exception as e:
            print(f"Ошибка сохранения Exclude.svs: {e}")
            return False
    
    def get_excluded_count(self) -> int:
        """
        Возвращает количество исключённых спутников.
        
        Returns:
            Число спутников в текущем списке исключений
        """
        return len(self.load_excluded())
    
    def is_excluded(self, satellite: str) -> bool:
        """
        Проверяет, исключён ли указанный спутник.
        
        Args:
            satellite: PRN номер спутника (например, "G05")
            
        Returns:
            True если спутник в списке исключённых, иначе False
            
        Note:
            Для невалидных имён всегда возвращает False.
        """
        return satellite in self.load_excluded()
    
    def get_excluded_list(self) -> List[str]:
        """
        Возвращает отсортированный список исключённых спутников.
        
        Returns:
            Список PRN номеров, отсортированный по возрастанию номеров
            (G01, G02, ..., G32). Пустой список, если исключений нет.
        """
        excluded = self.load_excluded()
        return sorted(excluded, key=lambda x: int(x[1:]))