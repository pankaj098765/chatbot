"""
bot/handlers/payment.py — Telegram Stars payment flow.

Plans:
  Premium (100 Stars) — unlocks gender filter (30 days)
  VIP     (250 Stars) — priority matching (30 days)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    SuccessfulPayment,
)

from bot.config import settings
from bot.database import mongodb as db
from bot.keyboards.inline import payment_keyboard, search_keyboard

router = Router()

_PLAN_INFO = {
    "premium": {
        "title": "⭐ Premium Plan",
        "description": (
            "Unlock <b>gender filter</b> — choose to match only with "
            "male or female strangers.\n\nValid for 30 days."
        ),
        "price": settings.premium_price_stars,
        "payload": "premium",
    },
    "vip": {
        "title": "👑 VIP Plan",
        "description": (
            "Get <b>priority matching</b> — jump to the front of the queue "
            "and get matched faster than everyone else.\n\nValid for 30 days."
        ),
        "price": settings.vip_price_stars,
        "payload": "vip",
    },
}


@router.message(Command("pay"))
async def cmd_pay(message: Message) -> None:
    await message.answer(
        "💳 <b>Choose a plan:</b>\n\n"
        f"⭐ <b>Premium</b> — {settings.premium_price_stars} Stars\n"
        "  → Gender filter: match only males or females\n"
        "  → 👀 <i>Premium unlocks more users in the pool</i>\n\n"
        f"👑 <b>VIP</b> — {settings.vip_price_stars} Stars\n"
        "  → Priority queue: get matched faster\n"
        "  → 🔥 <i>VIP users get faster matches — skip the wait</i>\n\n"
        "<i>Powered by Telegram Stars</i>",
        parse_mode="HTML",
        reply_markup=payment_keyboard(),
    )


@router.message(Command("vip"))
async def cmd_vip(message: Message) -> None:
    await message.answer(
        "👑 <b>VIP Plan</b>\n\n"
        f"Price: <b>{settings.vip_price_stars} Telegram Stars</b>\n\n"
        "Benefits:\n"
        "• 🔥 Priority queue — always matched before Free and Premium users\n"
        "• ⚡ Skip the wait — average match time under 10 seconds\n"
        "• 👀 Access to a larger pool of active users\n\n"
        f"Valid for {settings.subscription_days} days.",
        parse_mode="HTML",
        reply_markup=payment_keyboard(),
    )


async def _send_invoice(bot: Bot, chat_id: int, plan: str) -> None:
    info = _PLAN_INFO[plan]
    await bot.send_invoice(
        chat_id=chat_id,
        title=info["title"],
        description=info["description"].replace("<b>", "").replace("</b>", ""),
        payload=info["payload"],
        currency="XTR",                    # Telegram Stars currency code
        prices=[LabeledPrice(label=info["title"], amount=info["price"])],
        provider_token="",                 # Empty string for Telegram Stars
    )


@router.callback_query(F.data == "buy_premium")
async def cb_buy_premium(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    await _send_invoice(bot, callback.from_user.id, "premium")


@router.callback_query(F.data == "buy_vip")
async def cb_buy_vip(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    await _send_invoice(bot, callback.from_user.id, "vip")


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    """Always approve pre-checkout (validation happens on successful_payment)."""
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message) -> None:
    payment: SuccessfulPayment = message.successful_payment  # type: ignore[assignment]
    user_id = message.from_user.id  # type: ignore[union-attr]
    plan = payment.invoice_payload  # "premium" or "vip"

    expiry = datetime.now(timezone.utc) + timedelta(days=settings.subscription_days)

    if plan == "premium":
        await db.update_user(user_id, {"is_premium": True, "premium_expires": expiry})
        await message.answer(
            "✅ <b>Premium activated!</b>\n\n"
            "You can now set a gender preference with /search.\n"
            f"Expires: {expiry.strftime('%Y-%m-%d')}",
            parse_mode="HTML",
            reply_markup=search_keyboard(),
        )
    elif plan == "vip":
        await db.update_user(
            user_id, {"is_vip": True, "is_premium": True, "vip_expires": expiry, "premium_expires": expiry}
        )
        await message.answer(
            "✅ <b>VIP activated!</b>\n\n"
            "You now have priority matching and gender filter.\n"
            f"Expires: {expiry.strftime('%Y-%m-%d')}",
            parse_mode="HTML",
            reply_markup=search_keyboard(),
        )
