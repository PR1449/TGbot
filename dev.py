from secret_keys import BOT_TOKEN

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext


dp = Dispatcher()

def main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📝 Подать заявку"))
    builder.row(KeyboardButton(text="🔎 Статус заявки"))
    builder.row(KeyboardButton(text="ℹ️ О боте"))
    return builder.as_markup(resize_keyboard=True)

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer('''Привет! Я бот ЖКУ-контроль. Помогаю подать заявку в управляющую компанию 
    и отследить её статус без звонков в диспетчерскую.\n\n Выберите действие:''', reply_markup=main_menu())

@dp.message(F.text == "📝 Подать заявку")
async def start_ticket(message: Message, state: FSMContext) -> None:
    await message.answer('''Раздел "📝 Подать заявку" находится в разработке, пожалуйста выберите другую опцию''', reply_markup=main_menu())

@dp.message(F.text == "🔎 Статус заявки")
async def show_status(message: Message, state: FSMContext) -> None:
    await message.answer("Раздел в разработке", reply_markup=main_menu())

@dp.message(F.text == "ℹ️ О боте")
async def about(message: Message) -> None:
    await message.answer("Бот ЖКУ-контроль v0.1", reply_markup=main_menu())   

async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
