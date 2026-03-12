from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
@dataclass
class AnalysisResult:
    filename: str
    filepath: Path
    timestamp: datetime
    success: bool
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
class BaseAnalyzer(ABC):
    def __init__(self):
        self._results: Dict[str, AnalysisResult] = {}
    @abstractmethod
    def find_files(self, directory: str) -> List[str]:
        pass
    @abstractmethod
    def analyze_file(self, filepath: str) -> Optional[AnalysisResult]:
        pass
    def analyze_all(self, directory: str) -> Dict[str, AnalysisResult]:
        self._results.clear()
        files = self.find_files(directory)
        for filepath in files:
            try:
                result = self.analyze_file(filepath)
                if result:
                    self._results[result.filename] = result
            except Exception as e:
                filename = Path(filepath).name
                self._results[filename] = AnalysisResult(                    filename=filename,                    filepath=Path(filepath),                    timestamp=datetime.now(),                    success=False,                    error=str(e),                )
        return self.get_results()
    def get_results(self) -> Dict[str, AnalysisResult]:
        return self._results.copy()
    def get_result(self, filename: str) -> Optional[AnalysisResult]:
        return self._results.get(filename)
    def clear_results(self) -> None:
        self._results.clear()