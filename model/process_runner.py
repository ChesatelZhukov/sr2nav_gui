#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Асинхронный менеджер внешних процессов.
Запуск, мониторинг и безопасное завершение программ.
"""

import asyncio
import re
import signal
from typing import Optional, List, Callable, Dict, Set
from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime


class ProcessType(Enum):
    """Типы поддерживаемых внешних процессов."""
    INTERVAL = auto()
    SR2NAV = auto()
    
    @property
    def display_name(self) -> str:
        """Человекочитаемое имя процесса."""
        return {
            ProcessType.INTERVAL: "Interval.exe",
            ProcessType.SR2NAV: "SR2Nav.exe",
        }[self]


@dataclass
class ProcessStatus:
    """Текущее состояние процесса."""
    pid: Optional[int] = None
    process_type: Optional[ProcessType] = None
    is_running: bool = False
    exit_code: Optional[int] = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def duration(self) -> Optional[float]:
        """Длительность выполнения в секундах."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None


class ProcessRunner:
    """
    Управление внешними процессами с асинхронным вводом-выводом.
    
    Особенности:
        - Фильтрация потока вывода (только значимые строки)
        - Автоматическая отправка Enter для SR2Nav
        - Безопасное завершение (terminate → kill)
        - Декодирование в разных кодировках
    """
    
    # Ключевые фразы для фильтрации вывода SR2Nav
    SR2NAV_FILTER_KEYWORDS: Set[str] = {
        "Conversion JPS to Ashtech Format",
        "Rover   (E-File)", "Rover   (B-File)",
        "Base #1 (B-File)",
        "GPS Raw Data Files Checking",
        "Carrier Phase Differential Mode",
        "INS - GPS Integration",
        "Time span:",
        "Processing",
    }
    
    def __init__(
        self,
        message_callback: Callable[[str, str], None],
        sr2nav_enter_delay: float = 0.7,
    ):
        """
        Args:
            message_callback: Функция для отправки сообщений (текст, уровень)
            sr2nav_enter_delay: Задержка перед отправкой Enter для SR2Nav (сек)
        """
        self._message_callback = message_callback
        self._sr2nav_enter_delay = max(0.2, min(2.0, sr2nav_enter_delay))
        
        self._process: Optional[asyncio.subprocess.Process] = None
        self._process_type: Optional[ProcessType] = None
        self._status = ProcessStatus()
        
        self._read_tasks: List[asyncio.Task] = []
    
    # ==================== СВОЙСТВА ====================
    
    @property
    def is_running(self) -> bool:
        """Активен ли процесс в данный момент."""
        return self._process is not None and self._process.returncode is None
    
    @property
    def status(self) -> ProcessStatus:
        """Текущее состояние процесса (копия)."""
        status = ProcessStatus(
            pid=self._status.pid,
            process_type=self._process_type,
            is_running=self.is_running,
            exit_code=self._status.exit_code,
            error=self._status.error,
            start_time=self._status.start_time,
            end_time=self._status.end_time,
        )
        return status
    
    # ==================== ЗАПУСК ====================
    
    async def run(
        self,
        command: List[str],
        working_dir: str,
        process_type: ProcessType,
        timeout: Optional[float] = None,
    ) -> int:
        """
        Запускает внешний процесс и ожидает его завершения.
        
        Args:
            command: Команда и аргументы
            working_dir: Рабочая директория
            process_type: Тип процесса
            timeout: Максимальное время выполнения (None — бесконечно)
            
        Returns:
            Код возврата процесса, -1 при ошибке запуска
        """
        # Завершаем предыдущий процесс, если он ещё выполняется
        if self.is_running:
            await self.terminate()
        
        self._process_type = process_type
        self._status = ProcessStatus(
            start_time=datetime.now(),
            process_type=process_type,
        )
        
        self._send_message(
            f"🚀 Запуск {process_type.display_name}...",
            "info"
        )
        
        try:
            self._process = await asyncio.create_subprocess_exec(
                *command,
                cwd=working_dir,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
        except FileNotFoundError:
            self._status.error = f"Исполняемый файл не найден: {command[0]}"
            self._send_message(f"❌ {self._status.error}", "error")
            self._status.end_time = datetime.now()
            return -1
            
        except PermissionError:
            self._status.error = f"Нет прав на запуск: {command[0]}"
            self._send_message(f"❌ {self._status.error}", "error")
            self._status.end_time = datetime.now()
            return -1
            
        except Exception as error:
            self._status.error = f"Ошибка запуска: {error}"
            self._send_message(f"❌ {self._status.error}", "error")
            self._status.end_time = datetime.now()
            return -1
        
        self._status.pid = self._process.pid
        self._send_message(f"  PID: {self._status.pid}", "debug")
        
        # Запускаем асинхронное чтение потоков
        self._read_tasks = [
            asyncio.create_task(self._read_stream(self._process.stdout, "stdout")),
            asyncio.create_task(self._read_stream(self._process.stderr, "stderr")),
        ]
        
        # Специальная обработка для SR2Nav (требует нажатия Enter)
        if process_type == ProcessType.SR2NAV and self._process.stdin:
            asyncio.create_task(self._send_enter_with_delay())
        
        # Ожидаем завершения процесса
        try:
            return_code = await asyncio.wait_for(
                self._process.wait(),
                timeout=timeout
            )
            
        except asyncio.TimeoutError:
            if process_type == ProcessType.INTERVAL:
                # Interval.exe не завершается самостоятельно — это норма
                self._send_message(
                    "ℹ️ Interval.exe: превышен таймаут (штатное поведение)",
                    "debug"
                )
                return_code = 0
            else:
                self._send_message(
                    f"⚠️ Превышено время выполнения ({timeout} с)",
                    "warning"
                )
                await self.terminate()
                return_code = -1
                
        finally:
            # Отменяем задачи чтения
            for task in self._read_tasks:
                task.cancel()
            
            if self._read_tasks:
                await asyncio.gather(*self._read_tasks, return_exceptions=True)
                self._read_tasks.clear()
            
            self._status.end_time = datetime.now()
            self._status.exit_code = return_code
        
        # Итоговое сообщение
        if return_code == 0:
            self._send_message(
                f"✅ {process_type.display_name} успешно завершён",
                "success"
            )
        else:
            self._send_message(
                f"⚠️ {process_type.display_name} завершён с кодом: {return_code}",
                "warning"
            )
        
        return return_code
    
    async def _send_enter_with_delay(self) -> None:
        """Отправляет сигнал Enter после заданной задержки."""
        if not self._process or not self._process.stdin:
            return
        
        await asyncio.sleep(self._sr2nav_enter_delay)
        
        try:
            self._process.stdin.write(b'\n')
            await self._process.stdin.drain()
            self._send_message(
                f"📨 Отправлен Enter (задержка: {self._sr2nav_enter_delay:.1f} с)",
                "debug"
            )
        except (BrokenPipeError, ConnectionError) as error:
            self._send_message(
                f"⚠️ Не удалось отправить Enter: {error}",
                "warning"
            )
        except Exception as error:
            self._send_message(
                f"⚠️ Ошибка отправки Enter: {error}",
                "warning"
            )
    
    # ==================== ЧТЕНИЕ ВЫВОДА ====================
    
    async def _read_stream(self, stream: Optional[asyncio.StreamReader], name: str) -> None:
        """
        Читает поток вывода, фильтрует и отправляет в систему сообщений.
        
        Args:
            stream: Поток для чтения
            name: Имя потока (stdout/stderr)
        """
        if not stream:
            return
        
        buffer = bytearray()
        
        while True:
            try:
                chunk = await asyncio.wait_for(stream.read(256), timeout=0.1)
                
                if not chunk:
                    # Остаток данных в буфере
                    if buffer:
                        line = self._decode_bytes(buffer)
                        self._process_output_line(line)
                    break
                
                buffer.extend(chunk)
                
                # Разбиваем по символам новой строки
                while b'\n' in buffer:
                    line_bytes, buffer = buffer.split(b'\n', 1)
                    line = self._decode_bytes(line_bytes)
                    self._process_output_line(line)
                
                # Защита от бесконечного роста буфера
                if len(buffer) > 8192:
                    line = self._decode_bytes(buffer)
                    self._process_output_line(line)
                    buffer.clear()
                    
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as error:
                self._send_message(
                    f"⚠️ Ошибка чтения {name}: {error}",
                    "debug"
                )
                break
    
    def _decode_bytes(self, data: bytes) -> str:
        """
        Пытается декодировать байты в строку, перебирая кодировки.
        
        Returns:
            Декодированная строка, при полном провале — с игнорированием ошибок
        """
        for encoding in ['utf-8', 'cp1251', 'cp866', 'latin-1']:
            try:
                return data.decode(encoding).rstrip()
            except UnicodeDecodeError:
                continue
        
        return data.decode('utf-8', errors='ignore').rstrip()
    
    def _process_output_line(self, line: str) -> None:
        """Фильтрует и отправляет строку вывода."""
        if not line:
            return
        
        # Фильтрация по типу процесса
        if self._process_type == ProcessType.SR2NAV:
            if not self._should_show_sr2nav_line(line):
                return
        else:
            if not self._should_show_interval_line(line):
                return
        
        self._send_message(line, "info")
    
    def _should_show_sr2nav_line(self, line: str) -> bool:
        """Проверяет, нужно ли показывать строку вывода SR2Nav."""
        line_upper = line.upper()
        
        for keyword in self.SR2NAV_FILTER_KEYWORDS:
            if keyword in line or keyword.upper() in line_upper:
                return True
        
        return False
    
    def _should_show_interval_line(self, line: str) -> bool:
        """Проверяет, нужно ли показывать строку вывода Interval.exe."""
        line = line.strip()
        
        # Пропускаем рамку
        if line.startswith('*') and line.endswith('*'):
            return False
        
        # Пропускаем числовые данные
        if line.startswith('I:'):
            return False
        
        # Пропускаем строки только из цифр и разделителей
        if re.match(r'^[\d\s\.]+$', line):
            return False
        
        return bool(line)
    
    # ==================== ОСТАНОВКА ====================
    
    async def terminate(self) -> bool:
        """
        Безопасно завершает текущий процесс.
        
        Returns:
            True если процесс был остановлен
        """
        if not self._process:
            self._send_message("ℹ️ Нет активного процесса", "info")
            return False
        
        if self._process.returncode is not None:
            self._process = None
            self._process_type = None
            self._status.is_running = False
            return True
        
        process_name = self._process_type.display_name if self._process_type else "процесс"
        self._send_message(f"🛑 Остановка {process_name}...", "warning")
        
        try:
            # Мягкое завершение
            self._process.terminate()
            
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
                self._send_message(f"✓ {process_name} завершён", "info")
                return True
                
            except asyncio.TimeoutError:
                # Принудительное завершение
                self._send_message(f"⚠️ Принудительное завершение...", "warning")
                self._process.kill()
                await self._process.wait()
                self._send_message(f"✓ {process_name} остановлен", "info")
                return True
                
        except ProcessLookupError:
            self._send_message(f"✓ {process_name} уже завершён", "info")
            return True
            
        except Exception as error:
            self._send_message(f"❌ Ошибка остановки: {error}", "error")
            return False
            
        finally:
            self._process = None
            self._process_type = None
            self._status.is_running = False
            self._status.end_time = datetime.now()
    
    # ==================== ВСПОМОГАТЕЛЬНЫЕ ====================
    
    def _send_message(self, text: str, level: str = "info") -> None:
        """Отправляет сообщение через колбэк."""
        if self._message_callback:
            try:
                self._message_callback(text, level)
            except Exception:
                print(f"[ProcessRunner] {level.upper()}: {text}")