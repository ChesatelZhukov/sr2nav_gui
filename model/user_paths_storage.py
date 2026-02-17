#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Хранилище последних путей пользователя в ini-подобном текстовом файле.

Отвечает за сохранение и загрузку последних выбранных пользователем путей
к ключевым файлам (ровер, база1, база2) для восстановления состояния
между сессиями программы.

Формат файла:
    [LastUsed]
    rover = C:\path\to\last\rover.jps
    base1 = C:\path\to\last\base1.jps
    base2 = C:\path\to\last\base2.jps

Архитектура:
    Класс является частью Model и не имеет зависимостей от View.
    Все пути хранятся как строки. Валидация существования файлов
    не является его ответственностью.
"""
import os
import configparser
from pathlib import Path
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


class UserPathsStorage:
    """
    Управляет сохранением и загрузкой последних путей пользователя.

    Инкапсулирует работу с конфигурационным файлом, предоставляя простой
    интерфейс для контроллера. Пути хранятся в секции 'LastUsed' ini-файла.

    Attributes:
        config_file: Полный путь к конфигурационному файлу.
        _config: Внутренний объект ConfigParser для работы с файлом.
        _dirty: Флаг, указывающий, были ли изменения с момента последнего сохранения.
    """

    # Имя секции в ini-файле
    SECTION_LAST_USED = "LastUsed"
    # Ключи для различных типов файлов
    KEY_ROVER = "rover"
    KEY_BASE1 = "base1"
    KEY_BASE2 = "base2"
    KEY_SR2NAV = "sr2nav"  # <-- НОВЫЙ КЛЮЧ

    def __init__(self, config_dir: Path, filename: str = "user_paths.txt"):
        """
        Инициализация хранилища путей.

        Args:
            config_dir: Директория, в которой будет создан/находиться файл.
            filename: Имя файла для хранения путей (по умолчанию 'user_paths.txt').
        """
        self.config_file = config_dir / filename
        self._config = configparser.ConfigParser()
        self._dirty = False
        self._load()

    def _load(self) -> None:
        """Загружает конфигурацию из файла, если он существует."""
        if self.config_file.exists():
            try:
                self._config.read(self.config_file, encoding='utf-8')
                logger.debug(f"Конфигурация загружена из {self.config_file}")
            except Exception as e:
                logger.error(f"Ошибка загрузки конфигурации из {self.config_file}: {e}")
                # При ошибке чтения начинаем с чистой конфигурации
                self._config = configparser.ConfigParser()
        else:
            logger.info(f"Файл конфигурации не найден, будет создан при сохранении: {self.config_file}")

        # Убеждаемся, что секция существует, даже если файл пуст или не загрузился
        if not self._config.has_section(self.SECTION_LAST_USED):
            self._config.add_section(self.SECTION_LAST_USED)

    def save(self) -> bool:
        """
        Сохраняет текущие пути в конфигурационный файл, если были изменения.

        Returns:
            True, если сохранение прошло успешно или не требовалось, False в случае ошибки.
        """
        if not self._dirty:
            return True

        try:
            # Создаем директорию, если её нет
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config_file, 'w', encoding='utf-8') as f:
                self._config.write(f)
            logger.debug(f"Конфигурация сохранена в {self.config_file}")
            self._dirty = False
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения конфигурации в {self.config_file}: {e}")
            return False

    def get_path(self, key: str) -> Optional[str]:
        """
        Возвращает сохраненный путь для указанного ключа.

        Args:
            key: Ключ пути (например, 'rover', 'base1').

        Returns:
            Путь в виде строки или None, если ключ не найден.
        """
        try:
            return self._config.get(self.SECTION_LAST_USED, key, fallback=None)
        except Exception:
            return None

    def set_path(self, key: str, path: Optional[str]) -> None:
        """
        Устанавливает путь для указанного ключа.

        Изменения помечаются флагом _dirty и будут сохранены только
        при вызове метода save().

        Args:
            key: Ключ пути (например, 'rover', 'base1').
            path: Новый путь (может быть None или пустой строкой для удаления).
        """
        if not path:
            # Если путь пустой, пытаемся удалить ключ из секции
            if self._config.has_option(self.SECTION_LAST_USED, key):
                self._config.remove_option(self.SECTION_LAST_USED, key)
                self._dirty = True
                logger.debug(f"Путь для ключа '{key}' удален.")
        else:
            old_path = self.get_path(key)
            if old_path != path:
                self._config.set(self.SECTION_LAST_USED, key, str(path))
                self._dirty = True
                logger.debug(f"Путь для ключа '{key}' обновлен: {path}")

    def get_all_paths(self) -> Dict[str, Optional[str]]:
        """
        Возвращает словарь всех сохраненных путей.

        Returns:
            Словарь вида {ключ: путь} для всех известных ключей.
        """
        paths = {}
        for key in [self.KEY_ROVER, self.KEY_BASE1, self.KEY_BASE2, self.KEY_SR2NAV]:  # <-- ДОБАВИЛИ SR2NAV
            paths[key] = self.get_path(key)
        return paths

    def set_rover_path(self, path: Optional[str]) -> None:
        """Удобный метод для установки пути ровера."""
        self.set_path(self.KEY_ROVER, path)

    def set_base1_path(self, path: Optional[str]) -> None:
        """Удобный метод для установки пути базы 1."""
        self.set_path(self.KEY_BASE1, path)

    def set_base2_path(self, path: Optional[str]) -> None:
        """Удобный метод для установки пути базы 2."""
        self.set_path(self.KEY_BASE2, path)

    def set_sr2nav_path(self, path: Optional[str]) -> None:  # <-- НОВЫЙ МЕТОД
        """Удобный метод для установки пути к SR2Nav.exe."""
        self.set_path(self.KEY_SR2NAV, path)

    @property
    def rover_path(self) -> Optional[str]:
        """Возвращает последний путь к файлу ровера."""
        return self.get_path(self.KEY_ROVER)

    @property
    def base1_path(self) -> Optional[str]:
        """Возвращает последний путь к файлу базы 1."""
        return self.get_path(self.KEY_BASE1)

    @property
    def base2_path(self) -> Optional[str]:
        """Возвращает последний путь к файлу базы 2."""
        return self.get_path(self.KEY_BASE2)

    @property
    def sr2nav_path(self) -> Optional[str]:  # <-- НОВОЕ СВОЙСТВО
        """Возвращает последний путь к SR2Nav.exe."""
        return self.get_path(self.KEY_SR2NAV)