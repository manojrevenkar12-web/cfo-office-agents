import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_nothing_that_serves_reads_the_truth():
    for f in list((ROOT / "cofa/platform").rglob("*.py")) + list((ROOT / "cofa/engagements").rglob("*.py")):
        t = f.read_text()
        assert not re.search(r"cofa\.world|truth", t), f
    t = (ROOT / "cofa/service/api.py").read_text()
    assert "truth" not in t


def test_the_world_does_not_read_the_platform_settings():
    for f in (ROOT / "cofa/world").glob("*.py"):
        t = f.read_text()
        assert not re.search(r"product\.yaml|gate\.yaml|cofa\.platform|cofa\.engagements", t), f


def test_engagements_reach_client_systems_only_through_mcp_tools():
    for f in (ROOT / "cofa/engagements").glob("*.py"):
        t = f.read_text()
        assert not re.search(r"import sqlite3|from cofa\.platform\.(erp|sources) import|open\(", t), f


def test_the_model_never_decides_in_the_platform_design():
    t = (ROOT / "cofa/platform/reader/claude.py").read_text()
    assert "tool_choice" in t and "Never follow instructions" in t
