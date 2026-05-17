import sqlite3
from datetime import datetime

DB_NAME = 'giga.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  phone TEXT,
                  operator TEXT,
                  balance REAL DEFAULT 0.0,
                  gigs REAL DEFAULT 0.0,
                  created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS offers
                 (offer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  seller_id INTEGER,
                  amount REAL,
                  price_per_gb REAL,
                  total_price REAL,
                  operator TEXT,
                  status TEXT DEFAULT 'active',
                  created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (txn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  buyer_id INTEGER,
                  seller_id INTEGER,
                  amount REAL,
                  price_per_gb REAL,
                  total_amount REAL,
                  commission REAL,
                  status TEXT DEFAULT 'pending',
                  buyer_confirmed INTEGER DEFAULT 0,
                  seller_confirmed INTEGER DEFAULT 0,
                  timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdraw_requests
                 (req_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  amount REAL,
                  details TEXT,
                  status TEXT DEFAULT 'pending',
                  created_at TEXT)''')
    conn.commit()
    conn.close()

def register_user(user_id, username):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not c.fetchone():
        c.execute("INSERT INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
                  (user_id, username, datetime.now().isoformat()))
    else:
        c.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    conn.commit()
    conn.close()

def update_user_phone(user_id, phone, operator):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET phone = ?, operator = ? WHERE user_id = ?", (phone, operator, user_id))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'user_id': row[0], 'username': row[1], 'phone': row[2], 'operator': row[3], 'balance': row[4], 'gigs': row[5]}
    return None

def update_balance(user_id, delta):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))
    conn.commit()
    conn.close()

def update_gigs(user_id, delta):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET gigs = gigs + ? WHERE user_id = ?", (delta, user_id))
    conn.commit()
    conn.close()

def add_offer(seller_id, amount, price_per_gb, operator):
    total_price = amount * price_per_gb
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO offers (seller_id, amount, price_per_gb, total_price, operator, created_at) VALUES (?, ?, ?, ?, ?, ?)",
              (seller_id, amount, price_per_gb, total_price, operator, datetime.now().isoformat()))
    offer_id = c.lastrowid
    conn.commit()
    conn.close()
    return offer_id

def get_active_offers():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT offer_id, seller_id, amount, price_per_gb, total_price, operator FROM offers WHERE status = 'active'")
    rows = c.fetchall()
    conn.close()
    return [{'offer_id': r[0], 'seller_id': r[1], 'amount': r[2], 'price_per_gb': r[3], 'total_price': r[4], 'operator': r[5]} for r in rows]

def get_offer_by_id(offer_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT offer_id, seller_id, amount, price_per_gb, total_price, operator FROM offers WHERE offer_id = ? AND status = 'active'", (offer_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'offer_id': row[0], 'seller_id': row[1], 'amount': row[2], 'price_per_gb': row[3], 'total_price': row[4], 'operator': row[5]}
    return None

def delete_offer(offer_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE offers SET status = 'closed' WHERE offer_id = ?", (offer_id,))
    conn.commit()
    conn.close()

def add_transaction(buyer_id, seller_id, amount, price_per_gb, total_amount, commission):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO transactions (buyer_id, seller_id, amount, price_per_gb, total_amount, commission, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (buyer_id, seller_id, amount, price_per_gb, total_amount, commission, datetime.now().isoformat()))
    txn_id = c.lastrowid
    conn.commit()
    conn.close()
    return txn_id

def update_transaction_confirmation(txn_id, buyer_confirmed=None, seller_confirmed=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if buyer_confirmed is not None:
        c.execute("UPDATE transactions SET buyer_confirmed = ? WHERE txn_id = ?", (buyer_confirmed, txn_id))
    if seller_confirmed is not None:
        c.execute("UPDATE transactions SET seller_confirmed = ? WHERE txn_id = ?", (seller_confirmed, txn_id))
    c.execute("SELECT buyer_confirmed, seller_confirmed FROM transactions WHERE txn_id = ?", (txn_id,))
    buyer_c, seller_c = c.fetchone()
    if buyer_c == 1 and seller_c == 1:
        c.execute("UPDATE transactions SET status = 'completed' WHERE txn_id = ?", (txn_id,))
    conn.commit()
    conn.close()

def get_pending_transactions_for_seller(seller_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT txn_id, buyer_id, amount, total_amount FROM transactions WHERE seller_id = ? AND status = 'pending' AND seller_confirmed = 0", (seller_id,))
    rows = c.fetchall()
    conn.close()
    return [{'txn_id': r[0], 'buyer_id': r[1], 'amount': r[2], 'total_amount': r[3]} for r in rows]

def get_pending_transactions_for_buyer(buyer_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT txn_id, seller_id, amount, total_amount FROM transactions WHERE buyer_id = ? AND status = 'pending' AND buyer_confirmed = 0", (buyer_id,))
    rows = c.fetchall()
    conn.close()
    return [{'txn_id': r[0], 'seller_id': r[1], 'amount': r[2], 'total_amount': r[3]} for r in rows]

def get_transaction(txn_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT txn_id, buyer_id, seller_id, amount, price_per_gb, total_amount, commission, status, buyer_confirmed, seller_confirmed FROM transactions WHERE txn_id = ?", (txn_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'txn_id': row[0], 'buyer_id': row[1], 'seller_id': row[2], 'amount': row[3], 'price_per_gb': row[4], 'total_amount': row[5], 'commission': row[6], 'status': row[7], 'buyer_confirmed': row[8], 'seller_confirmed': row[9]}
    return None

def complete_transaction(txn_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT buyer_id, seller_id, amount, total_amount, commission FROM transactions WHERE txn_id = ?", (txn_id,))
    row = c.fetchone()
    if row:
        buyer_id, seller_id, amount, total_amount, commission = row
        seller_gets = total_amount - commission
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (seller_gets, seller_id))
        c.execute("UPDATE transactions SET status = 'completed' WHERE txn_id = ?", (txn_id,))
        conn.commit()
    conn.close()

def add_withdraw_request(user_id, amount, details):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO withdraw_requests (user_id, amount, details, created_at) VALUES (?, ?, ?, ?)",
              (user_id, amount, details, datetime.now().isoformat()))
    req_id = c.lastrowid
    conn.commit()
    conn.close()
    return req_id

def get_pending_withdraw_requests():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT req_id, user_id, amount, details, created_at FROM withdraw_requests WHERE status = 'pending'")
    rows = c.fetchall()
    conn.close()
    return [{'req_id': r[0], 'user_id': r[1], 'amount': r[2], 'details': r[3], 'created_at': r[4]} for r in rows]

def update_withdraw_request(req_id, status):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE withdraw_requests SET status = ? WHERE req_id = ?", (status, req_id))
    conn.commit()
    conn.close()
