import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import database as db

TOKEN = "8657499967:AAFq4WDXDCMCHyABu5Y7AeXMWSc8q7yZVQA"
ADMIN_ID = 6665494648
COMMISSION = 5

logging.basicConfig(level=logging.INFO)
db.init_db()

def fmt(n): return f"{n:.2f}"

# ========== ГЛАВНОЕ МЕНЮ (ВСЕГДА ОДИНАКОВОЕ) ==========
MAIN_MENU_TEXT = (
    "GIGA BAR - Биржа гигабайт\n\n"
    "Баланс: {balance} руб\n"
    "Гиги: {gigs} ГБ\n"
    "Телефон: {phone}\n"
    "Оператор: {operator}\n"
    "Комиссия: {comm}%\n\n"
    "Команды:\n"
    "/set_phone 79123456789 - указать номер\n"
    "/set_operator МТС - указать оператора\n"
    "/top_up 100 - демо-пополнение\n"
    "/sell 30 15 - продать 30 ГБ по 15 руб\n"
    "/buy - посмотреть предложения\n"
    "/my_offers - мои объявления\n"
    "/my_deals - мои сделки\n"
    "/withdraw 500 карта 1234 - вывести деньги"
)

def main_menu_keyboard(user_id):
    kb = [
        [InlineKeyboardButton("Баланс", callback_data='balance'),
         InlineKeyboardButton("Мои гиги", callback_data='my_gigs')],
        [InlineKeyboardButton("Продать гиги", callback_data='sell_hint'),
         InlineKeyboardButton("Купить гиги", callback_data='buy_list')],
        [InlineKeyboardButton("Мои объявления", callback_data='my_offers'),
         InlineKeyboardButton("Мои сделки", callback_data='my_deals')],
        [InlineKeyboardButton("Пополнить баланс", callback_data='deposit'),
         InlineKeyboardButton("Вывести деньги", callback_data='withdraw_hint')],
    ]
    if user_id == ADMIN_ID:
        kb.append([InlineKeyboardButton("Админ панель", callback_data='admin_menu')])
    return InlineKeyboardMarkup(kb)

async def send_main_menu(update: Update, user_id, message=None, edit=False):
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Ошибка. Напишите /start")
        return
    text = MAIN_MENU_TEXT.format(
        balance=fmt(user['balance']),
        gigs=fmt(user['gigs']),
        phone=user['phone'] or 'не указан',
        operator=user['operator'] or 'не указан',
        comm=COMMISSION
    )
    if edit and message:
        await message.edit_text(text, reply_markup=main_menu_keyboard(user_id))
    elif message:
        await message.reply_text(text, reply_markup=main_menu_keyboard(user_id))
    else:
        await update.message.reply_text(text, reply_markup=main_menu_keyboard(user_id))

# ========== СТАРТ И РЕГИСТРАЦИЯ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.username)
    u = db.get_user(user.id)
    if not u['phone'] or not u['operator']:
        contact_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("Отправить номер телефона", request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
        await update.message.reply_text(
            "Добро пожаловать в GIGA BAR!\n"
            "Нажмите кнопку, чтобы отправить номер телефона.\n"
            "Затем укажите оператора командой /set_operator",
            reply_markup=contact_keyboard
        )
        return
    await send_main_menu(update, user.id)

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact:
        await update.message.reply_text("Используйте кнопку.")
        return
    phone = contact.phone_number
    uid = update.effective_user.id
    user = db.get_user(uid)
    db.update_user_phone(uid, phone, user['operator'] if user else None)
    await update.message.reply_text(
        f"Номер {phone} сохранён.\nТеперь укажите оператора командой /set_operator",
        reply_markup=ReplyKeyboardRemove()
    )
    await send_main_menu(update, uid)

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
    await update.message.reply_text(f"Номер {phone} сохранён.")
    await send_main_menu(update, uid)

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
    await update.message.reply_text(f"Оператор {op} сохранён.")
    await send_main_menu(update, uid)

# ========== БАЛАНС И ГИГИ ==========
async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    await update.message.reply_text(f"Ваш баланс: {fmt(user['balance'])} руб")

async def my_gigs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    await update.message.reply_text(f"Ваши гиги: {fmt(user['gigs'])} ГБ")

# ========== ПРОДАЖА ==========
async def sell_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.message.reply_text("Использование: /sell [количество ГБ] [цена за 1 ГБ]\nПример: /sell 30 15")
        return
    try:
        amount = float(context.args[0])
        price = float(context.args[1])
        if amount <= 0 or amount > 100 or price <= 0:
            raise ValueError
    except:
        await update.message.reply_text("Ошибка: количество от 1 до 100 ГБ, цена больше 0.")
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
    await update.message.reply_text(f"Объявление #{oid} создано: {amount} ГБ по {price} руб/ГБ. Итого {fmt(amount*price)} руб")

# ========== ПОКУПКА (С ПАГИНАЦИЕЙ) ==========
PAGE_SIZE = 5

async def buy_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    query = update.callback_query
    await query.answer()
    offers = db.get_active_offers()
    if not offers:
        await query.edit_message_text("Нет активных предложений.")
        return
    total_pages = (len(offers) - 1) // PAGE_SIZE + 1
    if page >= total_pages:
        page = total_pages - 1
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_offers = offers[start:end]
    text = "Предложения (напишите номер ID для покупки):\n\n"
    for o in page_offers:
        seller = db.get_user(o['seller_id'])
        seller_name = seller['username'] if seller else str(o['seller_id'])
        text += f"ID {o['offer_id']}: {o['amount']} ГБ x {o['price_per_gb']} руб = {fmt(o['total_price'])} руб | {o['operator']} | от @{seller_name}\n"
    text += f"\nСтраница {page+1}/{total_pages}"
    keyboard = []
    if page > 0:
        keyboard.append(InlineKeyboardButton("<< Назад", callback_data=f'buy_page_{page-1}'))
    if page < total_pages - 1:
        keyboard.append(InlineKeyboardButton("Вперед >>", callback_data=f'buy_page_{page+1}'))
    keyboard.append(InlineKeyboardButton("Главное меню", callback_data='main_menu'))
    reply_markup = InlineKeyboardMarkup([keyboard]) if keyboard else InlineKeyboardMarkup([[InlineKeyboardButton("Главное меню", callback_data='main_menu')]])
    await query.edit_message_text(text, reply_markup=reply_markup)

async def buy_offer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /buy_offer [ID]\nПример: /buy_offer 3")
        return
    try:
        oid = int(context.args[0])
    except:
        await update.message.reply_text("ID должен быть числом")
        return
    buyer_id = update.effective_user.id
    offer = db.get_offer_by_id(oid)
    if not offer:
        await update.message.reply_text("Предложение не найдено")
        return
    buyer = db.get_user(buyer_id)
    if not buyer['phone'] or not buyer['operator']:
        await update.message.reply_text("Сначала укажите номер (/set_phone) и оператора (/set_operator)")
        return
    if buyer['balance'] < offer['total_price']:
        await update.message.reply_text(f"Не хватает {fmt(offer['total_price'])} руб. Пополните /top_up")
        return
    seller = db.get_user(offer['seller_id'])
    commission = offer['total_price'] * COMMISSION / 100
    txn = db.add_transaction(buyer_id, offer['seller_id'], offer['amount'], offer['price_per_gb'], offer['total_price'], commission)
    db.update_balance(buyer_id, -offer['total_price'])
    db.delete_offer(oid)

    ussd_map = {
        "МТС": f"*111*511*{buyer['phone']}*{int(offer['amount'])}#",
        "Билайн": f"*112*{buyer['phone']}*{int(offer['amount'])}#",
        "Мегафон": f"*105*{buyer['phone']}*{int(offer['amount'])}#",
        "Tele2": f"*203*{buyer['phone']}*{int(offer['amount'])}#",
        "Yota": "Передача через приложение Yota"
    }
    ussd = ussd_map.get(seller['operator'], "Передача через приложение оператора")
    await context.bot.send_message(
        seller['user_id'],
        f"НОВАЯ СДЕЛКА #{txn}\n"
        f"Покупатель: @{buyer['username']}\n"
        f"Объем: {offer['amount']} ГБ\n"
        f"Сумма: {fmt(offer['total_price'])} руб\n"
        f"Телефон покупателя: {buyer['phone']}\n"
        f"Передайте гиги через: {ussd}\n"
        f"После отправки нажмите /confirm_send {txn}"
    )
    await update.message.reply_text(
        f"Вы купили {offer['amount']} ГБ.\n"
        f"Деньги заморожены. Когда получите гиги, подтвердите: /confirm_receive {txn}"
    )

# ========== ПОДТВЕРЖДЕНИЕ ==========
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
    await context.bot.send_message(buyer['user_id'], f"Продавец подтвердил отправку {txn_data['amount']} ГБ. Если получили, нажмите /confirm_receive {txn}")
    await update.message.reply_text("Отправка подтверждена. Ожидаем покупателя.")

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
        await context.bot.send_message(seller['user_id'], f"Покупатель подтвердил получение {txn_data['amount']} ГБ. Вам зачислено {fmt(txn_data['total_amount'] - txn_data['commission'])} руб.")
        await update.message.reply_text("Сделка завершена!")
    else:
        await update.message.reply_text("Получение подтверждено. Ждём продавца.")

# ========== МОИ ОБЪЯВЛЕНИЯ И СДЕЛКИ ==========
async def my_offers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    offers = db.get_active_offers()
    mine = [o for o in offers if o['seller_id'] == uid]
    if not mine:
        await update.message.reply_text("У вас нет активных объявлений.")
        return
    text = "Ваши объявления:\n"
    for o in mine:
        text += f"ID {o['offer_id']}: {o['amount']} ГБ x {o['price_per_gb']} руб = {fmt(o['total_price'])} руб | {o['operator']}\n"
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

async def my_deals_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    import sqlite3
    conn = sqlite3.connect('giga.db')
    c = conn.cursor()
    c.execute("SELECT txn_id, amount, total_amount, status, timestamp FROM transactions WHERE (buyer_id = ? OR seller_id = ?) ORDER BY timestamp DESC LIMIT 10", (uid, uid))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("У вас нет сделок.")
        return
    text = "Последние сделки:\n"
    for r in rows:
        text += f"#{r[0]}: {r[1]} ГБ, {fmt(r[2])} руб, {r[3]}, {r[4][:10]}\n"
    await update.message.reply_text(text)

# ========== ПОПОЛНЕНИЕ И ВЫВОД ==========
async def top_up_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/top_up [сумма] (демо)")
        return
    try:
        amt = float(context.args[0])
        if amt <= 0: raise ValueError
        db.update_balance(update.effective_user.id, amt)
        await update.message.reply_text(f"Баланс пополнен на {fmt(amt)} руб (демо)")
    except:
        await update.message.reply_text("Сумма должна быть больше 0")

async def withdraw_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("/withdraw [сумма] [реквизиты]\nПример: /withdraw 500 карта 1234")
        return
    try:
        amount = float(context.args[0])
        if amount <= 0: raise ValueError
    except:
        await update.message.reply_text("Сумма должна быть больше 0")
        return
    details = ' '.join(context.args[1:])
    uid = update.effective_user.id
    user = db.get_user(uid)
    if user['balance'] < amount:
        await update.message.reply_text(f"Недостаточно средств. У вас {fmt(user['balance'])} руб.")
        return
    req_id = db.add_withdraw_request(uid, amount, details)
    await context.bot.send_message(ADMIN_ID, f"Заявка на вывод #{req_id}\nОт @{update.effective_user.username} (ID {uid})\nСумма: {fmt(amount)} руб\nРеквизиты: {details}")
    await update.message.reply_text(f"Заявка #{req_id} отправлена администратору.")

# ========== АДМИН-КОМАНДЫ ==========
async def admin_add_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) != 2: return
    try:
        uid = int(context.args[0])
        amt = float(context.args[1])
        db.update_balance(uid, amt)
        await update.message.reply_text(f"Начислено {fmt(amt)} руб пользователю {uid}")
    except: pass

async def admin_add_gigs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) != 2: return
    try:
        uid = int(context.args[0])
        gigs = float(context.args[1])
        db.update_gigs(uid, gigs)
        await update.message.reply_text(f"Начислено {fmt(gigs)} ГБ пользователю {uid}")
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

# ========== ОБРАБОТЧИК ЛЮБОГО СООБЩЕНИЯ (КРОМЕ КОМАНД) ==========
async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Если сообщение не команда и не callback, показываем главное меню
    if update.message and not update.message.text.startswith('/'):
        await send_main_menu(update, update.effective_user.id)

# ========== CALLBACK-ОБРАБОТЧИКИ ==========
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'balance':
        user = db.get_user(query.from_user.id)
        await query.edit_message_text(f"Ваш баланс: {fmt(user['balance'])} руб")
    elif data == 'my_gigs':
        user = db.get_user(query.from_user.id)
        await query.edit_message_text(f"Ваши гиги: {fmt(user['gigs'])} ГБ")
    elif data == 'sell_hint':
        await query.edit_message_text("Используйте команду:\n/sell [количество ГБ] [цена за 1 ГБ]\nПример: /sell 30 15")
    elif data == 'buy_list':
        await buy_list(update, context, 0)
    elif data == 'my_offers':
        await my_offers_cmd(update, context)
    elif data == 'my_deals':
        await my_deals_cmd(update, context)
    elif data == 'deposit':
        await query.edit_message_text("Пополнить баланс: /top_up [сумма]\nПример: /top_up 500")
    elif data == 'withdraw_hint':
        await query.edit_message_text("Вывести деньги: /withdraw [сумма] [реквизиты]\nПример: /withdraw 500 карта 1234")
    elif data == 'main_menu':
        await send_main_menu(update, query.from_user.id, message=query.message, edit=True)
    elif data.startswith('buy_page_'):
        page = int(data.split('_')[2])
        await buy_list(update, context, page)
    elif data == 'admin_menu' and query.from_user.id == ADMIN_ID:
        await query.edit_message_text(
            "Админ-команды:\n"
            "/admin_add_balance [user_id] [сумма]\n"
            "/admin_add_gigs [user_id] [ГБ]\n"
            "/approve_withdraw [id]\n"
            "/decline_withdraw [id]"
        )
    else:
        await query.edit_message_text("Неизвестная команда")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    # Команды
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
    app.add_handler(CommandHandler("top_up", top_up_cmd))
    app.add_handler(CommandHandler("withdraw", withdraw_cmd))
    # Админ
    app.add_handler(CommandHandler("admin_add_balance", admin_add_balance_cmd))
    app.add_handler(CommandHandler("admin_add_gigs", admin_add_gigs_cmd))
    app.add_handler(CommandHandler("approve_withdraw", approve_withdraw_cmd))
    app.add_handler(CommandHandler("decline_withdraw", decline_withdraw_cmd))
    # Обработчик контакта
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    # Любое другое сообщение — показываем меню
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))
    # Callback-запросы
    app.add_handler(CallbackQueryHandler(callback_handler))
    print("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
