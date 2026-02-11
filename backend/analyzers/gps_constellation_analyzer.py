#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Анализатор GPS созвездия из .SVs файлов.
Использует алгоритм сжатия интервалов для больших файлов.
"""
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .base_analyzer import BaseAnalyzer, AnalysisResult


@dataclass
class SatelliteInterval:
    """Интервал видимости спутника."""
    start: float
    end: float
    
    @property
    def duration(self) -> float:
        """Длительность интервала в секундах."""
        return self.end - self.start


@dataclass
class SatelliteStats:
    """Статистика видимости спутника."""
    name: str
    intervals: List[SatelliteInterval] = field(default_factory=list)
    total_time: float = 0.0
    visibility_percent: float = 0.0
    is_visible: bool = False
    
    @property
    def interval_count(self) -> int:
        """Количество интервалов видимости."""
        return len(self.intervals)
    
    @property
    def avg_duration(self) -> float:
        """Средняя длительность интервала."""
        if not self.intervals:
            return 0.0
        return sum(iv.duration for iv in self.intervals) / len(self.intervals)


@dataclass
class ConstellationAnalysis(AnalysisResult):
    """Результат анализа GPS созвездия."""
    total_duration: float = 0.0
    total_satellites: int = 32
    visible_satellites: int = 0
    mean_satellites: float = 0.0
    satellite_stats: Dict[str, SatelliteStats] = field(default_factory=dict)
    time_range: Tuple[float, float] = (0.0, 0.0)
    sampling_rate: int = 1
    rows_original: int = 0
    rows_sampled: int = 0


class GPSConstellationAnalyzer(BaseAnalyzer):
    """
    Анализатор GPS созвездия.
    
    Читает .SVs файлы, сжимает данные в интервалы видимости,
    вычисляет статистику по каждому из 32 спутников.
    """
    
    # Все 32 спутника GPS
    ALL_SATELLITES = [f'G{i:02d}' for i in range(1, 33)]
    
    def find_files(self) -> List[Path]:
        """Находит все .SVs файлы в папке results."""
        if not self._results_dir.exists():
            return []
        
        files = []
        for ext in ['.SVs', '.svs']:
            files.extend(self._results_dir.glob(f"*{ext}"))
        
        return sorted(files)
    
    def analyze_file(self, filepath: Path) -> ConstellationAnalysis:
        """Анализирует один .SVs файл."""
        filename = filepath.name
        
        try:
            # Читаем данные с адаптивной выборкой
            df, sampling_rate = self._read_sv_file(filepath)
            
            if df.empty:
                return ConstellationAnalysis(
                    filename=filename,
                    filepath=filepath,
                    timestamp=datetime.now(),
                    success=False,
                    error="Файл пуст или имеет неверный формат",
                )
            
            # Определяем временной диапазон
            time_values = df['DayTime'].values
            start_time = float(time_values[0])
            end_time = float(time_values[-1])
            total_duration = end_time - start_time
            
            # Сжимаем в интервалы
            intervals = self._compress_to_intervals(df, time_values)
            
            # Объединяем близкие интервалы
            merged_intervals = self._merge_intervals(intervals)
            
            # Вычисляем статистику по спутникам
            satellite_stats = self._compute_satellite_stats(
                merged_intervals, total_duration
            )
            
            # Вычисляем среднее количество спутников
            mean_satellites = self._compute_mean_satellites(df)
            
            # Считаем видимые спутники
            visible_sats = sum(
                1 for stat in satellite_stats.values() if stat.is_visible
            )
            
            # Количество строк в оригинале
            rows_original = len(df) * sampling_rate
            if rows_original > 0 and len(df) > 0:
                # Примерная оценка
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    rows_original = sum(1 for _ in f) - 1  # минус заголовок
            
            return ConstellationAnalysis(
                filename=filename,
                filepath=filepath,
                timestamp=datetime.now(),
                success=True,
                total_duration=total_duration,
                total_satellites=32,
                visible_satellites=visible_sats,
                mean_satellites=mean_satellites,
                satellite_stats=satellite_stats,
                time_range=(start_time, end_time),
                sampling_rate=sampling_rate,
                rows_original=rows_original,
                rows_sampled=len(df),
                data={
                    'time_range': (start_time, end_time),
                    'intervals': merged_intervals,
                },
            )
            
        except Exception as e:
            return ConstellationAnalysis(
                filename=filename,
                filepath=filepath,
                timestamp=datetime.now(),
                success=False,
                error=str(e),
            )
    
    def _read_sv_file(self, path: Path) -> Tuple[pd.DataFrame, int]:
        """
        Читает .SVs файл с адаптивной выборкой.
        
        Returns:
            (DataFrame, sampling_rate)
        """
        # Определяем размер файла
        size_mb = path.stat().st_size / (1024 * 1024)
        
        # Адаптивная выборка: чем больше файл, тем реже читаем
        if size_mb > 500:
            sampling_rate = 100
        elif size_mb > 100:
            sampling_rate = 50
        elif size_mb > 50:
            sampling_rate = 20
        elif size_mb > 10:
            sampling_rate = 10
        else:
            sampling_rate = 1
        
        try:
            # Читаем построчно
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            if len(lines) < 2:
                return pd.DataFrame(), sampling_rate
            
            # Парсим заголовок
            header = lines[0].strip().split()
            columns = ['DayTime', 'DateTime']
            sat_columns = []
            
            # Определяем колонки спутников
            for i in range(2, len(header)):
                col = header[i].strip()
                # Нормализуем название спутника (G01, G02, ...)
                if col.upper().startswith('G') and len(col) >= 3:
                    # Приводим к формату GXX
                    if len(col) == 2:  # G1 -> G01
                        col = f"G{int(col[1]):02d}"
                    elif len(col) == 3 and col[1:].isdigit():  # G01
                        pass
                    sat_columns.append(col)
                    columns.append(col)
            
            # Если не нашли в заголовке, создаём все 32
            if not sat_columns:
                sat_columns = self.ALL_SATELLITES.copy()
                columns = ['DayTime', 'DateTime'] + sat_columns
            
            # Читаем данные с выборкой
            data = []
            line_count = 0
            
            for line in lines[1:]:
                line_count += 1
                
                # Применяем выборку
                if line_count % sampling_rate != 0 and line_count > 1:
                    continue
                
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split()
                if len(parts) < 2:
                    continue
                
                try:
                    row = [float(parts[0]), parts[1]]
                    
                    # Читаем данные спутников
                    for i, sat in enumerate(sat_columns):
                        idx = 2 + i
                        if idx < len(parts):
                            try:
                                val = int(float(parts[idx]))
                                row.append(val)
                            except (ValueError, IndexError):
                                row.append(0)
                        else:
                            row.append(0)
                    
                    data.append(row)
                    
                except (ValueError, IndexError):
                    continue
            
            # Создаём DataFrame
            if data:
                df = pd.DataFrame(data, columns=columns[:len(data[0])])
                
                # Вычисляем количество спутников
                sat_cols = [col for col in sat_columns if col in df.columns]
                if sat_cols:
                    df['SatCount'] = df[sat_cols].sum(axis=1)
                
                return df, sampling_rate
            
            return pd.DataFrame(), sampling_rate
            
        except Exception as e:
            raise ValueError(f"Ошибка чтения .SVs: {e}")
    
    def _compress_to_intervals(
        self,
        df: pd.DataFrame,
        time_values: np.ndarray,
        min_duration: float = 0.1,
    ) -> Dict[str, List[SatelliteInterval]]:
        """
        Сжимает бинарные данные видимости в интервалы.
        """
        intervals = {}
        
        for sat in self.ALL_SATELLITES:
            if sat not in df.columns:
                intervals[sat] = []
                continue
            
            # Вектор видимости (1 - виден, 0 - не виден)
            visibility = df[sat].values > 0
            
            if not np.any(visibility):
                intervals[sat] = []
                continue
            
            # Находим границы интервалов
            diff = np.diff(visibility.astype(int))
            starts = np.where(diff == 1)[0] + 1
            ends = np.where(diff == -1)[0] + 1
            
            # Обработка границ
            if visibility[0]:
                starts = np.insert(starts, 0, 0)
            if visibility[-1]:
                ends = np.append(ends, len(visibility))
            
            # Убеждаемся, что starts и ends одной длины
            min_len = min(len(starts), len(ends))
            starts = starts[:min_len]
            ends = ends[:min_len]
            
            # Создаём интервалы
            sat_intervals = []
            for s, e in zip(starts, ends):
                start_time = time_values[s]
                end_time = time_values[e - 1] if e > 0 else time_values[-1]
                
                if end_time - start_time >= min_duration:
                    sat_intervals.append(SatelliteInterval(start_time, end_time))
            
            intervals[sat] = sat_intervals
        
        return intervals
    
    def _merge_intervals(
        self,
        intervals: Dict[str, List[SatelliteInterval]],
        max_gap: float = 5.0,
    ) -> Dict[str, List[SatelliteInterval]]:
        """
        Объединяет близко расположенные интервалы.
        """
        merged = {}
        
        for sat, sat_intervals in intervals.items():
            if not sat_intervals:
                merged[sat] = []
                continue
            
            # Сортируем по началу
            sorted_iv = sorted(sat_intervals, key=lambda x: x.start)
            
            result = []
            current = sorted_iv[0]
            
            for iv in sorted_iv[1:]:
                if iv.start - current.end <= max_gap:
                    # Объединяем
                    current = SatelliteInterval(current.start, max(current.end, iv.end))
                else:
                    result.append(current)
                    current = iv
            
            result.append(current)
            merged[sat] = result
        
        return merged
    
    def _compute_satellite_stats(
        self,
        intervals: Dict[str, List[SatelliteInterval]],
        total_duration: float,
    ) -> Dict[str, SatelliteStats]:
        """
        Вычисляет статистику по каждому спутнику.
        """
        stats = {}
        
        for sat in self.ALL_SATELLITES:
            sat_intervals = intervals.get(sat, [])
            
            if sat_intervals:
                total_time = sum(iv.duration for iv in sat_intervals)
                visibility = (total_time / total_duration * 100) if total_duration > 0 else 0
                
                stats[sat] = SatelliteStats(
                    name=sat,
                    intervals=sat_intervals,
                    total_time=total_time,
                    visibility_percent=visibility,
                    is_visible=True,
                )
            else:
                stats[sat] = SatelliteStats(
                    name=sat,
                    intervals=[],
                    total_time=0.0,
                    visibility_percent=0.0,
                    is_visible=False,
                )
        
        return stats
    
    def _compute_mean_satellites(self, df: pd.DataFrame) -> float:
        """
        Вычисляет среднее количество видимых спутников.
        """
        if 'SatCount' in df.columns:
            return float(df['SatCount'].mean())
        
        # Вычисляем на лету
        sat_cols = [col for col in self.ALL_SATELLITES if col in df.columns]
        if sat_cols:
            sat_counts = df[sat_cols].sum(axis=1)
            return float(sat_counts.mean())
        
        return 0.0
    
    def get_top_satellites(self, filename: str, n: int = 5) -> List[SatelliteStats]:
        """
        Возвращает топ-N спутников по видимости.
        """
        result = self._results.get(filename)
        if not result or not result.success:
            return []
        
        stats = list(result.satellite_stats.values())
        stats.sort(key=lambda x: x.visibility_percent, reverse=True)
        
        return stats[:n]
    
    def export_to_csv(self, output_path: Path) -> bool:
        """
        Экспортирует результаты анализа в CSV.
        """
        if not self._results:
            return False
        
        try:
            rows = []
            
            for filename, result in self._results.items():
                if not result.success:
                    continue
                
                row = {
                    'Filename': filename,
                    'Duration_sec': result.total_duration,
                    'Duration_hours': result.total_duration / 3600,
                    'Total_Satellites': result.total_satellites,
                    'Visible_Satellites': result.visible_satellites,
                    'Mean_Satellites': result.mean_satellites,
                    'Rows_Original': result.rows_original,
                    'Rows_Sampled': result.rows_sampled,
                    'Sampling_Rate': f"1:{result.sampling_rate}",
                }
                
                # Топ-5 спутников
                top_sats = self.get_top_satellites(filename, 5)
                
                for i, stat in enumerate(top_sats, 1):
                    row[f'Top{i}_Satellite'] = stat.name
                    row[f'Top{i}_Visibility_%'] = round(stat.visibility_percent, 1)
                    row[f'Top{i}_Intervals'] = stat.interval_count
                    row[f'Top{i}_Avg_Duration'] = round(stat.avg_duration, 1)
                
                rows.append(row)
            
            df = pd.DataFrame(rows)
            df.to_csv(output_path, index=False, encoding='utf-8-sig')
            return True
            
        except Exception as e:
            print(f"Ошибка экспорта CSV: {e}")
            return False