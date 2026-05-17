import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes, ConversationHandler
)
import database as db

TOKEN = "8657499967:AAFq4WDXDCMCHyABu5Y7AeXMWSc8q7yZVQA"
ADMIN_ID = 6665494648
COMMISSION_PERCENT = 5.0
MAX_GB_PER_TRADE = 100
OPERATORS = ['МТС', 'Билайн', 'Мегафон', 'Tele2']

# Состояния для разговоров
PHONE, OPERATOR, SELL_AMOUNT, SELL_PRICE, SELL_OPERATOR = range(5)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db.init_db()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_user_link(user_id):
    return f"[Пользователь](tg://user?id={user_id})"

def format_number(n):
    return f"{n:.2f}"

# ========== КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.username)
    
    # Проверяем, есть ли у пользователя телефон
    user_data = db.get_user(user.id)
    if not user_data['phone']:
        await update.message.reply_text(
            f"Добро пожаловать в GIGA BAR, {user.first_name}!\n\n"
            "🔐 Для работы с биржей нужно указать номер телефона и оператора.\n"
            "Отправьте ваш номер телефона (например: 79123456789)"
        )
        return PHONE
    
    await show_main_menu(update.message, user.id)

async def show_main_menu(message, user_id):
    user = db.get_user(user_id)
    keyboard = [
        [InlineKeyboardButton("💰 Баланс и гиги", callback_data='balance')],
        [InlineKeyboardButton("📦 Продать гиги", callback_data='sell_menu')],
        [InlineKeyboardButton("🛒 Купить гиги", callback_data='buy')],
        [InlineKeyboardButton("📋 Мои предложения", callback_data='my_offers')],
        [InlineKeyboardButton("✅ Подтвердить сделку", callback_data='confirm_menu')],
        [InlineKeyboardButton("🔧 Настройки", callback_data='settings')],
    ]
    if user['user_id'] == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data='admin_panel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(
        f"🏪 GIGA BAR — биржа реального трафика\n\n"
        f"💰 Баланс: {format_number(user['balance'])} руб\n"
        f"📦 Гигабайт: {format_number(user['gigs'])} ГБ\n"
        f"📱 Телефон: {user['phone'] or 'не указан'}\n"
        f"📡 Оператор: {user['operator'] or 'не указан'}\n\n"
        f"Комиссия биржи: {COMMISSION_PERCENT}%",
        reply_markup=reply_markup
    )

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = db.get_user(query.from_user.id)
    await query.edit_message_text(
        f"💰 Ваш баланс: {format_number(user['balance'])} руб\n"
        f"📦 Ваши гиги: {format_number(user['gigs'])} ГБ\n\n"
        f"Пополнить баланс: /top_up [сумма] (демо-режим)"
    )

async def sell_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📦 Продажа гигабайт\n\n"
        "Введите количество ГБ (макс 100 ГБ):\n"
        "Пример: 50"
    )
    return SELL_AMOUNT

async def sell_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        if amount <= 0 or amount > MAX_GB_PER_TRADE:
            await update.message.reply_text(f"Количество должно быть от 1 до {MAX_GB_PER_TRADE} ГБ")
            return SELL_AMOUNT
    except:
        await update.message.reply_text("Введите число, например: 30")
        return SELL_AMOUNT
    
    context.user_data['sell_amount'] = amount
    await update.message.reply_text("Введите цену за 1 ГБ в рублях:\nПример: 15")
    return SELL_PRICE

async def sell_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text)
        if price <= 0:
            raise ValueError
    except:
        await update.message.reply_text("Введите положительное число, например: 15")
        return SELL_PRICE
    
    context.user_data['sell_price'] = price
    await update.message.reply_text(
        f"Выберите оператора:\n" + "\n".join([f"{i+1}. {op}" for i, op in enumerate(OPERATORS)]),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(op, callback_data=f'sell_op_{op}') for op in OPERATORS]
        ])
    )
    return SELL_OPERATOR

async def sell_operator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    operator = query.data.replace('sell_op_', '')
    user_id = query.from_user.id
    amount = context.user_data['sell_amount']
    price = context.user_data['sell_price']
    total = amount * price
    
    # Проверяем, есть ли гиги у продавца
    user = db.get_user(user_id)
    if user['gigs'] < amount:
        await query.edit_message_text(f"У вас только {format_number(user['gigs'])} ГБ. Недостаточно!")
        return ConversationHandler.END
    
    # Создаём предложение
    db.update_gigs(user_id, -amount)
    offer_id = db.add_offer(user_id, amount, price, operator)
    
    await query.edit_message_text(
        f"✅ Предложение #{offer_id} создано!\n"
        f"📦 {amount} ГБ\n"
        f"💰 {price} руб/ГБ\n"
        f"📡 {operator}\n"
        f"💵 Итого: {format_number(total)} руб\n\n"
        f"Покупатели увидят ваше предложение в /buy"
    )
    return ConversationHandler.END

async def buy_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    offers = db.get_active_offers()
    if not offers:
        await query.edit_message_text("📭 Нет активных предложений.")
        return
    
    text = "📦 Доступные предложения:\n\n"
    for o in offers:
        text += f"#{o['offer_id']}: {o['amount']} ГБ × {o['price_per_gb']} руб = {format_number(o['total_price'])} руб | {o['operator']}\n"
    text += "\nДля покупки: /buy_offer [ID]"
    await query.edit_message_text(text)

async def buy_offer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /buy_offer [ID предложения]")
        return
    try:
        offer_id = int(context.args[0])
    except:
        await update.message.reply_text("ID должно быть числом")
        return
    
    buyer_id = update.effective_user.id
    offer = db.get_offer_by_id(offer_id)
    if not offer:
        await update.message.reply_text("Предложение не найдено или уже куплено.")
        return
    
    buyer = db.get_user(buyer_id)
    if not buyer['phone']:
        await update.message.reply_text("Сначала укажите телефон и оператора в /start")
        return
    
    if buyer['balance'] < offer['total_price']:
        await update.message.reply_text(f"Недостаточно средств. Нужно {format_number(offer['total_price'])} руб.\nПополните баланс: /top_up [сумма]")
        return
    
    # Создаём транзакцию
    commission = offer['total_price'] * COMMISSION_PERCENT / 100
    txn_id = db.add_transaction(buyer_id, offer['seller_id'], offer['amount'], offer['price_per_gb'], offer['total_price'], commission)
    
    # Списываем деньги у покупателя
    db.update_balance(buyer_id, -offer['total_price'])
    
    # Удаляем предложение
    db.delete_offer(offer_id)
    
    seller = db.get_user(offer['seller_id'])
    
    # Уведомляем продавца
    await context.bot.send_message(
        offer['seller_id'],
        f"🔔 У вас новая сделка #{txn_id}!\n"
        f"Покупатель: {get_user_link(buyer_id)}\n"
        f"Объём: {offer['amount']} ГБ\n"
        f"Сумма: {format_number(offer['total_price'])} руб\n\n"
        f"📌 Передайте гиги покупателю на номер {buyer['phone']} ({buyer['operator']})\n"
        f"Способ передачи: USSD-команда или приложение оператора.\n\n"
        f"✅ После отправки нажмите /confirm_send {txn_id}"
    )
    
    await update.message.reply_text(
        f"✅ Вы купили {offer['amount']} ГБ!\n"
        f"💰 Оплачено: {format_number(offer['total_price'])} руб\n"
        f"📡 Оператор продавца: {offer['operator']}\n\n"
        f"Ожидайте, продавец передаст гиги на ваш номер {buyer['phone']}\n"
        f"🔔 Когда получите гиги, подтвердите: /confirm_receive {txn_id}"
    )

async def my_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    offers = db.get_active_offers()
    my = [o for o in offers if o['seller_id'] == user_id]
    if not my:
        await query.edit_message_text("У вас нет активных предложений.")
        return
    text = "📋 Ваши предложения:\n\n"
    for o in my:
        text += f"#{o['offer_id']}: {o['amount']} ГБ × {o['price_per_gb']} руб = {format_number(o['total_price'])} руб | {o['operator']}\n"
    text += "\nОтменить: /cancel_offer [ID]"
    await query.edit_message_text(text)

async def cancel_offer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /cancel_offer [ID]")
        return
    try:
        offer_id = int(context.args[0])
    except:
        await update.message.reply_text("ID должно быть числом")
        return
    
    user_id = update.effective_user.id
    offers = db.get_active_offers()
    offer = next((o for o in offers if o['offer_id'] == offer_id and o['seller_id'] == user_id), None)
    if not offer:
        await update.message.reply_text("Предложение не найдено или не принадлежит вам.")
        return
    
    db.update_gigs(user_id, offer['amount'])
    db.delete_offer(offer_id)
    await update.message.reply_text(f"Предложение #{offer_id} отменено. Гиги возвращены.")

async def confirm_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /confirm_send [ID транзакции]")
        return
    try:
        txn_id = int(context.args[0])
    except:
        await update.message.reply_text("ID должно быть числом")
        return
    
    user_id = update.effective_user.id
    txn = db.get_transaction(txn_id)
    if not txn or txn['seller_id'] != user_id:
        await update.message.reply_text("Транзакция не найдена или не относится к вам.")
        return
    
    if txn['seller_confirmed'] == 1:
        await update.message.reply_text("Вы уже подтвердили отправку.")
        return
    
    db.update_transaction_confirmation(txn_id, seller_confirmed=1)
    
    # Уведомляем покупателя
    buyer = db.get_user(txn['buyer_id'])
    await context.bot.send_message(
        txn['buyer_id'],
        f"🔔 Продавец подтвердил отправку {txn['amount']} ГБ!\n"
        f"Проверьте баланс своего телефона.\n"
        f"✅ Если гиги пришли, подтвердите: /confirm_receive {txn_id}"
    )
    
    await update.message.reply_text(f"✅ Вы подтвердили отправку по сделке #{txn_id}. Ожидаем подтверждения от покупателя.")

async def confirm_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /confirm_receive [ID транзакции]")
        return
    try:
        txn_id = int(context.args[0])
    except:
        await update.message.reply_text("ID должно быть числом")
        return
    
    user_id = update.effective_user.id
    txn = db.get_transaction(txn_id)
    if not txn or txn['buyer_id'] != user_id:
        await update.message.reply_text("Транзакция не найдена или не относится к вам.")
        return
    
    if txn['buyer_confirmed'] == 1:
        await update.message.reply_text("Вы уже подтвердили получение.")
        return
    
    db.update_transaction_confirmation(txn_id, buyer_confirmed=1)
    
    # Если продавец тоже подтвердил — завершаем сделку
    txn_updated = db.get_transaction(txn_id)
    if txn_updated['seller_confirmed'] == 1:
        db.complete_transaction(txn_id)
        seller = db.get_user(txn['seller_id'])
        await update.message.reply_text(
            f"✅ Сделка #{txn_id} завершена!\n"
            f"Деньги переведены продавцу.\n"
            f"Спасибо за использование GIGA BAR!"
        )
        await context.bot.send_message(
            txn['seller_id'],
            f"✅ Покупатель подтвердил получение {txn['amount']} ГБ!\n"
            f"💰 {format_number(txn['total_amount'] - txn['commission'])} руб зачислены на ваш баланс.\n"
            f"Вывести: /withdraw"
        )
    else:
        await update.message.reply_text(
            f"✅ Вы подтвердили получение по сделке #{txn_id}.\n"
            f"Ожидаем, когда продавец подтвердит отправку."
        )

async def top_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /top_up [сумма] (демо-режим)")
        return
    try:
        amount = float(context.args[0])
        if amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("Сумма должна быть положительным числом")
        return
    
    db.update_balance(update.effective_user.id, amount)
    await update.message.reply_text(f"💰 Баланс пополнен на {format_number(amount)} руб. (демо-режим)")

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔧 Настройки\n\n"
        "/set_phone — изменить номер телефона\n"
        "/set_operator — изменить оператора"
    )

async def set_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправьте ваш номер телефона (пример: 79123456789)")
    return PHONE

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not phone.isdigit() or len(phone) < 10:
        await update.message.reply_text("Неверный формат. Пример: 79123456789")
        return PHONE
    
    db.update_user_phone(update.effective_user.id, phone, None)
    await update.message.reply_text("✅ Номер сохранён. Теперь укажите оператора.")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(op, callback_data=f'set_op_{op}') for op in OPERATORS]
    ])
    await update.message.reply_text("Выберите оператора:", reply_markup=keyboard)
    return OPERATOR

async def receive_operator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    operator = query.data.replace('set_op_', '')
    user_id = query.from_user.id
    user = db.get_user(user_id)
    db.update_user_phone(user_id, user['phone'], operator)
    await query.edit_message_text(f"✅ Оператор {operator} сохранён!")
    await show_main_menu(query.message, user_id)
    return ConversationHandler.END

# ========== АДМИН-ПАНЕЛЬ ==========
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("Нет доступа")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')],
        [InlineKeyboardButton("👥 Пользователи", callback_data='admin_users')],
        [InlineKeyboardButton("💰 Начислить баланс", callback_data='admin_add_balance')],
        [InlineKeyboardButton("📦 Начислить гиги", callback_data='admin_add_gigs')],
    ]
    await query.edit_message_text("👑 Админ-панель", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    
    data = query.data
    if data == 'admin_stats':
        users = db.get_all_users()
        total_balance = sum(u['balance'] for u in users)
        total_gigs = sum(u['gigs'] for u in users)
        await query.edit_message_text(
            f"📊 Статистика GIGA BAR\n\n"
            f"👥 Пользователей: {len(users)}\n"
            f"💰 Общий баланс: {format_number(total_balance)} руб\n"
            f"📦 Всего гигов: {format_number(total_gigs)} ГБ"
        )
    elif data == 'admin_users':
        users = db.get_all_users()
        text = "👥 Пользователи:\n\n"
        for u in users[:20]:
            text += f"ID: {u['user_id']} | @{u['username']} | {format_number(u['balance'])} руб | {format_number(u['gigs'])} ГБ\n"
        await query.edit_message_text(text[:4000])
    elif data == 'admin_add_balance':
        await query.edit_message_text("Используйте команду: /admin_add_balance [user_id] [сумма]")
    elif data == 'admin_add_gigs':
        await query.edit_message_text("Используйте команду: /admin_add_gigs [user_id] [ГБ]")

async def admin_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) != 2:
        await update.message.reply_text("Использование: /admin_add_balance [user_id] [сумма]")
        return
    try:
        user_id = int(context.args[0])
        amount = float(context.args[1])
    except:
        await update.message.reply_text("Ошибка ввода")
        return
    db.update_balance(user_id, amount)
    await update.message.reply_text(f"✅ Пользователю {user_id} начислено {format_number(amount)} руб")
    await context.bot.send_message(user_id, f"💰 Админ начислил вам {format_number(amount)} руб на баланс!")

async def admin_add_gigs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) != 2:
        await update.message.reply_text("Использование: /admin_add_gigs [user_id] [ГБ]")
        return
    try:
        user_id = int(context.args[0])
        gigs = float(context.args[1])
    except:
        await update.message.reply_text("Ошибка ввода")
        return
    db.update_gigs(user_id, gigs)
    await update.message.reply_text(f"✅ Пользователю {user_id} начислено {format_number(gigs)} ГБ")
    await context.bot.send_message(user_id, f"📦 Админ начислил вам {format_number(gigs)} ГБ!")

# ========== ОСНОВНОЙ ЗАПУСК ==========
async def main():
    app = Application.builder().token(TOKEN).build()
    
    # Регистрация команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("top_up", top_up))
    app.add_handler(CommandHandler("buy_offer", buy_offer_command))
    app.add_handler(CommandHandler("cancel_offer", cancel_offer_command))
    app.add_handler(CommandHandler("confirm_send", confirm_send))
    app.add_handler(CommandHandler("confirm_receive", confirm_receive))
    app.add_handler(CommandHandler("set_phone", set_phone))
    app.add_handler(CommandHandler("admin_add_balance", admin_add_balance))
    app.add_handler(CommandHandler("admin_add_gigs", admin_add_gigs))
    
    # Обработчики inline кнопок
    app.add_handler(CallbackQueryHandler(balance_command, pattern='^balance$'))
    app.add_handler(CallbackQueryHandler(sell_menu, pattern='^sell_menu$'))
    app.add_handler(CallbackQueryHandler(buy_list, pattern='^buy$'))
    app.add_handler(CallbackQueryHandler(my_offers, pattern='^my_offers$'))
    app.add_handler(CallbackQueryHandler(settings_menu, pattern='^settings$'))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern='^admin_panel$'))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern='^admin_'))
    app.add_handler(CallbackQueryHandler(sell_operator, pattern='^sell_op_'))
    app.add_handler(CallbackQueryHandler(receive_operator, pattern='^set_op_'))
    app.add_handler(CallbackQueryHandler(confirm_menu, pattern='^confirm_menu$'))
    
    # Разговор для продажи
    conv_sell = ConversationHandler(
        entry_points=[CallbackQueryHandler(sell_menu, pattern='^sell_menu$')],
        states={
            SELL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_amount)],
            SELL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_price)],
            SELL_OPERATOR: [CallbackQueryHandler(sell_operator, pattern='^sell_op_')],
        },
        fallbacks=[],
    )
    
    # Разговор для настроек телефона
    conv_phone = ConversationHandler(
        entry_points=[CommandHandler("set_phone", set_phone)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            OPERATOR: [CallbackQueryHandler(receive_operator, pattern='^set_op_')],
        },
        fallbacks=[],
    )
    
    app.add_handler(conv_sell)
    app.add_handler(conv_phone)
    
    print("🚀 GIGA BAR запущен!")
    print(f"👑 Админ ID: {ADMIN_ID}")
    print(f"💸 Комиссия: {COMMISSION_PERCENT}%")
    print(f"📦 Макс ГБ в сделке: {MAX_GB_PER_TRADE}")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())