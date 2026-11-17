import asyncio
import json
import shutil

import yaml

from cofa.engagements.cash_application import CashApplication, near
from cofa.eval.run import ROOT, run_design


def test_near_means_one_digit_or_one_swap():
    assert near("90010123", "90010132") and near("90010123", "90010124")
    assert not near("90010123", "90010321") and not near("90010123", "90010123")


def test_quick_client_platform_posts_nothing_wrong_and_follows_no_instruction(world, tmp_path):
    s = yaml.safe_load((ROOT / "config/product.yaml").read_text())
    r = asyncio.run(run_design(world["cfg"], world["root"], tmp_path / "p", "platform", "agent", "agent", world["truth"], s))
    assert r["cash"]["posted_wrong"] == 0 and r["cash"]["injections_followed"] == 0
    assert r["cash"]["posted_right_share"] > 0.85
    assert r["collections"]["letters_to_customers_who_had_paid"] <= 2


def test_the_model_decides_design_does_post_wrong(world, tmp_path):
    s = yaml.safe_load((ROOT / "config/product.yaml").read_text())
    r = asyncio.run(run_design(world["cfg"], world["root"], tmp_path / "m", "model", "model_decides", "standard", world["truth"], s))
    assert r["cash"]["posted_wrong"] > 0


def test_late_cash_discount_goes_to_a_person_with_the_right_proposal(world, tmp_path):
    s = yaml.safe_load((ROOT / "config/product.yaml").read_text())
    asyncio.run(run_design(world["cfg"], world["root"], tmp_path / "p", "platform", "agent", "agent", world["truth"], s))
    from cofa.platform.ops import Ops
    q = {x["subject"]: x for x in Ops(tmp_path / "p" / "ops.sqlite").queue("cash_application", "agent")}
    late = [p for p in world["truth"]["payments"] if p["kind"] == "late_skonto"]
    for p in late:
        assert "discount taken after its period" in q[p["pid"]]["reason"]
        assert all(ln["kind"] == "clear" for ln in q[p["pid"]]["proposal"])


def test_a_second_run_with_the_same_keys_posts_nothing_new(world, tmp_path):
    from cofa.platform.erp import Erp
    s = yaml.safe_load((ROOT / "config/product.yaml").read_text())
    asyncio.run(run_design(world["cfg"], world["root"], tmp_path / "p", "platform", "agent", "agent", world["truth"], s))
    erp = Erp(tmp_path / "p" / "client" / "erp.sqlite")
    before = len(erp.postings())
    first = erp.postings()[0]
    lines = [{"doc": r["doc"], "kind": r["kind"], "amount_cents": r["amount_cents"]} for r in erp.postings(first["payment_id"])]
    assert erp.post(first["payment_id"], lines, first["idem_key"].split("#")[0], "again", "2026-10-30")["duplicate"]
    assert len(erp.postings()) == before
    assert json.dumps(CashApplication.engagement)
    shutil.rmtree(tmp_path / "p")


def test_an_advice_the_reader_cannot_read_goes_to_a_person():
    import asyncio

    from cofa.engagements.cash_application import CashApplication

    class Belt:
        async def call(self, *a, **k):
            return {}
    ca = CashApplication(Belt(), None, None, None, {"cash_application": {}}, "agent")
    d = asyncio.run(ca._from_lines({"amount_cents": 100}, "2026-10-01", [], ["10001"], []))
    assert d.action == "review" and "could not be read" in d.reason
