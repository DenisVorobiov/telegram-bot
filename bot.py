import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ====== Налаштування ======
TOKEN = "8582965079:AAH4bz9IE0bRoyqsYlO2eriqgzE5jPpMCes"  # <- встав свій токен
CHAT_ID = -1002456737211  # <- основний чат/канал
# --------------------------

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ====== FSM стани ======
class PostStates(StatesGroup):
    waiting_for_thread = State()
    waiting_for_media = State()
    waiting_for_text = State()
    waiting_for_buttons = State()

# ====== Зберігання стану реакцій ======
reaction_counts = {}     # callback -> int
reaction_users = {}      # callback -> set(user_id)
user_has_reacted = set() # set(user_id)

# ====== Клавіатура ======
def create_keyboard(buttons_data):
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

    # URL кнопки динамічно: 1-2-1-2...
    i = 0
    while i < len(url_buttons):
        if i == 0:
            inline_keyboard.append([url_buttons[0]])
            i += 1
        else:
            inline_keyboard.append(url_buttons[i:i+2])
            i += 2

    # Callback кнопки
    for j in range(0, len(reaction_buttons), 3):
        inline_keyboard.append(reaction_buttons[j:j+3])

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

# ====== Команди ======
@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    await m.answer("Привіт! Бот живий. Використай /post щоб створити пост.")

@dp.message(Command("get_chat_id"))
async def get_chat_id(m: types.Message):
    await m.answer(f"CHAT_ID цього чату: {m.chat.id}")

@dp.message(Command("get_thread_id"))
async def get_thread_id(m: types.Message):
    if m.message_thread_id:
        await m.answer(f"THREAD_ID цієї теми: {m.message_thread_id}")
    else:
        await m.answer("Це повідомлення не в темі.")

# ====== Створення посту ======
@dp.message(Command("post"))
async def cmd_post_start(m: types.Message, state: FSMContext):
    await state.clear()
    reaction_counts.clear()
    reaction_users.clear()
    user_has_reacted.clear()
    await m.answer(
        "Введи THREAD_ID (число). Введи 0 щоб постити у основний чат."
    )
    await state.set_state(PostStates.waiting_for_thread)

# ====== THREAD_ID ======
@dp.message(PostStates.waiting_for_thread)
async def post_thread_input(m: types.Message, state: FSMContext):
    if not m.text.isdigit():
        await m.answer("Помилка: введи тільки число.")
        return
    thread_id = int(m.text)
    await state.update_data(thread_id=thread_id)
    await m.answer("Тепер надішли медіа (фото/відео/документ) або 0 якщо немає.")
    await state.set_state(PostStates.waiting_for_media)

# ====== Медiа ======
@dp.message(PostStates.waiting_for_media)
async def post_media_input(m: types.Message, state: FSMContext):
    if m.text == "0":
        await state.update_data(media=None)
    elif m.photo:
        await state.update_data(media=("photo", m.photo[-1].file_id))
    elif m.video:
        await state.update_data(media=("video", m.video.file_id))
    elif m.document:
        await state.update_data(media=("document", m.document.file_id))
    else:
        await m.answer("Невірний формат. Надішли фото, відео, документ або 0")
        return

    await m.answer("Тепер надішли текст або 0 якщо немає.")
    await state.set_state(PostStates.waiting_for_text)

# ====== Текст ======
@dp.message(PostStates.waiting_for_text)
async def post_text_input(m: types.Message, state: FSMContext):
    if m.text == "0":
        await state.update_data(text="")
    else:
        await state.update_data(text=m.text or "")
    await m.answer("Тепер додай кнопки (Текст URL або Текст callback) або надішли /done")
    await state.set_state(PostStates.waiting_for_buttons)

# ====== Кнопки / Відправка ======
@dp.message(PostStates.waiting_for_buttons)
async def post_buttons_input(m: types.Message, state: FSMContext):
    data = await state.get_data()
    buttons = data.get("buttons") or []

    if m.text == "/done":
        thread_id = data.get("thread_id", 0)
        media = data.get("media")
        text = data.get("text", "")
        kb = create_keyboard(buttons) if buttons else None

        kwargs = dict(chat_id=CHAT_ID, parse_mode="HTML", reply_markup=kb)
        if thread_id != 0:
            kwargs["message_thread_id"] = thread_id

        try:
            if media:
                type_, file_id = media
                if type_ == "photo":
                    await bot.send_photo(photo=file_id, caption=text or " ", **kwargs)
                elif type_ == "video":
                    await bot.send_video(video=file_id, caption=text or " ", **kwargs)
                elif type_ == "document":
                    await bot.send_document(document=file_id, caption=text or " ", **kwargs)
            else:
                await bot.send_message(text=text or " ", **kwargs)
            await m.answer("Пост опубліковано ✅")
        except Exception as e:
            await m.answer(f"Помилка при відправці: {e}")
            log.exception("Send error")

        await state.clear()
        reaction_counts.clear()
        reaction_users.clear()
        user_has_reacted.clear()
        return

    # Додаємо кнопку
    parts = m.text.strip().split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("http"):
        btn = {"text": parts[0], "url": parts[1]}
    elif len(parts) == 2:
        btn = {"text": parts[0], "callback": parts[1]}
    else:
        btn = {"text": parts[0], "callback": parts[0]}
    buttons.append(btn)
    await state.update_data(buttons=buttons)
    await m.answer(f"Кнопка додана: {btn['text']} ({'URL' if 'url' in btn else btn.get('callback')})")

# ====== Callback ======
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
    await cb.answer("Ти відреагував ✅")

# ====== Запуск ======
async def main():
    log.info("Bot starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        log.exception("Fatal")
