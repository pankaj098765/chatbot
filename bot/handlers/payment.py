"""
bot/handlers/payment.py — Telegram Stars payment flow.

Plans:
  Premium (100 Stars) — unlocks gender filter (30 days)
  VIP     (250 Stars) — priority matching (30 days)

# UPDATED: all user-facing strings are now rendered via t() so every message
  is delivered in the user's configured ui_language.
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
from bot.i18n import lang_of, t
from bot.keyboards.inline import payment_keyboard, search_keyboard

router = Router()

# Static plan metadata — only prices and payload identifiers (non-localised)
_PLAN_INFO = {
    "premium": {
        "price": settings.premium_price_stars,
        "payload": "premium",
    },
    "vip": {
        "price": settings.vip_price_stars,
        "payload": "vip",
    },
}


@router.message(Command("pay"))
async def cmd_pay(message: Message) -> None:
    user = await db.get_user(message.from_user.id)  # type: ignore[union-attr]
    lang = lang_of(user)
    await message.answer(
        t(
            "choose_plan",
            lang,
            premium_price=settings.premium_price_stars,
            vip_price=settings.vip_price_stars,
        ),
        parse_mode="HTML",
        reply_markup=payment_keyboard(),
    )


@router.message(Command("vip"))
async def cmd_vip(message: Message) -> None:
    user = await db.get_user(message.from_user.id)  # type: ignore[union-attr]
    lang = lang_of(user)
    await message.answer(
        t(
            "vip_info",
            lang,
            vip_price=settings.vip_price_stars,
            subscription_days=settings.subscription_days,
        ),
        parse_mode="HTML",
        reply_markup=payment_keyboard(),
    )


async def _send_invoice(bot: Bot, chat_id: int, plan: str, lang: str = "en") -> None:
    """Send a Telegram Stars invoice for *plan* in the user's language."""
    info = _PLAN_INFO[plan]
    title = t(f"{plan}_plan_title", lang)
    description = t(f"{plan}_plan_description", lang)
    await bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        payload=info["payload"],
        currency="XTR",                    # Telegram Stars currency code
        prices=[LabeledPrice(label=title, amount=info["price"])],
        provider_token="",                 # Empty string for Telegram Stars
    )


@router.callback_query(F.data == "buy_premium")
async def cb_buy_premium(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = lang_of(user)
    await _send_invoice(bot, callback.from_user.id, "premium", lang)


@router.callback_query(F.data == "buy_vip")
async def cb_buy_vip(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = lang_of(user)
    await _send_invoice(bot, callback.from_user.id, "vip", lang)


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
    expiry_str = expiry.strftime("%Y-%m-%d")

    user = await db.get_user(user_id)
    lang = lang_of(user)

    if plan == "premium":
        await db.update_user(user_id, {"is_premium": True, "premium_expires": expiry})
        await message.answer(
            t("premium_activated", lang, expiry=expiry_str),
            parse_mode="HTML",
            reply_markup=search_keyboard(),
        )
    elif plan == "vip":
        await db.update_user(
            user_id, {"is_vip": True, "is_premium": True, "vip_expires": expiry, "premium_expires": expiry}
        )
        await message.answer(
            t("vip_activated", lang, expiry=expiry_str),
            parse_mode="HTML",
            reply_markup=search_keyboard(),
        )
