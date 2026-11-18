from fastapi.testclient import TestClient

from hani2 import server


def test_root_path_injected(monkeypatch):
    monkeypatch.setenv("HANI2_ROOT_PATH", "/hanplay")
    c = TestClient(server.app)
    for url in ("/play", "/hanplay/play"):
        html = c.get(url).text
        assert 'name="hani2-base" content="/hanplay"' in html
        assert '"/hanplay/assets/' in html
    for url in ("/hanplay/api/config", "/api/config"):
        r = c.get(url)
        assert r.status_code == 200 and "auth_mode" in r.json()


def test_no_root_path(monkeypatch):
    monkeypatch.delenv("HANI2_ROOT_PATH", raising=False)
    assert "hani2-base" not in TestClient(server.app).get("/play").text


def test_assets_compressed_and_cached(monkeypatch):
    import gzip
    import re

    monkeypatch.setenv("HANI2_ROOT_PATH", "/hanplay")
    c = TestClient(server.app)
    html = c.get("/play").text
    js = re.search(r'"/hanplay(/assets/[^"]+\.js)"', html).group(1)
    raw = (server.WEB_DIR / js.lstrip("/")).read_bytes()
    for url in (js, "/hanplay" + js):
        r = c.get(url, headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200
        assert r.headers["content-encoding"] == "gzip"
        assert "immutable" in r.headers["cache-control"]
        assert "javascript" in r.headers["content-type"]
        assert r.content == raw  # the client decodes it
        assert int(r.headers["content-length"]) == len(gzip.compress(raw, compresslevel=9, mtime=0))
    plain = c.get(js, headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers and plain.content == raw
    assert c.get("/assets/nope.js").status_code == 404
    assert "def spa" not in c.get("/assets/%2e%2e/server.py").text
