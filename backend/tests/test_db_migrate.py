from thread.db.migrate import sync_database_url


def test_sync_database_url_converts_asyncpg_to_psycopg():
    url = "postgresql+asyncpg://thread:thread@127.0.0.1:55432/thread"
    assert sync_database_url(url) == "postgresql+psycopg://thread:thread@127.0.0.1:55432/thread"


def test_sync_database_url_passthrough_other_drivers():
    url = "postgresql+psycopg://thread:thread@127.0.0.1:55432/thread"
    assert sync_database_url(url) == url