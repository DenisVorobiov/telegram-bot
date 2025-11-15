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
CHAT_ID = -1003380446699  # <- основний чат/канал
# --------------------------

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
reaction_counts = {}     # callback -> int
reaction_users = {}      # callback -> set(user_id)
user_has_reacted = set() # set(user_id) — користувачі, які вже проголосували за поточний пост

# ====== Допоміжна функція для клавіатури ======
def create_keyboard(buttons_data, max_in_row=3):
    reaction_buttons = []
    url_buttons = []

    # Розділяємо кнопки
    for btn in buttons_data:
        if "url" in btn:
            url_buttons.append(InlineKeyboardButton(text=btn["text"], url=btn["url"]))
        else:
            cnt = reaction_counts.get(btn["callback"], 0)
            reaction_buttons.append(
                InlineKeyboardButton(text=f"{btn['text']} {cnt}", callback_data=btn["callback"])
            )

    inline_keyboard = []

    # ============================
    # URL кнопки — динамічне розміщення
    # ============================
    if url_buttons:
        # перша кнопка окремо
        inline_keyboard.append([url_buttons[0]])
        # решта по 2 на рядок
        for i in range(1, len(url_buttons), 2):
            inline_keyboard.append(url_buttons[i:i+2])

    # ============================
    # Callback кнопки
    # ============================
    for i in range(0, len(reaction_buttons), max_in_row):
        inline_keyboard.append(reaction_buttons[i:i+max_in_row])

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

# ====== Команди діагностики ======
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
    log.info("Started new /post flow, cleared reaction storages")

    await m.answer(
        "Введи THREAD_ID (число). Введи 0 щоб постити у основний канал (без гілки)."
    )
    await state.set_state(PostStates.waiting_for_thread)

# ====== THREAD_ID ======
@dp.message(PostStates.waiting_for_thread)
async def post_thread_input(m: types.Message, state: FSMContext):
    text = (m.text or "").strip()
    if not text.isdigit():
        await m.answer("Помилка: введи тільки число, наприклад: 0 або 4")
        return
    thread_id = int(text)
    await state.update_data(thread_id=thread_id)
    await m.answer(
        f"THREAD_ID збережено: {thread_id}\nТепер надішли текст посту (або медіа) → після тексту додаватимеш кнопки і /done."
    )
    await state.set_state(PostStates.waiting_for_text)

# ====== Текст або медіа ======
@dp.message(PostStates.waiting_for_text)
async def post_receive_text_or_media(m: types.Message, state: FSMContext):
    if m.photo:
        media = {"type": "photo", "file_id": m.photo[-1].file_id, "caption": m.caption or ""}
        await state.update_data(media=media, post_text="")
        await m.answer("Фото збережено. Тепер додавай кнопки або /done")
    elif m.video:
        media = {"type": "video", "file_id": m.video.file_id, "caption": m.caption or ""}
        await state.update_data(media=media, post_text="")
        await m.answer("Відео збережено. Тепер додавай кнопки або /done")
    elif m.document:
        media = {"type": "document", "file_id": m.document.file_id, "caption": m.caption or ""}
        await state.update_data(media=media, post_text="")
        await m.answer("Документ збережено. Тепер додавай кнопки або /done")
    else:
        # зберігаємо текст у HTML, щоб посилання залишались
        await state.update_data(post_text=m.text or "", media=None)
        await m.answer(
            "Текст збережено. Тепер додавай кнопки (формат: 'Текст URL' або 'Текст callback') або /done"
        )
    await state.set_state(PostStates.waiting_for_buttons)

# ====== Додавання кнопок / завершення ======
@dp.message(PostStates.waiting_for_buttons)
async def post_add_button_or_done(m: types.Message, state: FSMContext):
    data = await state.get_data()
    buttons = data.get("buttons") or []
    text = m.text or ""

    if text.strip() == "/done":
        post_text = data.get("post_text", "")
        media = data.get("media")
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
            log.info("Post published to chat_id=%s thread_id=%s", CHAT_ID, thread_id)
        except Exception as e:
            await m.answer(f"Помилка при відправці: {e}")
            log.exception("Send error")

        await state.clear()
        reaction_counts.clear()
        reaction_users.clear()
        user_has_reacted.clear()
        return

    # Розбираємо рядок як кнопку
    parts = text.strip().split(maxsplit=1)
    if not parts[0]:
        await m.answer("Невірний формат кнопки. Наприклад: 'Like like' або 'Go https://t.me'")
        return

    if len(parts) == 2 and parts[1].startswith("http"):
        btn = {"text": parts[0], "url": parts[1]}
    elif len(parts) == 2:
        btn = {"text": parts[0], "callback": parts[1]}
    else:
        btn = {"text": parts[0], "callback": parts[0]}

    buttons.append(btn)
    await state.update_data(buttons=buttons)
    await m.answer(f"Кнопка додана: {btn['text']} ({'url' if 'url' in btn else btn.get('callback')})")

# ====== Обробка callback ======
@dp.callback_query()
async def handle_reaction(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    key = cb.data

    if user_id in user_has_reacted:
        await cb.answer("Ти вже відреагував ❗", show_alert=True)
        return

    user_has_reacted.add(user_id)

    if key not in reaction_counts:
        reaction_counts[key] = 0
        reaction_users[key] = set()
    reaction_counts[key] += 1
    reaction_users[key].add(user_id)

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
