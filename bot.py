import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ====== Налаштування ======
TOKEN = "8582965079:AAH4bz9IE0bRoyqsYlO2eriqgzE5jPpMCes"               # <- встав свій токен
CHAT_ID = -1003380446699               # <- основний чат/канал

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ====== FSM стани ======
class PostStates(StatesGroup):
    waiting_for_thread = State()
    waiting_for_text = State()
    waiting_for_buttons = State()

# ====== Зберігання стану реакцій ======
reaction_counts = {}
reaction_users = {}
user_has_reacted = set()

# ====== Функція клавіатури ======
def create_keyboard(buttons_data, max_in_row=3):
    reaction_buttons = []
    url_buttons = []

    for btn in buttons_data:
        if "url" in btn:
            url_buttons.append(InlineKeyboardButton(text=btn["text"], url=btn["url"]))
        else:
            cnt = reaction_counts.get(btn["callback"], 0)
            reaction_buttons.append(
                InlineKeyboardButton(text=f"{btn['text']} {cnt}", callback_data=btn["callback"])
            )

    inline_keyboard = []
    for i in range(0, len(reaction_buttons), max_in_row):
        inline_keyboard.append(reaction_buttons[i:i+max_in_row])
    for i in range(0, len(url_buttons), max_in_row):
        inline_keyboard.append(url_buttons[i:i+max_in_row])

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

# ====== Команди ======
@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    await m.answer("Привіт! Використай /post щоб створити пост.")

@dp.message(Command("get_chat_id"))
async def get_chat_id(m: types.Message):
    await m.answer(f"CHAT_ID цього чату: {m.chat.id}")

@dp.message(Command("get_thread_id"))
async def get_thread_id(m: types.Message):
    if m.message_thread_id:
        await m.answer(f"THREAD_ID цієї теми: {m.message_thread_id}")
    else:
        await m.answer("Це повідомлення не в темі.")

# ====== Створення поста ======
@dp.message(Command("post"))
async def cmd_post_start(m: types.Message, state: FSMContext):
    await state.clear()
    reaction_counts.clear()
    reaction_users.clear()
    user_has_reacted.clear()
    await m.answer("Введи THREAD_ID (число). Введи 0 для основного каналу.")
    await state.set_state(PostStates.waiting_for_thread)

@dp.message(PostStates.waiting_for_thread)
async def post_thread_input(m: types.Message, state: FSMContext):
    if not m.text.isdigit():
        await m.answer("Помилка: введи число.")
        return
    thread_id = int(m.text)
    await state.update_data(thread_id=thread_id)
    await m.answer("Тепер надішли текст або медіа для посту.")
    await state.set_state(PostStates.waiting_for_text)

@dp.message(PostStates.waiting_for_text)
async def post_receive_text_or_media(m: types.Message, state: FSMContext):
    media = None
    post_text = ""
    if m.photo:
        media = {"type": "photo", "file_id": m.photo[-1].file_id}
        post_text = m.caption or ""
    elif m.video:
        media = {"type": "video", "file_id": m.video.file_id}
        post_text = m.caption or ""
    elif m.document:
        media = {"type": "document", "file_id": m.document.file_id}
        post_text = m.caption or ""
    else:
        post_text = m.text or ""

    await state.update_data(media=media, post_text=post_text)
    await m.answer("Контент збережено. Додавай кнопки або надішли /done")
    await state.set_state(PostStates.waiting_for_buttons)

@dp.message(PostStates.waiting_for_buttons)
async def post_add_button_or_done(m: types.Message, state: FSMContext):
    data = await state.get_data()
    buttons = data.get("buttons") or []
    text = m.text or ""

    if text.strip() == "/done":
        media = data.get("media")
        post_text = data.get("post_text", "")
        thread_id = data.get("thread_id", 0)
        keyboard = create_keyboard(buttons) if buttons else None

        try:
            if media:
                if media["type"] == "photo":
                    await bot.send_photo(
                        chat_id=CHAT_ID,
                        photo=media["file_id"],
                        caption=post_text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        message_thread_id=thread_id if thread_id != 0 else None
                    )
                elif media["type"] == "video":
                    await bot.send_video(
                        chat_id=CHAT_ID,
                        video=media["file_id"],
                        caption=post_text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        message_thread_id=thread_id if thread_id != 0 else None
                    )
                elif media["type"] == "document":
                    await bot.send_document(
                        chat_id=CHAT_ID,
                        document=media["file_id"],
                        caption=post_text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        message_thread_id=thread_id if thread_id != 0 else None
                    )
            else:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text=post_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    message_thread_id=thread_id if thread_id != 0 else None
                )

            await m.answer("Пост опубліковано ✅")
        except Exception as e:
            await m.answer(f"Помилка при відправці: {e}")
            log.exception("Send error")

        await state.clear()
        reaction_counts.clear()
        reaction_users.clear()
        user_has_reacted.clear()
        return

    # Додаємо кнопки
    parts = text.strip().split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("http"):
        btn = {"text": parts[0], "url": parts[1]}
    elif len(parts) == 2:
        btn = {"text": parts[0], "callback": parts[1]}
    else:
        btn = {"text": parts[0], "callback": parts[0]}
    buttons.append(btn)
    await state.update_data(buttons=buttons)
    await m.answer(f"Кнопка додана: {btn['text']}")

@dp.callback_query()
async def handle_reaction(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    key = cb.data

    if user_id in user_has_reacted:
        await cb.answer("Ти вже відреагував ❗", show_alert=True)
        return

    user_has_reacted.add(user_id)
    reaction_counts[key] = reaction_counts.get(key, 0) + 1
    reaction_users.setdefault(key, set()).add(user_id)

    # Оновлюємо клавіатуру
    old_buttons = []
    if cb.message.reply_markup and cb.message.reply_markup.inline_keyboard:
        for row in cb.message.reply_markup.inline_keyboard:
            for b in row:
                if getattr(b, "callback_data", None):
                    old_buttons.append({"text": b.text.split()[0], "callback": b.callback_data})
                elif getattr(b, "url", None):
                    old_buttons.append({"text": b.text, "url": b.url})

    new_kb = create_keyboard(old_buttons)
    try:
        await cb.message.edit_reply_markup(reply_markup=new_kb)
    except Exception:
        log.exception("Failed to edit reply_markup")

    await cb.answer("Відреаговано ✅")

async def main():
    log.info("Bot starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        log.exception("Fatal")
