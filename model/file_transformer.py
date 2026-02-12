#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТАЯ МОДЕЛЬ - Трансформация файлов в формат TBL.
ТОЛЬКО ФАЙЛОВЫЕ ОПЕРАЦИИ, НИКАКОГО UI!
"""
from enum import Enum
from pathlib import Path
from typing import List, Tuple, Optional, Callable
import shutil
import tempfile

from core.message_system import AppMessage


class TransformerFileType(Enum):
    """Типы файлов для трансформации."""
    ROVER_KIN = 1   # Phase_L1.VEL, Phase_IO.VEL, etc.
    BASE_STD = 2    # Base_Std.QC
    ROVER_STD = 3   # Rover_Std.QC
    
    @classmethod
    def detect(cls, filename: str) -> Optional['TransformerFileType']:
        """Определяет тип файла по имени."""
        name = filename.upper()
        
        if any(x in name for x in ['PHASE_L1', 'PHASE_IO', 'PHASEIOS', 'PHASEL1S']):
            return cls.ROVER_KIN
        elif 'BASE_STD' in name:
            return cls.BASE_STD
        elif 'ROVER_STD' in name:
            return cls.ROVER_STD
        
        return None


class FileTransformer:
    """
    ЧИСТАЯ МОДЕЛЬ - Трансформатор файлов в формат TBL.
    
    Для каждого типа файла:
        - Удаляет N строк из начала
        - Добавляет кастомный заголовок
    
    Никакого UI, только файловые операции!
    """
    
    # Конфигурация трансформации
    CONFIG = {
        TransformerFileType.ROVER_KIN: {
            'remove_lines': 2,
            'header': [
                "/= GPSSeconds :real",
                "/= Lat_rad :real",
                "/= Lon_rad :real",
                "/= Hei :real",
                "/= RmsPos :real",
                "/= V_E :real",
                "/= V_N :real",
                "/= V_UP :real",
                "/= RmsVel :real",
                "/= Svs :real",
                "/= Type :real",
            ],
        },
        TransformerFileType.BASE_STD: {
            'remove_lines': 1,
            'header': [
                "/= GPSSeconds :real",
                "/= Time :time",
                "/= Svs :real",
                "/= PDOP :real",
                "/= Lat_rad :real",
                "/= Lon_rad :real",
                "/= Hei :real",
                "/= RmsPos :real",
                "/= V_E :real",
                "/= V_N :real",
                "/= V_UP :real",
                "/= RmsVel :real",
                "/= ClockError :real",
                "/= ClockRateError :real",
            ],
        },
        TransformerFileType.ROVER_STD: {
            'remove_lines': 1,
            'header': [
                "/= GPSSeconds :real",
                "/= Time :time",
                "/= Svs :real",
                "/= PDOP :real",
                "/= Lat_rad :real",
                "/= Lon_rad :real",
                "/= Hei :real",
                "/= RmsPos :real",
                "/= V_E :real",
                "/= V_N :real",
                "/= V_UP :real",
                "/= RmsVel :real",
                "/= ClockError :real",
                "/= ClockRateError :real",
                "/= Al1 :real",
                "/= Al2 :real",
                "/= Bet3 :real",
                "/= Nu1 :real",
                "/= Nu2 :real",
                "/= Nu3 :real",
            ],
        },
    }
    
    def __init__(self, message_callback: Optional[Callable[[AppMessage], None]] = None):
        """
        :param message_callback: Функция для отправки сообщений
        """
        self._message_callback = message_callback
    
    def detect_file_type(self, filename: str) -> Optional[TransformerFileType]:
        """Определяет тип файла по имени."""
        return TransformerFileType.detect(filename)
    
    async def transform(
        self,
        src: Path,
        dst: Path,
        file_type: TransformerFileType,
    ) -> bool:
        """
        Асинхронно трансформирует файл.
        
        Args:
            src: Исходный файл
            dst: Выходной файл (.tbl)
            file_type: Тип файла
            
        Returns:
            True если успешно
        """
        try:
            config = self.CONFIG.get(file_type)
            if not config:
                self._send_message(AppMessage.error(
                    f"Неизвестный тип файла: {file_type}",
                    source="FileTransformer"
                ))
                return False
            
            self._send_message(AppMessage.info(
                f"🔄 Трансформация: {src.name} → {dst.name}",
                source="FileTransformer"
            ))
            
            # Создаём временный файл
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                suffix='.tmp',
                delete=False
            ) as tmp:
                temp_path = Path(tmp.name)
                
                # 1. Записываем заголовок
                for line in config['header']:
                    tmp.write(line + '\n')
                
                # 2. Читаем исходный файл, пропуская N строк
                with open(src, 'r', encoding='utf-8', errors='ignore') as f_src:
                    # Пропускаем строки
                    for _ in range(config['remove_lines']):
                        f_src.readline()
                    
                    # Копируем остальное
                    shutil.copyfileobj(f_src, tmp)
            
            # Перемещаем временный файл в целевой
            dst.parent.mkdir(exist_ok=True)
            shutil.move(str(temp_path), str(dst))
            
            self._send_message(AppMessage.info(
                f"✅ {dst.name} создан ({dst.stat().st_size / 1024:.0f} КБ)",
                source="FileTransformer"
            ))
            
            return True
            
        except Exception as e:
            self._send_message(AppMessage.error(
                f"Ошибка трансформации {src.name}: {e}",
                source="FileTransformer"
            ))
            return False
    
    def _send_message(self, message: AppMessage) -> None:
        """Отправляет сообщение через callback."""
        if self._message_callback:
            self._message_callback(message)