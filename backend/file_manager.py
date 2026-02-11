#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Менеджер файлов - вся работа с файловой системой.
Копирование, проверка заголовков JPS, создание конфигов.
"""
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
    """Типы файлов, используемые в приложении."""
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
        """Ожидаемое расширение файла."""
        return {
            FileType.ROVER: '.jps',
            FileType.BASE1: '.jps',
            FileType.BASE2: '.jps',
            FileType.POS1: '.pos',
            FileType.POS2: '.pos',
            FileType.CFG: '.cfg',
            FileType.AIR: '.air',
            FileType.SR2NAV_EXE: '.exe',
        }[self]
    
    @property
    def description(self) -> str:
        """Человекочитаемое описание."""
        return {
            FileType.ROVER: "Файл ровера (JPS)",
            FileType.BASE1: "Файл базы 1 (JPS)",
            FileType.BASE2: "Файл базы 2 (JPS)",
            FileType.POS1: "POS файл базы 1",
            FileType.POS2: "POS файл базы 2",
            FileType.CFG: "Конфигурационный файл",
            FileType.AIR: "Файл гравики",
            FileType.SR2NAV_EXE: "Исполняемый файл SR2Nav",
        }[self]
    
    @property
    def is_required(self) -> bool:
        """Обязателен ли файл для работы."""
        return self in (FileType.ROVER, FileType.SR2NAV_EXE)


@dataclass
class TimeInterval:
    """Временной интервал для обработки."""
    start: str = ""
    end: str = ""


class FileManager:
    """
    Менеджер файлов.
    Отвечает за:
        - Хранение путей к файлам
        - Копирование в рабочую директорию
        - Проверку и исправление JPS заголовков
        - Создание конфигурационных файлов
    """
    
    # Заголовок JPS файла в разных кодировках
    JPS_HEADER = "JP055"
    JPS_HEADER_BYTES = JPS_HEADER.encode('cp1251')
    
    def __init__(self, context: AppContext, message_callback: Callable[[AppMessage], None]):
        """
        :param context: Контекст приложения
        :param message_callback: Функция для отправки сообщений
        """
        self._ctx = context
        self._message_callback = message_callback
        
        # Словарь путей к файлам (оригинальные пути от пользователя)
        self._original_paths: Dict[FileType, Path] = {}
        
        # Словарь путей в рабочей директории (после копирования)
        self._working_paths: Dict[FileType, Path] = {}
        
        # Параметры
        self._cutoff_angle: float = 7.0
        self._time_interval = TimeInterval()
    
    # ==================== ПУБЛИЧНЫЙ API ====================
    
    def set_path(self, file_type: FileType, path: str | Path) -> None:
        """Устанавливает путь к файлу."""
        if not path:
            self._original_paths.pop(file_type, None)
            self._working_paths.pop(file_type, None)
            return
        
        path_obj = Path(path)
        self._original_paths[file_type] = path_obj
        
        # Если файл уже в рабочей директории - сразу обновляем working_paths
        if path_obj.parent == self._ctx.working_dir:
            self._working_paths[file_type] = path_obj
    
    def get_path(self, file_type: FileType) -> Optional[Path]:
        """Возвращает путь к файлу в рабочей директории (если есть)."""
        return self._working_paths.get(file_type)
    
    def get_original_path(self, file_type: FileType) -> Optional[Path]:
        """Возвращает оригинальный путь к файлу (от пользователя)."""
        return self._original_paths.get(file_type)
    
    def get_all_paths(self) -> Dict[str, str]:
        """
        Возвращает словарь {ключ_файла: путь} для синхронизации с UI.
        Ключи соответствуют FileType.value.
        """
        result = {}
        for file_type, path in self._working_paths.items():
            result[file_type.value] = str(path)
        return result
    
    # ==================== ПАРАМЕТРЫ ====================
    
    @property
    def cutoff_angle(self) -> float:
        """Угол отсечения в градусах."""
        return self._cutoff_angle
    
    def set_cutoff_angle(self, angle: float) -> None:
        """Устанавливает угол отсечения."""
        self._cutoff_angle = round(angle, 1)
    
    @property
    def time_interval(self) -> TimeInterval:
        """Временной интервал."""
        return self._time_interval
    
    # ==================== ПОДГОТОВКА ФАЙЛОВ ====================
    
    def prepare_files(self) -> Tuple[bool, str]:
        """
        Копирует все файлы в рабочую директорию и проверяет JPS заголовки.
        
        Returns:
            (успех, сообщение)
        """
        self._send_message(AppMessage.info("📋 Подготовка файлов..."))
        
        # 1. Копирование файлов
        copy_success, copy_msg = self._copy_all_files()
        if not copy_success:
            return False, copy_msg
        
        # 2. Проверка JPS файлов
        jps_success, jps_msg = self._fix_jps_headers()
        if not jps_success:
            return False, jps_msg
        
        # 3. Проверка обязательных файлов
        for file_type in [FileType.ROVER, FileType.SR2NAV_EXE]:
            if file_type not in self._working_paths:
                return False, f"{file_type.description} не найден в рабочей директории"
        
        return True, "Файлы готовы"
    
    def _copy_all_files(self) -> Tuple[bool, str]:
        """
        Копирует все файлы из оригинальных путей в рабочую директорию.
        """
        for file_type, src_path in self._original_paths.items():
            if not src_path.exists():
                self._send_message(AppMessage.warning(
                    f"Файл не найден: {src_path.name}", 
                    source="FileManager"
                ))
                continue
            
            # Если файл уже в рабочей директории - пропускаем
            if src_path.parent == self._ctx.working_dir:
                self._working_paths[file_type] = src_path
                continue
            
            dst_path = self._ctx.working_dir / src_path.name
            
            try:
                # Для больших JPS файлов - копирование с прогрессом
                if file_type in (FileType.ROVER, FileType.BASE1, FileType.BASE2):
                    self._copy_large_file(src_path, dst_path)
                else:
                    shutil.copy2(src_path, dst_path)
                
                self._working_paths[file_type] = dst_path
                self._send_message(AppMessage.info(f"✓ {src_path.name} → рабочая директория"))
                
            except Exception as e:
                return False, f"Ошибка копирования {src_path.name}: {e}"
        
        return True, "Копирование завершено"
    
    def _copy_large_file(self, src: Path, dst: Path, chunk_size: int = 64 * 1024 * 1024) -> None:
        """
        Копирует большой файл с выводом прогресса.
        
        Args:
            src: Исходный файл
            dst: Целевой файл
            chunk_size: Размер блока (64 МБ по умолчанию)
        """
        total = src.stat().st_size
        copied = 0
        
        with open(src, 'rb') as f_src, open(dst, 'wb') as f_dst:
            while True:
                chunk = f_src.read(chunk_size)
                if not chunk:
                    break
                f_dst.write(chunk)
                copied += len(chunk)
                
                # Отправляем прогресс каждые 10%
                progress = int((copied / total) * 100)
                if progress % 10 == 0:
                    self._send_message(AppMessage.debug(
                        f"Копирование {src.name}: {progress}%"
                    ))
    
    # ==================== JPS ЗАГОЛОВКИ ====================
    
    def _fix_jps_headers(self) -> Tuple[bool, str]:
        """
        Проверяет и исправляет заголовки JPS файлов.
        """
        jps_files = [
            (FileType.ROVER, "ровера"),
            (FileType.BASE1, "базы 1"),
            (FileType.BASE2, "базы 2"),
        ]
        
        fixed_count = 0
        
        for file_type, description in jps_files:
            if file_type not in self._working_paths:
                continue
            
            path = self._working_paths[file_type]
            
            # Проверяем заголовок
            if self._has_valid_header(path):
                self._send_message(AppMessage.debug(f"✓ {path.name}: заголовок JP055 OK"))
                continue
            
            # Добавляем заголовок
            if self._add_header(path):
                fixed_count += 1
                self._send_message(AppMessage.info(f"🔧 {path.name}: добавлен заголовок JP055"))
            else:
                return False, f"Не удалось исправить заголовок {path.name}"
        
        if fixed_count > 0:
            return True, f"Исправлено JPS файлов: {fixed_count}"
        
        return True, "JPS файлы в порядке"
    
    def _has_valid_header(self, path: Path) -> bool:
        """
        Проверяет наличие корректного заголовка JP055.
        """
        try:
            with open(path, 'rb') as f:
                header = f.read(5)
            
            # Проверяем в разных кодировках
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
        """
        Добавляет заголовок JP055 в начало файла.
        """
        temp_path = path.with_suffix('.tmp')
        backup_path = path.with_suffix('.bak')
        
        try:
            # Создаём резервную копию
            shutil.copy2(path, backup_path)
            
            # Создаём новый файл с заголовком
            with open(path, 'rb') as src, open(temp_path, 'wb') as dst:
                dst.write(self.JPS_HEADER_BYTES)
                shutil.copyfileobj(src, dst)
            
            # Заменяем оригинал
            shutil.move(temp_path, path)
            
            # Проверяем размер
            expected_size = path.stat().st_size + len(self.JPS_HEADER_BYTES)
            actual_size = backup_path.stat().st_size
            
            if actual_size == expected_size:
                # Удаляем бэкап
                backup_path.unlink(missing_ok=True)
                return True
            else:
                # Восстанавливаем из бэкапа
                shutil.move(backup_path, path)
                return False
                
        except Exception as e:
            self._send_message(AppMessage.error(f"Ошибка добавления заголовка: {e}"))
            
            # Пытаемся восстановить
            if backup_path.exists():
                shutil.move(backup_path, path)
            return False
    
    # ==================== СОЗДАНИЕ КОНФИГОВ ====================
    
    def create_config_files(self) -> Tuple[bool, str]:
        """
        Создаёт конфигурационные файлы для Interval.exe и SR2Nav.
        
        Returns:
            (успех, сообщение)
        """
        # 1. Mask.Ang
        mask_path = self._ctx.mask_ang
        try:
            mask_path.write_text(f"{self._cutoff_angle:.1f}\n")
            self._send_message(AppMessage.info(f"📝 Создан Mask.Ang: {self._cutoff_angle}°"))
        except Exception as e:
            return False, f"Ошибка создания Mask.Ang: {e}"
        
        # 2. SR2Nav.cfg
        cfg_path = self._ctx.sr2nav_cfg
        try:
            content = self._generate_cfg_content()
            cfg_path.write_text(content, encoding='utf-8')
            self._send_message(AppMessage.info(f"📝 Создан SR2Nav.cfg"))
        except Exception as e:
            return False, f"Ошибка создания SR2Nav.cfg: {e}"
        
        return True, "Конфигурационные файлы созданы"
    
    def _generate_cfg_content(self) -> str:
        """
        Генерирует содержимое SR2Nav.cfg.
        """
        lines = []
        
        # Строка 1: AIR файл
        air_path = self._working_paths.get(FileType.AIR)
        lines.append(f"*{air_path.name if air_path else ''}")
        
        # Строка 2: *18
        lines.append("*18")
        
        # Строка 3: *
        lines.append("*")
        
        # Строка 4: временной интервал (будет обновлён после Interval.exe)
        if self._time_interval.start and self._time_interval.end:
            lines.append(f"*{self._time_interval.start} {self._time_interval.end}")
        else:
            lines.append("*1111111")
        
        # Строки 5-7: файлы ровера и баз
        rover_path = self._working_paths.get(FileType.ROVER)
        base1_path = self._working_paths.get(FileType.BASE1)
        base2_path = self._working_paths.get(FileType.BASE2)
        
        lines.append(f"*{rover_path.name if rover_path else ''}")
        lines.append(f"*{base1_path.name if base1_path else ''}")
        lines.append(f"*{base2_path.name if base2_path else ''}")
        
        return "\n".join(lines) + "\n"
    
    def update_config_with_interval(self, start: str, end: str) -> None:
        """
        Обновляет SR2Nav.cfg с временным интервалом.
        """
        self._time_interval = TimeInterval(start, end)
        
        cfg_path = self._ctx.sr2nav_cfg
        if not cfg_path.exists():
            return
        
        try:
            lines = cfg_path.read_text(encoding='utf-8').splitlines()
            if len(lines) >= 4:
                lines[3] = f"*{start} {end}"
                cfg_path.write_text("\n".join(lines) + "\n", encoding='utf-8')
                self._send_message(AppMessage.info(f"📝 Обновлён интервал: {start} - {end}"))
        except Exception as e:
            self._send_message(AppMessage.error(f"Ошибка обновления конфига: {e}"))
    
    # ==================== INTERVAL.EXE ====================
    
    async def run_interval(self) -> Tuple[bool, str]:
        """
        Подготавливает и запускает Interval.exe.
        Этот метод вызывается из ProcessRunner.
        """
        # Подготовка файлов
        success, msg = self.prepare_files()
        if not success:
            return False, msg
        
        # Создание конфигов
        success, msg = self.create_config_files()
        if not success:
            return False, msg
        
        # Проверка наличия Interval.exe
        if not self._ctx.interval_exe.exists():
            return False, "Interval.exe не найден в рабочей директории"
        
        return True, "Готов к запуску Interval.exe"
    
    async def parse_interval_result(self) -> Tuple[bool, str]:
        """
        Парсит результат работы Interval.exe из interval.txt.
        """
        interval_file = self._ctx.interval_txt
        
        if not interval_file.exists():
            return False, "interval.txt не найден"
        
        try:
            content = interval_file.read_text(encoding='utf-8')
            
            # Ищем строку с [Common]
            for line in content.splitlines():
                if '[Common]' in line:
                    parts = line.split('-> [Common]')[0].strip().split()
                    if len(parts) >= 2:
                        start, end = parts[0], parts[1]
                        self.update_config_with_interval(start, end)
                        return True, f"Интервал: {start} - {end}"
            
            return False, "Временные метки не найдены"
            
        except Exception as e:
            return False, f"Ошибка парсинга: {e}"
    
    # ==================== SR2NAV ====================
    
    async def run_sr2nav(self) -> Tuple[bool, str]:
        """
        Подготавливает и запускает SR2Nav.exe.
        """
        # Проверяем наличие SR2Nav.exe
        sr2nav_path = self._working_paths.get(FileType.SR2NAV_EXE)
        if not sr2nav_path or not sr2nav_path.exists():
            return False, "SR2Nav.exe не найден"
        
        # Проверяем наличие конфига
        if not self._ctx.sr2nav_cfg.exists():
            success, msg = self.create_config_files()
            if not success:
                return False, msg
        
        return True, "Готов к запуску SR2Nav.exe"
    
    # ==================== ПЕРЕМЕЩЕНИЕ РЕЗУЛЬТАТОВ ====================
    
    def move_results_to_results_dir(self) -> None:
        """
        Перемещает результаты работы SR2Nav в папку results.
        """
        patterns = [
            '*.ins',
            'Phase*.VEL',
            '*_Std.QC',
            'Phase.QC',
            '*.EXIT',
            'Visible*.SVs',
        ]
        
        import glob
        moved = 0
        
        for pattern in patterns:
            for file_path in self._ctx.working_dir.glob(pattern):
                if file_path.is_file():
                    dest = self._ctx.results_dir / file_path.name
                    try:
                        shutil.move(str(file_path), str(dest))
                        moved += 1
                        self._send_message(AppMessage.debug(f"📦 {file_path.name} → results/"))
                    except Exception as e:
                        self._send_message(AppMessage.warning(
                            f"Не удалось переместить {file_path.name}: {e}"
                        ))
        
        if moved > 0:
            self._send_message(AppMessage.info(f"📦 Перемещено файлов в results: {moved}"))
    
    # ==================== СШИВАНИЕ JPS ====================
    
    def stitch_jps_files(self, input_files: List[str], output_path: str) -> Tuple[bool, str]:
        """
        Сшивает несколько JPS файлов в один.
        
        Args:
            input_files: Список путей к JPS файлам
            output_path: Путь к выходному файлу
            
        Returns:
            (успех, сообщение)
        """
        try:
            # Валидация
            paths = [Path(f) for f in input_files]
            for p in paths:
                if not p.exists():
                    return False, f"Файл не найден: {p.name}"
                if p.suffix.lower() != '.jps':
                    return False, f"Файл должен быть .jps: {p.name}"
            
            output = Path(output_path)
            if output.suffix.lower() != '.jps':
                return False, "Выходной файл должен иметь расширение .jps"
            
            # Создаём директорию
            output.parent.mkdir(exist_ok=True)
            
            # Конкатенация
            total_size = sum(p.stat().st_size for p in paths)
            self._send_message(AppMessage.info(
                f"🔗 Сшивание {len(paths)} файлов ({total_size / 1024 / 1024:.1f} МБ)"
            ))
            
            with open(output, 'wb') as dst:
                for src in paths:
                    with open(src, 'rb') as f:
                        shutil.copyfileobj(f, dst)
            
            # Проверяем заголовок
            if not self._has_valid_header(output):
                self._add_header(output)
                self._send_message(AppMessage.info("  Добавлен заголовок JP055"))
            
            return True, f"Файл сохранён: {output.name}"
            
        except Exception as e:
            return False, f"Ошибка сшивания: {e}"
    
    # ==================== ВСПОМОГАТЕЛЬНЫЕ ====================
    
    def _send_message(self, message: AppMessage) -> None:
        """Отправляет сообщение через callback."""
        if self._message_callback:
            self._message_callback(message)