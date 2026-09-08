import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path("store.db")

@contextmanager
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            unit TEXT NOT NULL,
            cost REAL NOT NULL,
            mrp REAL NOT NULL,
            qty REAL NOT NULL DEFAULT 0,
            reorder_level REAL NOT NULL DEFAULT 5,
            gst_rate REAL NOT NULL DEFAULT 5,
            hsn TEXT NOT NULL DEFAULT '0000'
        );
        CREATE TABLE IF NOT EXISTS bills(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL DEFAULT 'DRAFT',
            payment_method TEXT,
            customer TEXT,
            total REAL NOT NULL DEFAULT 0,
            gst_total REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS bill_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER NOT NULL REFERENCES bills(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            qty REAL NOT NULL,
            unit_price REAL NOT NULL,
            gst_rate REAL NOT NULL,
            line_subtotal REAL NOT NULL,
            line_gst REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS khata(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer TEXT NOT NULL,
            kind TEXT NOT NULL,
            amount REAL NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS preferences(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)

def now():
    return datetime.now().isoformat(timespec="seconds")

def normalize(s):
    return " ".join(s.lower().strip().split())

def find_product(name):
    q = normalize(name)
    with db() as c:
        row = c.execute("SELECT * FROM products WHERE lower(name)=?", (q,)).fetchone()
        if row:
            return dict(row)
        rows = c.execute("SELECT * FROM products WHERE lower(name) LIKE ?", (f"%{q}%",)).fetchall()
        if len(rows) == 1:
            return dict(rows[0])
        if len(rows) > 1:
            return {"ambiguous": [dict(x) for x in rows]}
    return None

def upsert_product(name, unit, cost, mrp, qty, reorder_level=5, gst_rate=5, hsn="0000"):
    with db() as c:
        existing = c.execute("SELECT id FROM products WHERE lower(name)=?", (normalize(name),)).fetchone()
        if existing:
            c.execute("""UPDATE products SET unit=?,cost=?,mrp=?,qty=qty+?,
                         reorder_level=?,gst_rate=?,hsn=? WHERE id=?""",
                      (unit,cost,mrp,qty,reorder_level,gst_rate,hsn,existing["id"]))
            pid = existing["id"]
        else:
            cur = c.execute("""INSERT INTO products(name,unit,cost,mrp,qty,reorder_level,gst_rate,hsn)
                               VALUES(?,?,?,?,?,?,?,?)""",
                            (name,unit,cost,mrp,qty,reorder_level,gst_rate,hsn))
            pid = cur.lastrowid
        return dict(c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone())

def list_stock(low_only=False):
    with db() as c:
        sql = "SELECT * FROM products"
        if low_only:
            sql += " WHERE qty <= reorder_level"
        return [dict(x) for x in c.execute(sql + " ORDER BY name").fetchall()]

def create_draft(items, payment_method=None, customer=None):
    with db() as c:
        cur = c.execute("INSERT INTO bills(status,payment_method,customer,created_at) VALUES('DRAFT',?,?,?)",
                        (payment_method,customer,now()))
        bid = cur.lastrowid
        for item in items:
            p = find_product(item["product"])
            if not p or "ambiguous" in p:
                raise ValueError(f"Product not uniquely found: {item['product']}")
            qty = float(item["qty"])
            if qty <= 0:
                raise ValueError("Quantity must be positive.")
            price = float(p["mrp"])
            sub = round(price * qty, 2)
            gst = round(sub * float(p["gst_rate"]) / 100, 2)
            c.execute("""INSERT INTO bill_items
                (bill_id,product_id,qty,unit_price,gst_rate,line_subtotal,line_gst)
                VALUES(?,?,?,?,?,?,?)""",
                (bid,p["id"],qty,price,p["gst_rate"],sub,gst))
        recalc_bill(bid, c)
    return get_bill(bid)

def recalc_bill(bid, c=None):
    own = c is None
    if own:
        ctx = db()
        c = ctx.__enter__()
    try:
        row = c.execute("""SELECT COALESCE(SUM(line_subtotal),0) total,
                                  COALESCE(SUM(line_gst),0) gst
                           FROM bill_items WHERE bill_id=?""",(bid,)).fetchone()
        c.execute("UPDATE bills SET total=?,gst_total=? WHERE id=?",
                  (round(row["total"],2),round(row["gst"],2),bid))
        if own: ctx.commit()
    finally:
        if own: ctx.__exit__(None,None,None)

def get_bill(bid):
    with db() as c:
        b = c.execute("SELECT * FROM bills WHERE id=?", (bid,)).fetchone()
        if not b: return None
        items = c.execute("""SELECT bi.*,p.name,p.unit,p.hsn FROM bill_items bi
                             JOIN products p ON p.id=bi.product_id WHERE bi.bill_id=?""",(bid,)).fetchall()
        return {"bill":dict(b), "items":[dict(x) for x in items]}

def replace_bill_items(bid, items):
    with db() as c:
        b = c.execute("SELECT status FROM bills WHERE id=?", (bid,)).fetchone()
        if not b: raise ValueError("Bill not found")
        if b["status"] == "FINALIZED": raise ValueError("Finalized bill cannot be edited.")
        c.execute("DELETE FROM bill_items WHERE bill_id=?", (bid,))
        for item in items:
            p = find_product(item["product"])
            if not p or "ambiguous" in p: raise ValueError(f"Product not uniquely found: {item['product']}")
            qty=float(item["qty"])
            sub=round(p["mrp"]*qty,2)
            gst=round(sub*p["gst_rate"]/100,2)
            c.execute("""INSERT INTO bill_items
                (bill_id,product_id,qty,unit_price,gst_rate,line_subtotal,line_gst)
                VALUES(?,?,?,?,?,?,?)""",
                (bid,p["id"],qty,p["mrp"],p["gst_rate"],sub,gst))
        recalc_bill(bid,c)
    return get_bill(bid)

def finalize_bill(bid):
    with db() as c:
        b = c.execute("SELECT * FROM bills WHERE id=?", (bid,)).fetchone()
        if not b: raise ValueError("Bill not found.")
        if b["status"] == "FINALIZED":
            return get_bill(bid)  # idempotent
        items = c.execute("SELECT * FROM bill_items WHERE bill_id=?", (bid,)).fetchall()
        for it in items:
            p = c.execute("SELECT * FROM products WHERE id=?", (it["product_id"],)).fetchone()
            if p["qty"] < it["qty"]:
                raise ValueError(f"OVERSOLD GUARD: only {p['qty']} {p['unit']} of {p['name']} left.")
        for it in items:
            c.execute("UPDATE products SET qty=qty-? WHERE id=?", (it["qty"],it["product_id"]))
        c.execute("UPDATE bills SET status='FINALIZED' WHERE id=?", (bid,))
    return get_bill(bid)

def add_credit(customer, amount, note="credit purchase"):
    with db() as c:
        c.execute("INSERT INTO khata(customer,kind,amount,note,created_at) VALUES(?,?,?,?,?)",
                  (customer,"CREDIT",float(amount),note,now()))
    return khata_balance(customer)

def record_payment(customer, amount, note="payment"):
    with db() as c:
        c.execute("INSERT INTO khata(customer,kind,amount,note,created_at) VALUES(?,?,?,?,?)",
                  (customer,"PAYMENT",float(amount),note,now()))
    return khata_balance(customer)

def khata_balance(customer):
    with db() as c:
        r=c.execute("""SELECT COALESCE(SUM(CASE WHEN kind='CREDIT' THEN amount ELSE -amount END),0) bal
                       FROM khata WHERE lower(customer)=?""",(normalize(customer),)).fetchone()
        return round(r["bal"],2)

def daily_sales():
    with db() as c:
        today=date.today().isoformat()
        r=c.execute("""SELECT COALESCE(SUM(total),0) total,COALESCE(SUM(gst_total),0) gst,
                              COUNT(*) bills
                       FROM bills WHERE status='FINALIZED' AND substr(created_at,1,10)=?""",(today,)).fetchone()
        top=c.execute("""SELECT p.name,SUM(bi.qty) qty FROM bill_items bi
                         JOIN bills b ON b.id=bi.bill_id JOIN products p ON p.id=bi.product_id
                         WHERE b.status='FINALIZED' AND substr(b.created_at,1,10)=?
                         GROUP BY p.id ORDER BY qty DESC LIMIT 5""",(today,)).fetchall()
        return {"date":today,"total":round(r["total"],2),"gst":round(r["gst"],2),
                "bills":r["bills"],"top":[dict(x) for x in top]}

def set_pref(key,value):
    with db() as c:
        c.execute("INSERT INTO preferences(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key,str(value)))
    return str(value)

def get_prefs():
    with db() as c:
        return {x["key"]:x["value"] for x in c.execute("SELECT key,value FROM preferences")}
