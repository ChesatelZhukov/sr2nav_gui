#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Асинхронный менеджер процессов.
Запуск, контроль и остановка внешних программ.
"""
import asyncio
import re
import signal
from typing import Optional, List, Callable
from enum import Enum
from dataclasses import dataclass

from core.message_system import AppMessage


class ProcessType(Enum):
    """Типы внешних процессов."""
    INTERVAL = "interval"
    SR2NAV = "sr2nav"


@dataclass
class ProcessStatus:
    """Статус запущенного процесса."""
    pid: int
    name: str
    is_running: bool
    exit_code: Optional[int] = None
    error: Optional[str] = None


class ProcessRunner:
    """
    Асинхронный раннер внешних процессов.
    
    Особенности:
        - Чтение stdout/stderr в реальном времени
        - Фильтрация вывода для SR2Nav
        - Автоматическая отправка Enter для SR2Nav
        - Безопасное завершение процессов
    """
    
    # Ключевые этапы вывода SR2Nav (только их показываем)
    SR2NAV_FILTER_KEYWORDS = {
        "Conversion JPS to Ashtech Format",
        "Rover   (E-File)", "Rover   (B-File)",
        "Base #1 (B-File)",
        "GPS Raw Data Files Checking",
        "Carrier Phase Differential Mode",
        "INS - GPS Integration",
        "Time span:",
        "Processing",
    }
    
    def __init__(self, message_callback: Callable[[AppMessage], None]):
        """
        :param message_callback: Функция для отправки сообщений
        """
        self._message_callback = message_callback
        self._process: Optional[asyncio.subprocess.Process] = None
        self._process_type: Optional[ProcessType] = None
        self._pid: Optional[int] = None
    
    # ==================== СВОЙСТВА ====================
    
    @property
    def is_running(self) -> bool:
        """Запущен ли процесс."""
        return self._process is not None and self._process.returncode is None
    
    @property
    def pid(self) -> Optional[int]:
        """PID процесса."""
        return self._pid
    
    # ==================== ЗАПУСК ====================
    
    async def run(
        self,
        cmd: List[str],
        cwd: str,
        process_type: ProcessType,
        timeout: Optional[float] = None,
    ) -> int:
        """
        Запускает процесс и ожидает завершения.
        
        Args:
            cmd: Команда для запуска
            cwd: Рабочая директория
            process_type: Тип процесса
            timeout: Таймаут ожидания (сек)
            
        Returns:
            Код возврата процесса
        """
        self._process_type = process_type
        
        self._send_message(AppMessage.info(
            f"🚀 Запуск {process_type.value}...",
            source="ProcessRunner"
        ))
        
        # Создаём подпроцесс
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        self._pid = self._process.pid
        self._send_message(AppMessage.debug(
            f"PID: {self._pid}",
            source="ProcessRunner"
        ))
        
        # Запускаем чтение потоков
        stdout_task = asyncio.create_task(
            self._read_stream(self._process.stdout, "stdout")
        )
        stderr_task = asyncio.create_task(
            self._read_stream(self._process.stderr, "stderr")
        )
        
        # Спецобработка для SR2Nav
        if process_type == ProcessType.SR2NAV and self._process.stdin:
            await self._send_enter_to_sr2nav()
        
        # Ожидание завершения
        try:
            return_code = await asyncio.wait_for(
                self._process.wait(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            if process_type == ProcessType.INTERVAL:
                # Interval.exe не завершается сам, это нормально
                self._send_message(AppMessage.debug(
                    "Interval.exe: таймаут (нормальное поведение)",
                    source="ProcessRunner"
                ))
                return_code = 0
            else:
                raise
        finally:
            # Отменяем задачи чтения
            stdout_task.cancel()
            stderr_task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        
        self._send_message(AppMessage.info(
            f"✅ Процесс {process_type.value} завершён (код: {return_code})",
            source="ProcessRunner"
        ))
        
        return return_code
    
    async def _send_enter_to_sr2nav(self) -> None:
        """Отправляет Enter для запуска SR2Nav."""
        await asyncio.sleep(0.5)  # Ждём инициализацию
        
        try:
            self._process.stdin.write(b'\n')
            await self._process.stdin.drain()
            self._send_message(AppMessage.debug(
                "📨 Отправлен сигнал Enter",
                source="ProcessRunner"
            ))
        except Exception as e:
            self._send_message(AppMessage.warning(
                f"Не удалось отправить Enter: {e}",
                source="ProcessRunner"
            ))
    
    # ==================== ЧТЕНИЕ ПОТОКОВ ====================
    
    async def _read_stream(self, stream: Optional[asyncio.StreamReader], name: str) -> None:
        """
        Читает поток вывода процесса и фильтрует его.
        """
        if not stream:
            return
        
        while True:
            try:
                line_bytes = await asyncio.wait_for(stream.readline(), timeout=0.1)
                if not line_bytes:
                    break
                
                line = self._decode_line(line_bytes)
                if line and self._should_show_line(line):
                    self._send_message(AppMessage.info(
                        line.strip(),
                        source=self._process_type.value
                    ))
                    
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._send_message(AppMessage.debug(
                    f"Ошибка чтения {name}: {e}",
                    source="ProcessRunner"
                ))
                break
    
    def _should_show_line(self, line: str) -> bool:
        """
        Определяет, нужно ли показывать строку вывода.
        """
        if not line.strip():
            return False
        
        # Пропускаем шапку Interval.exe
        if line.startswith('*   ') and line.endswith('   *'):
            return False
        
        # Пропускаем строки с I: (числовые данные)
        if line.startswith('I:'):
            return False
        
        # Пропускаем строки только из цифр и точек
        if re.match(r'^[\d\s\.]+$', line.strip()):
            return False
        
        # Для SR2Nav показываем только ключевые этапы
        if self._process_type == ProcessType.SR2NAV:
            return any(kw in line for kw in self.SR2NAV_FILTER_KEYWORDS)
        
        return True
    
    def _decode_line(self, line_bytes: bytes) -> str:
        """
        Декодирует байтовую строку в UTF-8 с fallback на другие кодировки.
        """
        for encoding in ['utf-8', 'cp1251', 'cp866', 'iso-8859-1']:
            try:
                return line_bytes.decode(encoding).rstrip()
            except UnicodeDecodeError:
                continue
        
        return line_bytes.decode('utf-8', errors='ignore').rstrip()
    
    # ==================== ОСТАНОВКА ====================
    
    async def terminate(self) -> None:
        """Безопасно завершает процесс."""
        if not self._process:
            self._send_message(AppMessage.info(
                "Нет активного процесса",
                source="ProcessRunner"
            ))
            return
        
        self._send_message(AppMessage.info(
            "🛑 Остановка процесса...",
            source="ProcessRunner"
        ))
        
        try:
            # Пробуем мягкое завершение
            self._process.terminate()
            await asyncio.wait_for(self._process.wait(), timeout=2.0)
            self._send_message(AppMessage.info(
                "✓ Процесс завершён",
                source="ProcessRunner"
            ))
        except asyncio.TimeoutError:
            # Принудительное завершение
            self._send_message(AppMessage.warning(
                "⚠️ Принудительное завершение...",
                source="ProcessRunner"
            ))
            self._process.kill()
            await self._process.wait()
        except Exception as e:
            self._send_message(AppMessage.error(
                f"Ошибка завершения: {e}",
                source="ProcessRunner"
            ))
        finally:
            self._process = None
            self._pid = None
    
    # ==================== ВСПОМОГАТЕЛЬНЫЕ ====================
    
    def _send_message(self, message: AppMessage) -> None:
        """Отправляет сообщение через callback."""
        if self._message_callback:
            self._message_callback(message)