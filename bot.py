import logging
import asyncio
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import database as db

TOKEN = "8657499967:AAFq4WDXDCMCHyABu5Y7AeXMWSc8q7yZVQA"
ADMIN_ID = 6665494648
COMMISSION = 5

logging.basicConfig(level=logging.INFO)
db.init_db()

def fmt(n): return f"{n:.2f}"

def get_rating_text(user_id):
    rating = db.get_avg_rating(user_id)
    if rating == 0:
        return "⭐️ нет оценок"
    stars = "⭐" * round(rating)
    return f"{stars} ({fmt(rating)})"

async def main_menu(update: Update, user_id, message=None):
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Ошибка: пользователь не найден. Напишите /start")
        return
    text = (f"🏪 *GIGA BAR*\n\n"
            f"💰 Баланс: `{fmt(user['balance'])}` руб\n"
            f"📦 Гиги: `{fmt(user['gigs'])}` ГБ\n"
            f"📱 Оператор: `{user['operator'] or '—'}`\n"
            f"⭐ Рейтинг: {get_rating_text(user_id)}\n"
            f"💸 Комиссия: {COMMISSION}%")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Баланс", callback_data='balance'), InlineKeyboardButton("📦 Мои гиги", callback_data='my_gigs')],
        [InlineKeyboardButton("📦 Продать гиги", callback_data='sell_hint'), InlineKeyboardButton("🛒 Купить гиги", callback_data='buy_list')],
        [InlineKeyboardButton("📋 Мои объявления", callback_data='my_offers'), InlineKeyboardButton("🤝 Мои сделки", callback_data='my_deals')],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data='deposit'), InlineKeyboardButton("💸 Вывести деньги", callback_data='withdraw_hint')],
    ])
    if user['user_id'] == ADMIN_ID:
        kb.inline_keyboard.append([InlineKeyboardButton("👑 Админ", callback_data='admin_menu')])
    if message:
        await message.edit_text(text, reply_markup=kb, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.username)
    u = db.get_user(user.id)
    if not u['phone'] or not u['operator']:
        await update.message.reply_text(
            "Добро пожаловать! Укажите номер и оператора:\n"
            "/set_phone 79123456789\n"
            "/set_operator МТС (или Билайн, Мегафон, Tele2, Yota)"
        )
        return
    await main_menu(update, user.id)

# --- Настройки ---
async def set_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пример: /set_phone 79123456789")
        return
    phone = context.args[0].strip()
    if not phone.isdigit() or len(phone) < 10:
        await update.message.reply_text("Неверный формат. Пример: 79123456789")
        return
    uid = update.effective_user.id
    user = db.get_user(uid)
    db.update_user_phone(uid, phone, user['operator'] if user else None)
    await update.message.reply_text(f"✅ Номер {phone} сохранён.")

async def set_operator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пример: /set_operator МТС")
        return
    op = context.args[0].strip()
    if op not in ['МТС', 'Билайн', 'Мегафон', 'Tele2', 'Yota']:
        await update.message.reply_text("Оператор должен быть: МТС, Билайн, Мегафон, Tele2, Yota")
        return
    uid = update.effective_user.id
    user = db.get_user(uid)
    db.update_user_phone(uid, user['phone'] if user else None, op)
    await update.message.reply_text(f"✅ Оператор {op} сохранён.")

# --- Баланс и гиги ---
async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    await update.message.reply_text(f"💰 Ваш баланс: {fmt(user['balance'])} руб")

async def my_gigs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    await update.message.reply_text(f"📦 Ваши гиги: {fmt(user['gigs'])} ГБ")

# --- Продажа ---
async def sell_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.message.reply_text("Использование: /sell [количество ГБ] [цена за 1 ГБ]")
        return
    try:
        amount = float(context.args[0])
        price = float(context.args[1])
        if amount <= 0 or amount > 100 or price <= 0:
            raise ValueError
    except:
        await update.message.reply_text("Ошибка: введите два положительных числа (ГБ до 100)")
        return
    uid = update.effective_user.id
    user = db.get_user(uid)
    if user['gigs'] < amount:
        await update.message.reply_text(f"У вас только {fmt(user['gigs'])} ГБ")
        return
    if not user['operator']:
        await update.message.reply_text("Сначала укажите оператора командой /set_operator")
        return
    db.update_gigs(uid, -amount)
    oid = db.add_offer(uid, amount, price, user['operator'])
    await update.message.reply_text(f"✅ Объявление #{oid} создано: {amount} ГБ по {price} руб/ГБ, итого {fmt(amount*price)} руб")

# --- Покупка ---
async def buy_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    offers = db.get_active_offers()
    if not offers:
        await update.message.reply_text("Нет активных объявлений.")
        return
    text = "📦 *Доступные объявления:*\n"
    for o in offers:
        seller = db.get_user(o['seller_id'])
        if seller:
            rating = get_rating_text(o['seller_id'])
            text += f"#{o['offer_id']}: {o['amount']} ГБ × {o['price_per_gb']} руб = {fmt(o['total_price'])} руб | {o['operator']} | Продавец: {rating}\n"
    text += "\nКупить: /buy_offer [ID]"
    await update.message.reply_text(text, parse_mode='Markdown')

async def buy_offer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/buy_offer [ID]")
        return
    try:
        oid = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    buyer_id = update.effective_user.id
    offer = db.get_offer_by_id(oid)
    if not offer:
        await update.message.reply_text("Объявление не найдено")
        return
    buyer = db.get_user(buyer_id)
    if not buyer['phone'] or not buyer['operator']:
        await update.message.reply_text("Сначала укажите номер и оператора: /set_phone, /set_operator")
        return
    if buyer['balance'] < offer['total_price']:
        await update.message.reply_text(f"Не хватает {fmt(offer['total_price'])} руб. Пополните: /top_up 500")
        return
    seller = db.get_user(offer['seller_id'])
    if db.is_blacklisted(seller['user_id']):
        await update.message.reply_text("Продавец в чёрном списке")
        return

    commission = offer['total_price'] * COMMISSION / 100
    txn = db.add_transaction(buyer_id, offer['seller_id'], offer['amount'], offer['price_per_gb'], offer['total_price'], commission)
    db.update_balance(buyer_id, -offer['total_price'])
    db.delete_offer(oid)

    ussd_map = {"МТС": f"*111*511*{buyer['phone']}*{int(offer['amount'])}#", "Билайн": f"*112*{buyer['phone']}*{int(offer['amount'])}#",
                "Мегафон": f"*105*{buyer['phone']}*{int(offer['amount'])}#", "Tele2": f"*203*{buyer['phone']}*{int(offer['amount'])}#",
                "Yota": "Передача через приложение Yota"}
    ussd = ussd_map.get(seller['operator'], "Передача через приложение оператора")

    await context.bot.send_message(
        seller['user_id'],
        f"🔔 Сделка #{txn}\nПокупатель: @{buyer['username']}\n{offer['amount']} ГБ, сумма {fmt(offer['total_price'])} руб\nТелефон покупателя: {buyer['phone']}\n"
        f"📲 Передайте гиги через: {ussd}\nПосле отправки: /confirm_send {txn}"
    )
    await update.message.reply_text(
        f"✅ Вы купили {offer['amount']} ГБ.\nДеньги заморожены. Когда получите гиги, подтвердите: /confirm_receive {txn}"
    )

# --- Подтверждения ---
async def confirm_send_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await context.bot.send_message(buyer['user_id'], f"🔔 Продавец подтвердил отправку {txn_data['amount']} ГБ. Подтвердите получение: /confirm_receive {txn}")
    await update.message.reply_text("✅ Отправка подтверждена, ожидаем покупателя.")

async def confirm_receive_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await context.bot.send_message(seller['user_id'], f"✅ Покупатель подтвердил получение {txn_data['amount']} ГБ. Вам зачислено {fmt(txn_data['total_amount'] - txn_data['commission'])} руб.")
        await update.message.reply_text("✅ Сделка завершена! Оцените продавца: /rate_seller [ID сделки] [1-5]")
    else:
        await update.message.reply_text("✅ Получение подтверждено, ожидаем продавца.")

# --- Оценка ---
async def rate_seller_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.message.reply_text("/rate_seller [ID сделки] [1-5]")
        return
    try:
        txn = int(context.args[0])
        rating = int(context.args[1])
        if rating < 1 or rating > 5: raise ValueError
    except:
        await update.message.reply_text("ID сделки и оценка 1-5")
        return
    uid = update.effective_user.id
    txn_data = db.get_transaction(txn)
    if not txn_data or txn_data['buyer_id'] != uid or txn_data['status'] != 'completed':
        await update.message.reply_text("Сделка не найдена или не завершена")
        return
    db.add_rating(uid, txn_data['seller_id'], txn, rating, "")
    await update.message.reply_text("Спасибо за оценку!")

# --- Мои объявления ---
async def my_offers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    offers = db.get_active_offers()
    mine = [o for o in offers if o['seller_id'] == uid]
    if not mine:
        await update.message.reply_text("У вас нет активных объявлений.")
        return
    text = "📋 Ваши объявления:\n"
    for o in mine:
        text += f"#{o['offer_id']}: {o['amount']} ГБ × {o['price_per_gb']} руб = {fmt(o['total_price'])} руб | {o['operator']}\n"
    text += "\nОтменить: /cancel_offer [ID]"
    await update.message.reply_text(text)

async def cancel_offer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# --- Мои сделки ---
async def my_deals_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = sqlite3.connect('giga.db')
    c = conn.cursor()
    c.execute("SELECT txn_id, amount, total_amount, status, timestamp FROM transactions WHERE (buyer_id = ? OR seller_id = ?) ORDER BY timestamp DESC LIMIT 10", (uid, uid))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("У вас нет сделок.")
        return
    text = "📜 Последние сделки:\n"
    for r in rows:
        text += f"#{r[0]}: {r[1]} ГБ, {fmt(r[2])} руб, {r[3]}, {r[4][:10]}\n"
    await update.message.reply_text(text)

# --- Пополнение и вывод ---
async def top_up_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/top_up [сумма] (демо)")
        return
    try:
        amt = float(context.args[0])
        if amt <= 0: raise ValueError
        db.update_balance(update.effective_user.id, amt)
        await update.message.reply_text(f"💰 Баланс пополнен на {fmt(amt)} руб (демо)")
    except:
        await update.message.reply_text("Сумма должна быть >0")

async def withdraw_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("/withdraw [сумма] [реквизиты]")
        return
    try:
        amount = float(context.args[0])
        if amount <= 0: raise ValueError
    except:
        await update.message.reply_text("Сумма должна быть >0")
        return
    details = ' '.join(context.args[1:])
    uid = update.effective_user.id
    user = db.get_user(uid)
    if user['balance'] < amount:
        await update.message.reply_text(f"Недостаточно средств. У вас {fmt(user['balance'])} руб.")
        return
    req_id = db.add_withdraw_request(uid, amount, details)
    await context.bot.send_message(ADMIN_ID, f"📨 Заявка на вывод #{req_id}\nОт @{update.effective_user.username} (ID {uid})\nСумма: {fmt(amount)} руб\nРеквизиты: {details}")
    await update.message.reply_text(f"✅ Заявка #{req_id} отправлена администратору.")

# --- Админ-команды ---
async def admin_add_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) != 2: return
    try:
        uid = int(context.args[0])
        amt = float(context.args[1])
        db.update_balance(uid, amt)
        await update.message.reply_text(f"✅ Начислено {fmt(amt)} руб пользователю {uid}")
    except: pass

async def admin_add_gigs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) != 2: return
    try:
        uid = int(context.args[0])
        gigs = float(context.args[1])
        db.update_gigs(uid, gigs)
        await update.message.reply_text(f"✅ Начислено {fmt(gigs)} ГБ пользователю {uid}")
    except: pass

async def block_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) < 2: return
    try:
        uid = int(context.args[0])
        reason = ' '.join(context.args[1:])
        db.add_to_blacklist(uid, reason, ADMIN_ID)
        await update.message.reply_text(f"Пользователь {uid} заблокирован")
    except: pass

async def unblock_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: return
    try:
        uid = int(context.args[0])
        db.remove_from_blacklist(uid)
        await update.message.reply_text(f"Пользователь {uid} разблокирован")
    except: pass

async def approve_withdraw_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: return
    try:
        rid = int(context.args[0])
        db.update_withdraw_request(rid, 'approved')
        await update.message.reply_text(f"Заявка #{rid} одобрена")
    except: pass

async def decline_withdraw_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: return
    try:
        rid = int(context.args[0])
        db.update_withdraw_request(rid, 'declined')
        await update.message.reply_text(f"Заявка #{rid} отклонена")
    except: pass

# --- Callback-заглушки для инлайн-кнопок (просто показывают подсказки) ---
async def callback_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await balance_cmd(update, context)

async def callback_my_gigs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await my_gigs_cmd(update, context)

async def callback_sell_hint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Используйте команду: /sell [ГБ] [цена]")

async def callback_buy_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await buy_list_cmd(update, context)

async def callback_my_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await my_offers_cmd(update, context)

async def callback_my_deals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await my_deals_cmd(update, context)

async def callback_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Пополнить баланс: /top_up [сумма]")

async def callback_withdraw_hint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Вывести деньги: /withdraw [сумма] [номер карты/кошелёк]")

async def callback_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.edit_message_text("Нет доступа")
        return
    await q.edit_message_text(
        "Админ-команды:\n"
        "/admin_add_balance [user_id] [сумма]\n"
        "/admin_add_gigs [user_id] [ГБ]\n"
        "/block_user [user_id] [причина]\n"
        "/unblock_user [user_id]\n"
        "/approve_withdraw [id]\n"
        "/decline_withdraw [id]"
    )

# --- Запуск ---
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set_phone", set_phone))
    app.add_handler(CommandHandler("set_operator", set_operator))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("my_gigs", my_gigs_cmd))
    app.add_handler(CommandHandler("sell", sell_cmd))
    app.add_handler(CommandHandler("buy_offer", buy_offer_cmd))
    app.add_handler(CommandHandler("my_offers", my_offers_cmd))
    app.add_handler(CommandHandler("cancel_offer", cancel_offer_cmd))
    app.add_handler(CommandHandler("my_deals", my_deals_cmd))
    app.add_handler(CommandHandler("confirm_send", confirm_send_cmd))
    app.add_handler(CommandHandler("confirm_receive", confirm_receive_cmd))
    app.add_handler(CommandHandler("rate_seller", rate_seller_cmd))
    app.add_handler(CommandHandler("top_up", top_up_cmd))
    app.add_handler(CommandHandler("withdraw", withdraw_cmd))

    app.add_handler(CommandHandler("admin_add_balance", admin_add_balance_cmd))
    app.add_handler(CommandHandler("admin_add_gigs", admin_add_gigs_cmd))
    app.add_handler(CommandHandler("block_user", block_user_cmd))
    app.add_handler(CommandHandler("unblock_user", unblock_user_cmd))
    app.add_handler(CommandHandler("approve_withdraw", approve_withdraw_cmd))
    app.add_handler(CommandHandler("decline_withdraw", decline_withdraw_cmd))

    app.add_handler(CallbackQueryHandler(callback_balance, pattern='^balance$'))
    app.add_handler(CallbackQueryHandler(callback_my_gigs, pattern='^my_gigs$'))
    app.add_handler(CallbackQueryHandler(callback_sell_hint, pattern='^sell_hint$'))
    app.add_handler(CallbackQueryHandler(callback_buy_list, pattern='^buy_list$'))
    app.add_handler(CallbackQueryHandler(callback_my_offers, pattern='^my_offers$'))
    app.add_handler(CallbackQueryHandler(callback_my_deals, pattern='^my_deals$'))
    app.add_handler(CallbackQueryHandler(callback_deposit, pattern='^deposit$'))
    app.add_handler(CallbackQueryHandler(callback_withdraw_hint, pattern='^withdraw_hint$'))
    app.add_handler(CallbackQueryHandler(callback_admin_menu, pattern='^admin_menu$'))

    print("🚀 GIGA BAR запущен (стабильная версия)")
    app.run_polling()

if __name__ == "__main__":
    main()
