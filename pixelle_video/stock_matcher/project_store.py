"""
Project persistence: every script you work on is a project saved on disk, so
analysis, search results, clip choices, custom uploads and download status
survive closing the window, a browser refresh or a restart.

Layout:
    output/stock_projects/<project>/project.json
    output/stock_projects/<project>/uploads/scene_NN.ext
"""

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from .models import SceneAnalysis, SearchOutcome

DEFAULT_ROOT = Path("output") / "stock_projects"
PROJECT_FILE = "project.json"


def slug_name(name: str) -> str:
    name = re.sub(r"[^\w\- ]+", "", name, flags=re.UNICODE).strip()
    return re.sub(r"\s+", "_", name)[:60] or "project"


@dataclass
class ProjectState:
    name: str
    script: str = ""
    scenes: list[SceneAnalysis] = field(default_factory=list)
    outcomes: dict[int, SearchOutcome] = field(default_factory=dict)
    selections: dict[int, str] = field(default_factory=dict)  # scene -> clip uid
    queries: dict[int, str] = field(default_factory=dict)  # scene -> edited query
    uploads: dict[int, str] = field(default_factory=dict)  # scene -> file path
    downloads: dict[int, str] = field(default_factory=dict)  # scene -> saved file
    excluded: list[int] = field(default_factory=list)  # scenes unticked for download
    download_uids: dict[int, str] = field(default_factory=dict)  # scene -> clip downloaded
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "name": self.name,
            "updated_at": self.updated_at,
            "script": self.script,
            "scenes": [s.to_dict() for s in self.scenes],
            "outcomes": {str(k): o.to_dict() for k, o in self.outcomes.items()},
            "selections": {str(k): v for k, v in self.selections.items()},
            "queries": {str(k): v for k, v in self.queries.items()},
            "uploads": {str(k): v for k, v in self.uploads.items()},
            "downloads": {str(k): v for k, v in self.downloads.items()},
            "excluded": sorted(self.excluded),
            "download_uids": {str(k): v for k, v in self.download_uids.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectState":
        def int_keys(d: Optional[dict]) -> dict:
            return {int(k): v for k, v in (d or {}).items()}

        return cls(
            name=data.get("name", "project"),
            script=data.get("script", ""),
            scenes=[SceneAnalysis.from_dict(s) for s in data.get("scenes", [])],
            outcomes={k: SearchOutcome.from_dict(v)
                      for k, v in int_keys(data.get("outcomes")).items()},
            selections=int_keys(data.get("selections")),
            queries=int_keys(data.get("queries")),
            uploads=int_keys(data.get("uploads")),
            downloads=int_keys(data.get("downloads")),
            excluded=[int(i) for i in data.get("excluded", [])],
            download_uids=int_keys(data.get("download_uids")),
            updated_at=data.get("updated_at", ""),
        )


class ProjectStore:
    def __init__(self, root: str | Path = DEFAULT_ROOT):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return self.root / slug_name(name)

    def list_projects(self) -> list[str]:
        """Project names, most recently saved first."""
        files = [p / PROJECT_FILE for p in self.root.iterdir() if (p / PROJECT_FILE).exists()]
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return [f.parent.name for f in files]

    def new_name(self, prefix: str = "project") -> str:
        base = f"{prefix}_{datetime.now():%Y%m%d_%H%M}"
        name, n = base, 2
        while self.path(name).exists():
            name, n = f"{base}_{n}", n + 1
        return name

    def load(self, name: str) -> Optional[ProjectState]:
        file = self.path(name) / PROJECT_FILE
        if not file.exists():
            return None
        try:
            state = ProjectState.from_dict(json.loads(file.read_text(encoding="utf-8")))
            state.name = self.path(name).name
            return state
        except Exception as e:
            logger.error(f"Could not read project {file}: {e}")
            backup = file.with_suffix(".broken.json")
            shutil.copyfile(file, backup)
            logger.error(f"A copy was kept at {backup}")
            return None

    def save(self, state: ProjectState) -> Path:
        """Atomic write so a crash mid-save never corrupts the project."""
        folder = self.path(state.name)
        folder.mkdir(parents=True, exist_ok=True)
        state.updated_at = datetime.now().isoformat(timespec="seconds")
        file = folder / PROJECT_FILE
        tmp = file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(file)
        return file

    def rename(self, old: str, new: str) -> str:
        target = self.path(new)
        if target.exists():
            raise FileExistsError(f"Project '{target.name}' already exists")
        self.path(old).rename(target)
        return target.name

    def delete(self, name: str) -> None:
        shutil.rmtree(self.path(name), ignore_errors=True)

    def uploads_dir(self, name: str) -> Path:
        folder = self.path(name) / "uploads"
        folder.mkdir(parents=True, exist_ok=True)
        return folder
