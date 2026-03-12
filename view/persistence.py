import os
import sys
import configparser
from pathlib import Path
from typing import Optional, Dict, Any
import logging
from view.themes import ThemeType, get_theme_name
logger = logging.getLogger(__name__)
class UIPersistence:
    _CONFIG_FILE = "user_prefs.ini"
    _SECTION_LAST_USED = "LastUsed"
    _SECTION_WINDOW = "Window"
    _KEY_DIRECTORY = "directory"
    _KEY_THEME = "theme"
    _KEY_WIDTH = "width"
    _KEY_HEIGHT = "height"
    _last_browse_dir: str = ""
    _selected_theme: str = "DARK"                                       
    _window_width: int = 1400
    _window_height: int = 850
    _config_dir: Optional[Path] = None
    _config: configparser.ConfigParser = None
    _dirty: bool = False
    @classmethod
    def initialize(cls, config_dir: Path) -> None:
        cls._config_dir = config_dir
        cls._config = configparser.ConfigParser()
        cls._load()
    @classmethod
    def _get_config_path(cls) -> Path:
        if cls._config_dir is None:
            cls._config_dir = Path.cwd()
        return cls._config_dir / cls._CONFIG_FILE
    @classmethod
    def _load(cls) -> None:
        config_path = cls._get_config_path()
        if config_path.exists():
            try:
                cls._config.read(config_path, encoding='utf-8')
                logger.debug(f"Конфигурация UI загружена из {config_path}")
                if cls._config.has_section(cls._SECTION_LAST_USED):
                    if cls._config.has_option(cls._SECTION_LAST_USED, cls._KEY_DIRECTORY):
                        dir_path = cls._config.get(cls._SECTION_LAST_USED, cls._KEY_DIRECTORY)
                        if dir_path and os.path.exists(dir_path):
                            cls._last_browse_dir = dir_path
                    if cls._config.has_option(cls._SECTION_LAST_USED, cls._KEY_THEME):
                        cls._selected_theme = cls._config.get(cls._SECTION_LAST_USED, cls._KEY_THEME)
                if cls._config.has_section(cls._SECTION_WINDOW):
                    if cls._config.has_option(cls._SECTION_WINDOW, cls._KEY_WIDTH):
                        try:
                            cls._window_width = int(cls._config.get(cls._SECTION_WINDOW, cls._KEY_WIDTH))
                        except:
                            pass
                    if cls._config.has_option(cls._SECTION_WINDOW, cls._KEY_HEIGHT):
                        try:
                            cls._window_height = int(cls._config.get(cls._SECTION_WINDOW, cls._KEY_HEIGHT))
                        except:
                            pass
            except Exception as e:
                logger.error(f"Ошибка загрузки конфигурации UI: {e}")
                cls._config = configparser.ConfigParser()
        else:
            logger.info(f"Файл конфигурации UI не найден, будет создан при сохранении")
            cls._config = configparser.ConfigParser()
        if not cls._config.has_section(cls._SECTION_LAST_USED):
            cls._config.add_section(cls._SECTION_LAST_USED)
        if not cls._config.has_section(cls._SECTION_WINDOW):
            cls._config.add_section(cls._SECTION_WINDOW)
    @classmethod
    def save(cls) -> bool:
        if not cls._dirty:
            return True
        config_path = cls._get_config_path()
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                cls._config.write(f)
            logger.debug(f"Конфигурация UI сохранена в {config_path}")
            cls._dirty = False
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения конфигурации UI: {e}")
            return False
    @classmethod
    def get_last_dir(cls) -> str:
        return cls._last_browse_dir
    @classmethod
    def set_last_dir(cls, path: str) -> None:
        if not path:
            return
        if sys.platform == 'win32' and len(path) > 240:
            path = '\\\\?\\' + path
        dir_path = os.path.dirname(path) if os.path.isfile(path) else path
        if dir_path and os.path.exists(dir_path):
            if cls._last_browse_dir != dir_path:
                cls._last_browse_dir = dir_path
                cls._config.set(cls._SECTION_LAST_USED, cls._KEY_DIRECTORY, dir_path)
                cls._dirty = True
    @classmethod
    def update_from_path(cls, path: str) -> None:
        cls.set_last_dir(path)
    @classmethod
    def get_theme(cls) -> ThemeType:
        try:
            return ThemeType[cls._selected_theme.upper()]
        except (KeyError, AttributeError):
            return ThemeType.DARK
    @classmethod
    def get_theme_name(cls) -> str:
        theme = cls.get_theme()
        return get_theme_name(theme)
    @classmethod
    def set_theme(cls, theme_type: ThemeType) -> None:
        theme_str = theme_type.name
        if cls._selected_theme != theme_str:
            cls._selected_theme = theme_str
            cls._config.set(cls._SECTION_LAST_USED, cls._KEY_THEME, theme_str)
            cls._dirty = True
    @classmethod
    def get_window_size(cls) -> tuple[int, int]:
        return cls._window_width, cls._window_height
    @classmethod
    def set_window_size(cls, width: int, height: int) -> None:
        if cls._window_width != width:
            cls._window_width = width
            cls._config.set(cls._SECTION_WINDOW, cls._KEY_WIDTH, str(width))
            cls._dirty = True
        if cls._window_height != height:
            cls._window_height = height
            cls._config.set(cls._SECTION_WINDOW, cls._KEY_HEIGHT, str(height))
            cls._dirty = True
    @classmethod
    def get_all_settings(cls) -> Dict[str, Any]:
        return {            'last_dir': cls._last_browse_dir,            'theme': cls._selected_theme,            'window_width': cls._window_width,            'window_height': cls._window_height,        }