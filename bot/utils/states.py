"""
bot/utils/states.py — FSM state definitions.

State machine:
  IDLE  ──/search──►  SEARCHING  ──matched──►  CONNECTED  ──/stop──►  IDLE
                           │                        │
                           └───timeout──►  COOLDOWN ◄┘

  IDLE  ──/language──►  SELECTING_LANGUAGE  ──selected──►  IDLE
"""
from aiogram.fsm.state import State, StatesGroup


class UserState(StatesGroup):
    IDLE = State()
    SEARCHING = State()
    CONNECTED = State()
    COOLDOWN = State()
    SELECTING_LANGUAGE = State()  # NEW: user is choosing their ui/chat language
