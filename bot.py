import logging
import asyncio
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters
)
import database as db

# === ТОКЕН В КОДЕ ===
TOKEN = "8657499967:AAFq4WDXDCMCHyABu5Y7AeXMWSc8q7yZVQA"
ADMIN_ID = 6665494648
COMMISSION = 5

# === USSD-инструкции для операторов ===
USSD_TEMPLATES = {
    "МТС": "*111*511*{phone}*{amount}#",
    "Билайн": "*112*{phone}*{amount}#",
    "Мегафон": "*105*{phone}*{amount}#",
    "Tele2": "*203*{phone}*{amount}#",
    "Yota": "В приложении Yota: передача гигов через профиль"
}

logging.basicConfig(level=logging.INFO)

db.init_db()

def fmt(n): return f"{n:.2f}"

def get_rating_text(user_id):
    rating = db.get_avg_rating(user_id)
    if rating == 0:
        return "⭐️ нет оценок"
    stars = "⭐" * round(rating)
    return f"{stars} ({fmt(rating)})"

# ========== ГЛАВНОЕ МЕНЮ ==========
async def main_menu(update, user_id, message=None, edit=False):
    user = db.get_user(user_id)
    text = (f"🏪 *GIGA BAR — Безопасный обмен гигабайтами*\n\n"
            f"💰 Баланс: `{fmt(user['balance'])}` руб\n"
            f"📦 Гиги: `{fmt(user['gigs'])}` ГБ\n"
            f"📱 Оператор: `{user['operator'] or '—'}`\n"
            f"⭐ Рейтинг: {get_rating_text(user_id)}\n\n"
            f"💸 Комиссия: {COMMISSION}%")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Баланс", callback_data='balance'),
         InlineKeyboardButton("📦 Мои гиги", callback_data='my_gigs')],
        [InlineKeyboardButton("📦 Продать гиги", callback_data='sell_menu'),
         InlineKeyboardButton("🛒 Купить гиги", callback_data='buy_list')],
        [InlineKeyboardButton("📋 Мои объявления", callback_data='my_offers'),
         InlineKeyboardButton("🤝 Мои сделки", callback_data='my_deals')],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data='deposit'),
         InlineKeyboardButton("💸 Вывести деньги", callback_data='withdraw_start')],
        [InlineKeyboardButton("🔔 Подписка на оператора", callback_data='subscribe')],
    ])
    if user['user_id'] == ADMIN_ID:
        kb.inline_keyboard.append([InlineKeyboardButton("👑 Админ", callback_data='admin_menu')])
    if edit and message:
        await message.edit_text(text, reply_markup=kb, parse_mode='Markdown')
    elif message:
        await message.reply_text(text, reply_markup=kb, parse_mode='Markdown')
    else:
        await update.effective_message.reply_text(text, reply_markup=kb, parse_mode='Markdown')

async def start(update, context):
    user = update.effective_user
    db.register_user(user.id, user.username)
    if db.is_blacklisted(user.id):
        await update.message.reply_text("⛔ Вы в чёрном списке. Обратитесь к администратору.")
        return
    if not db.get_user(user.id)['phone']:
        await update.message.reply_text(
            "Добро пожаловать в GIGA BAR!\n"
            "Сначала отправьте номер телефона: /set_phone\n"
            "Затем укажите оператора: /set_operator МТС / Билайн / Мегафон / Tele2 / Yota"
        )
        return
    await main_menu(update, user.id, message=update.message)

async def set_phone(update, context):
    await update.message.reply_text("Введите ваш номер телефона (пример: 79123456789):")
    return 1

async def receive_phone(update, context):
    phone = update.message.text.strip()
    if not phone.isdigit() or len(phone) < 10:
        await update.message.reply_text("Неверный формат. Пример: 79123456789")
        return 1
    context.user_data['phone'] = phone
    await update.message.reply_text("Теперь введите оператора (МТС, Билайн, Мегафон, Tele2, Yota):")
    return 2

async def receive_operator(update, context):
    op = update.message.text.strip()
    if op not in ['МТС', 'Билайн', 'Мегафон', 'Tele2', 'Yota']:
        await update.message.reply_text("Неверный оператор. Введите: МТС, Билайн, Мегафон, Tele2, Yota")
        return 2
    uid = update.effective_user.id
    db.update_user_phone(uid, context.user_data['phone'], op)
    await update.message.reply_text(f"✅ Номер {context.user_data['phone']} и оператор {op} сохранены.")
    # Показываем главное меню
    await main_menu(update, uid, message=update.message)
    return ConversationHandler.END

# ----- Баланс и гиги -----
async def balance_callback(update, context):
    q = update.callback_query
    await q.answer()
    u = db.get_user(q.from_user.id)
    await q.edit_message_text(f"💰 Ваш баланс: {fmt(u['balance'])} руб")

async def my_gigs_callback(update, context):
    q = update.callback_query
    await q.answer()
    u = db.get_user(q.from_user.id)
    await q.edit_message_text(f"📦 Ваши гиги: {fmt(u['gigs'])} ГБ")

# ----- Продажа -----
async def sell_menu(update, context):
    q = update.callback_query
    await q.answer()
    if db.is_blacklisted(q.from_user.id):
        await q.edit_message_text("⛔ Вы в чёрном списке и не можете продавать.")
        return
    await q.edit_message_text("📦 Введите количество ГБ (до 100):")
    return 1

async def sell_amount(update, context):
    try:
        amount = float(update.message.text)
        if amount <= 0 or amount > 100:
            raise ValueError
    except:
        await update.message.reply_text("Введите число от 1 до 100")
        return 1
    context.user_data['amount'] = amount
    await update.message.reply_text("💰 Введите цену за 1 ГБ (руб):")
    return 2

async def sell_price(update, context):
    try:
        price = float(update.message.text)
        if price <= 0:
            raise ValueError
    except:
        await update.message.reply_text("Цена должна быть >0")
        return 2
    uid = update.effective_user.id
    amount = context.user_data['amount']
    total = amount * price
    user = db.get_user(uid)
    if user['gigs'] < amount:
        await update.message.reply_text(f"У вас только {fmt(user['gigs'])} ГБ. Пополните гиги у админа.")
        return ConversationHandler.END
    if not user['operator']:
        await update.message.reply_text("Сначала укажите оператора через /set_operator")
        return ConversationHandler.END
    db.update_gigs(uid, -amount)
    oid = db.add_offer(uid, amount, price, user['operator'])
    await update.message.reply_text(f"✅ Объявление #{oid} создано!\n{amount} ГБ по {price} руб/ГБ, итого {fmt(total)} руб")
    subscribers = db.get_subscribers_by_operator(user['operator'])
    for sub in subscribers:
        if sub != uid:
            await context.bot.send_message(sub, f"🔔 Новое объявление от @{user['username']}: {amount} ГБ, {price} руб/ГБ, /buy_offer {oid}")
    return ConversationHandler.END

# ----- Покупка -----
async def buy_list(update, context):
    q = update.callback_query
    await q.answer()
    offers = db.get_active_offers()
    if not offers:
        await q.edit_message_text("Нет активных объявлений.")
        return
    text = "📦 *Доступные объявления:*\n"
    for o in offers:
        seller = db.get_user(o['seller_id'])
        if seller:
            rating = get_rating_text(o['seller_id'])
            text += f"#{o['offer_id']}: {o['amount']} ГБ × {o['price_per_gb']} руб = {fmt(o['total_price'])} руб | {o['operator']} | Продавец: {rating}\n"
    text += "\nКупить: /buy_offer [ID]"
    await q.edit_message_text(text, parse_mode='Markdown')

async def buy_offer_cmd(update, context):
    if db.is_blacklisted(update.effective_user.id):
        await update.message.reply_text("⛔ Вы в чёрном списке и не можете покупать.")
        return
    if not context.args:
        await update.message.reply_text("/buy_offer [ID]")
        return
    try:
        oid = int(context.args[0])
    except:
        await update.message.reply_text("ID должен быть числом")
        return
    buyer_id = update.effective_user.id
    offer = db.get_offer_by_id(oid)
    if not offer:
        await update.message.reply_text("Объявление не найдено")
        return
    buyer = db.get_user(buyer_id)
    if buyer['balance'] < offer['total_price']:
        await update.message.reply_text(f"Не хватает {fmt(offer['total_price'])} руб. Пополните баланс (демо: /top_up 500).")
        return
    seller = db.get_user(offer['seller_id'])
    if db.is_blacklisted(offer['seller_id']):
        await update.message.reply_text("Продавец в чёрном списке, сделка невозможна.")
        return

    commission = offer['total_price'] * COMMISSION / 100
    txn_id = db.add_transaction(buyer_id, offer['seller_id'], offer['amount'], offer['price_per_gb'], offer['total_price'], commission)
    db.update_balance(buyer_id, -offer['total_price'])
    db.delete_offer(oid)

    ussd = USSD_TEMPLATES.get(seller['operator'], "Передача через приложение оператора")
    ussd_command = ussd.format(phone=buyer['phone'], amount=int(offer['amount'])) if '{phone}' in ussd else ussd

    await context.bot.send_message(
        offer['seller_id'],
        f"🔔 *Новая сделка #{txn_id}*\n"
        f"Покупатель: @{buyer['username']}\n"
        f"Объём: {offer['amount']} ГБ\n"
        f"Сумма: {fmt(offer['total_price'])} руб\n"
        f"Телефон покупателя: `{buyer['phone']}`\n\n"
        f"📲 *Инструкция для передачи гигов:*\n"
        f"```\n{ussd_command}\n```\n"
        f"После отправки USSD-команды нажмите /confirm_send {txn_id}",
        parse_mode='Markdown'
    )
    await update.message.reply_text(
        f"✅ Вы купили {offer['amount']} ГБ.\n"
        f"Деньги зарезервированы. Продавец передаст гиги.\n"
        f"Когда получите гиги, подтвердите: /confirm_receive {txn_id}\n\n"
        f"📞 Ваш номер: `{buyer['phone']}` (оператор {buyer['operator']})",
        parse_mode='Markdown'
    )

# ----- Подтверждение сделок -----
async def confirm_send_cmd(update, context):
    if not context.args:
        await update.message.reply_text("/confirm_send [ID сделки]")
        return
    try:
        txn = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    uid = update.effective_user.id
    txn_data = db.get_transaction(txn)
    if not txn_data or txn_data['seller_id'] != uid or txn_data['seller_confirmed']:
        await update.message.reply_text("Не найдено или уже подтверждено")
        return
    db.update_transaction_confirmation(txn, seller_confirmed=1)
    buyer = db.get_user(txn_data['buyer_id'])
    await context.bot.send_message(
        txn_data['buyer_id'],
        f"🔔 Продавец подтвердил отправку {txn_data['amount']} ГБ.\n"
        f"Проверьте баланс телефона. Если гиги пришли, нажмите /confirm_receive {txn}\n"
        f"Если не пришли — /dispute {txn}"
    )
    await update.message.reply_text("✅ Отправка подтверждена. Ожидаем подтверждения покупателя.")

async def confirm_receive_cmd(update, context):
    if not context.args:
        await update.message.reply_text("/confirm_receive [ID сделки]")
        return
    try:
        txn = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    uid = update.effective_user.id
    txn_data = db.get_transaction(txn)
    if not txn_data or txn_data['buyer_id'] != uid or txn_data['buyer_confirmed']:
        await update.message.reply_text("Не найдено или уже подтверждено")
        return
    db.update_transaction_confirmation(txn, buyer_confirmed=1)
    txn_data = db.get_transaction(txn)
    if txn_data['seller_confirmed']:
        db.complete_transaction(txn)
        seller = db.get_user(txn_data['seller_id'])
        await context.bot.send_message(
            txn_data['seller_id'],
            f"✅ Покупатель подтвердил получение {txn_data['amount']} ГБ.\n"
            f"💰 {fmt(txn_data['total_amount'] - txn_data['commission'])} руб зачислены на ваш баланс."
        )
        await update.message.reply_text("✅ Сделка завершена! Спасибо.\nОцените продавца: /rate_seller [ID сделки] [1-5]")
    else:
        await update.message.reply_text("✅ Получение подтверждено. Ждём подтверждения от продавца.")

# ----- Оценка -----
async def rate_seller(update, context):
    if len(context.args) != 2:
        await update.message.reply_text("/rate_seller [ID сделки] [1-5]")
        return
    try:
        txn = int(context.args[0])
        rating = int(context.args[1])
        if rating < 1 or rating > 5:
            raise ValueError
    except:
        await update.message.reply_text("ID сделки и оценка 1-5")
        return
    uid = update.effective_user.id
    txn_data = db.get_transaction(txn)
    if not txn_data or txn_data['buyer_id'] != uid or txn_data['status'] != 'completed':
        await update.message.reply_text("Сделка не найдена или ещё не завершена.")
        return
    db.add_rating(uid, txn_data['seller_id'], txn, rating, "")
    await update.message.reply_text("Спасибо за оценку!")

# ----- Спор -----
async def dispute(update, context):
    if not context.args:
        await update.message.reply_text("/dispute [ID сделки]")
        return
    try:
        txn = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    uid = update.effective_user.id
    txn_data = db.get_transaction(txn)
    if not txn_data or (txn_data['buyer_id'] != uid and txn_data['seller_id'] != uid):
        await update.message.reply_text("Сделка не найдена")
        return
    db.update_transaction_confirmation(txn, dispute=1)
    await context.bot.send_message(
        ADMIN_ID,
        f"⚠️ Спор по сделке #{txn}\nПокупатель: {txn_data['buyer_id']}\nПродавец: {txn_data['seller_id']}\nСумма: {fmt(txn_data['total_amount'])} руб\nАдмин, решите вручную."
    )
    await update.message.reply_text("Жалоба отправлена администратору.")

# ----- Подписка -----
async def subscribe_menu(update, context):
    q = update.callback_query
    await q.answer()
    operators = ["МТС", "Билайн", "Мегафон", "Tele2", "Yota"]
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(op, callback_data=f'sub_{op}')] for op in operators])
    await q.edit_message_text("Выберите оператора для подписки на новые объявления:", reply_markup=kb)

async def subscribe_callback(update, context):
    q = update.callback_query
    await q.answer()
    op = q.data.replace('sub_', '')
    uid = q.from_user.id
    db.add_subscription(uid, op)
    await q.edit_message_text(f"✅ Вы подписаны на уведомления по оператору {op}")

# ----- Мои объявления и сделки -----
async def my_offers(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    offers = db.get_active_offers()
    mine = [o for o in offers if o['seller_id'] == uid]
    if not mine:
        await q.edit_message_text("У вас нет активных объявлений.")
        return
    text = "📋 Ваши объявления:\n"
    for o in mine:
        text += f"#{o['offer_id']}: {o['amount']} ГБ × {o['price_per_gb']} руб = {fmt(o['total_price'])} руб | {o['operator']}\n"
    text += "\nОтменить: /cancel_offer [ID]"
    await q.edit_message_text(text)

async def cancel_offer_cmd(update, context):
    if not context.args:
        await update.message.reply_text("/cancel_offer [ID]")
        return
    try:
        oid = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    uid = update.effective_user.id
    offers = db.get_active_offers()
    target = next((o for o in offers if o['offer_id'] == oid and o['seller_id'] == uid), None)
    if not target:
        await update.message.reply_text("Объявление не найдено")
        return
    db.update_gigs(uid, target['amount'])
    db.delete_offer(oid)
    await update.message.reply_text(f"Объявление #{oid} отменено, гиги возвращены.")

async def my_deals(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    conn = sqlite3.connect('giga.db')
    c = conn.cursor()
    c.execute("SELECT txn_id, amount, total_amount, status, timestamp FROM transactions WHERE (buyer_id = ? OR seller_id = ?) ORDER BY timestamp DESC LIMIT 10", (uid, uid))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await q.edit_message_text("У вас нет завершённых сделок.")
        return
    text = "📜 Последние сделки:\n"
    for r in rows:
        text += f"#{r[0]}: {r[1]} ГБ, {fmt(r[2])} руб, {r[3]}, {r[4][:10]}\n"
    await q.edit_message_text(text)

# ----- Пополнение и вывод -----
async def deposit(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("💳 Пополнение баланса:\nСейчас доступен демо-режим: /top_up [сумма]\nВ будущем - банковские карты и криптовалюта.")

async def top_up_demo(update, context):
    if not context.args:
        await update.message.reply_text("/top_up [сумма]")
        return
    try:
        amt = float(context.args[0])
        if amt <= 0: raise ValueError
        db.update_balance(update.effective_user.id, amt)
        await update.message.reply_text(f"💰 Баланс пополнен на {fmt(amt)} руб (демо)")
    except:
        await update.message.reply_text("Сумма должна быть >0")

async def withdraw_start(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("💰 Введите сумму для вывода (в рублях):")
    return 1

async def withdraw_amount(update, context):
    try:
        amount = float(update.message.text)
        if amount <= 0: raise ValueError
    except:
        await update.message.reply_text("Введите положительное число.")
        return 1
    uid = update.effective_user.id
    user = db.get_user(uid)
    if user['balance'] < amount:
        await update.message.reply_text(f"Недостаточно средств. У вас {fmt(user['balance'])} руб.")
        return 1
    context.user_data['amount'] = amount
    await update.message.reply_text("Введите реквизиты для вывода (номер карты, кошелёк):")
    return 2

async def withdraw_details(update, context):
    details = update.message.text
    uid = update.effective_user.id
    amount = context.user_data['amount']
    req_id = db.add_withdraw_request(uid, amount, details)
    await context.bot.send_message(
        ADMIN_ID,
        f"📨 Заявка на вывод #{req_id}\nПользователь: @{update.effective_user.username} (ID {uid})\nСумма: {fmt(amount)} руб\nРеквизиты: {details}"
    )
    await update.message.reply_text(f"✅ Заявка на вывод #{req_id} отправлена администратору.")
    return ConversationHandler.END

# ----- Админ-панель -----
async def admin_menu(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.edit_message_text("Нет доступа.")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')],
        [InlineKeyboardButton("💰 Начислить баланс", callback_data='admin_add_balance')],
        [InlineKeyboardButton("📦 Начислить гиги", callback_data='admin_add_gigs')],
        [InlineKeyboardButton("🚫 Чёрный список", callback_data='admin_blacklist')],
        [InlineKeyboardButton("📋 Заявки на вывод", callback_data='admin_withdraws')],
    ])
    await q.edit_message_text("👑 Админ-панель", reply_markup=kb)

async def admin_stats(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    users = db.get_all_users()
    total_balance = sum(u['balance'] for u in users)
    total_gigs = sum(u['gigs'] for u in users)
    await q.edit_message_text(
        f"📊 Статистика\n👥 Пользователей: {len(users)}\n"
        f"💰 Общий баланс: {fmt(total_balance)} руб\n"
        f"📦 Всего гигов: {fmt(total_gigs)} ГБ"
    )

async def admin_add_balance_cmd(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) != 2: return
    try:
        uid = int(context.args[0])
        amt = float(context.args[1])
        db.update_balance(uid, amt)
        await update.message.reply_text(f"✅ Начислено {fmt(amt)} руб пользователю {uid}")
    except: pass

async def admin_add_gigs_cmd(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) != 2: return
    try:
        uid = int(context.args[0])
        gigs = float(context.args[1])
        db.update_gigs(uid, gigs)
        await update.message.reply_text(f"✅ Начислено {fmt(gigs)} ГБ пользователю {uid}")
    except: pass

async def admin_blacklist(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    await q.edit_message_text("Команды:\n/block_user [ID] [причина]\n/unblock_user [ID]")

async def block_user(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) < 2: return
    try:
        uid = int(context.args[0])
        reason = ' '.join(context.args[1:])
        db.add_to_blacklist(uid, reason, ADMIN_ID)
        await update.message.reply_text(f"Пользователь {uid} заблокирован. Причина: {reason}")
    except: pass

async def unblock_user(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: return
    try:
        uid = int(context.args[0])
        db.remove_from_blacklist(uid)
        await update.message.reply_text(f"Пользователь {uid} разблокирован.")
    except: pass

async def admin_withdraws(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    reqs = db.get_pending_withdraw_requests()
    if not reqs:
        await q.edit_message_text("Нет активных заявок.")
        return
    text = "📋 Заявки на вывод:\n"
    for r in reqs:
        text += f"#{r['req_id']}: {fmt(r['amount'])} руб от {r['user_id']}\nРеквизиты: {r['details']}\n"
    text += "\nОдобрить: /approve_withdraw [ID]\nОтклонить: /decline_withdraw [ID]"
    await q.edit_message_text(text)

async def approve_withdraw(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: return
    try:
        rid = int(context.args[0])
        db.update_withdraw_request(rid, 'approved')
        await update.message.reply_text(f"Заявка #{rid} одобрена.")
    except: pass

async def decline_withdraw(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: return
    try:
        rid = int(context.args[0])
        db.update_withdraw_request(rid, 'declined')
        await update.message.reply_text(f"Заявка #{rid} отклонена.")
    except: pass

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()

    # Разговор для установки номера и оператора
    conv_setup = ConversationHandler(
        entry_points=[CommandHandler("set_phone", set_phone)],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_operator)],
        },
        fallbacks=[],
    )
    # Продажа
    sell_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(sell_menu, pattern='^sell_menu$')],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_amount)],
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_price)],
        },
        fallbacks=[],
    )
    # Вывод
    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(withdraw_start, pattern='^withdraw_start$')],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_details)],
        },
        fallbacks=[],
    )
    app.add_handler(conv_setup)
    app.add_handler(sell_conv)
    app.add_handler(withdraw_conv)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("top_up", top_up_demo))
    app.add_handler(CommandHandler("buy_offer", buy_offer_cmd))
    app.add_handler(CommandHandler("cancel_offer", cancel_offer_cmd))
    app.add_handler(CommandHandler("confirm_send", confirm_send_cmd))
    app.add_handler(CommandHandler("confirm_receive", confirm_receive_cmd))
    app.add_handler(CommandHandler("rate_seller", rate_seller))
    app.add_handler(CommandHandler("dispute", dispute))
    app.add_handler(CommandHandler("block_user", block_user))
    app.add_handler(CommandHandler("unblock_user", unblock_user))
    app.add_handler(CommandHandler("admin_add_balance", admin_add_balance_cmd))
    app.add_handler(CommandHandler("admin_add_gigs", admin_add_gigs_cmd))
    app.add_handler(CommandHandler("approve_withdraw", approve_withdraw))
    app.add_handler(CommandHandler("decline_withdraw", decline_withdraw))

    app.add_handler(CallbackQueryHandler(balance_callback, pattern='^balance$'))
    app.add_handler(CallbackQueryHandler(my_gigs_callback, pattern='^my_gigs$'))
    app.add_handler(CallbackQueryHandler(buy_list, pattern='^buy_list$'))
    app.add_handler(CallbackQueryHandler(my_offers, pattern='^my_offers$'))
    app.add_handler(CallbackQueryHandler(my_deals, pattern='^my_deals$'))
    app.add_handler(CallbackQueryHandler(deposit, pattern='^deposit$'))
    app.add_handler(CallbackQueryHandler(subscribe_menu, pattern='^subscribe$'))
    app.add_handler(CallbackQueryHandler(subscribe_callback, pattern='^sub_'))
    app.add_handler(CallbackQueryHandler(admin_menu, pattern='^admin_menu$'))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern='^admin_stats$'))
    app.add_handler(CallbackQueryHandler(admin_blacklist, pattern='^admin_blacklist$'))
    app.add_handler(CallbackQueryHandler(admin_withdraws, pattern='^admin_withdraws$'))
    # заглушки для кнопок, которые не имеют отдельных обработчиков
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.answer(), pattern='^admin_add_balance$'))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.answer(), pattern='^admin_add_gigs$'))

    print("🚀 GIGA BAR (гарант) запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
