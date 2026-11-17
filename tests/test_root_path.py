from fastapi.testclient import TestClient

from hani2 import server


def test_root_path_injected(monkeypatch):
    monkeypatch.setenv("HANI2_ROOT_PATH", "/hanplay")
    c = TestClient(server.app, root_path="/hanplay")
    for url in ("/play", "/hanplay/play"):
        html = c.get(url).text
        assert 'name="hani2-base" content="/hanplay"' in html
        assert '"/hanplay/assets/' in html
    assert c.get("/hanplay/api/config").status_code == 200


def test_no_root_path(monkeypatch):
    monkeypatch.delenv("HANI2_ROOT_PATH", raising=False)
    assert "hani2-base" not in TestClient(server.app).get("/play").text
