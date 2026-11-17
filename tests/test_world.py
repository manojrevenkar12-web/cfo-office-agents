import sqlite3

from cofa.platform.sources import Bank
from cofa.world.client import build, iban, respond


def valid_iban(s: str) -> bool:
    x = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in x)) % 97 == 1


def test_ibans_are_valid():
    import numpy as np
    r = np.random.default_rng(0)
    assert all(valid_iban(iban(c, r)) for c in ("DE", "AT", "CH") for _ in range(50))


def test_same_seed_same_client(world, tmp_path):
    again = build(world["cfg"], tmp_path)
    assert again == world["planted"]
    assert (tmp_path / "truth" / "truth.json").read_text() == (world["root"] / "truth" / "truth.json").read_text()


def test_the_bank_file_holds_every_payment_and_the_allocations_add_up(world):
    bank = Bank(world["root"] / "client" / "bank")
    entries = {e["entry_id"]: e for d in bank.days() for e in bank.entries(d)}
    for p in world["truth"]["payments"]:
        assert entries[p["pid"]]["amount_cents"] == p["amount_cents"]
        assert len(entries[p["pid"]]["reference"]) <= 140
        if p["allocations"]:
            assert sum(a["paid_cents"] for a in p["allocations"]) == p["amount_cents"]


def test_the_erp_starts_with_every_item_open_and_no_postings(world):
    db = sqlite3.connect(world["root"] / "client" / "erp.sqlite")
    assert db.execute("select count(*) from postings").fetchone()[0] == 0
    assert db.execute("select count(*) from items where status != 'open'").fetchone()[0] == 0


def test_customers_reply_only_about_items_a_letter_names(world, tmp_path):
    sit = next(s for s in world["truth"]["situations"] if s["kind"] != "no_reply")
    box = tmp_path / "mail"
    box.mkdir()
    assert respond(world["cfg"], world["root"], box, [{"letter_id": "MAHN-X", "kunnr": sit["kunnr"], "docs": ["99999999"]}]) == []
    out = respond(world["cfg"], world["root"], box, [{"letter_id": "MAHN-X", "kunnr": sit["kunnr"], "docs": sit["docs"][:1]}])
    assert out and all(set(m["situation_docs"]) <= set(sit["docs"][:1]) for m in out)
