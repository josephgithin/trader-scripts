from dataclasses import dataclass
from typing import Dict, Any, List
import json
import os
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='exchange_monitor.log'
)
logger = logging.getLogger(__name__)

@dataclass
class PairsConfig:
    usd_pairs: Dict[str, tuple] = None
    eur_pairs: Dict[str, tuple] = None
    gbp_pairs: Dict[str, tuple] = None
    btc_pairs: Dict[str, tuple] = None
    eth_pairs: Dict[str, tuple] = None
    stablecoin_pairs: Dict[str, tuple] = None
    
    def __post_init__(self):
        # Convert JSON lists to tuples for pairs
        if self.usd_pairs and isinstance(list(self.usd_pairs.values())[0], list):
            self.usd_pairs = {k: tuple(v) for k, v in self.usd_pairs.items()}
        if self.eur_pairs and isinstance(list(self.eur_pairs.values())[0], list):
            self.eur_pairs = {k: tuple(v) for k, v in self.eur_pairs.items()}
        if self.gbp_pairs and isinstance(list(self.gbp_pairs.values())[0], list):
            self.gbp_pairs = {k: tuple(v) for k, v in self.gbp_pairs.items()}
        if self.btc_pairs and isinstance(list(self.btc_pairs.values())[0], list):
            self.btc_pairs = {k: tuple(v) for k, v in self.btc_pairs.items()}
        if self.eth_pairs and isinstance(list(self.eth_pairs.values())[0], list):
            self.eth_pairs = {k: tuple(v) for k, v in self.eth_pairs.items()}
        if self.stablecoin_pairs and isinstance(list(self.stablecoin_pairs.values())[0], list):
            self.stablecoin_pairs = {k: tuple(v) for k, v in self.stablecoin_pairs.items()}
            
        # Initialize empty dictionaries if None
        if self.usd_pairs is None:
            self.usd_pairs = {}
        if self.eur_pairs is None:
            self.eur_pairs = {}
        if self.gbp_pairs is None:
            self.gbp_pairs = {}
        if self.btc_pairs is None:
            self.btc_pairs = {}
        if self.eth_pairs is None:
            self.eth_pairs = {}
        if self.stablecoin_pairs is None:
            self.stablecoin_pairs = {}
    
    def get_all_pairs(self) -> Dict[str, tuple]:
        """Combine all pairs into a single dictionary"""
        all_pairs = {}
        all_pairs.update(self.usd_pairs)
        all_pairs.update(self.eur_pairs)
        all_pairs.update(self.gbp_pairs)
        all_pairs.update(self.btc_pairs)
        all_pairs.update(self.eth_pairs)
        all_pairs.update(self.stablecoin_pairs)
        return all_pairs
    
    def get_kraken_pairs(self) -> List[str]:
        """Get all Kraken format pairs"""
        return [pair[0] for pair in self.get_all_pairs().values()]
    
    def get_coinbase_pairs(self) -> List[str]:
        """Get all Coinbase format pairs"""
        return [pair[1] for pair in self.get_all_pairs().values()]
    
    def get_standard_pair(self, kraken_pair: str = None, coinbase_pair: str = None) -> str:
        """Convert exchange-specific pair to standard pair name"""
        pairs = self.get_all_pairs()
        if kraken_pair:
            for std_pair, (k_pair, _) in pairs.items():
                if k_pair == kraken_pair:
                    return std_pair
        if coinbase_pair:
            for std_pair, (_, cb_pair) in pairs.items():
                if cb_pair == coinbase_pair:
                    return std_pair
        return None

@dataclass
class DisplayConfig:
    pair_width: int = 15
    price_width: int = 18
    var_width: int = 10
    time_width: int = 10
    price_decimals: Dict[str, int] = None
    
    def __post_init__(self):
        if self.price_decimals is None:
            self.price_decimals = {
                "default": 2,
                "< 0.01": 8,
                "< 1": 6,
                "< 100": 4,
                "≥ 100": 3
            }

@dataclass
class ColorConfig:
    variation_colors: Dict[str, tuple] = None
    
    def __post_init__(self):
        if self.variation_colors is None:
            self.variation_colors = {
                "low": (0.1, 3),      # White for low variation
                "medium": (0.5, 2),    # Green for medium variation
                "high": (float('inf'), 1)  # Red for high variation
            }

@dataclass
class UpdateConfig:
    refresh_rate: float = 1.0
    batch_size: int = 100
    max_pairs: int = 50
    price_history_length: int = 2
    partial_refresh: bool = True
    clear_screen_interval: int = 60

@dataclass
class Config:
    pairs: PairsConfig = None
    display: DisplayConfig = None
    colors: ColorConfig = None
    update: UpdateConfig = None
    
    def __post_init__(self):
        if self.pairs is None:
            self.pairs = PairsConfig()
        if self.display is None:
            self.display = DisplayConfig()
        if self.colors is None:
            self.colors = ColorConfig()
        if self.update is None:
            self.update = UpdateConfig()
    
    @classmethod
    def load(cls, filename: str = 'config.json') -> 'Config':
        logger.info(f"Loading configuration from {filename}")
        try:
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    data = json.load(f)
                    logger.info("Successfully loaded configuration file")
                    return cls(
                        pairs=PairsConfig(**data.get('pairs', {})),
                        display=DisplayConfig(**data.get('display', {})),
                        colors=ColorConfig(**data.get('colors', {})),
                        update=UpdateConfig(**data.get('update', {}))
                    )
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")
            
        logger.warning(f"Using default configuration")
        return cls()
    
    def save(self, filename: str = 'config.json'):
        try:
            config_dict = {
                'pairs': {
                    k: v for k, v in self.pairs.__dict__.items()
                    if not k.startswith('_')
                },
                'display': {
                    k: v for k, v in self.display.__dict__.items()
                    if not k.startswith('_')
                },
                'colors': {
                    'variation_colors': self.colors.variation_colors
                },
                'update': {
                    k: v for k, v in self.update.__dict__.items()
                    if not k.startswith('_')
                }
            }
            with open(filename, 'w') as f:
                json.dump(config_dict, f, indent=2, default=str)
            logger.info(f"Configuration saved to {filename}")
        except Exception as e:
            logger.error(f"Error saving config: {str(e)}")
