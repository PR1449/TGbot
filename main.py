from secret_keys import BOT_TOKEN
from db import init_db, insert_billing  

import asyncio
import logging
import sqlite3  

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove


dp = Dispatcher()

class BillingForm(StatesGroup):
    street      = State()
    house       = State()
    apartment   = State()
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
    await message.answer('''Привет! Я ТеплоБот. Помогаю подать заявку в управляющую компанию 
    и отследить её статус без звонков в диспетчерскую.\n\n Выберите действие:''', reply_markup=main_menu())

@dp.message(F.text == "⬅️ В меню")
async def back_to_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Вы в главном меню. Выберите действие:", reply_markup=main_menu())


@dp.message(F.text == "📝 Подать заявку/Задать вопрос")
async def start_ticket(message: Message, state: FSMContext) -> None:
    await message.answer('''Пожалуйста, выберите категорию''', reply_markup=application_menu())

@dp.message(F.text == "🔎 Статус заявки")
async def show_status(message: Message, state: FSMContext) -> None:
    await message.answer("Раздел '🔎 Статус заявки' в разработке, пожалуйста выберите другую опцию", reply_markup=main_menu())

@dp.message(F.text == "ℹ️ О боте")
async def about(message: Message) -> None:
    await message.answer("ТеплоБот v0.1", reply_markup=main_menu())

@dp.message(F.text == "🔧 Коммунальные услуги и их перебои")
async def show_status(message: Message, state: FSMContext) -> None:
    await message.answer("Раздел '🔎🔧 Коммунальные услуги и их перебои' в разработке, пожалуйста выберите другую опцию", reply_markup=main_menu())

@dp.message(F.text == "📄 Вопросы по квитанциям и начислениям")
async def billing_start(message: Message, state: FSMContext) -> None:
    await BillingForm.street.set()
    await message.answer("📍 Укажите улицу:", reply_markup=ReplyKeyboardRemove())

@dp.message(BillingForm.street)
async def f_street(message: Message, state: FSMContext) -> None:
    await state.update_data(street=message.text)
    await BillingForm.house.set()
    await message.answer("🏠 Номер дома?")

@dp.message(BillingForm.house)
async def f_house(message: Message, state: FSMContext) -> None:
    await state.update_data(house_number=message.text)
    await BillingForm.apartment.set()
    await message.answer("🚪 Номер квартиры (или «–» если не важно):")

@dp.message(BillingForm.apartment)
async def f_apartment(message: Message, state: FSMContext) -> None:
    await state.update_data(apartment_number=message.text if message.text != "–" else None)
    await BillingForm.description.set()
    await message.answer("📋 Опишите вопрос по квитанции / начислениям:")

@dp.message(BillingForm.description)
async def f_description(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    insert_billing(
        street=data["street"],
        house_number=data["house_number"],
        apartment_number=data.get("apartment_number"),
        description=message.text,
    )
    await state.clear()
    await message.answer(
        "✅ Вопрос по квитанции принят! Мы передадим его в управляющую компанию.",
        reply_markup=main_menu(),
    )   

@dp.message(F.text == "🚨 Аварийные ситуации")
async def show_status(message: Message, state: FSMContext) -> None:
    await message.answer("Раздел '🚨 Аварийные ситуации' в разработке, пожалуйста выберите другую опцию", reply_markup=main_menu())


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
