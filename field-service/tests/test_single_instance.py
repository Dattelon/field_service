import pytest
from aiohttp import ClientResponseError, RequestInfo
from multidict import CIMultiDict
from yarl import URL

from field_service.bots.common.polling import poll_with_single_instance_guard


class DummyBot:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, dict]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append((chat_id, text, kwargs))
        return True


class DummyDispatcher:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def start_polling(self, bot):
        raise self._exc


@pytest.mark.asyncio
async def test_poll_with_single_instance_guard_logs_and_exits():
    request_info = RequestInfo(URL("https://api.telegram.org"), "GET", CIMultiDict())
    error = ClientResponseError(
        request_info,
        history=tuple(),
        status=409,
        message="Conflict",
    )
    dispatcher = DummyDispatcher(error)
    bot = DummyBot()

    with pytest.raises(SystemExit) as excinfo:
        await poll_with_single_instance_guard(dispatcher, bot, logs_chat_id=555)

    assert excinfo.value.code == 0
    assert bot.calls
    assert bot.calls[0][0] == 555
    assert bot.calls[0][1] == "409 Conflict: another instance running → exit"
