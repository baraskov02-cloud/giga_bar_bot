import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes, ConversationHandler
)
import database as db

TOKEN = "8657499967:AAFq4WDXDCMCHyABu5Y7AeXMWSc8q7yZVQA"
ADMIN_ID = 6665494648
COMMISSION_PERCENT = 5.0
MAX_GB_PER_TRADE = 100
OPERATORS = ['МТС', 'Билайн', 'Мегафон', 'Tele2', 'Yota']

PHONE, OPERATOR, SELL_AMOUNT, SELL_PRICE, SELL_OPERATOR = range(5)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db.init_db()

def format_number(n):
    return f"{n:.2f}"

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
        f"🏪 GIGA BAR\n💰 Баланс: {format_number(user['balance'])} руб\n📦 Гиги: {format_number(user['gigs'])} ГБ\n📱 Телефон: {user['phone'] or 'не указан'}\n📡 Оператор: {user['operator'] or 'не указан'}\n\nКомиссия: {COMMISSION_PERCENT}%",
        reply_markup=reply_markup
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.username)
    
    user_data = db.get_user(user.id)
    if not user_data['phone']:
        contact_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Отправить номер", request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
        await update.message.reply_text(
            f"Добро пожаловать, {user.first_name}!\nНажмите кнопку, чтобы отправить номер телефона.",
            reply_markup=contact_keyboard
        )
        return PHONE
    
    await show_main_menu(update.message, user.id)
    return ConversationHandler.END

async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact:
        await update.message.reply_text("Используйте кнопку.")
        return PHONE
    
    phone = contact.phone_number
    db.update_user_phone(update.effective_user.id, phone, None)
    
    await update.message.reply_text(
        f"✅ Номер {phone} сохранён. Теперь выберите оператора:",
        reply_markup=ReplyKeyboardMarkup([[op for op in OPERATORS]], resize_keyboard=True)
    )
    return OPERATOR

async def receive_operator_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    operator = update.message.text
    if operator not in OPERATORS:
        await update.message.reply_text(f"Выберите из: {', '.join(OPERATORS)}")
        return OPERATOR
    
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    db.update_user_phone(user_id, user['phone'], operator)
    
    await update.message.reply_text(f"✅ Оператор {operator} сохранён!", reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True))
    await show_main_menu(update.message, user_id)
    return ConversationHandler.END

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = db.get_user(query.from_user.id)
    await query.edit_message_text(f"💰 Баланс: {format_number(user['balance'])} руб\n📦 Гиги: {format_number(user['gigs'])} ГБ")

async def sell_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите количество ГБ (макс 100):")
    return SELL_AMOUNT

async def sell_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        if amount <= 0 or amount > MAX_GB_PER_TRADE:
            await update.message.reply_text(f"От 1 до {MAX_GB_PER_TRADE} ГБ")
            return SELL_AMOUNT
    except:
        await update.message.reply_text("Введите число")
        return SELL_AMOUNT
    context.user_data['sell_amount'] = amount
    await update.message.reply_text("Введите цену за 1 ГБ (руб):")
    return SELL_PRICE

async def sell_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text)
        if price <= 0:
            raise ValueError
    except:
        await update.message.reply_text("Введите положительное число")
        return SELL_PRICE
    context.user_data['sell_price'] = price
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(op, callback_data=f'sell_op_{op}') for op in OPERATORS]])
    await update.message.reply_text("Выберите оператора:", reply_markup=keyboard)
    return SELL_OPERATOR

async def sell_operator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    operator = query.data.replace('sell_op_', '')
    user_id = query.from_user.id
    amount = context.user_data['sell_amount']
    price = context.user_data['sell_price']
    
    user = db.get_user(user_id)
    if user['gigs'] < amount:
        await query.edit_message_text(f"У вас только {format_number(user['gigs'])} ГБ")
        return ConversationHandler.END
    
    db.update_gigs(user_id, -amount)
    offer_id = db.add_offer(user_id, amount, price, operator)
    await query.edit_message_text(f"✅ Предложение #{offer_id} создано: {amount} ГБ по {price} руб/ГБ")
    return ConversationHandler.END

async def buy_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    offers = db.get_active_offers()
    if not offers:
        await query.edit_message_text("Нет активных предложений.")
        return
    text = "📦 Предложения:\n"
    for o in offers:
        text += f"#{o['offer_id']}: {o['amount']} ГБ × {o['price_per_gb']} руб = {format_number(o['total_price'])} руб | {o['operator']}\n"
    text += "\nКупить: /buy_offer [ID]"
    await query.edit_message_text(text)

async def buy_offer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/buy_offer [ID]")
        return
    try:
        offer_id = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    
    buyer_id = update.effective_user.id
    offer = db.get_offer_by_id(offer_id)
    if not offer:
        await update.message.reply_text("Предложение не найдено")
        return
    
    buyer = db.get_user(buyer_id)
    if not buyer['phone']:
        await update.message.reply_text("Сначала /start и укажите телефон")
        return
    
    if buyer['balance'] < offer['total_price']:
        await update.message.reply_text(f"Не хватает {format_number(offer['total_price'])} руб. /top_up")
        return
    
    commission = offer['total_price'] * COMMISSION_PERCENT / 100
    txn_id = db.add_transaction(buyer_id, offer['seller_id'], offer['amount'], offer['price_per_gb'], offer['total_price'], commission)
    db.update_balance(buyer_id, -offer['total_price'])
    db.delete_offer(offer_id)
    
    seller = db.get_user(offer['seller_id'])
    await context.bot.send_message(offer['seller_id'], f"🔔 Сделка #{txn_id}! Передайте {offer['amount']} ГБ на {buyer['phone']}. После отправки: /confirm_send {txn_id}")
    await update.message.reply_text(f"✅ Куплено {offer['amount']} ГБ. Ожидайте передачу. Подтвердите получение: /confirm_receive {txn_id}")

async def my_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    offers = db.get_active_offers()
    my = [o for o in offers if o['seller_id'] == user_id]
    if not my:
        await query.edit_message_text("Нет активных предложений")
        return
    text = "Ваши предложения:\n"
    for o in my:
        text += f"#{o['offer_id']}: {o['amount']} ГБ × {o['price_per_gb']} руб\n"
    await query.edit_message_text(text)

async def cancel_offer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/cancel_offer [ID]")
        return
    try:
        offer_id = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    user_id = update.effective_user.id
    offers = db.get_active_offers()
    offer = next((o for o in offers if o['offer_id'] == offer_id and o['seller_id'] == user_id), None)
    if not offer:
        await update.message.reply_text("Не найдено")
        return
    db.update_gigs(user_id, offer['amount'])
    db.delete_offer(offer_id)
    await update.message.reply_text(f"Предложение #{offer_id} отменено")

async def confirm_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/confirm_send [ID сделки]")
        return
    try:
        txn_id = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    user_id = update.effective_user.id
    txn = db.get_transaction(txn_id)
    if not txn or txn['seller_id'] != user_id:
        await update.message.reply_text("Не найдено")
        return
    if txn['seller_confirmed'] == 1:
        await update.message.reply_text("Уже подтверждено")
        return
    db.update_transaction_confirmation(txn_id, seller_confirmed=1)
    buyer = db.get_user(txn['buyer_id'])
    await context.bot.send_message(txn['buyer_id'], f"🔔 Продавец подтвердил отправку. Получили? /confirm_receive {txn_id}")
    await update.message.reply_text("✅ Отправка подтверждена")

async def confirm_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/confirm_receive [ID сделки]")
        return
    try:
        txn_id = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    user_id = update.effective_user.id
    txn = db.get_transaction(txn_id)
    if not txn or txn['buyer_id'] != user_id:
        await update.message.reply_text("Не найдено")
        return
    if txn['buyer_confirmed'] == 1:
        await update.message.reply_text("Уже подтверждено")
        return
    db.update_transaction_confirmation(txn_id, buyer_confirmed=1)
    txn2 = db.get_transaction(txn_id)
    if txn2['seller_confirmed'] == 1:
        db.complete_transaction(txn_id)
        seller = db.get_user(txn['seller_id'])
        await context.bot.send_message(txn['seller_id'], f"✅ Покупатель подтвердил. Деньги зачислены.")
        await update.message.reply_text("✅ Сделка завершена! Спасибо.")
    else:
        await update.message.reply_text("✅ Получение подтверждено. Ждём подтверждения от продавца.")

async def confirm_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    as_seller = db.get_pending_transactions_for_seller(user_id)
    as_buyer = db.get_pending_transactions_for_buyer(user_id)
    text = "✅ Подтверждение сделок:\n"
    for t in as_seller:
        text += f"Вы продавец: сделка #{t['txn_id']}, {t['amount']} ГБ. /confirm_send {t['txn_id']}\n"
    for t in as_buyer:
        text += f"Вы покупатель: сделка #{t['txn_id']}, {t['amount']} ГБ. /confirm_receive {t['txn_id']}\n"
    if not as_seller and not as_buyer:
        text = "Нет сделок на подтверждении."
    await query.edit_message_text(text)

async def top_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/top_up [сумма] (демо)")
        return
    try:
        amount = float(context.args[0])
        if amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("Сумма >0")
        return
    db.update_balance(update.effective_user.id, amount)
    await update.message.reply_text(f"💰 Пополнено на {format_number(amount)} руб (демо)")

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Настройки:\n/set_phone - изменить номер")

async def set_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await update.message.reply_text("Отправьте номер телефона кнопкой:", reply_markup=contact_keyboard)
    return PHONE

async def admin_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) != 2: return
    try:
        user_id = int(context.args[0])
        amount = float(context.args[1])
        db.update_balance(user_id, amount)
        await update.message.reply_text(f"Начислено {amount} руб пользователю {user_id}")
    except: pass

async def admin_add_gigs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) != 2: return
    try:
        user_id = int(context.args[0])
        gigs = float(context.args[1])
        db.update_gigs(user_id, gigs)
        await update.message.reply_text(f"Начислено {gigs} ГБ пользователю {user_id}")
    except: pass

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID: return
    keyboard = [[InlineKeyboardButton("Статистика", callback_data='admin_stats')]]
    await query.edit_message_text("Админ-панель", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID: return
    users = db.get_all_users()
    total_balance = sum(u['balance'] for u in users)
    await query.edit_message_text(f"Пользователей: {len(users)}\nОбщий баланс: {format_number(total_balance)} руб")

async def main():
    app = Application.builder().token(TOKEN).build()
    
    conv_phone = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHONE: [MessageHandler(filters.CONTACT, receive_contact)],
            OPERATOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_operator_text)],
        },
        fallbacks=[],
    )
    conv_sell = ConversationHandler(
        entry_points=[CallbackQueryHandler(sell_menu, pattern='^sell_menu$')],
        states={
            SELL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_amount)],
            SELL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_price)],
            SELL_OPERATOR: [CallbackQueryHandler(sell_operator, pattern='^sell_op_')],
        },
        fallbacks=[],
    )
    app.add_handler(conv_phone)
    app.add_handler(conv_sell)
    app.add_handler(CommandHandler("top_up", top_up))
    app.add_handler(CommandHandler("buy_offer", buy_offer_command))
    app.add_handler(CommandHandler("cancel_offer", cancel_offer_command))
    app.add_handler(CommandHandler("confirm_send", confirm_send))
    app.add_handler(CommandHandler("confirm_receive", confirm_receive))
    app.add_handler(CommandHandler("set_phone", set_phone))
    app.add_handler(CommandHandler("admin_add_balance", admin_add_balance))
    app.add_handler(CommandHandler("admin_add_gigs", admin_add_gigs))
    
    app.add_handler(CallbackQueryHandler(balance_command, pattern='^balance$'))
    app.add_handler(CallbackQueryHandler(buy_list, pattern='^buy$'))
    app.add_handler(CallbackQueryHandler(my_offers, pattern='^my_offers$'))
    app.add_handler(CallbackQueryHandler(settings_menu, pattern='^settings$'))
    app.add_handler(CallbackQueryHandler(confirm_menu, pattern='^confirm_menu$'))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern='^admin_panel$'))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern='^admin_'))
    
    print("🚀 GIGA BAR запущен")
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
