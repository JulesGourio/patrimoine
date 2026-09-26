from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("PATRIMOINE_DATA_DIR") or ROOT / "data"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "patrimoine.db"
