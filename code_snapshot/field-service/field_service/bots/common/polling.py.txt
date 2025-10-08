from __future__ import annotations

from aiohttp import ClientResponseError

from field_service.infra.notify import send_log

__all__ = ["poll_with_single_instance_guard"]


async def poll_with_single_instance_guard(
    dispatcher,
    bot,
    *,
    logs_chat_id: int | None = None,
) -> None:
    """Run dispatcher polling handling 409 conflicts gracefully."""

    try:
        # Keep signature minimal to be compatible with test doubles
        # and different dispatcher implementations.
        await dispatcher.start_polling(bot)
    except ClientResponseError as error:
        if error.status == 409:
            await send_log(bot, "409 Conflict: another instance running → exit", chat_id=logs_chat_id)
            raise SystemExit(0) from None
        raise
