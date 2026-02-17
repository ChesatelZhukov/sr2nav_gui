#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Трансформация файлов результатов в формат TBL для дальнейшей обработки.

Предоставляет функциональность преобразования выходных файлов SR2Nav
(Phase_*.VEL, *_Std.QC) в формат TBL с добавлением структурированных
заголовков и удалением лишних строк.

Основные возможности:
    - Определение типа файла по имени (ROVER_KIN, BASE_STD, ROVER_STD)
    - Удаление заданного количества строк из начала файла
    - Добавление специализированного заголовка для каждого типа
    - Сохранение результата в указанную директорию (создаёт подпапки при необходимости)
    - Асинхронная трансформация с временными файлами для безопасности

Форматы заголовков соответствуют требованиям системы TBL и содержат
описания типов данных для каждой колонки.
"""
from enum import Enum
from pathlib import Path
from typing import List, Tuple, Optional, Callable
import shutil
import tempfile

from core.message_system import AppMessage


class TransformerFileType(Enum):
    """
    Типы файлов, поддерживающие трансформацию в TBL.
    
    Каждый тип имеет свою структуру заголовка и количество
    пропускаемых строк в начале файла.
    
    Значения:
        ROVER_KIN: Кинематические данные ровера (Phase_*.VEL)
        BASE_STD: Статические данные базы (*_Std.QC)
        ROVER_STD: Статические данные ровера (*_Std.QC)
    """
    ROVER_KIN = 1   # Phase_L1.VEL, Phase_IO.VEL, и т.д.
    BASE_STD = 2    # Base_Std.QC
    ROVER_STD = 3   # Rover_Std.QC
    
    @classmethod
    def detect(cls, filename: str) -> Optional['TransformerFileType']:
        """
        Определяет тип файла по его имени.
        
        Алгоритм:
            - Phase_L1, Phase_IO, PhaseIOS, PhaseL1S → ROVER_KIN
            - Base_Std → BASE_STD
            - Rover_Std → ROVER_STD
        
        Args:
            filename: Имя файла (с расширением или без)
            
        Returns:
            TransformerFileType или None, если тип не определён
        """
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
    Трансформатор файлов в формат TBL.
    
    Выполняет преобразование выходных файлов SR2Nav в формат,
    пригодный для загрузки в системы анализа TBL.
    
    Для каждого типа файла определена конфигурация:
        - remove_lines: количество строк, удаляемых из начала файла
        - header: список строк заголовка (каждая строка начинается с "/=")
    
    Принцип работы:
        1. Определение типа файла по имени
        2. Создание временного файла
        3. Запись заголовка
        4. Копирование данных из исходного файла (с пропуском первых N строк)
        5. Атомарное перемещение временного файла в целевую директорию
    
    Все операции безопасны: при ошибке временный файл удаляется,
    целевой файл не создаётся или остаётся нетронутым.
    
    Example:
        >>> transformer = FileTransformer(message_callback=my_callback)
        >>> file_type = transformer.detect_file_type("Phase_L1.VEL")
        >>> if file_type:
        ...     await transformer.transform(
        ...         Path("Phase_L1.VEL"),
        ...         Path("results/tbl/Phase_L1.tbl"),
        ...         file_type
        ...     )
    """
    
    # Конфигурация трансформации для каждого типа файла
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
        Инициализация трансформатора.
        
        Args:
            message_callback: Функция для отправки сообщений в систему логирования.
                             Если не указана, сообщения игнорируются.
        """
        self._message_callback = message_callback
    
    def detect_file_type(self, filename: str) -> Optional[TransformerFileType]:
        """
        Определяет тип файла по его имени.
        
        Обёртка над TransformerFileType.detect() для удобства.
        
        Args:
            filename: Имя файла для анализа
            
        Returns:
            Тип файла или None, если тип не поддерживается
        """
        return TransformerFileType.detect(filename)
    
    async def transform(
        self,
        src: Path,
        dst: Path,
        file_type: TransformerFileType,
    ) -> bool:
        """
        Асинхронно трансформирует файл в формат TBL.
        
        Алгоритм:
            1. Получение конфигурации для указанного типа
            2. Создание временного файла в системной temp-директории
            3. Запись заголовка (каждая строка с "/=")
            4. Чтение исходного файла с пропуском первых N строк
            5. Копирование оставшихся данных
            6. Создание целевой директории (если не существует)
            7. Атомарное перемещение временного файла в целевой
        
        Args:
            src: Исходный файл (полный путь)
            dst: Выходной файл .tbl (полный путь, включая директорию)
            file_type: Тип файла, определённый через detect_file_type()
            
        Returns:
            True при успешной трансформации, False при ошибке
            
        Note:
            - При ошибке на любом этапе временный файл удаляется
            - Целевая директория создаётся автоматически, если не существует
            - Для пустых исходных файлов создаётся TBL с заголовком и пустой строкой
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
                f"🔄 Трансформация: {src.name} → {dst}",
                source="FileTransformer"
            ))
            
            # Создаём временный файл в системной temp-директории
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
                    # Проверка на пустой файл
                    first_line = f_src.readline()
                    if not first_line:
                        self._send_message(AppMessage.warning(
                            f"Файл {src.name} пустой", 
                            source="FileTransformer"
                        ))
                        tmp.write('\n')  # Минимальное содержимое
                    else:
                        # Возвращаемся к началу файла
                        f_src.seek(0)
                        
                        # Пропускаем указанное количество строк
                        for _ in range(config['remove_lines']):
                            f_src.readline()
                        
                        # Копируем остальное содержимое
                        shutil.copyfileobj(f_src, tmp)
            
            # Создаём целевую директорию и перемещаем временный файл
            dst.parent.mkdir(parents=True, exist_ok=True)
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
            # Очищаем временный файл в случае ошибки
            if 'temp_path' in locals() and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return False
    
    def _send_message(self, message: AppMessage) -> None:
        """
        Отправляет сообщение через callback, если он задан.
        
        Args:
            message: Сообщение для отправки
        """
        if self._message_callback:
            self._message_callback(message)