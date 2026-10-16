"""
SLayer semantic layer initialization.

Sets up SLayer with the local SQLite warehouse — auto-ingests models,
configures the query engine, search service, and inspect service.
"""

import os
import tempfile
from pathlib import Path

from slayer.async_utils import run_sync
from slayer.core.models import DatasourceConfig
from slayer.engine.ingestion import ingest_datasource
from slayer.engine.query_engine import SlayerQueryEngine
from slayer.inspect.service import InspectService
from slayer.search.service import SearchService
from slayer.storage.yaml_storage import YAMLStorage

_engine: SlayerQueryEngine | None = None
_storage: YAMLStorage | None = None
_search: SearchService | None = None
_inspect: InspectService | None = None


def _db_path() -> str:
    env = os.environ.get("WAREHOUSE_DB_PATH")
    if env:
        return env
    return str(Path(__file__).resolve().parent.parent / "warehouse.db")


def _init() -> None:
    global _engine, _storage, _search, _inspect

    if _engine is not None:
        return

    db = _db_path()
    workdir = tempfile.mkdtemp(prefix="slayer_wh_")
    _storage = YAMLStorage(base_dir=os.path.join(workdir, "slayer_data"))
    ds = DatasourceConfig(name="warehouse", type="sqlite", database=db)
    run_sync(_storage.save_datasource(ds))

    models = ingest_datasource(datasource=ds)
    for m in models:
        run_sync(_storage.save_model(m))

    _engine = SlayerQueryEngine(storage=_storage)

    # Build search index for semantic discovery
    _search = SearchService(storage=_storage)
    run_sync(_search.refresh_datasource(name="warehouse", models=models))

    _inspect = InspectService(storage=_storage)


def get_engine() -> SlayerQueryEngine:
    _init()
    return _engine


def get_search() -> SearchService:
    _init()
    return _search


def get_inspect() -> InspectService:
    _init()
    return _inspect
