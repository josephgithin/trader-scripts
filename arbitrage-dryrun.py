import asyncio
import json
import websockets
from collections import defaultdict
import time
import logging
import traceback

###############################################################################
# LOGGING SETUP
###############################################################################
logging.basicConfig(
    level=logging.INFO,  # Change to logging.DEBUG if you want to see debug logs in console
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('arbitrage.log')
    ]
)
logger = logging.getLogger(__name__)

###############################################################################
# CONFIG
###############################################################################

# We'll define a list of trading pairs we want to watch:
PAIRS_CONFIG = [
    {
        "cb_symbol": "BTC-USD",
        "kr_symbol": "XBT/USD",
        "min_spread_usd": 1.0,
        "fee_buy": 0.005,   # 0.5% taker fee if you buy on Coinbase
        "fee_sell": 0.005,  # 0.5% taker fee if you sell on Kraken
    },
    {
        "cb_symbol": "ETH-USD",
        "kr_symbol": "ETH/USD",
        "min_spread_usd": 0.75,
        "fee_buy": 0.005,
        "fee_sell": 0.005,
    },
]

# How frequently (in seconds) we check for arbitrage
CHECK_INTERVAL_SECS = 2

# We'll store the latest quotes in this global dictionary:
# latest_quotes["coinbase"]["BTC-USD"] = {"bid": float, "ask": float}
# latest_quotes["kraken"]["XBT/USD"]   = {"bid": float, "ask": float}
latest_quotes = defaultdict(lambda: defaultdict(lambda: {"bid": None, "ask": None}))

###############################################################################
# 1) WebSocket Subscriptions
###############################################################################

async def subscribe_coinbase(pairs_config):
    """
    Single WebSocket connection to Coinbase, subscribing to the 'ticker' channel
    for all specified pairs (cb_symbol).
    We'll store best bid/ask in latest_quotes["coinbase"][cb_symbol].
    """
    url = "wss://ws-feed.exchange.coinbase.com"
    product_ids = [p["cb_symbol"] for p in pairs_config]

    while True:
        try:
            async with websockets.connect(url) as ws:
                logger.info("[Coinbase WS] Connected.")
                subscribe_msg = {
                    "type": "subscribe",
                    "channels": [{"name": "ticker", "product_ids": product_ids}]
                }
                await ws.send(json.dumps(subscribe_msg))
                logger.info(f"[Coinbase WS] Subscribed to: {product_ids}")

                while True:
                    message = await ws.recv()
                    # Log every incoming message at DEBUG level
                    logger.debug(f"[Coinbase WS] Raw message: {message}")

                    data = json.loads(message)
                    if data.get("type") == "ticker":
                        cb_symbol = data.get("product_id")
                        best_bid = data.get("best_bid")
                        best_ask = data.get("best_ask")
                        if cb_symbol and best_bid and best_ask:
                            latest_quotes["coinbase"][cb_symbol]["bid"] = float(best_bid)
                            latest_quotes["coinbase"][cb_symbol]["ask"] = float(best_ask)
                            logger.info(
                                f"[Coinbase WS] Updated {cb_symbol}: Bid={best_bid}, Ask={best_ask}"
                            )

        except websockets.ConnectionClosed:
            logger.warning("[Coinbase WS] Connection closed; reconnecting...")
            logger.warning(f"[Coinbase WS] Connection close details: {traceback.format_exc()}")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"[Coinbase WS] Error: {e}; reconnecting...")
            logger.error(f"[Coinbase WS] Full traceback: {traceback.format_exc()}")
            await asyncio.sleep(5)


async def subscribe_kraken(pairs_config):
    """
    Single WebSocket connection to Kraken, subscribing to the 'ticker' channel
    for all specified pairs (kr_symbol).
    We'll store best bid/ask in latest_quotes["kraken"][kr_symbol].
    """
    url = "wss://ws.kraken.com/"
    channel_map = {}  # channel_id -> kr_symbol

    while True:
        try:
            async with websockets.connect(url) as ws:
                logger.info("[Kraken WS] Connected.")

                # Subscribe to each kr_symbol
                for p in pairs_config:
                    kr_symbol = p["kr_symbol"]
                    sub_msg = {
                        "event": "subscribe",
                        "pair": [kr_symbol],
                        "subscription": {"name": "ticker"}
                    }
                    await ws.send(json.dumps(sub_msg))
                    logger.info(f"[Kraken WS] Subscribing to: {kr_symbol}")

                # Listen indefinitely
                while True:
                    msg = await ws.recv()
                    logger.debug(f"[Kraken WS] Raw message: {msg}")

                    data = json.loads(msg)

                    if isinstance(data, dict) and data.get("event") == "subscriptionStatus":
                        # For example: {"channelID": 42, "event": "subscriptionStatus", "pair": "XBT/USD", "status": "subscribed", ...}
                        if data.get("status") == "subscribed":
                            channel_id = data.get("channelID")
                            pair_name = data.get("pair")
                            channel_map[channel_id] = pair_name
                            logger.info(
                                f"[Kraken WS] Subscribed (channel_id={channel_id}) to pair: {pair_name}"
                            )

                    elif isinstance(data, list) and len(data) > 1:
                        channel_id = data[0]
                        if channel_id in channel_map:
                            kr_symbol = channel_map[channel_id]
                            ticker_info = data[1]
                            if (isinstance(ticker_info, dict) 
                                and "b" in ticker_info 
                                and "a" in ticker_info):
                                bid_price = float(ticker_info["b"][0])
                                ask_price = float(ticker_info["a"][0])
                                latest_quotes["kraken"][kr_symbol]["bid"] = bid_price
                                latest_quotes["kraken"][kr_symbol]["ask"] = ask_price
                                logger.info(
                                    f"[Kraken WS] Updated {kr_symbol}: Bid={bid_price}, Ask={ask_price}"
                                )

        except websockets.ConnectionClosed:
            logger.warning("[Kraken WS] Connection closed; reconnecting...")
            logger.warning(f"[Kraken WS] Connection close details: {traceback.format_exc()}")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"[Kraken WS] Error: {e}; reconnecting...")
            logger.error(f"[Kraken WS] Full traceback: {traceback.format_exc()}")
            await asyncio.sleep(5)


###############################################################################
# 2) Fee & Spread Calculation (Dry-Run Only)
###############################################################################

def calc_net_spread(buy_price, sell_price, fee_buy, fee_sell):
    """
    For a hypothetical trade:
      - Buy at buy_price (with fee_buy% taker fee)
      - Sell at sell_price (with fee_sell% taker fee)
    Return the net difference in USD per unit of asset (e.g. per 1 BTC).
    
    Simplistic approach:
      - cost = buy_price + (buy_price * fee_buy)
      - revenue = sell_price - (sell_price * fee_sell)
      - net_spread = revenue - cost
    """
    cost = buy_price * (1 + fee_buy)
    revenue = sell_price * (1 - fee_sell)
    return revenue - cost

###############################################################################
# 3) Arbitrage Check Loop
###############################################################################

last_heartbeat_time = time.time()

async def check_arbitrage_loop():
    """
    Periodically check for potential cross-exchange spreads.
    Purely logs the opportunity; does not require or use private API calls.
    """
    global last_heartbeat_time
    while True:
        try:
            now = time.time()
            # Log a heartbeat every 30 seconds if no opportunities were found
            if now - last_heartbeat_time >= 30:
                logger.info("[Arb] Heartbeat: Checking for quotes/spreads...")
                last_heartbeat_time = now

            for cfg in PAIRS_CONFIG:
                cb_symbol = cfg["cb_symbol"]  # e.g. "BTC-USD"
                kr_symbol = cfg["kr_symbol"]  # e.g. "XBT/USD"
                min_spread = cfg["min_spread_usd"]
                fee_buy = cfg["fee_buy"]
                fee_sell = cfg["fee_sell"]

                cb_bid = latest_quotes["coinbase"][cb_symbol]["bid"]
                cb_ask = latest_quotes["coinbase"][cb_symbol]["ask"]
                kr_bid = latest_quotes["kraken"][kr_symbol]["bid"]
                kr_ask = latest_quotes["kraken"][kr_symbol]["ask"]

                if not all([cb_bid, cb_ask, kr_bid, kr_ask]):
                    logger.debug(
                        f"[Arb] Missing quotes for {cb_symbol} & {kr_symbol}: "
                        f"CB({cb_bid}/{cb_ask}), KR({kr_bid}/{kr_ask})"
                    )
                    continue

                # Route A: Buy on Coinbase @ ask, Sell on Kraken @ bid
                net_spread_A = calc_net_spread(cb_ask, kr_bid, fee_buy, fee_sell)
                
                # Route B: Buy on Kraken @ ask, Sell on Coinbase @ bid
                net_spread_B = calc_net_spread(kr_ask, cb_bid, fee_buy, fee_sell)

                # If net_spread_A > min_spread, log the opportunity
                if net_spread_A > min_spread:
                    logger.info(
                        f"[Arb] {cb_symbol}: BUY@Coinbase({cb_ask:.2f}) => SELL@Kraken({kr_bid:.2f}) "
                        f"Net Spread={net_spread_A:.2f} USD (after fees)"
                    )
                    last_heartbeat_time = time.time()  # reset so we don't log heartbeat immediately

                # If net_spread_B > min_spread, log the opportunity
                if net_spread_B > min_spread:
                    logger.info(
                        f"[Arb] {cb_symbol}: BUY@Kraken({kr_ask:.2f}) => SELL@Coinbase({cb_bid:.2f}) "
                        f"Net Spread={net_spread_B:.2f} USD (after fees)"
                    )
                    last_heartbeat_time = time.time()  # reset so we don't log heartbeat immediately

        except Exception as e:
            logger.error(f"[Arb] Error in check loop: {e}")

        await asyncio.sleep(CHECK_INTERVAL_SECS)


###############################################################################
# 4) Main Entry Point
###############################################################################

async def main():
    logger.info("[INIT] Starting Dry-Run Arbitrage Bot (No API keys needed).")
    logger.info(f"[CONFIG] Check interval: {CHECK_INTERVAL_SECS} seconds")
    logger.info("[CONFIG] Watching pairs:")
    for pair in PAIRS_CONFIG:
        logger.info(f"  - {pair['cb_symbol']} (Coinbase) / {pair['kr_symbol']} (Kraken)")
        logger.info(f"    Min spread: ${pair['min_spread_usd']}")
        logger.info(f"    Fees: Buy {pair['fee_buy']*100}%, Sell {pair['fee_sell']*100}%")

    # Kick off two tasks for WebSocket data from Coinbase & Kraken
    tasks = [
        subscribe_coinbase(PAIRS_CONFIG),
        subscribe_kraken(PAIRS_CONFIG),
        check_arbitrage_loop(),
    ]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[Main] Interrupted by user. Exiting gracefully.")

