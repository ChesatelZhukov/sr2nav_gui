from enum import Enum
from pathlib import Path
from typing import List, Tuple, Optional, Callable
import shutil
import tempfile
from core.message_system import AppMessage
class TransformerFileType(Enum):
    ROVER_KIN = 1                                       
    BASE_STD = 2                 
    ROVER_STD = 3                 
    @classmethod
    def detect(cls, filename: str) -> Optional['TransformerFileType']:
        name = filename.upper()
        if any(x in name for x in ['PHASE_L1', 'PHASE_IO', 'PHASEIOS', 'PHASEL1S']):
            return cls.ROVER_KIN
        elif 'BASE_STD' in name:
            return cls.BASE_STD
        elif 'ROVER_STD' in name:
            return cls.ROVER_STD
        return None
class FileTransformer:
    CONFIG = {        TransformerFileType.ROVER_KIN: {            'remove_lines': 2,            'header': [                "/= GPSSeconds :real",                "/= Lat_rad :real",                "/= Lon_rad :real",                "/= Hei :real",                "/= RmsPos :real",                "/= V_E :real",                "/= V_N :real",                "/= V_UP :real",                "/= RmsVel :real",                "/= Svs :real",                "/= Type :real",            ],        },        TransformerFileType.BASE_STD: {            'remove_lines': 1,            'header': [                "/= GPSSeconds :real",                "/= Time :time",                "/= Svs :real",                "/= PDOP :real",                "/= Lat_rad :real",                "/= Lon_rad :real",                "/= Hei :real",                "/= RmsPos :real",                "/= V_E :real",                "/= V_N :real",                "/= V_UP :real",                "/= RmsVel :real",                "/= ClockError :real",                "/= ClockRateError :real",            ],        },        TransformerFileType.ROVER_STD: {            'remove_lines': 1,            'header': [                "/= GPSSeconds :real",                "/= Time :time",                "/= Svs :real",                "/= PDOP :real",                "/= Lat_rad :real",                "/= Lon_rad :real",                "/= Hei :real",                "/= RmsPos :real",                "/= V_E :real",                "/= V_N :real",                "/= V_UP :real",                "/= RmsVel :real",                "/= ClockError :real",                "/= ClockRateError :real",                "/= Al1 :real",                "/= Al2 :real",                "/= Bet3 :real",                "/= Nu1 :real",                "/= Nu2 :real",                "/= Nu3 :real",            ],        },    }
    def __init__(self, message_callback: Optional[Callable[[AppMessage], None]] = None):
        self._message_callback = message_callback
    def detect_file_type(self, filename: str) -> Optional[TransformerFileType]:
        return TransformerFileType.detect(filename)
    async def transform(        self,        src: Path,        dst: Path,        file_type: TransformerFileType,    ) -> bool:
        try:
            config = self.CONFIG.get(file_type)
            if not config:
                self._send_message(AppMessage.error(                    f"Неизвестный тип файла: {file_type}",                    source="FileTransformer"                ))
                return False
            self._send_message(AppMessage.info(                f"🔄 Трансформация: {src.name} → {dst}",                source="FileTransformer"            ))
            with tempfile.NamedTemporaryFile(                mode='w',                encoding='utf-8',                suffix='.tmp',                delete=False            ) as tmp:
                temp_path = Path(tmp.name)
                for line in config['header']:
                    tmp.write(line + '\n')
                with open(src, 'r', encoding='utf-8', errors='ignore') as f_src:
                    first_line = f_src.readline()
                    if not first_line:
                        self._send_message(AppMessage.warning(                            f"Файл {src.name} пустой",                             source="FileTransformer"                        ))
                        tmp.write('\n')                          
                    else:
                        f_src.seek(0)
                        for _ in range(config['remove_lines']):
                            f_src.readline()
                        shutil.copyfileobj(f_src, tmp)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(temp_path), str(dst))
            self._send_message(AppMessage.info(                f"✅ {dst.name} создан ({dst.stat().st_size / 1024:.0f} КБ)",                source="FileTransformer"            ))
            return True
        except Exception as e:
            self._send_message(AppMessage.error(                f"Ошибка трансформации {src.name}: {e}",                source="FileTransformer"            ))
            if 'temp_path' in locals() and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return False
    def _send_message(self, message: AppMessage) -> None:
        if self._message_callback:
            self._message_callback(message)