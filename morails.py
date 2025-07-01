# File: swap_signal_bot.py

import os
import json
import time
import requests
from datetime import datetime
from dateutil import parser
import pytz
from dotenv import load_dotenv

# === Load environment variables ===
load_dotenv()
api_key = os.getenv("MORALIS_API_KEY")
telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

wallet_address = "0x5b2f0585296666e52b154b1a76677158cd7025c2".lower()
chain = "eth"
limit = 5
order = "DESC"

# === Paths ===
os.makedirs("morails", exist_ok=True)
SIGNAL_FILE = "morails/signal.json"

# === Time conversion ===
def utc_to_ist(utc_str):
    utc = parser.parse(utc_str).replace(tzinfo=pytz.utc)
    ist = utc.astimezone(pytz.timezone('Asia/Kolkata'))
    return ist.strftime("%Y-%m-%d %H:%M:%S")

# === Load known transaction hashes ===
def load_known_hashes():
    if os.path.exists(SIGNAL_FILE):
        with open(SIGNAL_FILE, "r") as f:
            data = json.load(f)
            return {d["transaction_id"] for d in data}, data
    return set(), []

# === Send Telegram message ===
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {
        "chat_id": telegram_chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload)
        if res.status_code != 200:
            print(f"❌ Telegram error: {res.text}")
    except Exception as e:
        print(f"⚠️ Telegram send failed: {e}")

# === Format Telegram message ===
def format_signal_msg(signal):
    prefix = "🟢" if signal["signal"].lower() == "buy" else "🔴"
    return f"""{prefix} *{signal['signal'].upper()} Signal*
• *ETH:* `{signal['eth']}`
• *Token:* `{signal['token']}`
• *USDT:* `{signal['usdt']}`
• *Pair:* `{signal['pair_address']}`
• *Swap:* `{signal['swap']}`
• *Time:* `{signal['time']}`"""

# === Extract new swap signals ===
def extract_new_signals(swaps, known_hashes):
    new_signals = []
    for tx in swaps.get("result", []):
        tx_hash = tx["transactionHash"]
        if tx_hash in known_hashes:
            continue

        direction = tx["transactionType"]
        weth = tx["bought"] if tx["bought"]["symbol"] == "WETH" else tx["sold"]
        token = tx["bought"] if tx["bought"]["symbol"] != "WETH" else tx["sold"]

        weth_amt = abs(float(weth["amount"]))
        token_amt = abs(float(token["amount"]))
        usdt_amt = abs(float(weth["usdAmount"]))

        if direction == "buy":
            eth_sign = "-"
            usdt_sign = "-"
            token_sign = "+"
        else:  # sell
            eth_sign = "+"
            usdt_sign = "+"
            token_sign = "-"

        logo = tx.get("exchangeLogo", "")
        swap_name = os.path.basename(logo).replace(".png", "") if logo else "unknown"

        new_signals.append({
            "signal": direction,
            "eth": f"{eth_sign}{weth_amt:.6f} ETH",
            "token": f"{token_sign}{token_amt:.6f} {token['symbol']}",
            "usdt": f"{usdt_sign}{usdt_amt:.2f} USDT",
            "pair_address": tx["pairAddress"],
            "swap": swap_name,
            "time": utc_to_ist(tx["blockTimestamp"]),
            "transaction_id": tx_hash
        })
    return new_signals

# === Fetch swaps and process new ===
def fetch_and_notify():
    print(f"🔍 {datetime.now().strftime('%H:%M:%S')} Checking swaps...")
    headers = {
        "Accept": "application/json",
        "X-API-Key": api_key
    }
    params = {
        "chain": chain,
        "order": order,
        "limit": limit
    }
    url = f"https://deep-index.moralis.io/api/v2.2/wallets/{wallet_address}/swaps"

    try:
        res = requests.get(url, headers=headers, params=params)
        if res.status_code != 200:
            print(f"❌ API failed: {res.status_code} → {res.text}")
            return

        swaps = res.json()
        known_hashes, existing_data = load_known_hashes()
        new_signals = extract_new_signals(swaps, known_hashes)

        if new_signals:
            # Update file (append at top)
            updated = new_signals + existing_data
            with open(SIGNAL_FILE, "w") as f:
                json.dump(updated, f, indent=2)

            print(f"✅ {len(new_signals)} new signal(s) sent.")
            for s in new_signals:
                send_telegram_message(format_signal_msg(s))
        else:
            print("🟡 No new swaps.")

    except Exception as e:
        print(f"💥 Error: {e}")

# === Run every 20 seconds ===
if __name__ == "__main__":
    while True:
        fetch_and_notify()
        time.sleep(30)
