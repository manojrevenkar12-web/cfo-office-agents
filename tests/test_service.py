from fastapi.testclient import TestClient

from cofa.service.api import build_demo, create_app


def test_a_person_can_post_a_proposal_once_and_drafts_are_listed(tmp_path):
    c = TestClient(create_app(build_demo(tmp_path / "run")))
    items = c.get("/api/review").json()["items"]
    with_prop = [i for i in items if i["proposal"]]
    if with_prop:
        s = with_prop[0]["subject"]
        assert c.post(f"/api/review/{s}/accept").status_code == 200
        assert c.post(f"/api/review/{s}/accept").status_code == 404
        assert s not in [i["subject"] for i in c.get("/api/review").json()["items"]]
    col = c.get("/api/collections").json()
    assert all(d["in_reply_to"] for d in col["drafts"])
    if col["drafts"]:
        assert c.get(f"/api/drafts/{col['drafts'][0]['name']}").json()["text"]
    assert c.get("/api/drafts/../../etc/passwd").status_code == 404
