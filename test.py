"""
Scratch test file, rewritten from empty at the start of each new prompt.
Not part of the game itself -- a place to verify behavior while working,
that you can look at afterward. Run directly: `python test.py`.

Common setup (pygame needs a real display surface for asset conversion,
even though nothing is actually shown):

    import pygame
    pygame.init()
    pygame.display.set_mode((100, 100), pygame.HIDDEN)

    from scripts.global_assets import load_assets
    load_assets()

Each check lives in its own test_*() function. main() runs them all in
order and reports pass/fail; an assertion failure inside one is caught and
reported without stopping the others.
"""

import pygame

pygame.init()
pygame.display.set_mode((100, 100), pygame.HIDDEN)

from scripts.global_assets import load_assets

load_assets()


def test_example():
    """Placeholder -- replace with whatever's being verified this session."""
    assert 1 + 1 == 2


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    passed, failed = 0, 0
    for name, fn in tests:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"[FAIL] {name}: {e}")
        else:
            passed += 1
            print(f"[PASS] {name}")
    print(f"\n{passed} passed, {failed} failed")


if __name__ == "__main__":
    main()
