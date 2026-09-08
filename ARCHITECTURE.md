# Architecture

```text
Telegram
   |
   v
bot.py  ---- conversation state
   |
   v
agent.py ---- Gemini function calling / safe fallback
   |
   +---- inventory tools ----+
   +---- billing tools ------+--> SQLite (WAL)
   +---- khata tools --------+
   +---- analytics ----------+
   |
   +---- artifacts.py --> PDF invoice / PPTX analysis
```

Business rules live in the tool/database layer rather than in the system prompt:
oversell checks, finalization idempotency, GST calculations and persistence.
