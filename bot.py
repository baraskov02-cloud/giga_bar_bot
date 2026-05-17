import logging
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes, ConversationHandler
)
import database as db

# === НАСТРОЙКИ ===
TOKEN = "8657499967:AAFq4WDXDCMCHyABu5Y7AeXMWSc8q7yZVQA"
ADMIN_ID = 6665494648
COMMISSION_PERCENT = 5.0
MAX_GB_PER_TRADE = 100
OPERATORS = ['МТС', 'Билайн', 'Мегафон', 'Tele2', 'Yota']

# === СОСТОЯНИЯ ДЛЯ РАЗГОВОРОВ ===
PHONE, OPERATOR, SELL_AMOUNT, SELL_PRICE, SELL_OPERATOR = range(5)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db.init_db()

def fmt(n):
    return f"{n:.2f}"

async def main_menu(message, user_id):
    user = db.get_user(user_id)
    keyboard = [
        [InlineKeyboardButton("💰 Баланс", callback_data='balance')],
        [InlineKeyboardButton("📦 Продать гиги", callback_data='sell_menu')],
        [InlineKeyboardButton("🛒 Купить гиги", callback_data='buy')],
        [InlineKeyboardButton("📋 Мои объявления", callback_data='my_offers')],
        [InlineKeyboardButton("✅ Подтвердить сделку", callback_data='confirm_menu')],
        [InlineKeyboardButton("⚙️ Настройки", callback_data='settings')],
    ]
    if user['user_id'] == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data='admin_panel')])
    
    await message.reply_text(
        f"🏪 *GIGA BAR — биржа гигабайт*\n\n"
        f"💰 Баланс: `{fmt(user['balance'])}` руб\n"
        f"📦 Гиги: `{fmt(user['gigs'])}` ГБ\n"
        f"📱 Телефон: `{user['phone'] or 'не указан'}`\n"
        f"📡 Оператор: `{user['operator'] or 'не указан'}`\n\n"
        f"💸 Комиссия: {COMMISSION_PERCENT}%",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.username)
    
    if not db.get_user(user.id)['phone']:
        btn = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Отправить номер", request_contact=True)]],
            resize_keyboard=True
        )
        await update.message.reply_text(
            f"Привет, {user.first_name}!\nНажми кнопку, чтобы указать номер.",
            reply_markup=btn
        )
        return PHONE
    await main_menu(update.message, user.id)
    return ConversationHandler.END

async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact:
        await update.message.reply_text("Используйте кнопку.")
        return PHONE
    db.update_user_phone(update.effective_user.id, contact.phone_number, None)
    await update.message.reply_text(
        "Теперь выберите оператора:",
        reply_markup=ReplyKeyboardMarkup([[op for op in OPERATORS]], resize_keyboard=True)
    )
    return OPERATOR

async def receive_operator_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    op = update.message.text
    if op not in OPERATORS:
        await update.message.reply_text(f"Выберите из списка: {', '.join(OPERATORS)}")
        return OPERATOR
    uid = update.effective_user.id
    user = db.get_user(uid)
    db.update_user_phone(uid, user['phone'], op)
    await update.message.reply_text(f"✅ Оператор {op} сохранён.", reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True))
    await main_menu(update.message, uid)
    return ConversationHandler.END

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    u = db.get_user(q.from_user.id)
    await q.edit_message_text(f"💰 Баланс: {fmt(u['balance'])} руб\n📦 Гиги: {fmt(u['gigs'])} ГБ")

async def sell_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("📦 Введите количество ГБ (до 100):")
    return SELL_AMOUNT

async def sell_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        a = float(update.message.text)
        if a <= 0 or a > MAX_GB_PER_TRADE:
            raise ValueError
    except:
        await update.message.reply_text(f"Число от 1 до {MAX_GB_PER_TRADE}")
        return SELL_AMOUNT
    context.user_data['amount'] = a
    await update.message.reply_text("💰 Цена за 1 ГБ (руб):")
    return SELL_PRICE

async def sell_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p = float(update.message.text)
        if p <= 0: raise ValueError
    except:
        await update.message.reply_text("Число >0")
        return SELL_PRICE
    context.user_data['price'] = p
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(op, callback_data=f'sell_op_{op}') for op in OPERATORS]])
    await update.message.reply_text("Выберите оператора:", reply_markup=kb)
    return SELL_OPERATOR

async def sell_operator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    op = q.data.replace('sell_op_', '')
    uid = q.from_user.id
    a = context.user_data['amount']
    p = context.user_data['price']
    user = db.get_user(uid)
    if user['gigs'] < a:
        await q.edit_message_text(f"У вас только {fmt(user['gigs'])} ГБ")
        return ConversationHandler.END
    db.update_gigs(uid, -a)
    oid = db.add_offer(uid, a, p, op)
    await q.edit_message_text(f"✅ Объявление #{oid}: {a} ГБ по {p} руб/ГБ")
    return ConversationHandler.END

async def buy_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    offers = db.get_active_offers()
    if not offers:
        await q.edit_message_text("Нет активных объявлений")
        return
    text = "📦 *Доступные объявления:*\n"
    for o in offers:
        text += f"#{o['offer_id']}: {o['amount']} ГБ × {o['price_per_gb']} руб = {fmt(o['total_price'])} руб | {o['operator']}\n"
    text += "\nКупить: `/buy_offer [ID]`"
    await q.edit_message_text(text, parse_mode="Markdown")

async def buy_offer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пример: /buy_offer 1")
        return
    try:
        oid = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    buyer = update.effective_user.id
    offer = db.get_offer_by_id(oid)
    if not offer:
        await update.message.reply_text("Объявление не найдено")
        return
    buyer_data = db.get_user(buyer)
    if not buyer_data['phone']:
        await update.message.reply_text("Сначала /start и укажите номер")
        return
    if buyer_data['balance'] < offer['total_price']:
        await update.message.reply_text(f"Не хватает {fmt(offer['total_price'])} руб. /top_up")
        return
    comm = offer['total_price'] * COMMISSION_PERCENT / 100
    tx = db.add_transaction(buyer, offer['seller_id'], offer['amount'], offer['price_per_gb'], offer['total_price'], comm)
    db.update_balance(buyer, -offer['total_price'])
    db.delete_offer(oid)
    seller_data = db.get_user(offer['seller_id'])
    await context.bot.send_message(
        offer['seller_id'],
        f"🔔 Сделка #{tx}!\nПередайте {offer['amount']} ГБ на {buyer_data['phone']}\nПосле отправки: /confirm_send {tx}"
    )
    await update.message.reply_text(f"✅ Куплено {offer['amount']} ГБ\nПосле получения: /confirm_receive {tx}")

async def my_offers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    offers = db.get_active_offers()
    mine = [o for o in offers if o['seller_id'] == uid]
    if not mine:
        await q.edit_message_text("У вас нет активных объявлений")
        return
    text = "📋 Ваши объявления:\n"
    for o in mine:
        text += f"#{o['offer_id']}: {o['amount']} ГБ × {o['price_per_gb']} руб\n"
    text += "\nОтменить: /cancel_offer [ID]"
    await q.edit_message_text(text)

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
    await update.message.reply_text(f"Объявление #{oid} отменено")

async def confirm_send_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/confirm_send [ID сделки]")
        return
    try:
        tx = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    uid = update.effective_user.id
    txn = db.get_transaction(tx)
    if not txn or txn['seller_id'] != uid or txn['seller_confirmed']:
        await update.message.reply_text("Не найдено или уже подтверждено")
        return
    db.update_transaction_confirmation(tx, seller_confirmed=1)
    buyer = db.get_user(txn['buyer_id'])
    await context.bot.send_message(txn['buyer_id'], f"🔔 Продавец подтвердил отправку. /confirm_receive {tx}")
    await update.message.reply_text("✅ Подтверждено")

async def confirm_receive_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/confirm_receive [ID сделки]")
        return
    try:
        tx = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    uid = update.effective_user.id
    txn = db.get_transaction(tx)
    if not txn or txn['buyer_id'] != uid or txn['buyer_confirmed']:
        await update.message.reply_text("Не найдено или уже подтверждено")
        return
    db.update_transaction_confirmation(tx, buyer_confirmed=1)
    txn2 = db.get_transaction(tx)
    if txn2['seller_confirmed']:
        db.complete_transaction(tx)
        seller = db.get_user(txn['seller_id'])
        await context.bot.send_message(txn['seller_id'], f"✅ Покупатель подтвердил получение. Деньги зачислены.")
        await update.message.reply_text("✅ Сделка завершена")
    else:
        await update.message.reply_text("✅ Получение подтверждено. Ждём продавца")

async def confirm_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    sell = db.get_pending_transactions_for_seller(uid)
    buy = db.get_pending_transactions_for_buyer(uid)
    text = "✅ *Ожидают подтверждения:*\n"
    for t in sell:
        text += f"Вы продавец: сделка #{t['txn_id']}, {t['amount']} ГБ. /confirm_send {t['txn_id']}\n"
    for t in buy:
        text += f"Вы покупатель: сделка #{t['txn_id']}, {t['amount']} ГБ. /confirm_receive {t['txn_id']}\n"
    if not sell and not buy:
        text = "Нет сделок на подтверждении"
    await q.edit_message_text(text, parse_mode="Markdown")

async def top_up_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/top_up [сумма] (демо)")
        return
    try:
        amt = float(context.args[0])
        if amt <= 0: raise ValueError
    except:
        await update.message.reply_text("Сумма >0")
        return
    db.update_balance(update.effective_user.id, amt)
    await update.message.reply_text(f"💰 Пополнено на {fmt(amt)} руб (демо)")

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Изменить номер: /set_phone")

async def set_phone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btn = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True
    )
    await update.message.reply_text("Нажмите кнопку, чтобы отправить номер", reply_markup=btn)
    return PHONE

# === АДМИН-ПАНЕЛЬ ===
async def admin_panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')]])
    await q.edit_message_text("👑 Админ-панель", reply_markup=kb)

async def admin_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    users = db.get_all_users()
    bal = sum(u['balance'] for u in users)
    await q.edit_message_text(f"👥 Пользователей: {len(users)}\n💰 Общий баланс: {fmt(bal)} руб")

async def admin_add_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) != 2: return
    try:
        uid = int(context.args[0])
        amt = float(context.args[1])
        db.update_balance(uid, amt)
        await update.message.reply_text(f"✅ {fmt(amt)} руб → {uid}")
    except: pass

async def admin_add_gigs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) != 2: return
    try:
        uid = int(context.args[0])
        gb = float(context.args[1])
        db.update_gigs(uid, gb)
        await update.message.reply_text(f"✅ {fmt(gb)} ГБ → {uid}")
    except: pass

# === ЗАПУСК ===
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
    app.add_handler(CommandHandler("top_up", top_up_cmd))
    app.add_handler(CommandHandler("buy_offer", buy_offer_cmd))
    app.add_handler(CommandHandler("cancel_offer", cancel_offer_cmd))
    app.add_handler(CommandHandler("confirm_send", confirm_send_cmd))
    app.add_handler(CommandHandler("confirm_receive", confirm_receive_cmd))
    app.add_handler(CommandHandler("set_phone", set_phone_cmd))
    app.add_handler(CommandHandler("admin_add_balance", admin_add_balance_cmd))
    app.add_handler(CommandHandler("admin_add_gigs", admin_add_gigs_cmd))
    app.add_handler(CallbackQueryHandler(balance_cmd, pattern='^balance$'))
    app.add_handler(CallbackQueryHandler(buy_list, pattern='^buy$'))
    app.add_handler(CallbackQueryHandler(my_offers_cmd, pattern='^my_offers$'))
    app.add_handler(CallbackQueryHandler(settings_cmd, pattern='^settings$'))
    app.add_handler(CallbackQueryHandler(confirm_menu_cmd, pattern='^confirm_menu$'))
    app.add_handler(CallbackQueryHandler(admin_panel_cmd, pattern='^admin_panel$'))
    app.add_handler(CallbackQueryHandler(admin_stats_cmd, pattern='^admin_stats$'))
    
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
