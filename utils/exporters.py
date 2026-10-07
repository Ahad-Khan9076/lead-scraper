"""
Export leads to CSV / Excel.
"""
from pathlib import Path
from typing import List
import pandas as pd
from datetime import datetime


def export_csv(leads: List[dict], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(leads)
    df.to_csv(path, index=False)
    return path


def export_excel(leads: List[dict], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(leads)
    df.to_excel(path, index=False, engine="openpyxl")
    return path


def default_export_name(prefix: str = "leads") -> str:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}"
