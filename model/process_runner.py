import asyncio
import re
from typing import Optional, List, Callable, Dict, Set, Tuple
from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime
from core.message_system import AppMessage, MessageLevel
class ProcessType(Enum):
    INTERVAL = auto()
    SR2NAV = auto()
    @property
    def display_name(self) -> str:
        return {            ProcessType.INTERVAL: "Interval.exe",            ProcessType.SR2NAV: "SR2Nav.exe",        }[self]
@dataclass
class ProcessStatus:
    pid: Optional[int] = None
    process_type: Optional[ProcessType] = None
    is_running: bool = False
    exit_code: Optional[int] = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    @property
    def duration(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
class ProcessRunner:
    SR2NAV_FILTER_RULES: Dict[str, Set[str]] = {        "header": {            "Moscow State Lomonosov",            "Control and Navigation",            "SR2Nav Ver.",            "E-mail:",            "www.navlab.ru",        },        "diagnostics": {            "Not Valid Control Sum in Message [JP]",            "Message Length Hex [055] = 85",        },        "time": {            "Time span:",        },        "conversion": {            "Conversion JPS to Ashtech Format",            "Rover (E-File):",            "Rover (B-File):",            "Base #1 (B-File):",            ".JPS",        },        "checking": {            "GPS Raw Data Files Checking",        },        "modes": {            "Standard Mode: Station Name -> [Rover]",            "Standard Phase Velocity Mode: Station Name -> [Rover]",            "Standard Phase Coordinate Mode: Station Name -> [Rover]",            "Standard Mode: Station Name -> [Base]",            "Code & Doppler Differential Mode:",            "Carrier Phase Differential Mode:",            "Phase Coordinates Differential Mode:",        },    }
    SR2NAV_ALLOWED_SUBSTRINGS: Set[str] = set()
    for category_rules in SR2NAV_FILTER_RULES.values():
        SR2NAV_ALLOWED_SUBSTRINGS.update(category_rules)
    SR2NAV_STRICT_BLOCKED: Set[str] = {        "SV =",        "Toe =",        "178925",        "208800",        "PRN",    }
    INTERVAL_BLOCK_PATTERNS: List[str] = [        r'^\*.*\*$',        r'^I:',        r'^[\d\s\.]+$',    ]
    GENERAL_BLOCK_RULES = {        "binary_data": lambda line: len(line) > 200 and any(c.isdigit() for c in line[:10]),        "starts_with_digit": lambda line: bool(line) and line[0].isdigit() and not line.startswith("Time span:"),        "contains_sv": lambda line: "SV =" in line,        "contains_toe": lambda line: "Toe =" in line,    }
    def __init__(        self,        message_callback: Callable[[AppMessage], None],    ):
        self._message_callback = message_callback
        self._process: Optional[asyncio.subprocess.Process] = None
        self._process_type: Optional[ProcessType] = None
        self._status = ProcessStatus()
        self._read_tasks: List[asyncio.Task] = []
        self._message_accumulator = {}                                      
    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None
    @property
    def status(self) -> ProcessStatus:
        status = ProcessStatus(            pid=self._status.pid,            process_type=self._process_type,            is_running=self.is_running,            exit_code=self._status.exit_code,            error=self._status.error,            start_time=self._status.start_time,            end_time=self._status.end_time,        )
        return status
    async def run(        self,        command: List[str],        working_dir: str,        process_type: ProcessType,        timeout: Optional[float] = None,    ) -> int:
        if self.is_running:
            await self.terminate()
        self._process_type = process_type
        self._status = ProcessStatus(            start_time=datetime.now(),            process_type=process_type,        )
        self._send_message(            AppMessage.info(                f"🚀 Запуск {process_type.display_name}...",                source="ProcessRunner"            )        )
        try:
            self._process = await asyncio.create_subprocess_exec(                *command,                cwd=working_dir,                stdin=asyncio.subprocess.PIPE,                stdout=asyncio.subprocess.PIPE,                stderr=asyncio.subprocess.PIPE,            )
        except FileNotFoundError:
            self._status.error = f"Исполняемый файл не найден: {command[0]}"
            self._send_message(                AppMessage.error(self._status.error, source="ProcessRunner")            )
            self._status.end_time = datetime.now()
            return -1
        except PermissionError:
            self._status.error = f"Нет прав на запуск: {command[0]}"
            self._send_message(                AppMessage.error(self._status.error, source="ProcessRunner")            )
            self._status.end_time = datetime.now()
            return -1
        except Exception as error:
            self._status.error = f"Ошибка запуска: {error}"
            self._send_message(                AppMessage.error(self._status.error, source="ProcessRunner")            )
            self._status.end_time = datetime.now()
            return -1
        self._status.pid = self._process.pid
        self._send_message(            AppMessage.debug(f"  PID: {self._status.pid}", source="ProcessRunner")        )
        self._read_tasks = [            asyncio.create_task(self._read_stream(self._process.stdout, "stdout")),            asyncio.create_task(self._read_stream(self._process.stderr, "stderr")),        ]
        try:
            return_code = await asyncio.wait_for(                self._process.wait(),                timeout=timeout            )
        except asyncio.TimeoutError:
            if process_type == ProcessType.INTERVAL:
                self._send_message(                    AppMessage.debug(                        "ℹ️ Interval.exe: превышен таймаут (штатное поведение)",                        source="ProcessRunner"                    )                )
                if self._process:
                    try:
                        self._process.terminate()
                        await asyncio.sleep(0.1)                            
                        if self._process.returncode is None:
                            self._process.kill()
                    except ProcessLookupError:
                        pass                          
                return_code = 0
            else:
                self._send_message(                    AppMessage.warning(                        f"⚠️ Превышено время выполнения ({timeout} с)",                        source="ProcessRunner"                    )                )
                await self.terminate()
                return_code = -1
        finally:
            for task in self._read_tasks:
                task.cancel()
            if self._read_tasks:
                await asyncio.gather(*self._read_tasks, return_exceptions=True)
                self._read_tasks.clear()
            self._status.end_time = datetime.now()
            self._status.exit_code = return_code
        if return_code == 0:
            self._send_message(                AppMessage.info(                    f"✅ {process_type.display_name} успешно завершён",                    source="ProcessRunner"                )            )
        else:
            self._send_message(                AppMessage.warning(                    f"⚠️ {process_type.display_name} завершён с кодом: {return_code}",                    source="ProcessRunner"                )            )
        return return_code
    async def _read_stream(self, stream: Optional[asyncio.StreamReader], name: str) -> None:
        if not stream:
            return
        buffer = bytearray()
        while True:
            try:
                chunk = await asyncio.wait_for(stream.read(8192), timeout=0.1)
                if not chunk:
                    if buffer:
                        line = self._decode_bytes(buffer)
                        self._process_output_line(line)
                    break
                buffer.extend(chunk)
                while b'\n' in buffer:
                    line_bytes, buffer = buffer.split(b'\n', 1)
                    line = self._decode_bytes(line_bytes)
                    cleaned = ' '.join(line.split())
                    if cleaned:
                        self._process_output_line(cleaned)
                if len(buffer) > 65536:
                    line = self._decode_bytes(buffer)
                    cleaned = ' '.join(line.split())
                    if cleaned:
                        self._process_output_line(cleaned)
                    buffer.clear()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as error:
                self._send_message(                    AppMessage.debug(                        f"⚠️ Ошибка чтения {name}: {error}",                        source="ProcessRunner"                    )                )
                break
    def _process_output_line(self, line: str) -> None:
        if not line:
            return
        if self.GENERAL_BLOCK_RULES["binary_data"](line):
            return
        if self.GENERAL_BLOCK_RULES["starts_with_digit"](line):
            return
        if self.GENERAL_BLOCK_RULES["contains_sv"](line):
            return
        if self.GENERAL_BLOCK_RULES["contains_toe"](line):
            return
        if self._process_type == ProcessType.SR2NAV:
            if not self._is_allowed_sr2nav_line(line):
                return
        elif self._process_type == ProcessType.INTERVAL:
            if not self._is_allowed_interval_line(line):
                return
        else:
            pass
        self._send_message(            AppMessage.info(                line,                 source=self._process_type.display_name if self._process_type else "Process"            )        )
    def _is_allowed_sr2nav_line(self, line: str) -> bool:
        if not line:
            return False
        for blocked in self.SR2NAV_STRICT_BLOCKED:
            if blocked in line:
                return False
        for allowed in self.SR2NAV_ALLOWED_SUBSTRINGS:
            if allowed in line:
                return True
        return False
    def _is_allowed_interval_line(self, line: str) -> bool:
        if not line:
            return False
        for pattern in self.INTERVAL_BLOCK_PATTERNS:
            if re.match(pattern, line):
                return False
        return True
    def _decode_bytes(self, data: bytes) -> str:
        for encoding in ['utf-8', 'cp1251', 'cp866', 'latin-1']:
            try:
                return data.decode(encoding).rstrip()
            except UnicodeDecodeError:
                continue
        return data.decode('utf-8', errors='ignore').rstrip()
    async def terminate(self) -> bool:
        if not self._process:
            self._send_message(                AppMessage.info("ℹ️ Нет активного процесса", source="ProcessRunner")            )
            return False
        if self._process.returncode is not None:
            self._process = None
            self._process_type = None
            self._status.is_running = False
            return True
        process_name = self._process_type.display_name if self._process_type else "процесс"
        self._send_message(            AppMessage.warning(f"🛑 Остановка {process_name}...", source="ProcessRunner")        )
        try:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
                self._send_message(                    AppMessage.info(f"✓ {process_name} завершён", source="ProcessRunner")                )
                return True
            except asyncio.TimeoutError:
                self._send_message(                    AppMessage.warning(f"⚠️ Принудительное завершение...", source="ProcessRunner")                )
                self._process.kill()
                await self._process.wait()
                self._send_message(                    AppMessage.info(f"✓ {process_name} остановлен", source="ProcessRunner")                )
                return True
        except ProcessLookupError:
            self._send_message(                AppMessage.info(f"✓ {process_name} уже завершён", source="ProcessRunner")            )
            return True
        except Exception as error:
            self._send_message(                AppMessage.error(f"❌ Ошибка остановки: {error}", source="ProcessRunner")            )
            return False
        finally:
            self._process = None
            self._process_type = None
            self._status.is_running = False
            self._status.end_time = datetime.now()
            self._message_accumulator.clear()
    def _send_message(self, message: AppMessage) -> None:
        if self._message_callback:
            try:
                self._message_callback(message)
            except Exception as e:
                print(f"[ProcessRunner] Ошибка отправки сообщения: {e}")