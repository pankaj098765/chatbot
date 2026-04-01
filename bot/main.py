"""
bot/main.py — Application entry point.

Initialises connections, registers all routers, and starts long-polling.
"""
from __future__ import annotations

import asyncio
import logging
import sys

import uvloop
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings, log_config_summary
from bot.database import mongodb, redis_client
from bot.handlers import chat, payment, search, start
from bot.services.retention_engine import run_watchdog
from bot.services.queue_monitor import run_queue_monitor

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    log_config_summary()
    logger.info("Connecting to MongoDB…")
    await mongodb.connect()
    logger.info("Connecting to Redis…")
    await redis_client.connect()
    # Fix #7 & #8: Start background monitoring tasks
    asyncio.create_task(run_watchdog(bot))
    asyncio.create_task(run_queue_monitor())
    logger.info("Bot started.")


async def on_shutdown(bot: Bot) -> None:
    logger.info("Shutting down…")
    await mongodb.disconnect()
    await redis_client.disconnect()
    logger.info("Goodbye.")


async def main() -> None:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # MemoryStorage is fine for single-instance; swap for RedisStorage in multi-replica.
    dp = Dispatcher(storage=MemoryStorage())

    # Lifecycle hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Register routers (order matters: more-specific first)
    dp.include_router(start.router)
    dp.include_router(payment.router)
    dp.include_router(search.router)
    dp.include_router(chat.router)

    # Drop pending updates on start to avoid processing stale messages
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("Starting polling…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    uvloop.install()
    asyncio.run(main())
