import logging
import asyncio
import requests
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import database as db

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8657499967:AAFq4WDXDCMCHyABu5Y7AeXMWSc8q7yZVQA"   # твой токен телеграм-бота
CRYPTOBOT_TOKEN = "583578:AA2YsU6vLEHBAvmwuuhWaK9XeFvi0WDlCzy" # токен от CryptoBot
ADMIN_ID = 6665494648
COMMISSION = 5

logging.basicConfig(level=logging.INFO)
db.init_db()

def fmt(n): return f"{n:.2f}"

# ========== МЕНЮ ==========
def get_main_menu_keyboard(user_id):
    kb = [
        [InlineKeyboardButton("💰 Баланс", callback_data='balance'),
         InlineKeyboardButton("📦 Мои гиги", callback_data='my_gigs')],
        [InlineKeyboardButton("📦 Продать гиги", callback_data='sell_start'),
         InlineKeyboardButton("🛒 Купить гиги", callback_data='buy_list')],
        [InlineKeyboardButton("📋 Мои объявления", callback_data='my_offers'),
         InlineKeyboardButton("🤝 Мои сделки", callback_data='my_deals')],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data='deposit'),
         InlineKeyboardButton("💸 Вывести деньги", callback_data='withdraw_start')],
    ]
    if user_id == ADMIN_ID:
        kb.append([InlineKeyboardButton("👑 Админ-панель", callback_data='admin_menu')])
    return InlineKeyboardMarkup(kb)

async def send_main_menu(update, user_id, message=None, edit=False):
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Ошибка. Напишите /start")
        return
    text = (
        f"🏪 GIGA BAR - Биржа гигабайт\n\n"
        f"💰 Баланс: {fmt(user['balance'])} руб\n"
        f"📦 Гиги: {fmt(user['gigs'])} ГБ\n"
        f"📱 Телефон: {user['phone'] or 'не указан'}\n"
        f"📡 Оператор: {user['operator'] or 'не указан'}\n"
        f"💸 Комиссия: {COMMISSION}%\n\n"
        f"Команды:\n"
        f"/sell [ГБ] [цена] - продать\n"
        f"/buy - список предложений\n"
        f"/my_offers - мои объявления\n"
        f"/my_deals - мои сделки\n"
        f"/withdraw [сумма] [реквизиты] - вывод"
    )
    if edit and message:
        await message.edit_text(text, reply_markup=get_main_menu_keyboard(user_id))
    elif message:
        await message.reply_text(text, reply_markup=get_main_menu_keyboard(user_id))
    else:
        await update.message.reply_text(text, reply_markup=get_main_menu_keyboard(user_id))

# ========== РЕГИСТРАЦИЯ ==========
async def start(update, context):
    user = update.effective_user
    db.register_user(user.id, user.username)
    u = db.get_user(user.id)
    if not u['phone']:
        contact_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Отправить номер", request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
        await update.message.reply_text(
            "Добро пожаловать!\nНажмите кнопку, чтобы отправить номер телефона.\n"
            "Затем укажите оператора командой /set_operator",
            reply_markup=contact_keyboard
        )
        return
    await send_main_menu(update, user.id)

async def contact_handler(update, context):
    contact = update.message.contact
    if not contact:
        await update.message.reply_text("Используйте кнопку.")
        return
    phone = contact.phone_number
    uid = update.effective_user.id
    user = db.get_user(uid)
    db.update_user_phone(uid, phone, user['operator'] if user else None)
    await update.message.reply_text(f"Номер {phone} сохранён.\nТеперь укажите оператора: /set_operator", reply_markup=ReplyKeyboardRemove())
    await send_main_menu(update, uid)

async def set_phone(update, context):
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

async def set_operator(update, context):
    if not context.args:
        await update.message.reply_text("Пример: /set_operator МТС")
        return
    op = context.args[0].strip()
    if op not in ['МТС', 'Билайн', 'Мегафон', 'Tele2', 'Yota']:
        await update.message.reply_text("Оператор: МТС, Билайн, Мегафон, Tele2, Yota")
        return
    uid = update.effective_user.id
    user = db.get_user(uid)
    db.update_user_phone(uid, user['phone'] if user else None, op)
    await update.message.reply_text(f"Оператор {op} сохранён.")
    await send_main_menu(update, uid)

# ========== БАЛАНС И ГИГИ ==========
async def balance_cmd(update, context):
    user = db.get_user(update.effective_user.id)
    await update.message.reply_text(f"Ваш баланс: {fmt(user['balance'])} руб")

async def my_gigs_cmd(update, context):
    user = db.get_user(update.effective_user.id)
    await update.message.reply_text(f"Ваши гиги: {fmt(user['gigs'])} ГБ")

# ========== ПРОДАЖА (ЛОТЫ) ==========
async def sell_start(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите количество ГБ (до 100):")
    context.user_data['step'] = 'sell_amount'

async def sell_amount(update, context):
    try:
        amount = float(update.message.text)
        if amount <= 0 or amount > 100:
            raise ValueError
        context.user_data['sell_amount'] = amount
        await update.message.reply_text("Введите цену за 1 ГБ (руб):")
        context.user_data['step'] = 'sell_price'
    except:
        await update.message.reply_text("Ошибка. Введите число от 1 до 100.")

async def sell_price(update, context):
    try:
        price = float(update.message.text)
        if price <= 0:
            raise ValueError
        uid = update.effective_user.id
        amount = context.user_data['sell_amount']
        user = db.get_user(uid)
        if user['gigs'] < amount:
            await update.message.reply_text(f"У вас только {fmt(user['gigs'])} ГБ. Пополните гиги у админа.")
            return
        if not user['operator']:
            await update.message.reply_text("Сначала укажите оператора: /set_operator")
            return
        db.update_gigs(uid, -amount)
        oid = db.add_offer(uid, amount, price, user['operator'])
        await update.message.reply_text(f"✅ Объявление #{oid} создано: {amount} ГБ по {price} руб/ГБ. Итого {fmt(amount*price)} руб")
        context.user_data.clear()
    except:
        await update.message.reply_text("Ошибка. Введите цену (число >0).")

# ========== ПОКУПКА (С ПАГИНАЦИЕЙ) ==========
PAGE_SIZE = 5

async def buy_list(update, context, page=0):
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
    text = "📦 Предложения (напишите ID для покупки):\n\n"
    for o in page_offers:
        seller = db.get_user(o['seller_id'])
        seller_name = seller['username'] if seller else str(o['seller_id'])
        text += f"ID {o['offer_id']}: {o['amount']} ГБ x {o['price_per_gb']} руб = {fmt(o['total_price'])} руб | {o['operator']} | от @{seller_name}\n"
    text += f"\nСтраница {page+1}/{total_pages}"
    keyboard = []
    if page > 0:
        keyboard.append(InlineKeyboardButton("◀ Назад", callback_data=f'buy_page_{page-1}'))
    if page < total_pages - 1:
        keyboard.append(InlineKeyboardButton("Вперёд ▶", callback_data=f'buy_page_{page+1}'))
    keyboard.append(InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu'))
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([keyboard]))

async def buy_offer_cmd(update, context):
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
        await update.message.reply_text(f"Не хватает {fmt(offer['total_price'])} руб. Пополните баланс через кнопку 'Пополнить'.")
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
        f"🔔 НОВАЯ СДЕЛКА #{txn}\n"
        f"Покупатель: @{buyer['username']}\n"
        f"Объём: {offer['amount']} ГБ\n"
        f"Сумма: {fmt(offer['total_price'])} руб\n"
        f"Телефон покупателя: {buyer['phone']}\n\n"
        f"📲 Передайте гиги через: {ussd}\n"
        f"После отправки нажмите /confirm_send {txn}"
    )
    await update.message.reply_text(
        f"✅ Вы купили {offer['amount']} ГБ.\n"
        f"Деньги заморожены. Когда получите гиги, подтвердите: /confirm_receive {txn}"
    )

# ========== ПОДТВЕРЖДЕНИЕ ==========
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
    await context.bot.send_message(buyer['user_id'], f"🔔 Продавец подтвердил отправку {txn_data['amount']} ГБ. Если получили, нажмите /confirm_receive {txn}")
    await update.message.reply_text("✅ Отправка подтверждена. Ожидаем покупателя.")

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
        await context.bot.send_message(seller['user_id'], f"✅ Покупатель подтвердил получение {txn_data['amount']} ГБ. Вам зачислено {fmt(txn_data['total_amount'] - txn_data['commission'])} руб.")
        await update.message.reply_text("✅ Сделка завершена!")
    else:
        await update.message.reply_text("✅ Получение подтверждено. Ждём продавца.")

# ========== МОИ ОБЪЯВЛЕНИЯ И СДЕЛКИ ==========
async def my_offers_cmd(update, context):
    uid = update.effective_user.id
    offers = db.get_active_offers()
    mine = [o for o in offers if o['seller_id'] == uid]
    if not mine:
        await update.message.reply_text("У вас нет активных объявлений.")
        return
    text = "📋 Ваши объявления:\n"
    for o in mine:
        text += f"ID {o['offer_id']}: {o['amount']} ГБ x {o['price_per_gb']} руб = {fmt(o['total_price'])} руб | {o['operator']}\n"
    text += "\nОтменить: /cancel_offer [ID]"
    await update.message.reply_text(text)

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

async def my_deals_cmd(update, context):
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
    text = "📜 Последние сделки:\n"
    for r in rows:
        text += f"#{r[0]}: {r[1]} ГБ, {fmt(r[2])} руб, {r[3]}, {r[4][:10]}\n"
    await update.message.reply_text(text)

# ========== ВЫВОД ДЕНЕГ ==========
async def withdraw_start(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите сумму и реквизиты одной командой:\n/withdraw [сумма] [реквизиты]\nПример: /withdraw 500 карта 1234")

async def withdraw_cmd(update, context):
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
    await context.bot.send_message(ADMIN_ID, f"📨 Заявка на вывод #{req_id}\nОт @{update.effective_user.username} (ID {uid})\nСумма: {fmt(amount)} руб\nРеквизиты: {details}")
    await update.message.reply_text(f"✅ Заявка #{req_id} отправлена администратору.")

# ========== ОПЛАТА ЧЕРЕЗ CRYPTOBOT ==========
async def deposit_menu(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💳 Пополнение баланса через CryptoBot\n\nВыберите сумму (в рублях):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("100 руб", callback_data='topup_100')],
            [InlineKeyboardButton("500 руб", callback_data='topup_500')],
            [InlineKeyboardButton("1000 руб", callback_data='topup_1000')],
            [InlineKeyboardButton("Назад", callback_data='main_menu')]
        ])
    )

async def create_invoice(amount_rub):
    # Упрощённый курс: 1 USDT = 100 руб
    amount_usdt = amount_rub / 100
    url = "https://pay.crypt.bot/api/createInvoice"
    payload = {
        "asset": "USDT",
        "amount": str(amount_usdt),
        "description": f"Пополнение баланса GIGA BAR на {amount_rub} руб",
        "paid_btn_name": "callback",
        "paid_btn_url": f"https://t.me/ваш_бот"
    }
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                return data['result']['bot_invoice_url']
    except Exception as e:
        logging.error(f"CryptoBot error: {e}")
    return None

async def topup_callback(update, context):
    query = update.callback_query
    await query.answer()
    amount_rub = int(query.data.split('_')[1])
    invoice_url = await create_invoice(amount_rub)
    if invoice_url:
        # Сохраняем информацию об ожидаемой оплате (в данном случае просто запоминаем)
        context.user_data['expected_payment'] = {'user_id': query.from_user.id, 'amount': amount_rub}
        await query.edit_message_text(
            f"✅ Счёт создан!\n"
            f"Сумма: {amount_rub} руб (≈ {amount_rub/100:.2f} USDT)\n"
            f"Оплатите по ссылке:\n{invoice_url}\n\n"
            f"После оплаты нажмите кнопку 'Я оплатил', и администратор зачислит средства.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Я оплатил", callback_data='payment_done')],
                [InlineKeyboardButton("Назад", callback_data='main_menu')]
            ])
        )
    else:
        await query.edit_message_text("Ошибка создания счёта. Попробуйте позже.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data='main_menu')]]))

async def payment_done(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    # Отправляем уведомление админу
    await context.bot.send_message(
        ADMIN_ID,
        f"💰 ПОСТУПИЛА ЗАЯВКА НА ПОПОЛНЕНИЕ\n"
        f"Пользователь: @{query.from_user.username} (ID {user_id})\n"
        f"Сумма: {context.user_data.get('expected_payment', {}).get('amount', 'неизвестно')} руб\n"
        f"Проверьте оплату в CryptoBot и начислите вручную командой /admin_add_balance {user_id} [сумма]"
    )
    await query.edit_message_text(
        "✅ Заявка отправлена администратору. Ожидайте зачисления в ближайшее время.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Главное меню", callback_data='main_menu')]])
    )

# ========== АДМИН-КОМАНДЫ ==========
async def admin_menu(update, context):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("Нет доступа")
        return
    await query.edit_message_text(
        "👑 Админ-панель\n\n"
        "Команды:\n"
        "/admin_add_balance [user_id] [сумма]\n"
        "/admin_add_gigs [user_id] [ГБ]\n"
        "/approve_withdraw [id]\n"
        "/decline_withdraw [id]"
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

async def approve_withdraw_cmd(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: return
    try:
        rid = int(context.args[0])
        db.update_withdraw_request(rid, 'approved')
        await update.message.reply_text(f"Заявка #{rid} одобрена")
    except: pass

async def decline_withdraw_cmd(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: return
    try:
        rid = int(context.args[0])
        db.update_withdraw_request(rid, 'declined')
        await update.message.reply_text(f"Заявка #{rid} отклонена")
    except: pass

# ========== CALLBACK-ОБРАБОТЧИК ==========
async def callback_handler(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'balance':
        user = db.get_user(query.from_user.id)
        await query.edit_message_text(f"💰 Ваш баланс: {fmt(user['balance'])} руб")
    elif data == 'my_gigs':
        user = db.get_user(query.from_user.id)
        await query.edit_message_text(f"📦 Ваши гиги: {fmt(user['gigs'])} ГБ")
    elif data == 'sell_start':
        await query.edit_message_text("Введите количество ГБ (до 100):")
        context.user_data['step'] = 'sell_amount'
    elif data == 'buy_list':
        await buy_list(update, context, 0)
    elif data == 'my_offers':
        await my_offers_cmd(update, context)
    elif data == 'my_deals':
        await my_deals_cmd(update, context)
    elif data == 'deposit':
        await deposit_menu(update, context)
    elif data == 'withdraw_start':
        await withdraw_start(update, context)
    elif data == 'main_menu':
        await send_main_menu(update, query.from_user.id, message=query.message, edit=True)
    elif data.startswith('buy_page_'):
        page = int(data.split('_')[2])
        await buy_list(update, context, page)
    elif data.startswith('topup_'):
        await topup_callback(update, context)
    elif data == 'payment_done':
        await payment_done(update, context)
    elif data == 'admin_menu' and query.from_user.id == ADMIN_ID:
        await admin_menu(update, context)
    else:
        await query.edit_message_text("Неизвестная команда")

# ========== ОБРАБОТЧИК ЛЮБЫХ СООБЩЕНИЙ ==========
async def any_message(update, context):
    if update.message and not update.message.text.startswith('/'):
        # Если это шаги продажи
        if context.user_data.get('step') == 'sell_amount':
            await sell_amount(update, context)
        elif context.user_data.get('step') == 'sell_price':
            await sell_price(update, context)
        else:
            await send_main_menu(update, update.effective_user.id)

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set_phone", set_phone))
    app.add_handler(CommandHandler("set_operator", set_operator))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("my_gigs", my_gigs_cmd))
    app.add_handler(CommandHandler("sell", sell_start))
    app.add_handler(CommandHandler("buy_offer", buy_offer_cmd))
    app.add_handler(CommandHandler("my_offers", my_offers_cmd))
    app.add_handler(CommandHandler("cancel_offer", cancel_offer_cmd))
    app.add_handler(CommandHandler("my_deals", my_deals_cmd))
    app.add_handler(CommandHandler("confirm_send", confirm_send_cmd))
    app.add_handler(CommandHandler("confirm_receive", confirm_receive_cmd))
    app.add_handler(CommandHandler("withdraw", withdraw_cmd))
    app.add_handler(CommandHandler("admin_add_balance", admin_add_balance_cmd))
    app.add_handler(CommandHandler("admin_add_gigs", admin_add_gigs_cmd))
    app.add_handler(CommandHandler("approve_withdraw", approve_withdraw_cmd))
    app.add_handler(CommandHandler("decline_withdraw", decline_withdraw_cmd))

    # Контакт
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    # Любые сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))
    # Колбэки
    app.add_handler(CallbackQueryHandler(callback_handler))

    print("🚀 GIGA BAR с оплатой CryptoBot запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
