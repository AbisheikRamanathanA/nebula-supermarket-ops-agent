import os
import re
from dotenv import load_dotenv
from db import *
from artifacts import invoice_pdf, analysis_pptx

load_dotenv()

def receive_stock(product: str, unit: str, cost: float, mrp: float, qty: float, gst_rate: float = 5.0, hsn: str = "0000", reorder_level: float = 5.0):
    """Receive stock for an existing or new SKU. Prices, GST and quantity become durable store data."""
    return upsert_product(product, unit, cost, mrp, qty, reorder_level, gst_rate, hsn)

def check_stock(product: str = ""):
    """Read current stock. If product is empty, return all stock."""
    if product:
        p=find_product(product)
        if not p: return {"error":f"No product named {product}"}
        if "ambiguous" in p: return p
        return p
    return list_stock()

def low_stock() -> list:
    """Return SKUs at or below their reorder level."""
    return list_stock(True)

def start_bill(items_text: str, payment_method: str = "UPI", customer: str = ""):
    """Create a draft bill from items_text such as '2 sugar, 1 Maggi'. Stock is not changed until finalize."""
    items=[]
    for part in re.split(r",| and ",items_text,flags=re.I):
        m=re.match(r"\s*(\d+(?:\.\d+)?)\s+(.+?)\s*$",part.strip())
        if not m: raise ValueError("Could not parse an item. Use: quantity product, quantity product.")
        items.append({"qty":float(m.group(1)),"product":m.group(2)})
    return create_draft(items,payment_method,customer or None)

def edit_bill(bill_id: int, items_text: str):
    """Replace items in an unfinalized draft bill."""
    items=[]
    for part in re.split(r",| and ",items_text,flags=re.I):
        m=re.match(r"\s*(\d+(?:\.\d+)?)\s+(.+?)\s*$",part.strip())
        if not m: raise ValueError("Use: quantity product, quantity product.")
        items.append({"qty":float(m.group(1)),"product":m.group(2)})
    return replace_bill_items(int(bill_id),items)

def finalize(bill_id: int):
    """Finalize a draft bill. Performs transactional oversell protection and is idempotent."""
    return finalize_bill(int(bill_id))

def credit(customer: str, amount: float):
    """Put an amount on a customer's khata."""
    return {"customer":customer,"balance":add_credit(customer,amount)}

def payment(customer: str, amount: float):
    """Record a customer payment against khata."""
    return {"customer":customer,"balance":record_payment(customer,amount)}

def balance(customer: str):
    """Return a customer's current khata balance."""
    return {"customer":customer,"balance":khata_balance(customer)}

def close_day() -> dict:
    """Return today's sales, GST and top-selling items."""
    return daily_sales()

def make_invoice(bill_id: int):
    """Generate a GST invoice PDF for a bill."""
    return {"file":invoice_pdf(int(bill_id))}

def make_analysis() -> dict:
    """Generate a PowerPoint sales-analysis deck."""
    return {"file":analysis_pptx()}

def set_preference(key: str, value: str):
    """Persist a store-owner preference across restarts and chats."""
    return {"key":key,"value":set_pref(key,value)}

def preferences() -> dict:
    """Read persistent store-owner preferences."""
    return get_prefs()

TOOLS=[receive_stock,check_stock,low_stock,start_bill,edit_bill,finalize,credit,payment,balance,close_day,make_invoice,make_analysis,set_preference,preferences]

SYSTEM = """You are KiranaOps, an agent running a small Indian kirana store.
The chat is the product. Use tools to inspect and change store state; never invent stock, prices or balances.
IMPORTANT TOOL ROUTING: For questions about existing inventory such as how much is left, stock, available, or what is running out, use check_stock or low_stock. NEVER use receive_stock for a read-only question. Use receive_stock ONLY when the user explicitly says stock arrived, received, added, or stocked in.
Use INR. GST is stored per product and tools calculate it. Never claim a bill is final until finalize succeeds.
If a request is ambiguous, ask a concise clarification instead of guessing.
For a bill, create a draft, allow edits, then finalize only when the owner asks.
For preferences, store them with set_preference so they survive a fresh chat.
Be concise and practical, like an experienced shopkeeper.
"""
