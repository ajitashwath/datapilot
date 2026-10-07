import socket
import sqlite3
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.connectors import PostgresConnection, normalise_url, public_addresses
from app.errors import UserError
from app.main import create_app
from fakes import ScriptedLLM

PUBLIC_IP = "93.184.216.34"
SHEET_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"


def resolver(mapping):
    def fake(host, port, **kwargs):
        ip = mapping.get(host, PUBLIC_IP)
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]

    return fake


@pytest.fixture
def quiet(settings):
    settings.scheduler_enabled = False
    return settings


@pytest.fixture
def dns(monkeypatch):
    mapping = {}
    monkeypatch.setattr(socket, "getaddrinfo", resolver(mapping))
    return mapping


@pytest.fixture
def client(quiet, dns):
    with TestClient(create_app(quiet, lambda s, o=None: ScriptedLLM())) as c:
        yield c


@pytest.fixture
def sid(client):
    return client.post("/api/sessions").json()["session_id"]


def wait_for(client, job_id, headers=None):
    for _ in range(200):
        job = client.get(f"/api/jobs/{job_id}", headers=headers).json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def serve(client, handler):
    client.app.state.http_transport = httpx.MockTransport(handler)


class TestUrlRules:
    def test_only_https_without_credentials(self):
        assert normalise_url("https://example.com/data.csv", False) == "https://example.com/data.csv"
        for bad in ["http://example.com/a.csv", "ftp://example.com/a.csv", "file:///etc/passwd", "javascript:alert(1)", "example.com/a.csv", "https://user:pw@example.com/a.csv"]:
            with pytest.raises(UserError):
                normalise_url(bad, False)
        assert normalise_url("http://localhost:9000/a.csv", True).startswith("http://localhost")

    def test_google_sheet_links_become_csv_export_links(self):
        link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid=123#gid=123"
        assert normalise_url(link, False) == f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=123"
        plain = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
        assert normalise_url(plain, False).endswith("export?format=csv&gid=0")
        assert normalise_url(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid=abc", False).endswith("gid=0")

    @pytest.mark.parametrize("ip", ["127.0.0.1", "10.1.2.3", "192.168.0.5", "172.16.9.9", "169.254.169.254", "100.64.0.1", "0.0.0.0", "::1", "fe80::1", "fd00::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1"])
    def test_private_and_internal_addresses_are_blocked(self, monkeypatch, ip):
        monkeypatch.setattr(socket, "getaddrinfo", resolver({"host.example": ip}))
        with pytest.raises(UserError) as exc:
            public_addresses("host.example", 443, allow_private=False)
        assert exc.value.code == "blocked_address"
        assert public_addresses("host.example", 443, allow_private=True)

    def test_public_and_unresolvable_hosts(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", resolver({}))
        assert public_addresses("example.com", 443, False) == [PUBLIC_IP]

        def failing(*args, **kwargs):
            raise socket.gaierror("no such host")

        monkeypatch.setattr(socket, "getaddrinfo", failing)
        with pytest.raises(UserError) as exc:
            public_addresses("nowhere.invalid", 443, False)
        assert exc.value.code == "unresolvable_host"

    def test_a_host_with_one_private_address_is_rejected(self, monkeypatch):
        def mixed(host, port, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, port)), (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port))]

        monkeypatch.setattr(socket, "getaddrinfo", mixed)
        with pytest.raises(UserError):
            public_addresses("rebind.example", 443, False)


class TestUrlImport:
    def test_imports_csv_pins_the_resolved_address_and_records_the_source(self, client, sid):
        seen = {}

        def handler(request):
            seen.update(host=request.url.host, header=request.headers["host"], sni=request.extensions.get("sni_hostname"))
            return httpx.Response(200, content=b"city,sales\nA,1\nB,2\nC,3\n")

        serve(client, handler)
        job = client.post(f"/api/sessions/{sid}/connectors/url", json={"url": "https://data.example.com/Sales%20Q3.csv"}).json()
        result = wait_for(client, job["job_id"])
        assert result["status"] == "done" and result["datasets"] == ["sales_q3"]
        assert seen == {"host": PUBLIC_IP, "header": "data.example.com", "sni": b"data.example.com"} or seen["host"] == PUBLIC_IP
        assert seen["header"] == "data.example.com"
        state = client.get(f"/api/sessions/{sid}").json()
        assert state["datasets"][0]["profile"]["source"] == "url:https://data.example.com/Sales%20Q3.csv"

    def test_google_sheet_download_and_name(self, client, sid):
        paths = []
        serve(client, lambda request: (paths.append(str(request.url.path) + "?" + request.url.query.decode()), httpx.Response(200, content=b"a,b\n1,2\n3,4\n"))[1])
        job = client.post(f"/api/sessions/{sid}/connectors/url", json={"url": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=7"}).json()
        result = wait_for(client, job["job_id"])
        assert result["status"] == "done" and result["datasets"] == ["sheet"]
        assert paths == [f"/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=7"]

    def test_unshared_sheet_returns_a_clear_error(self, client, sid):
        serve(client, lambda request: httpx.Response(200, content=b"<!DOCTYPE html><html><body>Sign in</body></html>"))
        job = client.post(f"/api/sessions/{sid}/connectors/url", json={"url": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"}).json()
        result = wait_for(client, job["job_id"])
        assert result["status"] == "error" and "share the sheet" in result["message"]
        assert client.get(f"/api/sessions/{sid}").json()["datasets"] == []

    @pytest.mark.parametrize("status", [403, 404, 500])
    def test_http_errors_are_reported(self, client, sid, status):
        serve(client, lambda request: httpx.Response(status))
        result = wait_for(client, client.post(f"/api/sessions/{sid}/connectors/url", json={"url": "https://data.example.com/a.csv"}).json()["job_id"])
        assert result["status"] == "error" and str(status) in result["message"]

    def test_oversized_downloads_are_cut_off(self, client, sid):
        client.app.state.settings.max_upload_mb = 1
        serve(client, lambda request: httpx.Response(200, content=b"a\n" + b"1\n" * (2 * 1024 * 1024)))
        result = wait_for(client, client.post(f"/api/sessions/{sid}/connectors/url", json={"url": "https://data.example.com/big.csv"}).json()["job_id"])
        assert result["status"] == "error" and "limit" in result["message"]
        assert list((client.app.state.sessions.root / sid / "incoming").iterdir()) == []

    def test_redirects_are_followed_but_each_hop_is_checked(self, client, sid, dns):
        def handler(request):
            host = request.headers["host"]
            if host == "short.example.com":
                return httpx.Response(302, headers={"location": "https://cdn.example.com/real.csv"})
            return httpx.Response(200, content=b"a,b\n1,2\n3,4\n")

        serve(client, handler)
        ok = wait_for(client, client.post(f"/api/sessions/{sid}/connectors/url", json={"url": "https://short.example.com/x"}).json()["job_id"])
        assert ok["status"] == "done"
        dns["evil.example.com"] = "169.254.169.254"

        def sneaky(request):
            return httpx.Response(302, headers={"location": "https://evil.example.com/meta"})

        serve(client, sneaky)
        blocked = wait_for(client, client.post(f"/api/sessions/{sid}/connectors/url", json={"url": "https://short.example.com/y"}).json()["job_id"])
        assert blocked["status"] == "error" and "not publicly reachable" in blocked["message"]

    def test_redirect_loops_stop(self, client, sid):
        serve(client, lambda request: httpx.Response(302, headers={"location": "https://loop.example.com/again"}))
        result = wait_for(client, client.post(f"/api/sessions/{sid}/connectors/url", json={"url": "https://loop.example.com/a"}).json()["job_id"])
        assert result["status"] == "error" and "redirected" in result["message"]

    def test_private_targets_are_rejected_before_any_request(self, client, sid, dns):
        dns["internal.example.com"] = "10.0.0.8"
        called = []
        serve(client, lambda request: (called.append(1), httpx.Response(200, content=b"a\n1\n"))[1])
        result = wait_for(client, client.post(f"/api/sessions/{sid}/connectors/url", json={"url": "https://internal.example.com/a.csv"}).json()["job_id"])
        assert result["status"] == "error" and called == []

    def test_refresh_replaces_data_and_keeps_old_data_on_failure(self, client, sid):
        content = {"body": b"k,v\na,1\nb,2\nc,3\n", "status": 200}
        serve(client, lambda request: httpx.Response(content["status"], content=content["body"]))
        wait_for(client, client.post(f"/api/sessions/{sid}/connectors/url", json={"url": "https://data.example.com/kv.csv"}).json()["job_id"])
        content["body"] = b"k,v\na,10\nb,20\nc,30\nd,40\ne,50\n"
        done = wait_for(client, client.post(f"/api/sessions/{sid}/datasets/kv/refresh").json()["job_id"])
        assert done["status"] == "done"
        assert client.get(f"/api/sessions/{sid}/datasets/kv/preview").json()["row_count"] == 5
        content["status"] = 500
        failed = wait_for(client, client.post(f"/api/sessions/{sid}/datasets/kv/refresh").json()["job_id"])
        assert failed["status"] == "error"
        assert client.get(f"/api/sessions/{sid}/datasets/kv/preview").json()["row_count"] == 5
        content.update(status=200, body=b"k,v\n")
        empty = wait_for(client, client.post(f"/api/sessions/{sid}/datasets/kv/refresh").json()["job_id"])
        assert empty["status"] == "error" and client.get(f"/api/sessions/{sid}/datasets/kv/preview").json()["row_count"] == 5

    def test_uploaded_files_cannot_be_refreshed(self, client, sid):
        client.post(f"/api/sessions/{sid}/datasets", files=[("files", ("up.csv", b"a,b\n1,2\n3,4\n", "text/csv"))])
        result = wait_for(client, client.post(f"/api/sessions/{sid}/datasets/up/refresh").json()["job_id"])
        assert result["status"] == "error" and "link" in result["message"]

    def test_invalid_url_inputs(self, client, sid):
        assert client.post(f"/api/sessions/{sid}/connectors/url", json={"url": "short"}).status_code == 422
        result = wait_for(client, client.post(f"/api/sessions/{sid}/connectors/url", json={"url": "http://data.example.com/a.csv"}).json()["job_id"])
        assert result["status"] == "error" and "https" in result["message"]


class TestSqliteImport:
    def build(self, path):
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE customers (id INTEGER, name TEXT)")
        con.executemany("INSERT INTO customers VALUES (?, ?)", [(i, f"c{i}") for i in range(1, 6)])
        con.execute("CREATE TABLE orders (id INTEGER, customer_id INTEGER, amount REAL)")
        con.executemany("INSERT INTO orders VALUES (?, ?, ?)", [(i, (i % 5) + 1, i * 2.5) for i in range(1, 21)])
        con.execute("CREATE TABLE empty_table (x INTEGER)")
        con.execute("CREATE VIEW big_orders AS SELECT * FROM orders WHERE amount > 20")
        con.commit()
        con.close()

    def test_imports_tables_and_views_and_skips_empty_ones(self, client, sid, tmp_path):
        path = tmp_path / "shop.db"
        self.build(path)
        job = client.post(f"/api/sessions/{sid}/connectors/sqlite", files=[("file", ("shop.db", path.read_bytes(), "application/octet-stream"))]).json()
        result = wait_for(client, job["job_id"])
        assert result["status"] == "done" and set(result["datasets"]) == {"customers", "orders", "big_orders"}
        state = client.get(f"/api/sessions/{sid}").json()
        sources = {d["profile"]["name"]: d["profile"]["source"] for d in state["datasets"]}
        assert sources["orders"] == "sqlite:shop.db:orders"
        assert any(r["left_table"] in ("orders", "customers") for r in state["relationships"])

    def test_rejects_files_that_are_not_sqlite(self, client, sid):
        job = client.post(f"/api/sessions/{sid}/connectors/sqlite", files=[("file", ("fake.db", b"this is not a database at all", "application/octet-stream"))]).json()
        result = wait_for(client, job["job_id"])
        assert result["status"] == "error" and "not a SQLite" in result["message"]

    def test_database_without_rows_is_rejected(self, client, sid, tmp_path):
        path = tmp_path / "empty.db"
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE t (x INTEGER)")
        con.commit()
        con.close()
        result = wait_for(client, client.post(f"/api/sessions/{sid}/connectors/sqlite", files=[("file", ("empty.db", path.read_bytes(), "x"))]).json()["job_id"])
        assert result["status"] == "error"

    def test_respects_the_row_cap(self, client, sid, tmp_path):
        client.app.state.settings.connector_max_rows = 7
        path = tmp_path / "shop.db"
        self.build(path)
        wait_for(client, client.post(f"/api/sessions/{sid}/connectors/sqlite", files=[("file", ("shop.db", path.read_bytes(), "x"))]).json()["job_id"])
        rows = {d["profile"]["name"]: d["profile"]["rows"] for d in client.get(f"/api/sessions/{sid}").json()["datasets"]}
        assert rows["orders"] == 7


class FakeCopy:
    def __init__(self, chunks):
        self.chunks = chunks

    def __enter__(self):
        return iter(self.chunks)

    def __exit__(self, *args):
        return False


class FakeCursor:
    def __init__(self, tables, data, log):
        self.tables, self.data, self.log = tables, data, log

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.log.append(("execute", sql))

    def fetchall(self):
        return [tuple(t.split(".", 1)) for t in self.tables]

    def copy(self, statement):
        self.log.append(("copy", statement))
        table = statement.split("FROM ")[1].split(" LIMIT")[0].replace('"', "")
        return FakeCopy(self.data[table])


class FakeConnection:
    def __init__(self, tables, data, log):
        self.cursor_args = (tables, data, log)
        self.closed = False

    def cursor(self):
        return FakeCursor(*self.cursor_args)

    def close(self):
        self.closed = True


class TestPostgres:
    CONN = {"host": "db.example.com", "port": 5432, "dbname": "shop", "user": "reader", "password": "hunter2-very-secret"}

    @pytest.fixture
    def fake(self, client):
        log, calls = [], []
        data = {
            "public.customers": [b"id,name\n1,Ann\n", b"2,Bob\n3,Cy\n"],
            "sales.orders": [b"id,customer_id,amount\n1,1,9.5\n2,2,3.0\n3,3,4.25\n"],
        }

        def connect(**kwargs):
            calls.append(kwargs)
            return FakeConnection(list(data), data, log)

        client.app.state.postgres_connect = connect
        return log, calls

    def test_lists_tables(self, client, sid, fake):
        response = client.post(f"/api/sessions/{sid}/connectors/postgres/tables", json={"connection": self.CONN})
        assert response.json() == {"tables": ["public.customers", "sales.orders"]}
        log, calls = fake
        assert calls[0]["options"].startswith("-c default_transaction_read_only=on")
        assert calls[0]["sslmode"] == "require" and calls[0]["connect_timeout"] == 10

    def test_imports_selected_tables_with_a_read_only_copy(self, client, sid, fake):
        job = client.post(f"/api/sessions/{sid}/connectors/postgres", json={"connection": self.CONN, "tables": ["public.customers", "sales.orders"]}).json()
        result = wait_for(client, job["job_id"])
        assert result["status"] == "done" and result["datasets"] == ["customers", "orders"]
        log, _ = fake
        statements = [s for kind, s in log if kind == "copy"]
        assert statements[0].startswith('COPY (SELECT * FROM "public"."customers" LIMIT 1000000) TO STDOUT')
        state = client.get(f"/api/sessions/{sid}").json()
        by_name = {d["profile"]["name"]: d["profile"] for d in state["datasets"]}
        assert by_name["customers"]["rows"] == 3 and by_name["orders"]["source"] == "postgres:db.example.com/shop:sales.orders"
        assert "hunter2" not in str(result) and "hunter2" not in str(state)

    def test_unknown_tables_and_empty_selection_are_rejected(self, client, sid, fake):
        unknown = wait_for(client, client.post(f"/api/sessions/{sid}/connectors/postgres", json={"connection": self.CONN, "tables": ["public.secrets"]}).json()["job_id"])
        assert unknown["status"] == "error" and "do not exist" in unknown["message"]
        none = wait_for(client, client.post(f"/api/sessions/{sid}/connectors/postgres", json={"connection": self.CONN, "tables": []}).json()["job_id"])
        assert none["status"] == "error"

    def test_injection_style_table_names_are_never_sent_to_the_database(self, client, sid, fake):
        evil = 'public.customers"; DROP TABLE users; --'
        result = wait_for(client, client.post(f"/api/sessions/{sid}/connectors/postgres", json={"connection": self.CONN, "tables": [evil]}).json()["job_id"])
        assert result["status"] == "error"
        assert not [s for kind, s in fake[0] if kind == "copy"]

    def test_private_database_hosts_are_blocked_by_default(self, client, sid, fake, dns):
        dns["db.internal"] = "10.0.0.5"
        response = client.post(f"/api/sessions/{sid}/connectors/postgres/tables", json={"connection": {**self.CONN, "host": "db.internal"}})
        assert response.status_code == 422 and response.json()["error"]["code"] == "blocked_address"
        client.app.state.settings.allow_private_connections = True
        assert client.post(f"/api/sessions/{sid}/connectors/postgres/tables", json={"connection": {**self.CONN, "host": "db.internal"}}).status_code == 200

    def test_connection_failures_do_not_leak_credentials(self, client, sid):
        def failing(**kwargs):
            raise RuntimeError("FATAL: password authentication failed for user reader with password hunter2-very-secret")

        client.app.state.postgres_connect = failing
        response = client.post(f"/api/sessions/{sid}/connectors/postgres/tables", json={"connection": self.CONN})
        assert response.status_code == 422 and "hunter2" not in response.text

    def test_validation(self, client, sid):
        assert client.post(f"/api/sessions/{sid}/connectors/postgres/tables", json={"connection": {**self.CONN, "port": 99999}}).status_code == 422
        assert client.post(f"/api/sessions/{sid}/connectors/postgres/tables", json={"connection": {**self.CONN, "sslmode": "bogus"}}).status_code == 422
        bad = client.post(f"/api/sessions/{sid}/connectors/postgres/tables", json={"connection": {**self.CONN, "password": "x" * 500}})
        assert bad.status_code == 422 and "x" * 50 not in bad.text

    def test_real_driver_is_importable(self):
        import psycopg

        assert hasattr(psycopg, "connect")

    def test_connection_model_hides_the_password(self):
        model = PostgresConnection(**self.CONN)
        assert "hunter2" not in repr(model) and "hunter2" not in model.model_dump_json()


class TestJobs:
    def test_unknown_jobs_404(self, client):
        assert client.get("/api/jobs/nope").status_code == 404

    def test_jobs_are_private_to_workspace_members(self, quiet, dns):
        quiet.auth_mode = "accounts"
        with TestClient(create_app(quiet, lambda s, o=None: ScriptedLLM())) as client:
            def register(email):
                token = client.post("/api/auth/register", json={"email": email, "password": "correct horse battery", "name": "N"}).json()["token"]
                return {"Authorization": f"Bearer {token}"}

            ann, bob = register("ann@example.com"), register("bob@example.com")
            sid = client.post("/api/sessions", headers=ann).json()["session_id"]
            serve(client, lambda request: httpx.Response(200, content=b"a,b\n1,2\n3,4\n"))
            job = client.post(f"/api/sessions/{sid}/connectors/url", headers=ann, json={"url": "https://data.example.com/a.csv"}).json()["job_id"]
            assert wait_for(client, job, ann)["status"] == "done"
            assert client.get(f"/api/jobs/{job}", headers=bob).status_code == 404
            assert client.post(f"/api/sessions/{sid}/connectors/url", headers=bob, json={"url": "https://data.example.com/a.csv"}).status_code == 404
