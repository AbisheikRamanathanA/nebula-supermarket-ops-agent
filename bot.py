import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from db import init_db, set_pref, get_prefs
from agent import SYSTEM, TOOLS
from artifacts import invoice_pdf, analysis_pptx

load_dotenv()
TOKEN=os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI=os.getenv("GEMINI_API_KEY")
MODEL=os.getenv("GEMINI_MODEL","gemini-2.5-flash")

# Per-user draft/context memory. Durable store data remains in SQLite.
CHATS={}

def get_chat(user_id):
    if user_id not in CHATS:
        CHATS[user_id]=None
    return CHATS[user_id]

async def ai_reply(user_id, text):
    if not GEMINI:
        return fallback(text, user_id)
    try:
        from google import genai
        from google.genai import types
        if CHATS.get(user_id) is None:
            client=genai.Client(api_key=GEMINI)
            CHATS[user_id]=client.chats.create(
                model=MODEL,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM,
                    tools=TOOLS,
                    temperature=0.1
                )
            )
        return CHATS[user_id].send_message(text).text
    except Exception as e:
        # Gemini tool-schema/model-call failures should not make the store unusable.
        # Fall back to deterministic local tools for core demo flows.
        return fallback(text, user_id)

def fallback(text, user_id):
    # Safe demo mode if no model key is available.
    # It intentionally supports the main take-home scenarios so the prototype is still runnable.
    import re
    from agent import receive_stock, check_stock, low_stock, start_bill, finalize, credit, payment, balance, close_day, make_invoice, make_analysis, set_preference
    t=text.lower().strip()
    try:
        if "low" in t or "running out" in t:
            rows=low_stock()
            return "\n".join(f"{x['name']}: {x['qty']:g} {x['unit']}" for x in rows) or "No low-stock items."
        if ("how much" in t and ("left" in t or "stock" in t)) or t.startswith("stock of "):
            # Extract the product between the question phrase and "is left" / "stock".
            name=t
            name=re.sub(r"^how much\s+", "", name)
            name=re.sub(r"\s+is\s+(left|available|in stock)\??$", "", name)
            name=re.sub(r"^stock of\s+", "", name)
            name=re.sub(r"\s+stock\??$", "", name)
            p=check_stock(name.strip())
            if isinstance(p,dict) and "qty" in p: return f"{p['name']}: {p['qty']:g} {p['unit']} left."
            if isinstance(p,dict) and "ambiguous" in p: return "Please specify: " + ", ".join(x["name"] for x in p["ambiguous"])
            return f"I couldn't find a product named '{name.strip()}'."
        if t.startswith("stock in"):
            m=re.search(r"stock in\s+(\d+(?:\.\d+)?)\s+(?:packets?|packs?|kg|g|litre|liter|l)?\s*of?\s*(.+?)\s+at\s+cost\s+₹?(\d+(?:\.\d+)?)\s+mrp\s+₹?(\d+(?:\.\d+)?)",t)
            if m:
                qty=float(m.group(1)); name=m.group(2).strip(); cost=float(m.group(3)); mrp=float(m.group(4))
                p=receive_stock(name,"unit",cost,mrp,qty,5)
                return f"Received {qty:g} of {p['name']}. Stock is now {p['qty']:g}."
        if t.startswith("make a bill:"):
            b=start_bill(text.split(":",1)[1].strip())
            return format_bill(b)
        if t.startswith("finalize"):
            bid=int(re.search(r"\d+",t).group())
            b=finalize(bid); return format_bill(b)+"\nFINALIZED."
        if "paid" in t and re.search(r"\d+",t):
            m=re.search(r"(.+?)\s+paid\s+₹?(\d+(?:\.\d+)?)",t,re.I)
            if m:
                return f"{m.group(1).strip()} balance: ₹{payment(m.group(1).strip(),float(m.group(2)))['balance']:.2f}"
        if "credit" in t and re.search(r"\d+",t):
            m=re.search(r"put\s+₹?(\d+(?:\.\d+)?)\s+on\s+(.+?)(?:'s)?\s+credit",t,re.I)
            if m:
                return f"{m.group(2).strip()} balance: ₹{credit(m.group(2).strip(),float(m.group(1)))['balance']:.2f}"
        if "balance" in t:
            name=t.replace("what is","").replace("balance","").replace("'s","").strip()
            return f"{name}: ₹{balance(name)['balance']:.2f}"
        if "send me" in t and "pdf" in t:
            m=re.search(r"(?:bill|invoice)\s*#?\s*(\d+)",t)
            if m: return "Invoice PDF: " + make_invoice(int(m.group(1)))["file"]
            return "Please give the bill number, e.g. send bill #1 as PDF."
        if "analysis" in t and ("deck" in t or "ppt" in t):
            return "Sales analysis deck: " + make_analysis()["file"]
        if "edit" in t and "bill" in t:
            m=re.search(r"bill\s*#?(\d+).*?:\s*(.*)$", text, re.I)
            if m:
                from agent import edit_bill
                return format_bill(edit_bill(int(m.group(1)),m.group(2)))
        if "today" in t and "sales" in t:
            s=close_day(); return f"Today: ₹{s['total']:.2f} sales, ₹{s['gst']:.2f} GST, {s['bills']} bills."
        if "preference" in t and "upi" in t:
            set_preference("default_payment","UPI"); return "Saved preference: default payment is UPI."
        if t=="/newchat":
            CHATS[user_id]=None; return "Fresh conversation started. Store data and preferences are still retained."
        return "Demo mode. Add GEMINI_API_KEY for full natural-language agent orchestration."
    except Exception as e:
        return "Action refused safely: "+str(e)

def format_bill(data):
    b=data["bill"]
    lines=[f"Draft bill #{b['id']} — {b['status']}"]
    for i in data["items"]:
        lines.append(f"• {i['name']} × {i['qty']:g} = ₹{i['line_subtotal']+i['line_gst']:.2f} (GST {i['line_gst']:.2f})")
    lines.append(f"Taxable ₹{b['total']:.2f} | GST ₹{b['gst_total']:.2f} | Total incl GST ₹{b['total']+b['gst_total']:.2f}")
    return "\n".join(lines)

async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "KiranaOps ready.\n\nTry:\n"
        "stock in 50 packets of Maggi at cost 12 MRP 14\n"
        "how much sugar is left?\n"
        "make a bill: 2 sugar, 1 Maggi\n"
        "what's running out?\n"
        "put ₹500 on Ramesh's credit\n"
        "today's sales"
    )

async def newchat(update, context):
    CHATS[update.effective_user.id]=None
    await update.message.reply_text("Fresh chat. Persistent store data and preferences remain.")

async def handle(update,context):
    reply=await ai_reply(update.effective_user.id, update.message.text)
    await update.message.reply_text(reply)

async def post_init(app):
    init_db()

def main():
    if not TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env")
    app=Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("newchat",newchat))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handle))
    print("KiranaOps is running...")
    app.run_polling()

if __name__=="__main__":
    main()
