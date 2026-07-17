import os
import pickle
import time
from concurrent.futures import ThreadPoolExecutor

import pygame


class AssetManager:
    IMAGE_EXTS = {".png", ".bmp", ".jpg", ".jpeg", ".gif", ".webp"}

    def __init__(self, root="assets", use_cache=False, cache_file=".asset_cache"):
        self.root = root
        self.use_cache = use_cache
        self.cache_file = os.path.join(root, cache_file)
        self.images = {}
        self._raw = {}
        self.unused = set()

    def load(self, verbose=True, loading_screen=None):
        start = time.perf_counter()
        paths = self._discover()

        if self.use_cache and self._load_from_cache(paths, loading_screen):
            if verbose:
                print(f"[assets] loaded {len(self.images)} from cache in {time.perf_counter() - start:.2f}s")
            return time.perf_counter() - start

        with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
            for name, surf in ex.map(self._load_one, paths.items()):
                if surf is not None:
                    self._raw[name] = surf

        for name, surf in self._raw.items():
            self.images[name] = surf.convert_alpha()
            if loading_screen:
                loading_screen.put(len(self.images) / len(paths), f"Loading assets ({len(self.images)}/{len(paths)})")

        self._raw.clear()

        self.unused = set(self.images.keys())

        if self.use_cache:
            if loading_screen:
                loading_screen.put(1.0, "Saving asset cache")
            self._save_to_cache(paths)

        if verbose:
            print(f"[assets] loaded {len(self.images)} images in {time.perf_counter() - start:.2f}s")

        return time.perf_counter() - start

    def get(self, name):
        try:
            self.unused.discard(name)
            return self.images[name]
        except KeyError as e:
            raise KeyError(f"No asset named {name!r}. Available: {sorted(self.images)[:10]}...") from e

    def __getitem__(self, name):
        return self.get(name)

    def __contains__(self, name):
        return name in self.images

    def __len__(self):
        return len(self.images)

    def _discover(self):
        paths = {}
        for dirpath, _, files in os.walk(self.root):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in self.IMAGE_EXTS:
                    continue
                full = os.path.join(dirpath, fn)
                paths[self._name_for(full)] = full
        return paths

    def _name_for(self, full_path):
        rel = os.path.relpath(full_path, self.root)
        rel = os.path.splitext(rel)[0]
        return rel.replace(os.sep, "/")

    @staticmethod
    def _load_one(item):
        name, path = item
        try:
            return name, pygame.image.load(path)
        except Exception as e:  # noqa: BLE001
            print(f"[assets] failed to load {path}: {e}")
            return name, None

    def _signature(self, paths):
        return {name: os.path.getmtime(p) for name, p in paths.items()}

    def _load_from_cache(self, paths, loading_screen=None):
        try:
            with open(self.cache_file, "rb") as f:
                blob = pickle.load(f)
        except (FileNotFoundError, EOFError, pickle.UnpicklingError):
            return False

        if blob.get("sig") != self._signature(paths):
            return False

        if loading_screen:
            loading_screen.put(1.0, "Loading asset cache")

        for name, (raw, size, fmt) in blob["data"].items():
            surf = pygame.image.frombytes(raw, size, fmt)
            self.images[name] = surf.convert_alpha()
        return True

    def _save_to_cache(self, paths):
        data = {}
        for name, surf in self.images.items():
            fmt = "RGBA"
            data[name] = (pygame.image.tobytes(surf, fmt), surf.get_size(), fmt)
        blob = {"sig": self._signature(paths), "data": data}
        try:
            with open(self.cache_file, "wb") as f:
                pickle.dump(blob, f, protocol=pickle.HIGHEST_PROTOCOL)
        except OSError as e:
            print(f"[assets] could not write cache: {e}")
