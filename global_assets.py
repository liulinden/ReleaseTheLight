
import pygame

from asset_manager import AssetManager

asset_manager = AssetManager("assets", use_cache=True)

def load_assets(loading_screen=None) -> None:
    asset_manager.load(loading_screen=loading_screen)

def get_asset(name: str) -> pygame.Surface:
    return asset_manager.get(name)
