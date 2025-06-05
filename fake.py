import discord
import asyncio

# --- Discord Setup ---
DISCORD_TOKEN = ""
# TARGET_CHANNEL_ID = 1379815950588842105

client = discord.Client(intents=discord.Intents.default())

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    channel = client.get_channel(TARGET_CHANNEL_ID)
    if channel:
        message = """

**Daily Trade Summary for 06/05/2025 @everyone**

Total Trades: 6 (4 Wins, 1 Loss, 1 Open Position)

**Tier 1:**
- SPX put @ $2.45. Sold at $3.15 8m later for a 28.57% gain :fire: :chart_with_upwards_trend:

**Tier 2:**
- SPY call @ $0.48. Sold at $0.63 3m later for a 31.25% gain :fire: :chart_with_upwards_trend:
- SPY put @ $0.7. Sold at $0.35 11m later for a -50.0% gain
- SPY call @ $0.64. Sold some at $0.74, $0.77 for a 17.97% avg gain :fire: :chart_with_upwards_trend:

**Tier 3:**
- NBIS call @ $1.75. Sold at $3.50 1114m later for a 100.0% gain :fire: :fire: :fire:

🔒 Want to see our open trades? [Get a premium membership](https://discord.com/channels/1350549258310385694/1372399067514011749)!
"""
        await channel.send(message)
        print("✅ Summary sent!")
    await client.close()

asyncio.run(client.start(DISCORD_TOKEN))
