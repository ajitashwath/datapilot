import os
import time
import uuid

import pytest

from app.config import Settings
from app.connectors import PostgresConnection, import_postgres, list_postgres_tables, open_postgres
from app.data.datasets import DatasetStore
from app.errors import UserError
from app.session import Session
from tls_proxy import TlsPostgresProxy

ADMIN = {
    "host": os.environ.get("TEST_PG_HOST"),
    "port": int(os.environ.get("TEST_PG_PORT", "5432")),
    "user": os.environ.get("TEST_PG_USER", "postgres"),
    "password": os.environ.get("TEST_PG_PASSWORD", ""),
}

pytestmark = pytest.mark.skipif(not ADMIN["host"], reason="set TEST_PG_HOST (and port, user, password) to run against a real Postgres")

READER_PASSWORD = "reader-pass-12345"


@pytest.fixture(scope="module")
def database():
    import psycopg

    name = "dp_" + uuid.uuid4().hex[:10]
    admin = psycopg.connect(dbname="postgres", autocommit=True, **ADMIN)
    admin.execute(f'CREATE DATABASE "{name}"')
    admin.execute("DROP ROLE IF EXISTS dp_reader")
    admin.execute(f"CREATE ROLE dp_reader LOGIN PASSWORD '{READER_PASSWORD}'")
    shop = psycopg.connect(dbname=name, autocommit=True, **ADMIN)
    shop.execute("CREATE SCHEMA sales")
    shop.execute("CREATE TABLE public.customers (id int PRIMARY KEY, name text, joined date, balance numeric(10,2), note text)")
    shop.execute(
        "INSERT INTO public.customers VALUES (1, 'Ann', '2024-01-05', 10.50, 'plain'), (2, 'Bob, Jr.', '2024-02-10', NULL, 'has \"quotes\" and, commas'), "
        "(3, 'Zoë', NULL, 99.99, E'two\\nlines'), (4, NULL, '2024-03-01', 0, NULL)"
    )
    shop.execute('CREATE TABLE sales."Order Items" (order_id int, "Item Name" text, qty int)')
    shop.execute('INSERT INTO sales."Order Items" SELECT g, \'item \' || g, g % 7 FROM generate_series(1, 5000) g')
    shop.execute("""CREATE TABLE public."Weird ""Name" (a int, b int)""")
    shop.execute("""INSERT INTO public."Weird ""Name" VALUES (1, 2), (3, 4), (5, 6)""")
    shop.execute("CREATE TABLE public.big (id int, payload text)")
    shop.execute("INSERT INTO public.big SELECT g, md5(g::text) FROM generate_series(1, 200000) g")
    shop.execute("CREATE VIEW public.vip AS SELECT * FROM public.customers WHERE balance > 50")
    shop.execute("CREATE TABLE public.secret_hr (id int, salary int)")
    shop.execute("INSERT INTO public.secret_hr VALUES (1, 100000)")
    admin.execute("DROP ROLE IF EXISTS dp_narrow")
    admin.execute(f"CREATE ROLE dp_narrow LOGIN PASSWORD '{READER_PASSWORD}'")
    shop.execute(f'GRANT CONNECT ON DATABASE "{name}" TO dp_reader, dp_narrow')
    shop.execute("GRANT USAGE ON SCHEMA public TO dp_narrow")
    shop.execute("GRANT SELECT ON public.customers TO dp_narrow")
    shop.execute("GRANT USAGE ON SCHEMA public, sales TO dp_reader")
    shop.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public, sales TO dp_reader")
    shop.close()
    yield name
    admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    admin.execute("DROP ROLE IF EXISTS dp_reader")
    admin.execute("DROP ROLE IF EXISTS dp_narrow")
    admin.close()


def connection(database, **overrides) -> PostgresConnection:
    values = {"host": ADMIN["host"], "port": ADMIN["port"], "dbname": database, "user": "dp_reader", "password": READER_PASSWORD, "sslmode": "disable"}
    return PostgresConnection(**{**values, **overrides})


@pytest.fixture
def settings(tmp_path):
    return Settings(upload_root=str(tmp_path / "up"), allow_private_connections=True, connector_max_rows=1_000_000, max_upload_mb=50)


@pytest.fixture
def session(settings, tmp_path):
    store = DatasetStore(tmp_path / "store", settings)
    yield Session(id="pg-test", store=store)
    store.close()


def test_lists_user_tables_and_views_but_not_system_schemas(database, settings):
    tables = list_postgres_tables(connection(database), settings)
    assert "public.customers" in tables and "sales.Order Items" in tables and "public.vip" in tables
    assert not [t for t in tables if t.startswith(("pg_catalog", "information_schema"))]


def test_imports_awkward_values_exactly(database, settings, session):
    names = import_postgres(session, settings, connection(database), ["public.customers"])
    assert names == ["customers"]
    store = session.store
    assert store.get_profile("customers").rows == 4
    assert store.get_profile("customers").source == f"postgres:{ADMIN['host']}/{database}:public.customers"
    rows = {r[0]: r for r in store.query("SELECT id, name, joined, balance, note FROM customers ORDER BY id").rows}
    assert rows[2][1] == "Bob, Jr." and rows[2][4] == 'has "quotes" and, commas' and rows[2][3] is None
    assert rows[3][1] == "Zoë" and rows[3][4] == "two\nlines" and rows[3][2] is None
    assert rows[1][2] == "2024-01-05" and rows[1][3] == 10.5
    kinds = {c.name: c.kind for c in store.get_profile("customers").columns}
    assert kinds["joined"] == "date" and kinds["balance"] == "numeric"


def test_odd_identifiers_are_quoted_correctly(database, settings, session):
    names = import_postgres(session, settings, connection(database), ['sales.Order Items', 'public.Weird "Name'])
    assert len(names) == 2
    order_items = next(n for n in names if n.startswith("order"))
    assert session.store.get_profile(order_items).rows == 5000
    assert "Item Name" in [c.name for c in session.store.get_profile(order_items).columns]


def test_row_cap_is_enforced_by_the_database(database, settings, session):
    settings.connector_max_rows = 1234
    import_postgres(session, settings, connection(database), ["public.big"])
    assert session.store.get_profile("big").rows == 1234


def test_large_table_streams_quickly(database, settings, session):
    started = time.perf_counter()
    import_postgres(session, settings, connection(database), ["public.big"])
    assert session.store.get_profile("big").rows == 200000
    assert time.perf_counter() - started < 30


def test_views_can_be_imported(database, settings, session):
    names = import_postgres(session, settings, connection(database), ["public.vip"])
    assert session.store.get_profile(names[0]).rows == 1


def test_tables_outside_the_catalog_list_are_refused(database, settings, session):
    for evil in ['public.customers"; DROP TABLE public.customers; --', "public.nonexistent", "pg_catalog.pg_shadow"]:
        with pytest.raises(UserError) as exc:
            import_postgres(session, settings, connection(database), [evil])
        assert exc.value.code == "unknown_table"


def test_connection_is_read_only_with_a_statement_timeout(database, settings):
    import psycopg

    live = open_postgres(connection(database), settings)
    try:
        with live.cursor() as cursor:
            cursor.execute("SHOW default_transaction_read_only")
            assert cursor.fetchone()[0] == "on"
            cursor.execute("SHOW statement_timeout")
            assert cursor.fetchone()[0] in ("1min", "60s", "60000ms")
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                cursor.execute("CREATE TABLE public.should_not_exist (x int)")
    finally:
        live.close()


def test_an_account_with_narrow_grants_only_sees_and_imports_what_it_may_read(database, settings, session):
    narrow = connection(database, user="dp_narrow", password=READER_PASSWORD)
    assert list_postgres_tables(narrow, settings) == ["public.customers"]
    with pytest.raises(UserError) as exc:
        import_postgres(session, settings, narrow, ["public.secret_hr"])
    assert exc.value.code == "unknown_table"


def test_wrong_password_and_missing_database_give_a_generic_error(database, settings):
    for bad in [{"password": "definitely-wrong"}, {"dbname": "no_such_database"}, {"user": "no_such_user"}]:
        with pytest.raises(UserError) as exc:
            list_postgres_tables(connection(database, **bad), settings)
        assert exc.value.code == "connection_failed"
        assert "definitely-wrong" not in exc.value.message and READER_PASSWORD not in exc.value.message


def test_require_ssl_fails_cleanly_against_a_server_without_tls(database, settings):
    with pytest.raises(UserError) as exc:
        list_postgres_tables(connection(database, sslmode="require"), settings)
    assert exc.value.code == "connection_failed"


@pytest.fixture
def tls_proxy(tmp_path):
    proxy = TlsPostgresProxy(ADMIN["host"], ADMIN["port"], tmp_path).start()
    yield proxy
    proxy.stop()


def test_require_negotiates_real_tls_and_imports_through_it(database, settings, session, tls_proxy):
    conn = connection(database, port=tls_proxy.port, sslmode="require")
    live = open_postgres(conn, settings)
    try:
        assert live.pgconn.ssl_in_use is True
    finally:
        live.close()
    names = import_postgres(session, settings, conn, ["public.customers"])
    assert session.store.get_profile(names[0]).rows == 4
    assert tls_proxy.tls_sessions >= 2 and tls_proxy.plain_sessions == 0


def test_prefer_upgrades_to_tls_when_offered_and_disable_never_does(database, settings, tls_proxy):
    preferred = open_postgres(connection(database, port=tls_proxy.port, sslmode="prefer"), settings)
    disabled = open_postgres(connection(database, port=tls_proxy.port, sslmode="disable"), settings)
    try:
        assert preferred.pgconn.ssl_in_use is True and disabled.pgconn.ssl_in_use is False
    finally:
        preferred.close()
        disabled.close()
    assert tls_proxy.tls_sessions == 1 and tls_proxy.plain_sessions == 1


def test_verify_full_refuses_a_certificate_that_is_not_trusted(database, settings, tls_proxy):
    with pytest.raises(UserError) as exc:
        list_postgres_tables(connection(database, port=tls_proxy.port, sslmode="verify-full"), settings)
    assert exc.value.code == "connection_failed" and "certificate" not in exc.value.message.lower()
    assert tls_proxy.plain_sessions == 0


def test_require_alone_accepts_any_certificate_which_is_why_verify_full_exists(database, settings, tls_proxy):
    assert "public.customers" in list_postgres_tables(connection(database, port=tls_proxy.port, sslmode="require"), settings)


def test_private_hosts_are_refused_unless_allowed(database, settings):
    settings.allow_private_connections = False
    with pytest.raises(UserError) as exc:
        list_postgres_tables(connection(database), settings)
    assert exc.value.code == "blocked_address"


def test_full_http_flow_with_the_real_driver(database, settings):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from fakes import ScriptedLLM

    settings.scheduler_enabled = False
    with TestClient(create_app(settings, lambda s, o=None: ScriptedLLM())) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        body = {"connection": {"host": ADMIN["host"], "port": ADMIN["port"], "dbname": database, "user": "dp_reader", "password": READER_PASSWORD, "sslmode": "disable"}}
        tables = client.post(f"/api/sessions/{sid}/connectors/postgres/tables", json=body).json()["tables"]
        assert "public.customers" in tables
        job = client.post(f"/api/sessions/{sid}/connectors/postgres", json={**body, "tables": ["public.customers", "sales.Order Items"]}).json()["job_id"]
        for _ in range(200):
            status = client.get(f"/api/jobs/{job}").json()
            if status["status"] in ("done", "error"):
                break
            time.sleep(0.05)
        assert status["status"] == "done" and len(status["datasets"]) == 2
        assert READER_PASSWORD not in str(status)
        state = client.get(f"/api/sessions/{sid}").json()
        assert {d["profile"]["rows"] for d in state["datasets"]} == {4, 5000}
        assert READER_PASSWORD not in str(state)
