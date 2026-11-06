"""
Telegram-бот «Заң және табиғат» / «Закон и природа»
Двуязычный (қазақша / русский). Принимает сигналы граждан и пересылает
их напрямую в закрытый чат прокурора (а не в общий чат органов).

Запуск:
    pip install aiogram==3.*
    export BOT_TOKEN="токен от @BotFather"
    export PROSECUTOR_CHAT_ID="-100xxxxxxxxxx"   # id закрытой группы прокурора
    python zan_tabigat_bot.py

Чтобы узнать id группы: добавьте бота в группу и отправьте там /chatid
"""
import asyncio
import logging
import os
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
PROSECUTOR_CHAT_ID = int(os.environ.get("PROSECUTOR_CHAT_ID", "0"))
DB_PATH = os.environ.get("DB_PATH", "signals.db")
# Необязательно: id людей, которым разрешено нажимать кнопки статуса
# (через запятую). Если не задано — кнопки доступны всем в чате прокурора.
ALLOWED_IDS = {
    int(x) for x in os.environ.get("PROSECUTOR_IDS", "").replace(" ", "").split(",") if x
}

# ---------------------------------------------------------------- тексты
T = {
    "kk": {
        "choose_lang": "Тілді таңдаңыз / Выберите язык:",
        "welcome": (
            "🌿 <b>Заң және табиғат</b>\n"
            "Экологиялық құқық бұзушылықтарды жедел анықтау және болдырмау "
            "жөніндегі прокурорлық тетік.\n\n"
            "Сигнал тікелей прокурорға түседі. Құпия, жылдам, тиімді.\n\n"
            "Мәзірден таңдаңыз 👇"
        ),
        "btn_send": "📨 Сигнал жіберу",
        "btn_about": "ℹ️ Жоба туралы",
        "btn_how": "⚙️ Қалай жұмыс істейді?",
        "btn_lang": "🌐 Тіл / Язык",
        "btn_done": "✅ Жіберу",
        "btn_cancel": "❌ Бас тарту",
        "btn_location": "📍 Геолокация жіберу",
        "about": (
            "🎯 <b>Жоба мақсаты</b>\n"
            "Азаматтар мен СҚО маманданған табиғат қорғау прокуратурасы "
            "арасында тікелей байланыс арнасын құру: табиғат қорғау "
            "заңнамасын ықтимал бұзу туралы сигналдарды жедел алу және "
            "прокурорлық ден қою шараларын қабылдау.\n\n"
            "⭐ <b>Негізгі ерекшелік — «изюминка»</b>\n"
            "• Сигнал алғашында уәкілетті органдардың жалпы чатына емес, "
            "тікелей прокурорға түседі.\n"
            "• Прокурор алғашқы бағалауды жүргізіп, тексеру тәртібін "
            "анықтайды.\n"
            "• Бағалаудан кейін одан әрі шешім қабылданады."
        ),
        "how": (
            "⚙️ <b>Қалай жұмыс істейді?</b>\n\n"
            "1️⃣ Азаматтан сигнал (фото, видео, геолокация, қысқаша сипаттама)\n"
            "2️⃣ Прокурордың сигналды алуы — басқа органдарға автоматты "
            "берусіз\n"
            "3️⃣ Алғашқы бағалау және тексеру\n"
            "4️⃣ Ден қою — қажет болса құзыретті органдар қосылады\n"
            "5️⃣ Нәтижені бақылау"
        ),
        "choose_cat": "Құқық бұзушылық түрін таңдаңыз:",
        "collect": (
            "Енді мынаны жіберіңіз:\n"
            "• фото / видео\n"
            "• 📍 геолокация (төмендегі батырма)\n"
            "• қысқаша сипаттама (қайда, не болды, қашан)\n\n"
            "Бәрін жіберген соң <b>«✅ Жіберу»</b> батырмасын басыңыз."
        ),
        "empty": "Алдымен кемінде бір хабарлама (фото, видео, мәтін немесе геолокация) жіберіңіз.",
        "accepted": (
            "✅ Сигнал қабылданды. Нөмірі: <b>№{id}</b>\n"
            "Ол тікелей прокурорға жіберілді. Рақмет, табиғатты бірге сақтаймыз! 🌲"
        ),
        "cancelled": "Бас тартылды. Мәзірге оралдыңыз.",
        "added": "Қосылды ✔️ Тағы жібере аласыз немесе «✅ Жіберу» басыңыз.",
        "send_failed": "⚠️ Қате орын алды, кейінірек қайталап көріңіз.",
        "notify": {
            "taken": "🔔 №{id} сигналыңыз бойынша прокурор қарауға кірісті.",
            "checked": "🔎 №{id} сигналыңызды прокурор тексерді. Өтініш үшін рақмет!",
            "rejected": (
                "ℹ️ №{id} сигнал бойынша тексеру аяқталды: көрсетілген "
                "фактілер расталмады. Сақтығыңыз үшін рақмет."
            ),
            "done": (
                "✅ №{id} сигналыңыз бойынша прокурорлық ден қою шаралары "
                "қабылданды. Табиғатты сақтағаныңыз үшін рақмет! 🌲"
            ),
        },
        "cats": {
            "logging": "🌲 Заңсыз ағаш кесу",
            "hunting": "🦌 Заңсыз аң аулау",
            "mining": "⛏ Жер қойнауын өздігінен пайдалану",
            "fishing": "🐟 Заңсыз балық аулау",
            "air": "🏭 Атмосфералық ауаны ластау",
            "water": "💧 Су объектілерін ластау",
            "land": "🌍 Жерді бүлдіру",
        },
    },
    "ru": {
        "choose_lang": "Тілді таңдаңыз / Выберите язык:",
        "welcome": (
            "🌿 <b>Закон и природа</b>\n"
            "Прокурорский механизм оперативного выявления и предупреждения "
            "экологических правонарушений.\n\n"
            "Сигнал поступает напрямую прокурору. Быстро, конфиденциально, "
            "эффективно.\n\n"
            "Выберите действие в меню 👇"
        ),
        "btn_send": "📨 Отправить сигнал",
        "btn_about": "ℹ️ О проекте",
        "btn_how": "⚙️ Как это работает?",
        "btn_lang": "🌐 Тіл / Язык",
        "btn_done": "✅ Отправить",
        "btn_cancel": "❌ Отмена",
        "btn_location": "📍 Отправить геолокацию",
        "about": (
            "🎯 <b>Цель проекта</b>\n"
            "Создание прямого канала связи граждан со специализированной "
            "природоохранной прокуратурой СКО для оперативного получения "
            "сигналов о возможных нарушениях природоохранного "
            "законодательства и принятия мер прокурорского реагирования.\n\n"
            "⭐ <b>Ключевая особенность — «изюминка»</b>\n"
            "• Сигнал первоначально поступает непосредственно прокурору, "
            "а не в общий чат уполномоченных органов.\n"
            "• Прокурор проводит первичную оценку информации, определяет "
            "порядок проверки.\n"
            "• После оценки принимается решение о дальнейшем порядке "
            "реагирования и контроле результатов."
        ),
        "how": (
            "⚙️ <b>Как работает проект?</b>\n\n"
            "1️⃣ Сигнал от гражданина (фото, видео, геолокация, краткое описание)\n"
            "2️⃣ Получение сигнала прокурором — без автоматической передачи "
            "в другие органы\n"
            "3️⃣ Первичная оценка и проверка\n"
            "4️⃣ Реагирование — при необходимости подключаются компетентные "
            "органы\n"
            "5️⃣ Контроль результата"
        ),
        "choose_cat": "Выберите вид нарушения:",
        "collect": (
            "Теперь отправьте:\n"
            "• фото / видео\n"
            "• 📍 геолокацию (кнопка ниже)\n"
            "• краткое описание (где, что произошло, когда)\n\n"
            "Когда всё отправили, нажмите <b>«✅ Отправить»</b>."
        ),
        "empty": "Сначала отправьте хотя бы одно сообщение (фото, видео, текст или геолокацию).",
        "accepted": (
            "✅ Сигнал принят. Номер: <b>№{id}</b>\n"
            "Он направлен непосредственно прокурору. Спасибо, вместе сохраним природу! 🌲"
        ),
        "cancelled": "Отменено. Вы в главном меню.",
        "added": "Добавлено ✔️ Можете отправить ещё или нажать «✅ Отправить».",
        "send_failed": "⚠️ Произошла ошибка, попробуйте позже.",
        "notify": {
            "taken": "🔔 По вашему сигналу №{id} прокурор приступил к рассмотрению.",
            "checked": "🔎 Ваш сигнал №{id} проверен прокурором. Спасибо за обращение!",
            "rejected": (
                "ℹ️ По сигналу №{id} проверка завершена: изложенные факты "
                "не подтвердились. Спасибо за бдительность."
            ),
            "done": (
                "✅ По вашему сигналу №{id} приняты меры прокурорского "
                "реагирования. Спасибо, что сохраняете природу! 🌲"
            ),
        },
        "cats": {
            "logging": "🌲 Незаконная рубка деревьев",
            "hunting": "🦌 Незаконная охота",
            "mining": "⛏ Самовольное пользование недрами",
            "fishing": "🐟 Незаконная рыбалка",
            "air": "🏭 Загрязнение атмосферного воздуха",
            "water": "💧 Загрязнение водных объектов",
            "land": "🌍 Порча земли",
        },
    },
}

# ---------------------------------------------------------------- база
db = sqlite3.connect(DB_PATH)
db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, lang TEXT)")
db.execute(
    """CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, category TEXT, created TEXT, items INTEGER)"""
)
# Колонки статуса (для старых баз добавляются автоматически)
for _col in ("status", "handled_by", "handled_at"):
    try:
        db.execute(f"ALTER TABLE signals ADD COLUMN {_col} TEXT")
    except sqlite3.OperationalError:
        pass
db.commit()


def get_lang(user_id: int) -> str:
    row = db.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)).fetchone()
    return row[0] if row else "ru"


def set_lang(user_id: int, lang: str) -> None:
    db.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", (user_id, lang))
    db.commit()


# ---------------------------------------------------------------- клавиатуры
def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🇰🇿 Қазақша", callback_data="lang:kk"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
        ]]
    )


def menu_kb(lang: str) -> ReplyKeyboardMarkup:
    t = T[lang]
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t["btn_send"])],
            [KeyboardButton(text=t["btn_about"]), KeyboardButton(text=t["btn_how"])],
            [KeyboardButton(text=t["btn_lang"])],
        ],
        resize_keyboard=True,
    )


def cats_kb(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"cat:{key}")]
        for key, name in T[lang]["cats"].items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def collect_kb(lang: str) -> ReplyKeyboardMarkup:
    t = T[lang]
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t["btn_location"], request_location=True)],
            [KeyboardButton(text=t["btn_done"]), KeyboardButton(text=t["btn_cancel"])],
        ],
        resize_keyboard=True,
    )


def both(key: str) -> set:
    return {T["kk"][key], T["ru"][key]}


# ---------------------------------------------------------------- логика
class Signal(StatesGroup):
    collecting = State()


router = Router()


@router.message(Command("chatid"))
async def chatid(m: Message):
    await m.answer(f"chat_id: <code>{m.chat.id}</code>", parse_mode="HTML")


@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(T["ru"]["choose_lang"], reply_markup=lang_kb())


@router.message(F.text.in_(both("btn_lang")))
async def change_lang(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(T["ru"]["choose_lang"], reply_markup=lang_kb())


@router.callback_query(F.data.startswith("lang:"))
async def pick_lang(c: CallbackQuery):
    lang = c.data.split(":")[1]
    set_lang(c.from_user.id, lang)
    await c.message.answer(T[lang]["welcome"], parse_mode="HTML", reply_markup=menu_kb(lang))
    await c.answer()


@router.message(F.text.in_(both("btn_about")))
async def about(m: Message):
    await m.answer(T[get_lang(m.from_user.id)]["about"], parse_mode="HTML")


@router.message(F.text.in_(both("btn_how")))
async def how(m: Message):
    await m.answer(T[get_lang(m.from_user.id)]["how"], parse_mode="HTML")


@router.message(F.text.in_(both("btn_send")))
async def send_signal(m: Message, state: FSMContext):
    lang = get_lang(m.from_user.id)
    await state.clear()
    await m.answer(T[lang]["choose_cat"], reply_markup=cats_kb(lang))


@router.callback_query(F.data.startswith("cat:"))
async def pick_cat(c: CallbackQuery, state: FSMContext):
    lang = get_lang(c.from_user.id)
    cat = c.data.split(":")[1]
    await state.set_state(Signal.collecting)
    await state.update_data(category=cat, items=[])
    await c.message.answer(
        f"<b>{T[lang]['cats'][cat]}</b>\n\n{T[lang]['collect']}",
        parse_mode="HTML",
        reply_markup=collect_kb(lang),
    )
    await c.answer()


@router.message(Signal.collecting, F.text.in_(both("btn_cancel")))
async def cancel(m: Message, state: FSMContext):
    lang = get_lang(m.from_user.id)
    await state.clear()
    await m.answer(T[lang]["cancelled"], reply_markup=menu_kb(lang))


@router.message(Signal.collecting, F.text.in_(both("btn_done")))
async def done(m: Message, state: FSMContext, bot: Bot):
    lang = get_lang(m.from_user.id)
    data = await state.get_data()
    items = data.get("items", [])
    if not items:
        await m.answer(T[lang]["empty"])
        return

    cat = data["category"]
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    cur = db.execute(
        "INSERT INTO signals (user_id, category, created, items) VALUES (?,?,?,?)",
        (m.from_user.id, cat, now, len(items)),
    )
    db.commit()
    sid = cur.lastrowid

    try:
        # Заголовок БЕЗ персональных данных отправителя (конфиденциальность).
        header = await bot.send_message(
            PROSECUTOR_CHAT_ID,
            header_text(sid, cat, now, len(items), None, None),
            parse_mode="HTML",
            reply_markup=status_kb(sid),
        )
        for chat_id, msg_id in items:
            await bot.copy_message(
                PROSECUTOR_CHAT_ID, chat_id, msg_id,
                reply_to_message_id=header.message_id,
            )
    except Exception:
        logging.exception("Не удалось переслать сигнал %s", sid)
        await m.answer(T[lang]["send_failed"])
        return

    await state.clear()
    await m.answer(
        T[lang]["accepted"].format(id=sid), parse_mode="HTML", reply_markup=menu_kb(lang)
    )


@router.message(Signal.collecting)
async def collect(m: Message, state: FSMContext):
    lang = get_lang(m.from_user.id)
    data = await state.get_data()
    items = data.get("items", [])
    items.append((m.chat.id, m.message_id))
    await state.update_data(items=items)
    await m.answer(T[lang]["added"])


STATUS_RU = {
    "taken": "🟡 Принято в работу",
    "checked": "🔎 Проверено",
    "rejected": "❌ Не подтвердилось",
    "done": "✅ Меры приняты",
}


def header_text(sid, cat, created, n_items, status, who) -> str:
    text = (
        f"🚨 <b>Сигнал №{sid}</b>\n"
        f"Категория: {T['ru']['cats'][cat]}\n"
        f"Время: {created}\n"
        f"Материалов: {n_items}"
    )
    if status:
        text += f"\n\n<b>Статус:</b> {STATUS_RU[status]}"
        if who:
            text += f"\nОтветственный: {who}"
    return text


def status_kb(sid: int) -> InlineKeyboardMarkup:
    def b(label, status):
        return InlineKeyboardButton(text=label, callback_data=f"st:{sid}:{status}")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [b("🟡 В работу", "taken"), b("🔎 Проверено", "checked")],
            [b("✅ Меры приняты", "done"), b("❌ Не подтвердилось", "rejected")],
        ]
    )


@router.callback_query(F.data.startswith("st:"))
async def set_status(c: CallbackQuery, bot: Bot):
    # Кнопки работают только в чате прокурора
    if c.message.chat.id != PROSECUTOR_CHAT_ID:
        await c.answer()
        return
    if ALLOWED_IDS and c.from_user.id not in ALLOWED_IDS:
        await c.answer("Нет доступа", show_alert=True)
        return

    _, sid_s, status = c.data.split(":")
    sid = int(sid_s)
    row = db.execute(
        "SELECT user_id, category, created, items, status FROM signals WHERE id=?",
        (sid,),
    ).fetchone()
    if not row:
        await c.answer("Сигнал не найден", show_alert=True)
        return
    user_id, cat, created, n_items, old_status = row
    if old_status == status:
        await c.answer("Этот статус уже установлен")
        return

    who = c.from_user.full_name
    db.execute(
        "UPDATE signals SET status=?, handled_by=?, handled_at=? WHERE id=?",
        (status, who, datetime.now().strftime("%d.%m.%Y %H:%M"), sid),
    )
    db.commit()

    # Обновляем сообщение в чате прокурора; после финального статуса кнопки убираем
    final = status in ("done", "rejected")
    await c.message.edit_text(
        header_text(sid, cat, created, n_items, status, who),
        parse_mode="HTML",
        reply_markup=None if final else status_kb(sid),
    )

    # Уведомляем гражданина на его языке
    lang = get_lang(user_id)
    try:
        await bot.send_message(user_id, T[lang]["notify"][status].format(id=sid))
        await c.answer("Гражданин уведомлён ✅")
    except Exception:
        logging.exception("Не удалось уведомить пользователя по сигналу %s", sid)
        await c.answer(
            "Статус сохранён, но уведомить гражданина не удалось", show_alert=True
        )


@router.message()
async def fallback(m: Message):
    lang = get_lang(m.from_user.id)
    await m.answer(T[lang]["welcome"], parse_mode="HTML", reply_markup=menu_kb(lang))


async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
