import pytest

from storage.sql._async import AsyncSQLImpl


@pytest.mark.asyncio
async def test_transaction_error_log_does_not_include_exception_message(monkeypatch):
    events = []
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def rollback(self): pass
    monkeypatch.setattr("storage.sql._async.AsyncSession", lambda *args, **kwargs: Session())
    class Logger:
        def error(self, message): events.append(message)
    monkeypatch.setattr("storage.sql._async.logger", Logger())

    with pytest.raises(Exception):
        async with AsyncSQLImpl(object()).asession_scope():
            raise RuntimeError("api_key=super-secret")

    assert events == ["Async transaction failed (RuntimeError)"]
