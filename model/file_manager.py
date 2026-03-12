import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Callable
import re
from core.app_context import APP_CONTEXT, AppContext
from core.message_system import AppMessage
class FileType(Enum):
    ROVER = "rover"
    BASE1 = "base1"
    BASE2 = "base2"
    POS1 = "pos1"
    POS2 = "pos2"
    CFG = "cfg"
    AIR = "air"
    SR2NAV_EXE = "sr2nav"
    @property
    def extension(self) -> str:
        return {            FileType.ROVER: '.jps',            FileType.BASE1: '.jps',            FileType.BASE2: '.jps',            FileType.POS1: '.pos',            FileType.POS2: '.pos',            FileType.CFG: '.cfg',            FileType.AIR: '.air',            FileType.SR2NAV_EXE: '.exe',        }[self]
    @property
    def description(self) -> str:
        return {            FileType.ROVER: "Файл ровера (JPS)",            FileType.BASE1: "Файл базы 1 (JPS)",            FileType.BASE2: "Файл базы 2 (JPS)",            FileType.POS1: "POS файл базы 1",            FileType.POS2: "POS файл базы 2",            FileType.CFG: "Конфигурационный файл",            FileType.AIR: "Файл гравики",            FileType.SR2NAV_EXE: "Исполняемый файл SR2Nav",        }[self]
    @property
    def is_required(self) -> bool:
        return self in (FileType.ROVER, FileType.SR2NAV_EXE)
@dataclass
class TimeInterval:
    start: str = ""
    end: str = ""
    manual: bool = False                                                
    @property
    def is_valid(self) -> bool:
        return bool(self.start and self.end)
    def set_manual(self, start: str, end: str) -> None:
        self.start = start
        self.end = end
        self.manual = True
    def set_auto(self, start: str, end: str) -> None:
        self.start = start
        self.end = end
        self.manual = False
class FileManager:
    RESULT_FILE_PATTERNS = [        '*.ins',        'Phase*.VEL',        '*_Std.QC',        'Phase.QC',        '*.EXIT',        'Visible*.SVs',    ]
    JPS_HEADER = "JP055"
    JPS_HEADER_BYTES = JPS_HEADER.encode('cp1251')
    def __init__(self, context: AppContext, message_callback: Callable[[AppMessage], None]):
        self._ctx = context
        self._message_callback = message_callback
        self._original_paths: Dict[FileType, Path] = {}
        self._working_paths: Dict[FileType, Path] = {}
        self._cutoff_angle: float = 7.0
        self._time_interval = TimeInterval()
    def set_path(self, file_type: FileType, path: str | Path) -> None:
        if not path or str(path).strip() == '':
            self._original_paths.pop(file_type, None)
            return
        path_obj = Path(path)
        self._original_paths[file_type] = path_obj
    def set_rover_path(self, path: str | Path) -> None:
        if not path or str(path).strip() == '':
            self._original_paths.pop(FileType.ROVER, None)
            return
        path_obj = Path(path)
        self._original_paths[FileType.ROVER] = path_obj
        new_dir = self._ctx.set_results_dir_from_rover(str(path))
        self._send_message(AppMessage.info(            f"📁 Папка результатов: {new_dir.name}",            source="FileManager"        ))
    def get_original_path(self, file_type: FileType) -> Optional[Path]:
        return self._original_paths.get(file_type)
    def get_all_original_paths(self) -> Dict[str, str]:
        result = {}
        for file_type in FileType:                             
            path = self._original_paths.get(file_type)
            if path:                                   
                result[file_type.value] = str(path)
        return result
    @property
    def cutoff_angle(self) -> float:
        return self._cutoff_angle
    def set_cutoff_angle(self, angle: float) -> None:
        self._cutoff_angle = round(angle, 1)
    @property
    def time_interval(self) -> TimeInterval:
        return self._time_interval
    def cleanup_results_dir(self, force: bool = False) -> Tuple[int, bool]:
        patterns = self.RESULT_FILE_PATTERNS
        deleted = 0
        existing_files = []
        results_dir = self._ctx.results_dir
        if not results_dir.exists():
            results_dir.mkdir(parents=True, exist_ok=True)
            return 0, False
        for pattern in patterns:
            existing_files.extend(list(results_dir.glob(pattern)))
        if existing_files and not force:
            self._send_message(AppMessage.warning(                f"⚠️ В папке {results_dir.name} найдены файлы ({len(existing_files)} шт.)\n"                f"Очистка удалит их перед запуском.",                source="FileManager"            ))
            return 0, True
        for pattern in patterns:
            for file_path in results_dir.glob(pattern):
                try:
                    file_path.unlink()
                    deleted += 1
                    self._send_message(AppMessage.debug(                        f"🧹 Удалён старый результат: {file_path.name}",                        source="FileManager"                    ))
                except Exception as e:
                    self._send_message(AppMessage.warning(                        f"Не удалось удалить {file_path.name}: {e}",                        source="FileManager"                    ))
        return deleted, False
    def _is_path_in_working_dir(self, path: Path) -> bool:
        try:
            working_dir_resolved = self._ctx.working_dir.resolve()
            path_resolved = path.resolve()
            return (working_dir_resolved == path_resolved or                     working_dir_resolved in path_resolved.parents)
        except Exception:
            return False
    def prepare_files(self, files_to_copy: List[FileType]) -> Tuple[bool, str, Dict[FileType, Path]]:
        self._send_message(AppMessage.info("📋 Подготовка файлов к обработке..."))
        prepared_paths: Dict[FileType, Path] = {}
        self._working_paths.clear()                                   
        for file_type in files_to_copy:
            src_path = self._original_paths.get(file_type)
            if not src_path:
                self._send_message(AppMessage.warning(                    f"Пропуск {file_type.description}: исходный файл не выбран.",                    source="FileManager"                ))
                continue
            if not src_path.exists():
                return False, f"Исходный файл не найден: {src_path}", prepared_paths
            if self._is_path_in_working_dir(src_path):
                use_path = src_path
                self._send_message(AppMessage.debug(                    f"✓ {src_path.name} уже в рабочей директории, копирование не требуется.",                    source="FileManager"                ))
            else:
                dst_path = self._ctx.working_dir / src_path.name
                if dst_path.exists():
                    self._send_message(AppMessage.warning(                        f"⚠️ Файл {dst_path.name} уже существует в рабочей директории и будет перезаписан.",                        source="FileManager"                    ))
                try:
                    if file_type in (FileType.ROVER, FileType.BASE1, FileType.BASE2):
                        self._copy_large_file(src_path, dst_path)
                    else:
                        shutil.copy2(src_path, dst_path)
                    use_path = dst_path
                    self._send_message(AppMessage.info(                        f"✓ {src_path.name} скопирован в рабочую директорию."                    ))
                except Exception as e:
                    return False, f"Ошибка копирования {src_path.name}: {e}", prepared_paths
            prepared_paths[file_type] = use_path
            self._working_paths[file_type] = use_path
        if not prepared_paths:
            return False, "Не удалось подготовить ни одного файла.", prepared_paths
        return True, "Подготовка файлов завершена", prepared_paths
    def _copy_large_file(self, src: Path, dst: Path, chunk_size: int = 64 * 1024 * 1024) -> None:
        total = src.stat().st_size
        copied = 0
        with open(src, 'rb') as f_src, open(dst, 'wb') as f_dst:
            while True:
                chunk = f_src.read(chunk_size)
                if not chunk:
                    break
                f_dst.write(chunk)
                copied += len(chunk)
                progress = int((copied / total) * 100)
                if progress % 10 == 0:
                    self._send_message(AppMessage.debug(                        f"Копирование {src.name}: {progress}%"                    ))
    def fix_jps_headers(self, jps_files: Dict[FileType, Path]) -> Tuple[bool, str, int]:
        fixed_count = 0
        file_descriptions = {            FileType.ROVER: "ровера",            FileType.BASE1: "базы 1",            FileType.BASE2: "базы 2",        }
        for file_type, description in file_descriptions.items():
            path = jps_files.get(file_type)
            if not path:
                continue
            if self._has_valid_header(path):
                self._send_message(AppMessage.debug(f"✓ {path.name}: заголовок JP055 OK"))
                continue
            if self._add_header(path):
                fixed_count += 1
                self._send_message(AppMessage.info(f"🔧 {path.name}: добавлен заголовок JP055"))
            else:
                return False, f"Не удалось исправить заголовок {path.name}", fixed_count
        return True, "JPS файлы в порядке", fixed_count
    def _has_valid_header(self, path: Path) -> bool:
        try:
            with open(path, 'rb') as f:
                header = f.read(5)
            try:
                return header.decode('cp1251') == self.JPS_HEADER
            except UnicodeDecodeError:
                try:
                    return header.decode('utf-8') == self.JPS_HEADER
                except UnicodeDecodeError:
                    return False
        except Exception:
            return False
    def _add_header(self, path: Path) -> bool:
        temp_path = path.with_suffix('.tmp')
        backup_path = path.with_suffix('.bak')
        try:
            shutil.copy2(path, backup_path)
            with open(path, 'rb') as src, open(temp_path, 'wb') as dst:
                dst.write(self.JPS_HEADER_BYTES)
                shutil.copyfileobj(src, dst)
            original_size = backup_path.stat().st_size
            new_size = temp_path.stat().st_size
            if new_size == original_size + len(self.JPS_HEADER_BYTES):
                os.replace(temp_path, path)
                backup_path.unlink(missing_ok=True)
                return True
            else:
                os.replace(backup_path, path)
                if temp_path.exists():
                    temp_path.unlink()
                return False
        except Exception as e:
            self._send_message(AppMessage.error(f"Ошибка добавления заголовка: {e}"))
            if backup_path.exists():
                os.replace(backup_path, path)
            return False
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
    def reset_manual_mode(self) -> None:
        if self._time_interval.manual:
            self._send_message(AppMessage.debug(                "🔄 Сброс ручного режима интервала",                source="FileManager"            ))
            self._time_interval.manual = False
    def update_time_interval(self, start: str, end: str, manual: bool = False) -> None:
        if manual:
            self._time_interval.set_manual(start, end)
            self._send_message(AppMessage.info(                f"📝 Установлен интервал вручную: {start} - {end}",                source="FileManager"            ))
        else:
            if self._time_interval.manual:
                self._send_message(AppMessage.warning(                    f"⚠️ Интервал установлен вручную ({self._time_interval.start} - {self._time_interval.end})\n"                    f"   Результат Interval.exe ({start} - {end}) игнорируется.\n"                    f"   Для использования авто-интервала снимите ручной режим.",                    source="FileManager"                ))
                return
            self._time_interval.set_auto(start, end)
        self._update_config_interval()
    def _update_config_interval(self) -> None:
        cfg_path = self._ctx.sr2nav_cfg
        if not cfg_path.exists():
            return
        try:
            lines = cfg_path.read_text(encoding='cp1251', errors='ignore').splitlines()
            while len(lines) < 4:
                lines.append("")
            if self._time_interval.start and self._time_interval.end:
                interval_line = f"*{self._time_interval.start} {self._time_interval.end}"
            else:
                interval_line = "*1111111"
            lines[3] = interval_line
            cfg_path.write_text("\n".join(lines) + "\n", encoding='cp1251')
            self._send_message(AppMessage.debug(                f"📝 Конфиг обновлён: интервал {self._time_interval.start} - {self._time_interval.end}",                source="FileManager"            ))
        except Exception as e:
            self._send_message(AppMessage.error(                f"Ошибка обновления SR2Nav.cfg: {e}",                source="FileManager"            ))
    def create_config_files(self, working_paths: Dict[FileType, Path]) -> Tuple[bool, str]:
        mask_success, mask_msg = self.update_mask_file()
        if not mask_success:
            return False, mask_msg
        cfg_path = self._ctx.sr2nav_cfg
        try:
            content = self._generate_cfg_content(working_paths)
            cfg_path.write_text(content, encoding='cp1251')
            self._send_message(AppMessage.info(f"📝 Создан SR2Nav.cfg"))
        except Exception as e:
            return False, f"Ошибка создания SR2Nav.cfg: {e}"
        return True, "Конфигурационные файлы созданы"
    def update_mask_file(self) -> Tuple[bool, str]:
        """
        Обновляет только файл Mask.Ang на основе текущего угла отсечения.
        Используется как при полном цикле подготовки конфигов, так и при
        отдельном обновлении угла без запуска Interval.exe.
        """
        mask_path = self._ctx.mask_ang
        try:
            mask_path.write_text(f"{self._cutoff_angle:.1f}\n")
            self._send_message(AppMessage.info(
                f"📝 Обновлён Mask.Ang: {self._cutoff_angle}°",
                source="FileManager"
            ))
            return True, "Mask.Ang обновлён"
        except Exception as e:
            return False, f"Ошибка создания Mask.Ang: {e}"
    def _generate_cfg_content(self, working_paths: Dict[FileType, Path]) -> str:
        lines = []
        air_path = working_paths.get(FileType.AIR)
        lines.append(f"*{air_path.name if air_path else ''}")
        lines.append("*18")
        lines.append("*")
        if self._time_interval.start and self._time_interval.end:
            lines.append(f"*{self._time_interval.start} {self._time_interval.end}")
        else:
            lines.append("*1111111")
        rover_path = working_paths.get(FileType.ROVER)
        base1_path = working_paths.get(FileType.BASE1)
        base2_path = working_paths.get(FileType.BASE2)
        lines.append(f"*{rover_path.name if rover_path else ''}")
        lines.append(f"*{base1_path.name if base1_path else ''}")
        lines.append(f"*{base2_path.name if base2_path else ''}")
        return "\n".join(lines) + "\n"
    async def run_interval(self) -> Tuple[bool, str, Optional[Dict[FileType, Path]]]:
        files_needed = [FileType.ROVER, FileType.BASE1, FileType.BASE2, FileType.AIR]
        success, msg, prepared_paths = self.prepare_files(files_needed)
        if not success:
            return False, msg, None
        jps_files = {ft: p for ft, p in prepared_paths.items() if ft in (FileType.ROVER, FileType.BASE1, FileType.BASE2)}
        jps_success, jps_msg, fixed_count = self.fix_jps_headers(jps_files)
        if not jps_success:
            return False, jps_msg, prepared_paths
        cfg_success, cfg_msg = self.create_config_files(prepared_paths)
        if not cfg_success:
            return False, cfg_msg, prepared_paths
        return True, "Готов к запуску Interval.exe", prepared_paths
    async def parse_interval_result(self) -> Tuple[bool, str]:
        interval_file = self._ctx.interval_txt
        if not interval_file.exists():
            return False, "interval.txt не найден"
        try:
            content = interval_file.read_text(encoding='utf-8')
            for line in content.splitlines():
                if '[Common]' in line:
                    parts = line.split('-> [Common]')[0].strip().split()
                    if len(parts) >= 2:
                        start, end = parts[0], parts[1]
                        if self._time_interval.manual:
                            return True, (                                f"⚠️ Интервал сохранён вручную: {self._time_interval.start} - {self._time_interval.end}\n"                                f"   Результат Interval.exe игнорируется. Снимите ручной режим для авто-интервала."                            )
                        self.update_time_interval(start, end, manual=False)
                        return True, f"Интервал из Interval.exe: {start} - {end}"
            return False, "Временные метки не найдены"
        except Exception as e:
            return False, f"Ошибка парсинга: {e}"
    async def run_sr2nav(self) -> Tuple[bool, str, Optional[Dict[FileType, Path]]]:
        files_needed = [FileType.SR2NAV_EXE, FileType.ROVER, FileType.BASE1, FileType.BASE2, FileType.AIR]
        success, msg, prepared_paths = self.prepare_files(files_needed)
        if not success:
            return False, msg, None
        jps_files = {ft: p for ft, p in prepared_paths.items() if ft in (FileType.ROVER, FileType.BASE1, FileType.BASE2)}
        jps_success, jps_msg, fixed_count = self.fix_jps_headers(jps_files)
        if not jps_success:
            return False, jps_msg, prepared_paths
        cfg_success, cfg_msg = self.create_config_files(prepared_paths)
        if not cfg_success:
            return False, cfg_msg, prepared_paths
        return True, "Готов к запуску SR2Nav.exe", prepared_paths
    def move_results_to_results_dir(self) -> int:
        patterns = self.RESULT_FILE_PATTERNS
        results_dir = self._ctx.results_dir
        results_dir.mkdir(parents=True, exist_ok=True)
        moved = 0
        for pattern in patterns:
            for file_path in self._ctx.working_dir.glob(pattern):
                if file_path.is_file():
                    dest = results_dir / file_path.name
                    try:
                        if dest.exists():
                            dest.unlink()
                        shutil.move(str(file_path), str(dest))
                        moved += 1
                        self._send_message(AppMessage.debug(                            f"📦 {file_path.name} → {results_dir.name}/",                            source="FileManager"                        ))
                    except Exception as e:
                        self._send_message(AppMessage.warning(                            f"Не удалось переместить {file_path.name}: {e}",                            source="FileManager"                        ))
        return moved
    def stitch_jps_files(self, input_files: List[str], output_path: str) -> Tuple[bool, str]:
        try:
            paths = [Path(f) for f in input_files]
            output = Path(output_path)
            for p in paths:
                if p.suffix.lower() != '.jps':
                    return False, f"Файл должен быть .jps: {p.name}"
            if output.suffix.lower() != '.jps':
                return False, "Выходной файл должен иметь расширение .jps"
            output.parent.mkdir(exist_ok=True)
            total_size = sum(p.stat().st_size for p in paths)
            self._send_message(AppMessage.info(                f"🔗 Сшивание {len(paths)} файлов ({total_size / 1024 / 1024:.1f} МБ)"            ))
            with open(output, 'wb') as dst:
                for src in paths:
                    with open(src, 'rb') as f:
                        shutil.copyfileobj(f, dst)
            if not self._has_valid_header(output):
                self._send_message(AppMessage.info(f"  Добавлен заголовок JP055"))
                if not self._add_header(output):
                    return False, "Не удалось добавить заголовок JP055"
            else:
                self._send_message(AppMessage.debug(f"  Заголовок JP055 уже присутствует"))
            return True, f"Файл сохранён: {output.name}"
        except Exception as e:
            return False, f"Ошибка сшивания: {e}"
    def cleanup_working_directory(self, exclude_patterns: List[str] = None) -> Tuple[int, List[str]]:
        if exclude_patterns is None:
            # Не трогаем исполняемые файлы и служебный README_EXE.md
            exclude_patterns = ['*.exe', '*.py', '*.pyw', 'README_EXE.md']
        deleted_count = 0
        errors = []
        self._send_message(AppMessage.info(            "🧹 Очистка рабочей директории...",            source="FileManager"        ))
        try:
            for item in self._ctx.working_dir.iterdir():
                if item.is_dir():
                    continue
                should_exclude = False
                for pattern in exclude_patterns:
                    if item.match(pattern):
                        should_exclude = True
                        break
                if should_exclude:
                    self._send_message(AppMessage.debug(                        f"  Сохранён: {item.name} (исключён по паттерну)",                        source="FileManager"                    ))
                    continue
                try:
                    item.unlink()
                    deleted_count += 1
                    self._send_message(AppMessage.debug(                        f"  Удалён: {item.name}",                        source="FileManager"                    ))
                except Exception as e:
                    error_msg = f"Не удалось удалить {item.name}: {e}"
                    errors.append(error_msg)
                    self._send_message(AppMessage.warning(                        error_msg,                        source="FileManager"                    ))
            removed_from_working = 0
            for file_type, path in list(self._working_paths.items()):
                if not path.exists():
                    self._working_paths.pop(file_type, None)
                    removed_from_working += 1
                    self._send_message(AppMessage.debug(                        f"  🧹 Удалена ссылка на несуществующий файл: {path.name}",                        source="FileManager"                    ))
            if removed_from_working > 0:
                self._send_message(AppMessage.info(                    f"  Синхронизировано состояние: удалено {removed_from_working} несуществующих файлов из списка",                    source="FileManager"                ))
            if deleted_count > 0:
                self._send_message(AppMessage.info(                    f"✅ Очистка завершена. Удалено файлов: {deleted_count}",                    source="FileManager"                ))
            else:
                self._send_message(AppMessage.info(                    "✨ В рабочей директории нет файлов для удаления",                    source="FileManager"                ))
        except Exception as e:
            error_msg = f"Ошибка при очистке рабочей директории: {e}"
            errors.append(error_msg)
            self._send_message(AppMessage.error(                error_msg,                source="FileManager"            ))
        return deleted_count, errors
    def _send_message(self, message: AppMessage) -> None:
        if self._message_callback:
            self._message_callback(message)