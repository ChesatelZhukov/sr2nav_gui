from pathlib import Path
from typing import Set, Optional, List
from core.app_context import AppContext
class GPSExcluder:
    ALL_SATELLITES = [f"G{i:02d}" for i in range(1, 33)]
    def __init__(self, context: AppContext):
        self._ctx = context
        self._exclude_file = self._ctx.exclude_svs
        self._ensure_file_exists()
    def _ensure_file_exists(self) -> None:
        if not self._exclude_file.exists():
            try:
                self._exclude_file.write_text("", encoding='utf-8')
            except Exception as e:
                print(f"Предупреждение: не удалось создать Exclude.svs: {e}")
    def load_excluded(self) -> Set[str]:
        self._ensure_file_exists()                                          
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
        try:
            valid_sats = {sat for sat in excluded if sat in self.ALL_SATELLITES}
            sorted_sats = sorted(valid_sats, key=lambda x: int(x[1:]))
            content = "\n".join(sorted_sats)
            self._exclude_file.write_text(content, encoding='utf-8')
            return True
        except Exception as e:
            print(f"Ошибка сохранения Exclude.svs: {e}")
            return False
    def get_excluded_count(self) -> int:
        return len(self.load_excluded())
    def is_excluded(self, satellite: str) -> bool:
        return satellite in self.load_excluded()
    def get_excluded_list(self) -> List[str]:
        excluded = self.load_excluded()
        return sorted(excluded, key=lambda x: int(x[1:]))