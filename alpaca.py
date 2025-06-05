

import discord
from discord.ext import commands
from openai import OpenAI
import json
from datetime import datetime, time
import pytz
from alpaca_trade_api.rest import REST

# -------- Inline Secrets --------
DISCORD_TOKEN = ""
OPENAI_KEY = ""
ALPACA_API_KEY = ""
ALPACA_SECRET_KEY = ""
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
OWNER_ID = 1346220314262110258

# -------- Channels to Listen In --------
ALLOWED_CHANNEL_IDS = [
    1379132006629118113,  # Tier 1
    1379132047783624717   # Tier 2
]

# -------- API Clients --------
client = OpenAI(api_key=OPENAI_KEY)
alpaca = REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL)

# -------- Discord Bot Setup --------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# -------- Market Time Check --------
def is_market_open():
    now_et = datetime.now(pytz.timezone("US/Eastern")).time()
    return time(9, 30) <= now_et <= time(16, 0)

# -------- GPT Parser --------
async def parse_with_gpt(message: str):
    today = datetime.now().strftime("%m/%d/%Y")
    prompt = f"""
Today is {today}.

Extract this trading message into a JSON object.

Message:
\"{message}\"

Expected format:

{{
  "action": "entry",
  "asset_type": "stock",
  "ticker": "AAPL",
  "side": "buy",
  "quantity": 1,
  "price": float or null
}}

Exit:
{{
  "action": "exit",
  "ticker": "AAPL",
  "exit_price": float
}}

- Ignore messages that only mention a price target or SL.
- Return null if the message is not a valid stock trading signal.
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a trading assistant that parses messages into structured JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ OpenAI error: {e}")
        return None

# -------- Message Handler --------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.channel.id not in ALLOWED_CHANNEL_IDS:
        return

    parsed = await parse_with_gpt(message.content)
    if not parsed:
        return

    print(f"📡 Parsed signal: {parsed}")

    if parsed.get("action") == "entry" and parsed.get("asset_type") == "stock":
        ticker = parsed["ticker"]
        qty = parsed.get("quantity", 1)
        side = parsed.get("side", "buy")
        price = parsed.get("price")

        # ⏰ Market time check
        if not is_market_open():
            print("⏰ Market is closed. Skipping order.")
            return

        # 🛒 Submit stock order
        try:
            alpaca.submit_order(
                symbol=ticker,
                qty=qty,
                side=side,
                type="market",
                time_in_force="gtc"
            )
            print(f"🛒 Submitted stock order: {side.upper()} {qty} {ticker}")
        except Exception as e:
            print(f"❌ Alpaca stock order error: {e}")

        # 📬 DM the owner
        try:
            user = await bot.fetch_user(OWNER_ID)
            if user:
                msg = f"New Entry Signal: {ticker} {side}"
                if price:
                    msg += f" at ${price} per share"
                await user.send(msg)
        except Exception as e:
            print(f"❌ Failed to DM: {e}")

    await bot.process_commands(message)

# -------- Command --------
@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

# -------- Run --------
bot.run(DISCORD_TOKEN)