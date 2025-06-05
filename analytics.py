import re
import json
from datetime import datetime, timedelta
from collections import defaultdict

CHANNEL_ID_OUTPUT = 1379132047783624717

# --- Trading Day Utilities ---
def get_trading_days_today(ref_date=None):
    ref_date = ref_date or datetime.today()
    return [ref_date.strftime("%Y-%m-%d")] if ref_date.weekday() < 5 else []

def get_trading_days_this_week(ref_date=None):
    ref_date = ref_date or datetime.today()
    start_of_week = ref_date - timedelta(days=ref_date.weekday())
    return [(start_of_week + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((ref_date - start_of_week).days + 1)
            if (start_of_week + timedelta(days=i)).weekday() < 5]

def get_trading_days_this_month(ref_date=None):
    ref_date = ref_date or datetime.today()
    start_of_month = ref_date.replace(day=1)
    return [(start_of_month + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((ref_date - start_of_month).days + 1)
            if (start_of_month + timedelta(days=i)).weekday() < 5]

def build_prompt_for_lines(lines, date_list):
    return f"""
You are a trading assistant. Extract and match real trade signals from chat logs.
Each trade may span multiple days. An entry could happen on one day and the exit on the next.

Return a valid JSON array. Each object must include:
- channel
- ticker
- type (call or put)
- expiry
- entry (e.g. "$1.17")
- exit (e.g. "$2.10" or null)
- status ("open" or "closed")
- summary ("yes" if entry is in the date list)
- entry_time (e.g. "2025-06-02 14:38")
- exit_time (e.g. "2025-06-03 11:04" or null)

Rules:
- Match "Exit" or "Exit TICKER" with the most recent unmatched entry of the same ticker in the same channel *only if* the exit time is **after** the entry time.
- Ignore commentary unless it includes entry/exit.
- Status is "closed" if exit is found.

Chat Messages:
{''.join(lines)}
"""

async def run_trade_summary(mode, message, openai_client):
    from discord import File
    print("[Analytics] Starting trade summary for:", mode)

    now = datetime.now()
    if mode == "today":
        date_list = get_trading_days_today(now)
    elif mode == "week":
        date_list = get_trading_days_this_week(now)
    elif mode == "month":
        date_list = get_trading_days_this_month(now)
    else:
        await message.channel.send("❌ Invalid mode. Use `!data today`, `!data week`, or `!data month`.")
        return

    await message.channel.send(f"📥 Collecting messages for `{mode}`...")
    print("[Step 1] Reading channel dump...")

    with open("full_channel_dump.txt", "r", encoding="utf-8") as f:
        lines = f.readlines()

    filtered_lines = [line for line in lines if any(f"[{date}" in line for date in date_list)]
    output_filename = now.strftime("%m%d%Y") + f"_{mode}_signals.txt"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.writelines(filtered_lines)

    await message.channel.send("📊 Parsing signals by tier...")
    print("[Step 2] Splitting and prompting...")

    tiered_lines = {"free": [], "1": [], "2": [], "3": []}
    for line in filtered_lines:
        if "live-signals-free" in line:
            tiered_lines["free"].append(line)
        elif "live-signals-tier-1" in line:
            tiered_lines["1"].append(line)
        elif "live-signals-tier-2" in line:
            tiered_lines["2"].append(line)
        elif "live-signals-tier-3" in line:
            tiered_lines["3"].append(line)

    all_trades = []
    for tier, lines in tiered_lines.items():
        if not lines:
            continue

        print(f"[Step 3] Prompting Tier {tier}...")
        prompt = build_prompt_for_lines(lines, date_list)

        try:
            response = openai_client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": "You are a trading assistant that processes signals from chat logs."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            cleaned_json = re.sub(r"^```(?:json)?|```$", "", response.choices[0].message.content.strip(), flags=re.MULTILINE).strip()
            trades = json.loads(cleaned_json)

            for trade in trades:
                entry_day = trade["entry_time"].split()[0]
                trade["summary"] = "yes" if entry_day in date_list else "no"
            all_trades.extend(trades)

            # Define file name for open positions
            open_trades_file = "open_positions.jsonl"

            # Step 1: Load existing open positions (if the file exists)
            try:
                with open(open_trades_file, "r", encoding="utf-8") as f:
                    existing_lines = f.readlines()
                    existing_trades = [json.loads(line.strip()) for line in existing_lines if line.strip()]
            except FileNotFoundError:
                existing_trades = []

            # Step 2: Identify new open trades (status=open, no exit)
            def is_duplicate(trade, existing):
                return any(
                    t.get("channel") == trade.get("channel") and
                    t.get("ticker") == trade.get("ticker") and
                    t.get("entry_time") == trade.get("entry_time") and
                    t.get("entry") == trade.get("entry") and
                    t.get("type") == trade.get("type")
                    for t in existing
                )

            new_open_trades = [
                trade for trade in all_trades
                if trade.get("status") == "open" and not trade.get("exit")
                and not is_duplicate(trade, existing_trades)
            ]

            # Step 3: Append new open trades to file (in JSONL format)
            if new_open_trades:
                with open(open_trades_file, "a", encoding="utf-8") as f:
                    for trade in new_open_trades:
                        f.write(json.dumps(trade) + "\n")
                print(f"✅ Added {len(new_open_trades)} new open trades to {open_trades_file}")
            else:
                print("❌ No new open trades to add.")

        except Exception as e:
            print(f"❌ Error parsing tier {tier}: {e}")

    summary_trades = [t for t in all_trades if t.get("summary") == "yes"]
    grouped_trades = defaultdict(list)

    for trade in summary_trades:
        key = (trade["channel"], trade["ticker"], trade["entry_time"])
        if key not in grouped_trades:
            grouped_trades[key] = []
        grouped_trades[key].append(trade)

    trade_details = []
    win_count = 0
    loss_count = 0
    open_count = 0

    for (channel, ticker, entry_time), trades in grouped_trades.items():
        try:
            entry = float(trades[0]["entry"].replace("$", "")) if trades[0]["entry"] else None
            if entry is None:
                continue

            exits = []
            for trade in trades:
                if trade.get("status") == "closed" and trade.get("exit"):
                    try:
                        exit = float(trade["exit"].replace("$", ""))
                        fmt = "%Y-%m-%d %H:%M"
                        dt_entry = datetime.strptime(trade["entry_time"], fmt)
                        dt_exit = datetime.strptime(trade["exit_time"], fmt)
                        duration = int((dt_exit - dt_entry).total_seconds() / 60)
                        exits.append({
                            "exit": exit,
                            "change": ((exit - entry) / entry) * 100,
                            "duration": duration
                        })
                    except:
                        continue

            if exits:
                avg_change = sum(e["change"] for e in exits) / len(exits)
                avg_duration = sum(e["duration"] for e in exits) / len(exits)

                trade_details.append({
                    "channel": channel,
                    "ticker": ticker,
                    "type": trades[0]["type"],
                    "entry": entry,
                    "percent_change": round(avg_change, 2),
                    "duration": f"{int(avg_duration)}m",
                    "status": "closed",
                    "partial": len(exits) > 1,
                    "exits": [f"${e['exit']}" for e in exits]
                })

                if avg_change > 0:
                    win_count += 1
                else:
                    loss_count += 1
            else:
                open_count += 1

        except Exception as e:
            print(f"⚠️ Skipping grouped trade due to error: {e}")

    channel_names = {
        "free": "Free Tier",
        "1": "Tier 1",
        "2": "Tier 2",
        "3": "Tier 3"
    }

    channel_grouped = defaultdict(list)
    for t in trade_details:
        channel_grouped[t["channel"]].append(t)

    if mode == "today":
        summary_title = f"**Daily Trade Summary for {now.strftime('%m/%d/%Y')} @everyone**"
    elif mode == "week":
        summary_title = f"**Weekly Trade Summary for {now.strftime('%m/%d/%Y')} @everyone**"
    elif mode == "month":
        summary_title = f"**Monthly Trade Summary for {now.strftime('%B')} @everyone**"
    else:
        summary_title = f"**Trade Summary @everyone**"

    

    win_label = "Win" if win_count == 1 else "Wins"
    loss_label = "Loss" if loss_count == 1 else "Losses"
    open_label = "Open Position" if open_count == 1 else "Open Positions"

    full_message = f"{summary_title}\n\n"
    full_message += f"Total Trades: {len(grouped_trades)} ({win_count} {win_label}, {loss_count} {loss_label}, {open_count} {open_label})\n\n"


    for ch, trades in channel_grouped.items():
        if "live-signals-free" in ch:
            normalized_ch = "free"
        elif "live-signals-tier-1" in ch:
            normalized_ch = "1"
        elif "live-signals-tier-2" in ch:
            normalized_ch = "2"
        elif "live-signals-tier-3" in ch:
            normalized_ch = "3"
        else:
            normalized_ch = "unknown"
        ch_name_base = channel_names.get(normalized_ch, f"Tier {normalized_ch}")
        full_message += f"{ch_name_base}:\n"

        for t in trades:
            entry_price = f"${t['entry']:.2f}" if t['entry'] is not None else "?"
            trade_str = f"- {t['ticker']} {t['type']} @ {entry_price}"
            if t["status"] == "closed":
                pct_val = t['percent_change']
                pct = f"{pct_val}%"
                mins = t['duration'] if t['duration'] else "unknown"

                if pct_val >= 50:
                    emojis = ":fire: :fire: :fire:"
                elif pct_val >= 0:
                    emojis = ":fire: :chart_with_upwards_trend:"
                else:
                    emojis = ""

                if t.get("partial"):
                    exits_str = ", ".join(t["exits"])
                    trade_str += f". Sold some at {exits_str} for a {pct} avg gain {emojis}"
                else:
                    trade_str += f". Sold at {t['exits'][0]} {mins} later for a {pct} gain {emojis}"
            full_message += trade_str + "\n"
        full_message += "\n"

    full_message += "\ud83d\udd10 Want to see our open trades? [Get a premium membership!](https://discord.com/channels/1350549258310385694/1372399067514011749)\n"

    if output_channel := message.guild.get_channel(CHANNEL_ID_OUTPUT):
        await output_channel.send(full_message)

    return full_message
