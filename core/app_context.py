import sys
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union
@dataclass(frozen=True)
class AppContext:
    base_dir: Path = field(default_factory=lambda: AppContext._locate_base_dir())
    working_dir: Path = field(init=False)
    _results_dir_value: Optional[Path] = field(default=None, init=False)
    def __post_init__(self) -> None:
        object.__setattr__(self, 'working_dir', self.base_dir)
        object.__setattr__(self, 'tbl_dir', self.working_dir / "tbl")
        self._ensure_directories()
    @staticmethod
    def _locate_base_dir() -> Path:
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent.absolute()
        return Path(__file__).parent.parent.absolute()
    def _ensure_directories(self) -> None:
        """
        Зарезервирован для будущих проверок/создания служебных директорий.
        Папка tbl больше не создаётся автоматически при старте приложения,
        а создаётся только при непосредственной трансформации файлов.
        """
        return
    @property
    def results_dir(self) -> Path:
        if self._results_dir_value is None:
            return self.working_dir / "results"
        return self._results_dir_value
    tbl_dir: Path = field(init=False)
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
    def set_results_dir_from_rover(self, rover_path: Union[str, Path]) -> Path:
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
    def resolve(self, path: Union[str, Path]) -> Path:
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return (self.working_dir / path_obj).resolve()
    def exists_in_working_dir(self, filename: str) -> bool:
        return (self.working_dir / filename).exists()
    def __repr__(self) -> str:
        results_display = self._results_dir_value.name if self._results_dir_value else "results (default)"
        return (            f"AppContext(\n"            f"  working_dir={self.working_dir},\n"
            f"  results_dir={results_display},\n"
            f"  tbl_dir={self.tbl_dir}\n"
            f")"        )
_APP_CONTEXT_INSTANCE: Optional[AppContext] = None
def get_app_context() -> AppContext:
    global _APP_CONTEXT_INSTANCE
    if _APP_CONTEXT_INSTANCE is None:
        _APP_CONTEXT_INSTANCE = AppContext()
    return _APP_CONTEXT_INSTANCE
APP_CONTEXT = get_app_context()