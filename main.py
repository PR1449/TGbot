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


async def _geocode(query: str) -> tuple[dict | None, str | None]:
    params = {
        "apikey": YANDEX_GEOCODER_KEY,
        "geocode": query,
        "format": "json",
        "results": 1,
        "lang": "ru_RU",
    }
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession() as session:
            async with session.get(GEOCODER_URL, params=params, timeout=timeout) as resp:
                if resp.status != 200:
                    logging.warning("Геокодер вернул статус %s", resp.status)
                    return None, None
                data = await resp.json()

        collection = data.get("response", {}).get("GeoObjectCollection", {})
        meta = collection.get("metaDataProperty", {}).get("GeocoderResponseMetaData", {})
        suggestion = meta.get("suggest")
        logging.info(
            "Геокодер: запрос=%s, найдено=%s, suggest=%s",
            query, meta.get("found"), suggestion,
        )
        return data, suggestion
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logging.exception("Ошибка сети при геокодировании: %s", e)
        return None, None


def _street_from_suggestion(suggestion: str) -> str:
    parts = suggestion.split(", ")
    return parts[-1] if len(parts) > 1 else suggestion


async def check_street(street: str) -> tuple[str, str | None, str | None]:
    data, suggestion = await _geocode(f"{CITY}, {street}")
    if data is None:
        return "network_error", None, None
    features = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
    if not features:
        return "street_error", suggestion, None

    geo = features[0].get("GeoObject", {})
    real_street = geo.get("name", "")
    return "ok", suggestion, real_street


async def check_house(street: str, house: str) -> tuple[str, str | None]:
    data, suggestion = await _geocode(f"{CITY}, {street}, {house}")
    if data is None:
        return "network_error", None
    features = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
    if not features:
        return "house_error", suggestion

    meta = features[0].get("GeoObject", {}).get("metaDataProperty", {}).get("GeocoderMetaData", {})
    precision = meta.get("precision")
    logging.info("Геокодер: precision=%s, адрес=%s", precision, meta.get("text"))
    return ("ok", None) if precision in GOOD_PRECISION else ("house_error", suggestion)


class TicketForm(StatesGroup):
    street = State()
    street_suggest = State()
    house = State()
    house_suggest = State()
    apartment = State()
    description = State()
    summary = State()
    edit_choice = State()


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


def yes_no_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет"))
    return builder.as_markup(resize_keyboard=True)


def summary_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="✅ Всё верно"), KeyboardButton(text="✏️ Исправить"))
    return builder.as_markup(resize_keyboard=True)


def edit_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📍 Улица"))
    builder.row(KeyboardButton(text="🏠 Дом"))
    builder.row(KeyboardButton(text="🚪 Квартира"))
    builder.row(KeyboardButton(text="📋 Описание"))
    builder.row(KeyboardButton(text="⬅️ В меню"))
    return builder.as_markup(resize_keyboard=True)


def summary_text(data: dict) -> str:
    apartment = data.get("apartment_number") or "не указана"
    category = CATEGORY_NAMES.get(data["table"], data["table"])
    return (
        "📋 Проверьте заявку целиком:\n\n"
        f"🗂 Категория: {category}\n"
        f"📍 Улица: {data['street']}\n"
        f"🏠 Дом: {data['house_number']}\n"
        f"🚪 Квартира: {apartment}\n"
        f"📝 Описание: {data['description']}"
    )


async def go_summary(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(TicketForm.summary)
    await message.answer(summary_text(data) + "\n\nВсё верно?", reply_markup=summary_menu())


async def after_street_confirmed(message: Message, state: FSMContext, street: str) -> None:
    data = await state.get_data()
    await state.update_data(street=street)

    if data.get("editing"):
        house = data.get("house_number")
        if house:
            status, _ = await check_house(street, house)
            if status == "ok":
                await go_summary(message, state)
                return
            await state.update_data(house_number=None)
            await state.set_state(TicketForm.house)
            await message.answer(
                "🏠 Так как улица изменилась, прежний дом больше не подходит.\n"
                "Введите номер дома (например, 12 или 12а):",
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        await state.set_state(TicketForm.house)
        await message.answer("🏠 Номер дома (например, 12 или 12а):")
        return

    await state.set_state(TicketForm.house)
    await message.answer("🏠 Номер дома (например, 12 или 12а):")


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
    await state.clear()
    await message.answer("Пожалуйста, выберите категорию:", reply_markup=application_menu())


@dp.message(F.text == "🔎 Статус заявки")
async def show_status(message: Message) -> None:
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
        await message.answer("Похоже, это не название улицы. Введите ещё раз, например: Ленина")
        return

    await message.answer("🔎 Проверяю улицу...")
    status, suggestion, real_street = await check_street(street)

    if status == "network_error":
        await message.answer("⚠️ Сервис проверки адресов не отвечает. Попробуйте ещё раз позже:")
        return

    if status == "street_error":
        if suggestion:
            fixed = _street_from_suggestion(suggestion)
            await state.update_data(street=street, suggestion=fixed)
            await state.set_state(TicketForm.street_suggest)
            await message.answer(
                f"❓ Вы написали «{street}». Возможно, вы имели в виду:\n"
                f"📍 «{fixed}»\n\nПодтверждаете?",
                reply_markup=yes_no_menu(),
            )
        else:
            await message.answer("❌ Такая улица не нашлась на карте. Проверьте название и введите ещё раз:")
        return

    if real_street:
        clean_real = re.sub(
            r'^(улица|проспект|бульвар|набережная|шоссе|перевалок|перекрёсток)\s+',
            '', real_street, flags=re.IGNORECASE
        ).strip()
        if clean_real.lower() != street.lower():
            await state.update_data(street=street, suggestion=clean_real)
            await state.set_state(TicketForm.street_suggest)
            await message.answer(
                f"❓ Вы написали «{street}». Найдено с исправлением:\n"
                f"📍 «{clean_real}»\n\nПодтверждаете?",
                reply_markup=yes_no_menu(),
            )
            return

    await after_street_confirmed(message, state, street)


@dp.message(TicketForm.street_suggest)
async def f_street_suggest(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    data = await state.get_data()

    if text == "✅ Да":
        await after_street_confirmed(message, state, data["suggestion"])
        return

    if text == "❌ Нет":
        await state.set_state(TicketForm.street)
        await message.answer("📍 Введите название улицы ещё раз:", reply_markup=ReplyKeyboardRemove())
        return

    await message.answer("Выберите «✅ Да» или «❌ Нет»:")


@dp.message(TicketForm.house, F.text)
async def f_house(message: Message, state: FSMContext) -> None:
    house = message.text.strip()
    if not HOUSE_RE.match(house):
        await message.answer("Номер дома должен начинаться с цифры, например «12» или «12а». Попробуйте ещё раз:")
        return

    data = await state.get_data()
    await message.answer("🔎 Проверяю адрес...")
    status, suggestion = await check_house(data["street"], house)

    if status == "network_error":
        await message.answer("⚠️ Сервис проверки адресов не отвечает. Попробуйте ещё раз позже:")
        return

    if status == "house_error":
        if suggestion:
            await state.update_data(house_number=house, suggestion=suggestion)
            await state.set_state(TicketForm.house_suggest)
            await message.answer(
                f"❓ Дом не нашёлся. Возможно, имелся в виду адрес:\n📍 «{suggestion}»\n\nПодтверждаете?",
                reply_markup=yes_no_menu(),
            )
        else:
            await message.answer("❌ Такой дом на этой улице не нашёлся. Введите номер дома ещё раз:")
        return

    await after_house_confirmed(message, state, house)


@dp.message(TicketForm.house_suggest)
async def f_house_suggest(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    data = await state.get_data()

    if text == "✅ Да":
        house = data["suggestion"].split(", ")[-1]
        await after_house_confirmed(message, state, house)
        return

    if text == "❌ Нет":
        await state.set_state(TicketForm.house)
        await message.answer("🏠 Введите номер дома ещё раз:", reply_markup=ReplyKeyboardRemove())
        return

    await message.answer("Выберите «✅ Да» или «❌ Нет»:")


async def after_house_confirmed(message: Message, state: FSMContext, house: str) -> None:
    data = await state.get_data()
    await state.update_data(house_number=house)

    if data.get("editing"):
        await go_summary(message, state)
        return

    await state.set_state(TicketForm.apartment)
    await message.answer("🚪 Номер квартиры (или «0» если не важно):")


@dp.message(TicketForm.apartment, F.text)
async def f_apartment(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if text != "0" and not text.isdigit():
        await message.answer("Введите номер квартиры цифрами или «0»:")
        return
    await state.update_data(apartment_number=text if text != "0" else None)

    data = await state.get_data()
    if data.get("editing"):
        await go_summary(message, state)
        return

    await state.set_state(TicketForm.description)
    await message.answer("📋 Опишите проблему:")


@dp.message(TicketForm.description, F.text)
async def f_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text)

    data = await state.get_data()
    if data.get("editing"):
        await go_summary(message, state)
        return

    await go_summary(message, state)


@dp.message(TicketForm.summary)
async def f_summary(message: Message, state: FSMContext) -> None:
    text = message.text.strip()

    if text == "✅ Всё верно":
        data = await state.get_data()
        ticket_id = insert_ticket(
            table=data["table"],
            user_id=message.from_user.id,
            street=data["street"],
            house_number=data["house_number"],
            apartment_number=data.get("apartment_number"),
            description=data["description"],
        )
        await state.clear()
        await message.answer(
            f"✅ Заявка №{ticket_id} зарегистрирована!\n"
            f"Отслеживать статус можно в разделе «🔎 Статус заявки».",
            reply_markup=main_menu(),
        )
        return

    if text == "✏️ Исправить":
        await state.set_state(TicketForm.edit_choice)
        await message.answer("Что исправляем?", reply_markup=edit_menu())
        return

    await message.answer("Выберите «✅ Всё верно» или «✏️ Исправить»:")


@dp.message(TicketForm.edit_choice, F.text)
async def f_edit_choice(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    await state.update_data(editing=True)

    if text == "📍 Улица":
        await state.set_state(TicketForm.street)
        await message.answer("📍 Введите улицу заново:", reply_markup=ReplyKeyboardRemove())
        return
    if text == "🏠 Дом":
        await state.set_state(TicketForm.house)
        await message.answer("🏠 Введите номер дома заново:", reply_markup=ReplyKeyboardRemove())
        return
    if text == "🚪 Квартира":
        await state.set_state(TicketForm.apartment)
        await message.answer("🚪 Введите номер квартиры (или «0»):", reply_markup=ReplyKeyboardRemove())
        return
    if text == "📋 Описание":
        await state.set_state(TicketForm.description)
        await message.answer("📋 Опишите проблему заново:", reply_markup=ReplyKeyboardRemove())
        return
    if text == "⬅️ В меню":
        await state.clear()
        await message.answer("Вы в главном меню. Выберите действие:", reply_markup=main_menu())
        return

    await message.answer("Выберите, что исправить, кнопкой из списка:", reply_markup=edit_menu())


@dp.message(TicketForm.street)
@dp.message(TicketForm.street_suggest)
@dp.message(TicketForm.house)
@dp.message(TicketForm.house_suggest)
@dp.message(TicketForm.apartment)
@dp.message(TicketForm.description)
@dp.message(TicketForm.summary)
@dp.message(TicketForm.edit_choice)
async def not_text(message: Message) -> None:
    await message.answer("Пожалуйста, используйте кнопки или введите текст.")


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
async def fallback(message: Message):
    await message.answer("Не понял вас. Выберите действие из меню:", reply_markup=main_menu())


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
