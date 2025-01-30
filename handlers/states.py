from aiogram.fsm.state import StatesGroup, State

class CityStates(StatesGroup):
    """Состояния для процесса выбора города и района."""
    CITY_SELECTED = State()