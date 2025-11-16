import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ======================
# ⚙ НАЛАШТУВАННЯ
# ======================
TOKEN = "8582965079:AAH4bz9IE0bRoyqsYlO2eriqgzE5jPpMCes"
CHAT_ID = -1002456737211  # твій основний чат

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ======================
# 📌 FSM стани
# ======================
class PostStates(StatesGroup):
    waiting_thread = State()
    waiting_media = State()
    waiting_text = State()
    waiting_buttons = State()

# ======================
# 🧩 Розміщення URL-кнопок (1,2,1,2…)
# ======================
def build_buttons(buttons):
    url_btns = [b for b in buttons if "url" in b]
    cb_btns = [b for b in buttons if "callback" in b]

    keyboard = []

    # --- Алгоритм для URL кнопок: 1,2,1,2… ---
    i = 0
    odd = True
    while i < len(url_btns):
        if odd:
            keyboard.append([InlineKeyboardButton(text=url_btns[i]["text"], url=url_btns[i]["url"])])
            i += 1
        else:
            keyboard.append([
                InlineKeyboardButton(text=url_btns[i]["text"], url=url_btns[i]["url"]),
                InlineKeyboardButton(text=url_btns[i + 1]["text"], url=url_btns[i + 1]["url"])
            ])
            i += 2
        odd = not odd

    # --- Callback кнопки (до 3 в ряд) ---
    for i in range(0, len(cb_btns), 3):
        row = []
        for b in cb_btns[i:i + 3]:
            row.append(InlineKeyboardButton(text=b["text"], callback_data=b["callback"]))
        keyboard.append(row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ======================
# 🔥 /post — запуск створення поста
# ======================
@dp.message(Command("post"))
async def start_post(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer("Введи THREAD_ID (0 = головний чат):")
    await state.set_state(PostStates.waiting_thread)


# ======================
# 🧵 THREAD_ID
# ======================
@dp.message(PostStates.waiting_thread)
async def set_thread(m: types.Message, state: FSMContext):
    if not m.text.isdigit():
        await m.answer("Введи число, наприклад 0 або 5.")
        return

    await state.update_data(thread_id=int(m.text))
    await m.answer("Тепер надішли МЕДІА або 0:")
    await state.set_state(PostStates.waiting_media)


# ======================
# 🖼 МЕДІА або 0
# ======================
@dp.message(PostStates.waiting_media)
async def set_media(m: types.Message, state: FSMContext):
    if m.text == "0":
        await state.update_data(media=None)
    else:
        media = None
        if m.photo:
            media = ("photo", m.photo[-1].file_id)
        elif m.video:
            media = ("video", m.video.file_id)
        elif m.document:
            media = ("document", m.document.file_id)

        if not media:
            await m.answer("Надішли МЕДІА або 0.")
            return

        await state.update_data(media=media)

    await m.answer("Тепер надішли ТЕКСТ або 0:")
    await state.set_state(PostStates.waiting_text)


# ======================
# 📝 ТЕКСТ або 0
# ======================
@dp.message(PostStates.waiting_text)
async def set_text(m: types.Message, state: FSMContext):
    if m.text == "0":
        await state.update_data(text="")
    else:
        await state.update_data(text=m.html_text)

    await state.update_data(buttons=[])
    await m.answer("Додавай кнопки (Формат: `Name URL` або `Name callback`) або /done")
    await state.set_state(PostStates.waiting_buttons)


# ======================
# 🔘 Додавання кнопок або публікація
# ======================
@dp.message(PostStates.waiting_buttons)
async def add_buttons(m: types.Message, state: FSMContext):
    data = await state.get_data()
    buttons = data["buttons"]

    if m.text == "/done":
        return await publish_post(m, state)

    parts = m.text.split(maxsplit=1)

    if len(parts) == 2 and parts[1].startswith("http"):
        buttons.append({"text": parts[0], "url": parts[1]})
    elif len(parts) == 2:
        buttons.append({"text": parts[0], "callback": parts[1]})
    else:
        await m.answer("Невірний формат. Приклад:\n`Like like`\n`Open https://t.me/...`")
        return

    await state.update_data(buttons=buttons)
    await m.answer("Кнопка додана!")


# ======================
# 🚀 Публікація поста
# ======================
async def publish_post(m: types.Message, state: FSMContext):
    data = await state.get_data()

    thread_id = data["thread_id"]
    media = data["media"]
    text = data["text"]
    buttons = data["buttons"]

    kb = build_buttons(buttons) if buttons else None

    kwargs = dict(
        chat_id=CHAT_ID,
        reply_markup=kb,
        parse_mode="HTML"
    )
    if thread_id != 0:
        kwargs["message_thread_id"] = thread_id

    # --- Відправка контенту ---
    if media:
        type_, file_id = media
        if type_ == "photo":
            await bot.send_photo(photo=file_id, caption=text, **kwargs)
        elif type_ == "video":
            await bot.send_video(video=file_id, caption=text, **kwargs)
        elif type_ == "document":
            await bot.send_document(document=file_id, caption=text, **kwargs)
    else:
        await bot.send_message(text=text, **kwargs)

    await m.answer("Пост опубліковано ✅")
    await state.clear()


# ======================
# ▶ Запуск бота
# ======================
async def main():
    log.info("Bot started.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
