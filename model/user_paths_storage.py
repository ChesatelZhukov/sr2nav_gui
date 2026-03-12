import os
import configparser
from pathlib import Path
from typing import Optional, Dict
import logging
logger = logging.getLogger(__name__)
class UserPathsStorage:
    SECTION_LAST_USED = "LastUsed"
    KEY_ROVER = "rover"
    KEY_BASE1 = "base1"
    KEY_BASE2 = "base2"
    KEY_SR2NAV = "sr2nav"                  
    def __init__(self, config_dir: Path, filename: str = "user_paths.txt"):
        self.config_file = config_dir / filename
        self._config = configparser.ConfigParser()
        self._dirty = False
        self._load()
    def _load(self) -> None:
        if self.config_file.exists():
            try:
                self._config.read(self.config_file, encoding='utf-8')
                logger.debug(f"Конфигурация загружена из {self.config_file}")
            except Exception as e:
                logger.error(f"Ошибка загрузки конфигурации из {self.config_file}: {e}")
                self._config = configparser.ConfigParser()
        else:
            logger.info(f"Файл конфигурации не найден, будет создан при сохранении: {self.config_file}")
        if not self._config.has_section(self.SECTION_LAST_USED):
            self._config.add_section(self.SECTION_LAST_USED)
    def save(self) -> bool:
        if not self._dirty:
            return True
        try:
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
        try:
            return self._config.get(self.SECTION_LAST_USED, key, fallback=None)
        except Exception:
            return None
    def set_path(self, key: str, path: Optional[str]) -> None:
        if not path:
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
        paths = {}
        for key in [self.KEY_ROVER, self.KEY_BASE1, self.KEY_BASE2, self.KEY_SR2NAV]:                       
            paths[key] = self.get_path(key)
        return paths
    def set_rover_path(self, path: Optional[str]) -> None:
        self.set_path(self.KEY_ROVER, path)
    def set_base1_path(self, path: Optional[str]) -> None:
        self.set_path(self.KEY_BASE1, path)
    def set_base2_path(self, path: Optional[str]) -> None:
        self.set_path(self.KEY_BASE2, path)
    def set_sr2nav_path(self, path: Optional[str]) -> None:                   
        self.set_path(self.KEY_SR2NAV, path)
    @property
    def rover_path(self) -> Optional[str]:
        return self.get_path(self.KEY_ROVER)
    @property
    def base1_path(self) -> Optional[str]:
        return self.get_path(self.KEY_BASE1)
    @property
    def base2_path(self) -> Optional[str]:
        return self.get_path(self.KEY_BASE2)
    @property
    def sr2nav_path(self) -> Optional[str]:                      
        return self.get_path(self.KEY_SR2NAV)