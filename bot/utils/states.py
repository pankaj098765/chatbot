"""
bot/utils/states.py — FSM state definitions.

State machine:
  IDLE  ──/search──►  SEARCHING  ──matched──►  CONNECTED  ──/stop──►  IDLE
                           │                        │
                           └───timeout──►  COOLDOWN ◄┘
"""
from aiogram.fsm.state import State, StatesGroup


class UserState(StatesGroup):
    IDLE = State()
    SEARCHING = State()
    CONNECTED = State()
    COOLDOWN = State()
