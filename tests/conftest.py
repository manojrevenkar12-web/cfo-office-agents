import json
from pathlib import Path

import pytest

from cofa.world.client import build, load

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def world(tmp_path_factory):
    """The quick dev client: 30 customers, 12 bank days."""
    cfg = load(ROOT / "config/world.yaml")
    cfg = {**cfg, "customers": 30, "bank_days": 12, "collections": {**cfg["collections"], "dunning_day": 8}}
    root = tmp_path_factory.mktemp("client")
    planted = build(cfg, root)
    return {"cfg": cfg, "root": root, "planted": planted, "truth": json.loads((root / "truth" / "truth.json").read_text())}
