

import discord
import asyncio
from datetime import datetime
import os

DISCORD_TOKEN = ""
CHANNEL_IDS = [1350549419204018176, 1371236886101754046, 1371194846353817832, 1371195227859320852]

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    local_tz = datetime.now().astimezone().tzinfo

    file_name = "full_channel_dump.txt"
    if os.path.exists(file_name):
        os.remove(file_name)

    with open(file_name, "w", encoding="utf-8") as f:
        for channel_id in CHANNEL_IDS:
            channel = client.get_channel(channel_id)
            if not channel:
                print(f"⚠️ Could not access channel {channel_id}")
                continue

            messages = []
            async for msg in channel.history(limit=None):
                messages.append(msg)

            print(f"📥 Found {len(messages)} messages in {channel.name}")

            for m in reversed(messages):
                timestamp = m.created_at.astimezone(local_tz).strftime("%Y-%m-%d %H:%M")
                author = m.author.name
                content = m.content
                f.write(f"{channel.name} [{timestamp}] {author}: {content}\n")

    print("✅ Dumped all messages to full_channel_dump.txt")
    await client.close()

# Expose as coroutine
async def start_parser_bot():
    await client.start(DISCORD_TOKEN)
