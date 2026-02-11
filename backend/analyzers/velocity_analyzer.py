#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Анализатор VEL файлов.
Извлекает и анализирует скорости V_E, V_N, V_UP.
"""
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from .base_analyzer import BaseAnalyzer, AnalysisResult


@dataclass
class VelocityStats:
    """Статистика скоростей."""
    max_v_e: float = 0.0
    max_v_n: float = 0.0
    max_v_up: float = 0.0
    mean_v_e: float = 0.0
    mean_v_n: float = 0.0
    mean_v_up: float = 0.0
    std_v_e: float = 0.0
    std_v_n: float = 0.0
    std_v_up: float = 0.0
    max_speed_2d: float = 0.0
    max_speed_3d: float = 0.0
    mean_speed_2d: float = 0.0
    mean_speed_3d: float = 0.0
    samples: int = 0


@dataclass
class VelocityAnalysis(AnalysisResult):
    """Результат анализа VEL файла."""
    time_range: Tuple[float, float] = (0.0, 0.0)
    stats: Optional[VelocityStats] = None
    data: Optional[Dict[str, np.ndarray]] = field(default_factory=dict)


class VelocityFileAnalyzer(BaseAnalyzer):
    """
    Анализатор VEL файлов.
    
    Читает файлы формата:
        (1)Time        Lat          Lon           Hei         RmsPos       V_E        V_N        V_UP      RmsVel   SVs  Type
    """
    
    # Ожидаемые колонки
    EXPECTED_COLUMNS = ['Time', 'V_E', 'V_N', 'V_UP']
    
    def find_files(self) -> List[Path]:
        """Находит все .VEL файлы в папке results."""
        if not self._results_dir.exists():
            return []
        
        # Сортируем: сначала L1/IO, потом остальные
        vel_files = list(self._results_dir.glob("*.VEL"))
        
        def priority(f: Path) -> int:
            name = f.name.upper()
            if 'L1' in name or 'IO' in name:
                return 0
            return 1
        
        return sorted(vel_files, key=priority)
    
    def analyze_file(self, filepath: Path) -> VelocityAnalysis:
        """Анализирует один VEL файл."""
        filename = filepath.name
        
        try:
            # Читаем файл
            df = self._read_vel_file(filepath)
            
            if df.empty:
                return VelocityAnalysis(
                    filename=filename,
                    filepath=filepath,
                    timestamp=datetime.now(),
                    success=False,
                    error="Файл пуст или имеет неверный формат",
                )
            
            # Извлекаем данные
            time_data = df['Time'].values
            v_e = df['V_E'].values
            v_n = df['V_N'].values
            v_up = df['V_UP'].values if 'V_UP' in df.columns else np.zeros_like(v_e)
            
            # Вычисляем статистику
            stats = self._compute_stats(v_e, v_n, v_up)
            
            # Даунсэмплинг для графиков (если данных слишком много)
            if len(time_data) > 10000:
                step = len(time_data) // 5000
                time_data = time_data[::step]
                v_e = v_e[::step]
                v_n = v_n[::step]
                v_up = v_up[::step]
            
            return VelocityAnalysis(
                filename=filename,
                filepath=filepath,
                timestamp=datetime.now(),
                success=True,
                time_range=(float(df['Time'].iloc[0]), float(df['Time'].iloc[-1])),
                stats=stats,
                data={
                    'time': time_data,
                    'v_e': v_e,
                    'v_n': v_n,
                    'v_up': v_up,
                },
            )
            
        except Exception as e:
            return VelocityAnalysis(
                filename=filename,
                filepath=filepath,
                timestamp=datetime.now(),
                success=False,
                error=str(e),
            )
    
    def _read_vel_file(self, path: Path) -> pd.DataFrame:
        """
        Читает VEL файл и возвращает DataFrame.
        """
        try:
            # Пробуем читать как CSV с пропуском первых двух строк
            df = pd.read_csv(
                path,
                skiprows=2,
                delim_whitespace=True,
                header=None,
                encoding='utf-8',
                on_bad_lines='skip',
            )
            
            # Назначаем имена колонок
            columns = [
                'Time', 'Lat', 'Lon', 'Hei', 'RmsPos',
                'V_E', 'V_N', 'V_UP', 'RmsVel', 'SVs', 'Type'
            ]
            
            # Обрезаем до реального количества колонок
            n_cols = min(len(columns), len(df.columns))
            df = df.iloc[:, :n_cols]
            df.columns = columns[:n_cols]
            
            # Конвертируем типы
            for col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Удаляем NaN в критических колонках
            df = df.dropna(subset=['Time', 'V_E', 'V_N'])
            
            return df
            
        except Exception as e:
            raise ValueError(f"Ошибка чтения VEL файла: {e}")
    
    def _compute_stats(self, v_e: np.ndarray, v_n: np.ndarray, v_up: np.ndarray) -> VelocityStats:
        """Вычисляет статистику скоростей."""
        speed_2d = np.sqrt(v_e**2 + v_n**2)
        speed_3d = np.sqrt(v_e**2 + v_n**2 + v_up**2)
        
        return VelocityStats(
            max_v_e=float(np.max(np.abs(v_e))),
            max_v_n=float(np.max(np.abs(v_n))),
            max_v_up=float(np.max(np.abs(v_up))),
            mean_v_e=float(np.mean(v_e)),
            mean_v_n=float(np.mean(v_n)),
            mean_v_up=float(np.mean(v_up)),
            std_v_e=float(np.std(v_e)),
            std_v_n=float(np.std(v_n)),
            std_v_up=float(np.std(v_up)),
            max_speed_2d=float(np.max(speed_2d)),
            max_speed_3d=float(np.max(speed_3d)),
            mean_speed_2d=float(np.mean(speed_2d)),
            mean_speed_3d=float(np.mean(speed_3d)),
            samples=len(v_e),
        )
    
    def export_to_csv(self, output_path: Path) -> bool:
        """
        Экспортирует результаты анализа в CSV.
        """
        if not self._results:
            return False
        
        try:
            rows = []
            
            for filename, result in self._results.items():
                if not result.success or not result.stats:
                    continue
                
                stats = result.stats
                row = {
                    'Filename': filename,
                    'Samples': stats.samples,
                    'Time_Start': result.time_range[0],
                    'Time_End': result.time_range[1],
                    'Max_V_E': stats.max_v_e,
                    'Max_V_N': stats.max_v_n,
                    'Max_V_UP': stats.max_v_up,
                    'Mean_V_E': stats.mean_v_e,
                    'Mean_V_N': stats.mean_v_n,
                    'Mean_V_UP': stats.mean_v_up,
                    'Std_V_E': stats.std_v_e,
                    'Std_V_N': stats.std_v_n,
                    'Std_V_UP': stats.std_v_up,
                    'Max_Speed_2D': stats.max_speed_2d,
                    'Max_Speed_3D': stats.max_speed_3d,
                    'Mean_Speed_2D': stats.mean_speed_2d,
                    'Mean_Speed_3D': stats.mean_speed_3d,
                }
                rows.append(row)
            
            df = pd.DataFrame(rows)
            df.to_csv(output_path, index=False, encoding='utf-8-sig')
            return True
            
        except Exception as e:
            print(f"Ошибка экспорта CSV: {e}")
            return False