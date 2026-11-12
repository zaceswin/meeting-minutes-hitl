from fastapi.testclient import TestClient

from minutes.review_app import create_app


def client(path):
    return TestClient(create_app(path))


def test_session_endpoint(demo_path):
    j = client(demo_path).get("/api/session").json()
    assert j["session"]["name"] == "demo" and "L009" in j["uncovered"] and j["blockers"]


def test_audio_is_served_with_range(demo_path):
    c = client(demo_path)
    r = c.get("/api/audio", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100


def test_cannot_accept_mismatched_quote_then_requote(demo_path):
    c = client(demo_path)
    # human corrects the line the decision cites -> old quote no longer matches
    c.put("/api/lines/L005", json={"text": "Objections? None. Then it is agreed, the levy is 600 shillings from March.", "error_type": "number"})
    r = c.patch("/api/items/D1", json={"status": "accepted"})
    assert r.status_code == 409
    assert c.patch("/api/items/D1", json={"requote": True}).status_code == 200
    assert c.patch("/api/items/D1", json={"status": "accepted"}).status_code == 200


def test_line_edit_is_logged(demo_path):
    c = client(demo_path)
    c.put("/api/lines/L002", json={"text": "The borehole pump failed again.", "error_type": "dropped"})
    log = (demo_path.parent / "error_log.csv").read_text(encoding="utf-8")
    assert "L002" in log and "dropped" in log and "four thousand five hundred" in log


def test_human_added_item_cites_full_line(demo_path):
    c = client(demo_path)
    assert c.post("/api/items", json={"kind": "decision", "text": "Vote on gate fee next month", "line_id": "L009"}).status_code == 200
    s = c.get("/api/session").json()
    new = [i for i in s["session"]["items"] if i["origin"] == "human"][0]
    assert new["evidence"][0]["quote"].startswith("Tumekubaliana") and "L009" not in s["uncovered"]


def test_full_review_and_export(demo_path):
    c = client(demo_path)
    assert c.post("/api/export", json={"reviewer": "Sec"}).status_code == 409  # pending items
    for i in c.get("/api/session").json()["session"]["items"]:
        assert c.patch(f"/api/items/{i['id']}", json={"status": "accepted"}).status_code == 200
    r = c.post("/api/export", json={"reviewer": "Sec"})
    assert r.status_code == 200 and (demo_path.parent / "minutes.md").exists()


def test_html_served_and_no_innerhtml(demo_path):
    c = client(demo_path)
    html = c.get("/").text
    assert "Minutes review" in html and "innerHTML" not in html  # XSS guard: text only via textContent
