from secret_keys import BOT_TOKEN, YANDEX_GEOCODER_KEY, GEOCODER_URL
from db import init_db, insert_ticket, get_user_tickets, STATUS_MAP, CATEGORY_NAMES

import asyncio
import logging
import re
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, ErrorEvent
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

dp = Dispatcher()

STREET_RE = re.compile(r"^[а-яёА-ЯЁa-zA-Z][а-яёА-ЯЁa-zA-Z\s\-\.\№]{2,60}$")
HOUSE_RE = re.compile(r"^\d+[а-яА-Яa-zA-Z]?(?:\s*(?:к|корп|стр)\.?\s*\d+)?$")
CITY = "Псков"
GOOD_PRECISION = {"exact", "number", "near", "range"}
TABLE_MAP = {
    "🔧 Коммунальные услуги и их перебои": "utility_issues",
    "📄 Вопросы по квитанциям и начислениям": "billing_questions",
    "🚨 Аварийные ситуации": "emergency_situations",
}

def status_label(code: str) -> str:
    return STATUS_MAP.get(code, f"❔ {code}")

async def geocode_check(street: str, house: str) -> bool:
    params = {
        "apikey": YANDEX_GEOCODER_KEY,
        "geocode": f"{CITY}, {street}, {house}",
        "format": "json",
        "results": 1,
    }
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession() as session:
            async with session.get(GEOCODER_URL, params=params, timeout=timeout) as resp:
                if resp.status != 200:
                    logging.warning("Геокодер вернул статус %s", resp.status)
                    return False
                data = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logging.exception("Ошибка запроса к геокодеру: %s", e)
        return False

    features = (
        data.get("response", {})
        .get("GeoObjectCollection", {})
        .get("featureMember", [])
    )
    if not features:
        return False

    meta = (
        features[0].get("GeoObject", {})
        .get("metaDataProperty", {})
        .get("GeocoderMetaData", {})
    )
    precision = meta.get("precision")
    logging.info("Геокодер: precision=%s, адрес=%s", precision, meta.get("text"))

    # Если Яндекс подтвердил только улицу — номер дома не проверен
    return precision in GOOD_PRECISION

class TicketForm(StatesGroup):
    street = State()
    house = State()
    apartment = State()
    description = State()


def main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📝 Подать заявку/Задать вопрос"))
    builder.row(KeyboardButton(text="🔎 Статус заявки"))
    builder.row(KeyboardButton(text="ℹ️ О боте"))
    return builder.as_markup(resize_keyboard=True)


def application_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🔧 Коммунальные услуги и их перебои"))
    builder.row(KeyboardButton(text="📄 Вопросы по квитанциям и начислениям"))
    builder.row(KeyboardButton(text="🚨 Аварийные ситуации"))
    builder.row(KeyboardButton(text="⬅️ В меню"))
    return builder.as_markup(resize_keyboard=True)


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(
        "Привет! Я ТеплоБот. Помогаю подать заявку в управляющую компанию "
        "и отследить её статус без звонков в диспетчерскую.\n\nВыберите действие:",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "⬅️ В меню")
async def back_to_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Вы в главном меню. Выберите действие:", reply_markup=main_menu())


@dp.message(F.text == "📝 Подать заявку/Задать вопрос")
async def start_ticket(message: Message, state: FSMContext) -> None:
    await message.answer("Пожалуйста, выберите категорию:", reply_markup=application_menu())


@dp.message(F.text == "🔎 Статус заявки")
async def show_status(message: Message, state: FSMContext) -> None:
    tickets = get_user_tickets(message.from_user.id)
    if not tickets:
        await message.answer(
            "У вас пока нет заявок.\n\nЧтобы подать заявку, нажмите "
            "«📝 Подать заявку/Задать вопрос».",
            reply_markup=main_menu(),
        )
        return

    lines = []
    for t in tickets[:10]:
        address = f"ул. {t['street']}, д. {t['house_number']}"
        if t.get("apartment_number"):
            address += f", кв. {t['apartment_number']}"
        lines.append(
            f"🗂 Заявка №{t['id']} — {CATEGORY_NAMES.get(t['category'], t['category'])}\n"
            f"📍 Адрес: {address}\n"
            f"📅 Подана: {t['created_at']} в {t['created_time']}\n"
            f"🏷 Статус: {status_label(t['status'])}"
        )

    await message.answer("📋 Ваши заявки:\n\n" + "\n\n".join(lines), reply_markup=main_menu())


@dp.message(F.text == "ℹ️ О боте")
async def about(message: Message) -> None:
    await message.answer("ТеплоБот v0.1", reply_markup=main_menu())


for _text, _table in TABLE_MAP.items():
    @dp.message(F.text == _text)
    async def _start(message: Message, state: FSMContext, table=_table):
        await state.update_data(table=table)
        await state.set_state(TicketForm.street)
        await message.answer("📍 Укажите улицу:", reply_markup=ReplyKeyboardRemove())


@dp.message(TicketForm.street, F.text)
async def f_street(message: Message, state: FSMContext) -> None:
    street = message.text.strip()
    if not STREET_RE.match(street):
        await message.answer(
            "Похоже, это не название улицы. Введите ещё раз, например: Ленина"
        )
        return
    await state.update_data(street=street)
    await state.set_state(TicketForm.house)
    await message.answer("🏠 Номер дома (например, 12 или 12а):")


@dp.message(TicketForm.house, F.text)
async def f_house(message: Message, state: FSMContext) -> None:
    house = message.text.strip()
    if not HOUSE_RE.match(house):
        await message.answer("Номер дома должен начинаться с цифры, например «12» или «12а». Попробуйте ещё раз:")
        return
    data = await state.get_data()
    await message.answer("🔎 Проверяю адрес...")
    if not await geocode_check(data["street"], house):
        await message.answer(
            "❌ Такой адрес не нашёлся на карте. Проверьте улицу и номер дома.\n"
            "Введите номер дома ещё раз:"
        )
        return
    await state.update_data(house_number=house)
    await state.set_state(TicketForm.apartment)
    await message.answer("🚪 Номер квартиры (или «0» если не важно):")


@dp.message(TicketForm.apartment, F.text)
async def f_apartment(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if text != "–" and not text.isdigit():
        await message.answer("Введите номер квартиры цифрами или «0»:")
        return
    await state.update_data(apartment_number=text if text != "0" else None)
    await state.set_state(TicketForm.description)
    await message.answer("📋 Опишите проблему:")


@dp.message(TicketForm.description, F.text)
async def f_description(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    insert_ticket(
        table=data["table"],
        user_id=message.from_user.id,
        street=data["street"],
        house_number=data["house_number"],
        apartment_number=data.get("apartment_number"),
        description=message.text,
    )
    await state.clear()
    await message.answer("✅ Заявка принята!", reply_markup=main_menu())

@dp.message(TicketForm.description, F.text)
async def f_description(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    ticket_id = insert_ticket(
        table=data["table"],
        user_id=message.from_user.id,
        street=data["street"],
        house_number=data["house_number"],
        apartment_number=data.get("apartment_number"),
        description=message.text,
    )
    await state.clear()
    await message.answer(
        f"✅ Заявка №{ticket_id} зарегистрирована!\n"
        f"Отслеживать статус можно в разделе «🔎 Статус заявки».",
        reply_markup=main_menu(),
    )

@dp.message(TicketForm.street)
@dp.message(TicketForm.house)
@dp.message(TicketForm.apartment)
@dp.message(TicketForm.description)
async def not_text(message: Message) -> None:
    await message.answer("Пожалуйста, введите ответ текстом.")

@dp.error()
async def errors_handler(event: ErrorEvent) -> bool:
    logging.exception(
        "Ошибка при обработке апдейта: %s", event.exception,
        exc_info=event.exception,
    )
    message = event.update.message
    if message:
        await message.answer("⚠️ Произошла ошибка. Попробуйте ещё раз позже.")
    return True
@dp.message()
async def fallback(message: Message, state: FSMContext):
    await message.answer("Не понял вас. Выберите действие из меню:", reply_markup=main_menu())

async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
