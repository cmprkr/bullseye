

import discord
import asyncio
import subprocess
from openai import OpenAI
from analytics import run_trade_summary
from parse_signals import start_parser_bot

DISCORD_TOKEN = ""
OPENAI_KEY = ""
CHANNEL_ID_TRIGGER = 1379132047783624717
CHANNEL_ID_SECONDARY_OUTPUT = 1379132006629118113

client = discord.Client(intents=discord.Intents.all())
openai_client = OpenAI(api_key=OPENAI_KEY)

last_summary_message = ""

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")

@client.event
async def on_message(message):
    global last_summary_message

    if message.channel.id != CHANNEL_ID_TRIGGER or message.author == client.user:
        return

    args = message.content.strip().lower().split()
    if len(args) == 2 and args[0] == "!data":
        last_summary_message = await run_trade_summary(mode=args[1], message=message, openai_client=openai_client)
        return

    if args[0] == "!push":
        output_channel = client.get_channel(CHANNEL_ID_SECONDARY_OUTPUT)
        if not output_channel:
            await message.channel.send("❌ Could not find the output channel.")
            return

        if last_summary_message:
            await output_channel.send(last_summary_message)
            await message.channel.send(f"✅ Message has been successfully posted in **{output_channel.name}**.")
        else:
            await message.channel.send("⚠️ No message available to push.")

    if args[0] == "!parse":
        await message.channel.send("🔄 Running parse_signals.py...")
        try:
            await start_parser_bot()
            await message.channel.send("✅ `parse_signals.py` ran successfully.")
        except Exception as e:
            await message.channel.send(f"❌ Exception occurred while running parser: {str(e)}")

# --- Run ---
asyncio.run(client.start(DISCORD_TOKEN))
