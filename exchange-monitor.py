import asyncio
import os
import websockets
import json
import pandas as pd
from datetime import datetime
import logging
import curses
from curses import wrapper
import time
from collections import deque
from config import Config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='exchange_monitor.log'
)
logger = logging.getLogger(__name__)

class ConsoleUI:
    def __init__(self, stdscr, config: Config):
        self.stdscr = stdscr
        self.config = config
        self.variations_window = None
        self.status_window = None
        self.help_window = None
        self.price_history = {}
        self.last_full_refresh = time.time()
        self.sort_by = 'variation_percentage'
        self.sort_ascending = False
        self.filter_text = ''
        self.messages = deque(maxlen=5)
        self.header_drawn = False
        
        # Enable non-blocking input
        self.stdscr.nodelay(1)
        self.stdscr.timeout(100)
        
        # Initialize colors
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_RED, -1)     # High variation
            curses.init_pair(2, curses.COLOR_GREEN, -1)   # Medium variation
            curses.init_pair(3, curses.COLOR_WHITE, -1)   # Low variation
            logger.info("Colors initialized successfully")
        except Exception as e:
            logger.error(f"Color initialization error: {str(e)}")
        
        # Setup windows
        self.setup_windows()

    def setup_windows(self):
        try:
            height, width = self.stdscr.getmaxyx()
            
            # Create variations window (main display)
            self.variations_window = curses.newwin(height - 8, width, 0, 0)
            self.variations_window.scrollok(True)
            
            # Create status window (bottom)
            self.status_window = curses.newwin(3, width, height - 8, 0)
            
            # Create help window (very bottom)
            self.help_window = curses.newwin(5, width, height - 5, 0)
            
            # Initial draw
            self.draw_help()
            self.draw_status("Starting up...")
            logger.info("Windows setup completed")
        except Exception as e:
            logger.error(f"Window setup error: {str(e)}")

    def draw_help(self):
        try:
            self.help_window.clear()
            help_text = [
                "Controls:",
                "q: Quit | s: Sort by variation | p: Sort by pair | r: Reverse sort | f: Filter pairs",
                "↑/↓: Scroll | Space: Pause/Resume"
            ]
            for i, text in enumerate(help_text):
                self.help_window.addstr(i, 1, text)
            self.help_window.refresh()
        except curses.error as e:
            logger.error(f"Help window error: {str(e)}")

    def draw_status(self, message):
        try:
            self.messages.append(f"{datetime.now().strftime('%H:%M:%S')} - {message}")
            self.status_window.clear()
            for i, msg in enumerate(self.messages):
                self.status_window.addstr(i, 1, msg[:self.status_window.getmaxyx()[1]-2])
            self.status_window.refresh()
        except curses.error as e:
            logger.error(f"Status window error: {str(e)}")

    def get_price_trend(self, pair, current_price):
        """Calculate price trend comparing current price with previous"""
        if current_price is None:
            return " "
            
        if pair not in self.price_history:
            self.price_history[pair] = deque(maxlen=2)
            self.price_history[pair].append(float(current_price))
            return " "
            
        # Add new price
        prev_price = self.price_history[pair][-1] if self.price_history[pair] else None
        self.price_history[pair].append(float(current_price))
        
        # Compare with previous price
        if prev_price is None:
            return " "
            
        diff = float(current_price) - float(prev_price)
        if abs(diff) < 0.000001:  # Handle floating point comparison
            return "-"
        return "↑" if diff > 0 else "↓"

    def format_price(self, price, decimals=None):
        """Format price with appropriate decimal places"""
        if price is None:
            return "N/A".rjust(self.config.display.price_width)
            
        try:
            if decimals is None:
                if price < 0.01:
                    decimals = self.config.display.price_decimals["< 0.01"]
                elif price < 1:
                    decimals = self.config.display.price_decimals["< 1"]
                elif price < 100:
                    decimals = self.config.display.price_decimals["< 100"]
                else:
                    decimals = self.config.display.price_decimals["≥ 100"]
            
            return f"{price:>{self.config.display.price_width}.{decimals}f}"
        except (TypeError, KeyError):
            return f"{price:>{self.config.display.price_width}.2f}"

    def format_difference(self, diff):
        """Format price difference with appropriate decimal places"""
        if abs(diff) < 0.01:
            return f"{diff:.8f}"
        elif abs(diff) < 1:
            return f"{diff:.6f}"
        elif abs(diff) < 100:
            return f"{diff:.4f}"
        else:
            return f"{diff:.2f}"

    def draw_variations(self, variations_df):
        if variations_df.empty:
            return
            
        try:
            now = time.time()
            need_full_refresh = (now - self.last_full_refresh) > self.config.update.clear_screen_interval
            
            if need_full_refresh:
                self.variations_window.clear()
                self.last_full_refresh = now
                self.header_drawn = False

            # Create header
            if not self.header_drawn or need_full_refresh:
                header = (
                    f"{'Pair':{self.config.display.pair_width}} "
                    f"{'Kraken Price':{self.config.display.price_width}} "
                    f"{'Arbitrage':<25} "
                    f"{'Coinbase Price':{self.config.display.price_width}} "
                    f"{'Var%':{self.config.display.var_width}} "
                    f"{'Time':{self.config.display.time_width}}"
                )
                self.variations_window.addstr(0, 1, header, curses.A_BOLD)
                self.variations_window.addstr(1, 1, "-" * len(header))
                self.header_drawn = True

            # Sort and filter data
            df = variations_df.copy()
            df = df.sort_values(self.sort_by, ascending=self.sort_ascending)
            if self.filter_text:
                df = df[df['standard_pair'].str.contains(self.filter_text, case=False)]

            # Draw rows
            max_rows = min(self.config.update.max_pairs, 
                         self.variations_window.getmaxyx()[0] - 3)
            
            for i, row in enumerate(df.head(max_rows).itertuples(), start=2):
                k_trend = self.get_price_trend(f"kraken_{row.standard_pair}", row.kraken_price)
                c_trend = self.get_price_trend(f"coinbase_{row.standard_pair}", row.coinbase_price)
                
                # Format prices
                k_fmt = self.format_price(row.kraken_price)
                c_fmt = self.format_price(row.coinbase_price)
                
                # Determine arbitrage direction and size
                price_diff = abs(row.kraken_price - row.coinbase_price)
                if row.kraken_price > row.coinbase_price:
                    arb = f"Buy CB → Sell KR ({self.format_difference(price_diff)})"
                else:
                    arb = f"Buy KR → Sell CB ({self.format_difference(price_diff)})"
                
                time_str = pd.to_datetime(row.timestamp).strftime('%H:%M:%S')
                
                line = (
                    f"{row.standard_pair:{self.config.display.pair_width}} "
                    f"{k_trend}{k_fmt} "
                    f"{arb:<25} "
                    f"{c_trend}{c_fmt} "
                    f"{row.variation_percentage:>{self.config.display.var_width}.3f}% "
                    f"{time_str:>{self.config.display.time_width}}"
                )
                
                try:
                    # Determine color based on variation percentage
                    if row.variation_percentage > 0.5:
                        color = curses.color_pair(2) | curses.A_BOLD  # Green + Bold
                    elif row.variation_percentage > 0.1:
                        color = curses.color_pair(2)  # Green
                    else:
                        color = curses.color_pair(3)  # White
                        
                    self.variations_window.addstr(i, 1, line, color)
                except curses.error:
                    break
                    
            self.variations_window.refresh()
        except Exception as e:
            logger.error(f"Display error: {str(e)}")
            self.draw_status(f"Display error: {str(e)}")

class ExchangeConsoleMonitor:
    def __init__(self, stdscr, config: Config):
        self.kraken_ws_url = "wss://ws.kraken.com"
        self.coinbase_ws_url = "wss://ws-feed.exchange.coinbase.com"
        self.prices = {'kraken': {}, 'coinbase': {}}
        self.config = config
        
        # Initialize DataFrame
        self.variations_df = pd.DataFrame({
            'standard_pair': pd.Series(dtype='str'),
            'kraken_price': pd.Series(dtype='float64'),
            'coinbase_price': pd.Series(dtype='float64'),
            'variation_percentage': pd.Series(dtype='float64'),
            'timestamp': pd.Series(dtype='datetime64[ns]')
        })
        
        self.ui = ConsoleUI(stdscr, config)
        self.running = True
        self.paused = False
        
    async def handle_user_input(self):
        while self.running:
            try:
                key = self.ui.stdscr.getch()
                if key == ord('q'):
                    self.running = False
                elif key == ord('s'):
                    self.ui.sort_by = 'variation_percentage'
                    self.ui.draw_status("Sorting by variation")
                elif key == ord('p'):
                    self.ui.sort_by = 'standard_pair'
                    self.ui.draw_status("Sorting by pair")
                elif key == ord('r'):
                    self.ui.sort_ascending = not self.ui.sort_ascending
                    self.ui.draw_status(f"Sort order: {'ascending' if self.ui.sort_ascending else 'descending'}")
                elif key == ord('f'):
                    curses.echo()
                    self.ui.status_window.clear()
                    self.ui.status_window.addstr(0, 1, "Filter: ")
                    self.ui.status_window.refresh()
                    filter_str = self.ui.status_window.getstr(0, 9).decode('utf-8')
                    curses.noecho()
                    if filter_str:
                        self.ui.filter_text = filter_str
                        self.ui.draw_status(f"Filtering by: {filter_str}")
                    else:
                        self.ui.filter_text = ''
                        self.ui.draw_status("Filter cleared")
                elif key == ord(' '):
                    self.paused = not self.paused
                    self.ui.draw_status(f"{'Paused' if self.paused else 'Resumed'} price updates")
            except Exception as e:
                logger.error(f"Input error: {str(e)}")
            await asyncio.sleep(0.1)

    async def kraken_message_handler(self, websocket):
        try:
            async for message in websocket:
                if not self.running:
                    break
                if self.paused:
                    continue
                    
                data = json.loads(message)
                if isinstance(data, list) and len(data) > 1:
                    if isinstance(data[1], dict) and 'c' in data[1]:
                        try:
                            kraken_pair = data[3]
                            price = float(data[1]['c'][0])
                            standard_pair = self.config.pairs.get_standard_pair(kraken_pair=kraken_pair)
                            if standard_pair:
                                self.prices['kraken'][standard_pair] = price
                                await self.update_variations(standard_pair)
                        except (IndexError, KeyError, ValueError) as e:
                            logger.error(f"Error processing Kraken message: {str(e)}")
        except Exception as e:
            logger.error(f"Kraken websocket error: {str(e)}")
            self.ui.draw_status("Lost connection to Kraken - reconnecting...")

    async def coinbase_message_handler(self, websocket):
        try:
            async for message in websocket:
                if not self.running:
                    break
                if self.paused:
                    continue
                    
                data = json.loads(message)
                if data.get('type') == 'ticker':
                    try:
                        coinbase_pair = data['product_id']
                        price = float(data['price'])
                        standard_pair = self.config.pairs.get_standard_pair(coinbase_pair=coinbase_pair)
                        if standard_pair:
                            self.prices['coinbase'][standard_pair] = price
                            await self.update_variations(standard_pair)
                    except (KeyError, ValueError) as e:
                        logger.error(f"Error processing Coinbase message: {str(e)}")
        except Exception as e:
            logger.error(f"Coinbase websocket error: {str(e)}")
            self.ui.draw_status("Lost connection to Coinbase - reconnecting...")

    async def update_variations(self, standard_pair: str):
        try:
            kraken_price = self.prices['kraken'].get(standard_pair)
            coinbase_price = self.prices['coinbase'].get(standard_pair)
            
            if kraken_price and coinbase_price and kraken_price > 0:
                variation = abs((kraken_price - coinbase_price) / kraken_price * 100)
                
                # Create new row
                new_data = pd.DataFrame({
                    'standard_pair': [standard_pair],
                    'kraken_price': [float(kraken_price)],
                    'coinbase_price': [float(coinbase_price)],
                    'variation_percentage': [float(variation)],
                    'timestamp': [pd.Timestamp.now()]
                })
                
                # Update existing DataFrame
                self.variations_df = self.variations_df[
                    self.variations_df['standard_pair'] != standard_pair
                ]
                
                self.variations_df = pd.concat(
                    [self.variations_df, new_data],
                    ignore_index=True
                ).sort_values('variation_percentage', ascending=False)
                
                # Store prices for trend calculation
                self.ui.get_price_trend(f"kraken_{standard_pair}", kraken_price)
                self.ui.get_price_trend(f"coinbase_{standard_pair}", coinbase_price)
                
                # Update the display
                if not self.paused:
                    self.ui.draw_variations(self.variations_df)
                
        except Exception as e:
            logger.error(f"Error updating variations for {standard_pair}: {str(e)}")
            self.ui.draw_status(f"Update error: {str(e)}")

    async def monitor_prices(self):
        while self.running:
            try:
                async with websockets.connect(self.kraken_ws_url) as kraken_ws, \
                           websockets.connect(self.coinbase_ws_url) as coinbase_ws:
                    
                    # Subscribe to Kraken feed
                    kraken_pairs = self.config.pairs.get_kraken_pairs()
                    await kraken_ws.send(json.dumps({
                        "event": "subscribe",
                        "pair": kraken_pairs,
                        "subscription": {"name": "ticker"}
                    }))
                    
                    # Subscribe to Coinbase feed
                    coinbase_pairs = self.config.pairs.get_coinbase_pairs()
                    await coinbase_ws.send(json.dumps({
                        "type": "subscribe",
                        "product_ids": coinbase_pairs,
                        "channels": ["ticker"]
                    }))
                    
                    self.ui.draw_status("Connected to exchanges")
                    logger.info("Connected to exchanges")
                    
                    await asyncio.gather(
                        self.kraken_message_handler(kraken_ws),
                        self.coinbase_message_handler(coinbase_ws),
                        self.handle_user_input()
                    )
            except Exception as e:
                logger.error(f"Connection error: {str(e)}")
                if self.running:
                    await asyncio.sleep(5)
                    self.ui.draw_status("Attempting to reconnect...")

async def main(stdscr):
    try:
        # Load configuration
        config = Config.load()
        logger.info("Configuration loaded successfully")
        
        # Initialize and run monitor
        monitor = ExchangeConsoleMonitor(stdscr, config)
        await monitor.monitor_prices()
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise

async def cleanup():
    """Cleanup function to reset terminal state"""
    try:
        curses.echo()
        curses.nocbreak()
        curses.endwin()
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

if __name__ == "__main__":
    try:
        # Check if config exists, if not create default
        if not os.path.exists('config.json'):
            config = Config()
            config.save()
            logger.info("Created default configuration file")
        
        # Run the application
        wrapper(lambda stdscr: asyncio.run(main(stdscr)))
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
        print("\nShutting down...")
    except Exception as e:
        logger.error(f"Application error: {e}")
        print(f"\nError: {e}")
    finally:
        # Reset terminal state
        asyncio.run(cleanup())#
