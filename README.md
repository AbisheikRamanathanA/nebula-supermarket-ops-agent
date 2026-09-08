# Supermarket Ops Agent

A Telegram-first AI agent for running a small Indian kirana store from plain language.

## What it demonstrates

- Receive stock and maintain SKU inventory
- Add new products
- Create multi-item GST bills
- Edit a draft bill before finalizing
- Oversell protection: billing cannot make stock negative
- GST calculation with CGST + SGST split
- Khata / customer credit ledger
- Daily close and sales analytics
- GST invoice PDF generation
- PPTX sales-analysis deck generation
- Persistent SQLite storage
- Natural-language orchestration through Gemini function calling
- Safe fallback command mode when no Gemini key is configured

The assignment explicitly evaluates agent-first orchestration, business rules in tools, persistence, GST correctness, oversell guards, idempotency and real artifacts.

## Architecture

Telegram -> Agent layer -> Tool layer -> SQLite / PDF / PPTX

The model decides which tool to call. The tool layer owns business rules and database writes.

## Quick start

1. Install Python 3.11+.
2. Create a Telegram bot with `@BotFather` using `/newbot` and copy the token.
3. Create a Gemini API key and put it in `.env`.
4. Copy `.env.example` to `.env`.
5. Install dependencies:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

6. Run:

```bash
python bot.py
```

7. Open your Telegram bot and send `/start`.

## Demo script

Use these messages in order:

1. `stock in 50 packets of Maggi at cost 12 MRP 14`
2. `stock in 20 kg sugar cost 42 MRP 48`
3. `stock in 10 packs Aashirvaad atta 5kg cost 240 MRP 280`
4. `how much sugar is left?`
5. `what is running out?`
6. `make a bill: 2 kg sugar, 1 Aashirvaad atta 5kg, 2 Maggi, UPI`
7. `change that bill: drop the Maggi and add 1 Maggi`
8. `finalize the bill`
9. `put 500 on Ramesh credit`
10. `Ramesh paid 300`
11. `what is Ramesh's balance?`
12. `today's sales`
13. `send me that bill as a PDF`
14. `make this week's sales analysis deck`

## Important engineering notes

- Stock is decremented only on finalization, not while drafting.
- Finalization is idempotent: repeating it cannot double-decrement stock.
- Overselling is checked inside the database transaction.
- GST rates are stored per SKU and GST is calculated per line.
- A bill is rejected if stock is insufficient.
- Ambiguous product names produce a clarification request.
- Generated files go under `generated/`.

## Limitations / honest scope

This is a take-home prototype, not a production POS. Payment gateways, barcode scanning, multi-store tenancy and enterprise auth are intentionally out of scope. The README and demo emphasize what is reliable and what should be extended next.

## GitHub submission

The assignment asks for a private repository and the collaborators:
- Aswath363
- akshaiP
- ashwant hnebula

Add the exact usernames from the task sheet as collaborators, then paste the private repository URL into the placement form.

## Evidence to record

Make a 4-5 minute screen recording showing:
receive stock -> multi-item bill -> edit -> oversell rejection -> khata -> PDF invoice -> analysis deck -> `/newchat`/fresh chat and a stored preference.

