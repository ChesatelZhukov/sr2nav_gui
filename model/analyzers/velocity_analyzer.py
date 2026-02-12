#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСТАЯ МОДЕЛЬ - Только алгоритмы анализа скоростей, НИКАКОГО UI!
"""
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class VelocityData:
    """Данные скоростей из VEL файла."""
    filename: str
    filepath: str
    time: np.ndarray
    v_e: np.ndarray
    v_n: np.ndarray
    v_up: np.ndarray
    rows: int
    time_span: Tuple[float, float]
    
    @property
    def duration(self) -> float:
        """Длительность записи в секундах."""
        return self.time_span[1] - self.time_span[0] if len(self.time) > 1 else 0


@dataclass
class VelocityStatistics:
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
    rows_analyzed: int = 0


@dataclass
class VelocityAnalysisResult:
    """Полный результат анализа VEL файла."""
    filename: str
    filepath: str
    data: VelocityData
    statistics: VelocityStatistics
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    error: Optional[str] = None


class VelocityAnalyzer:
    """
    ЧИСТАЯ МОДЕЛЬ - Анализатор VEL файлов.
    Только алгоритмы, никакого UI, никаких окон!
    """
    
    def __init__(self):
        self._results: Dict[str, VelocityAnalysisResult] = {}
    
    def find_vel_files(self, results_dir: str) -> List[str]:
        """Находит все VEL файлы в директории."""
        vel_files = []
        if os.path.exists(results_dir):
            for file in os.listdir(results_dir):
                if file.endswith('.VEL'):
                    vel_files.append(os.path.join(results_dir, file))
        
        # Приоритет: L1, IO, затем остальные
        priority = []
        others = []
        for f in vel_files:
            name = os.path.basename(f)
            if 'L1' in name or 'IO' in name:
                priority.append(f)
            else:
                others.append(f)
        
        return priority + others
    
    def parse_file(self, filepath: str) -> Optional[VelocityData]:
        """
        Парсит VEL файл и возвращает структурированные данные.
        Чистая функция без побочных эффектов.
        """
        filename = os.path.basename(filepath)
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            if len(lines) < 3:
                return None
            
            time_data = []
            v_e_data = []
            v_n_data = []
            v_up_data = []
            
            for line in lines[2:]:  # Пропускаем заголовки
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split()
                if len(parts) >= 9:
                    try:
                        time_data.append(float(parts[0]))
                        v_e_data.append(float(parts[5]))
                        v_n_data.append(float(parts[6]))
                        v_up_data.append(float(parts[7]))
                    except (ValueError, IndexError):
                        continue
            
            if not time_data:
                return None
            
            return VelocityData(
                filename=filename,
                filepath=filepath,
                time=np.array(time_data),
                v_e=np.array(v_e_data),
                v_n=np.array(v_n_data),
                v_up=np.array(v_up_data),
                rows=len(time_data),
                time_span=(time_data[0], time_data[-1])
            )
            
        except Exception as e:
            print(f"Ошибка парсинга {filename}: {e}")
            return None
    
    def calculate_statistics(self, data: VelocityData) -> VelocityStatistics:
        """Рассчитывает статистику скоростей."""
        stats = VelocityStatistics(rows_analyzed=data.rows)
        
        if data.rows == 0:
            return stats
        
        # Скорости по осям
        stats.max_v_e = float(np.max(np.abs(data.v_e)))
        stats.max_v_n = float(np.max(np.abs(data.v_n)))
        stats.max_v_up = float(np.max(np.abs(data.v_up)))
        
        stats.mean_v_e = float(np.mean(data.v_e))
        stats.mean_v_n = float(np.mean(data.v_n))
        stats.mean_v_up = float(np.mean(data.v_up))
        
        stats.std_v_e = float(np.std(data.v_e))
        stats.std_v_n = float(np.std(data.v_n))
        stats.std_v_up = float(np.std(data.v_up))
        
        # 2D и 3D скорости
        speed_2d = np.sqrt(data.v_e**2 + data.v_n**2)
        speed_3d = np.sqrt(data.v_e**2 + data.v_n**2 + data.v_up**2)
        
        stats.max_speed_2d = float(np.max(speed_2d))
        stats.max_speed_3d = float(np.max(speed_3d))
        stats.mean_speed_2d = float(np.mean(speed_2d))
        stats.mean_speed_3d = float(np.mean(speed_3d))
        
        return stats
    
    def analyze_file(self, filepath: str) -> Optional[VelocityAnalysisResult]:
        """Анализирует один VEL файл."""
        data = self.parse_file(filepath)
        if not data:
            return None
        
        stats = self.calculate_statistics(data)
        
        result = VelocityAnalysisResult(
            filename=data.filename,
            filepath=filepath,
            data=data,
            statistics=stats
        )
        
        self._results[data.filename] = result
        return result
    
    def analyze_all(self, results_dir: str) -> Dict[str, VelocityAnalysisResult]:
        """Анализирует все VEL файлы в директории."""
        self._results.clear()
        
        for filepath in self.find_vel_files(results_dir):
            result = self.analyze_file(filepath)
            if result:
                self._results[result.filename] = result
        
        return self.get_results()
    
    def get_results(self) -> Dict[str, VelocityAnalysisResult]:
        """Возвращает все результаты анализа."""
        return self._results.copy()
    
    def get_summary_statistics(self) -> Dict[str, Any]:
        """Возвращает сводную статистику по всем файлам."""
        if not self._results:
            return {}
        
        summary = {
            'total_files': len(self._results),
            'files': [],
            'max_velocities': {
                'v_e': 0.0, 'v_n': 0.0, 'v_up': 0.0
            },
            'max_speeds': {
                '2d': 0.0, '3d': 0.0
            }
        }
        
        for filename, result in self._results.items():
            summary['files'].append(filename)
            stats = result.statistics
            
            summary['max_velocities']['v_e'] = max(
                summary['max_velocities']['v_e'], 
                stats.max_v_e
            )
            summary['max_velocities']['v_n'] = max(
                summary['max_velocities']['v_n'], 
                stats.max_v_n
            )
            summary['max_velocities']['v_up'] = max(
                summary['max_velocities']['v_up'], 
                stats.max_v_up
            )
            summary['max_speeds']['2d'] = max(
                summary['max_speeds']['2d'], 
                stats.max_speed_2d
            )
            summary['max_speeds']['3d'] = max(
                summary['max_speeds']['3d'], 
                stats.max_speed_3d
            )
        
        return summary
    
    def export_to_csv(self, output_file: str) -> bool:
        """Экспортирует результаты в CSV."""
        if not self._results:
            return False
        
        try:
            export_data = []
            for filename, result in self._results.items():
                row = {
                    'Filename': filename,
                    'Rows': result.data.rows,
                    'Duration_sec': result.data.duration,
                    'Max_V_E': result.statistics.max_v_e,
                    'Max_V_N': result.statistics.max_v_n,
                    'Max_V_UP': result.statistics.max_v_up,
                    'Mean_V_E': result.statistics.mean_v_e,
                    'Mean_V_N': result.statistics.mean_v_n,
                    'Mean_V_UP': result.statistics.mean_v_up,
                    'Std_V_E': result.statistics.std_v_e,
                    'Std_V_N': result.statistics.std_v_n,
                    'Std_V_UP': result.statistics.std_v_up,
                    'Max_Speed_2D': result.statistics.max_speed_2d,
                    'Max_Speed_3D': result.statistics.max_speed_3d,
                }
                export_data.append(row)
            
            df = pd.DataFrame(export_data)
            df.to_csv(output_file, index=False, encoding='utf-8')
            return True
            
        except Exception:
            return False