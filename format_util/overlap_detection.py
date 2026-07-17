import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

EXCLUDED_DIRS = {".git", ".venv", "venv", "env", "__pycache__", "node_modules", "build", "dist", ".tox", ".mypy_cache", ".pytest_cache"}

DUNDER_RE = re.compile(r"^__[a-zA-Z0-9_]+__$")
KEEP_NAMES = {"self", "cls"}


def camel_to_snake(name: str) -> str:
    prefix = name[: len(name) - len(name.lstrip("_"))]
    core = name[len(prefix) :]
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", core)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    return prefix + s2.lower()


def iter_py_files(root: Path):
    for path in root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        yield path


def collect_names(root: Path) -> dict:
    """name -> set of (relative_path, lineno) where it's bound."""
    occurrences = defaultdict(set)
    for path in iter_py_files(root):
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (SyntaxError, UnicodeDecodeError):
            continue

        rel = path.relative_to(root)
        for node in ast.walk(tree):
            name = None
            lineno = None
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name, lineno = node.name, node.lineno
            elif isinstance(node, ast.arg):
                name, lineno = node.arg, node.lineno
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                name, lineno = node.id, node.lineno
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store) and isinstance(node.value, ast.Name) and node.value.id in ("self", "cls"):
                name, lineno = node.attr, node.lineno

            if name and name not in KEEP_NAMES and not DUNDER_RE.match(name):
                occurrences[name].add((str(rel), lineno))

    return occurrences


def main():
    if len(sys.argv) != 2:
        print("Usage: python check_snake_collisions.py /path/to/project", file=sys.stderr)
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    occurrences = collect_names(root)

    # group original names by what they'd become after conversion
    groups = defaultdict(set)
    for name in occurrences:
        groups[camel_to_snake(name)].add(name)

    collisions = {snake: originals for snake, originals in groups.items() if len(originals) > 1}

    if not collisions:
        print("No collisions found -- safe to run the renamer.")
        return

    print(f"Found {len(collisions)} collision(s). Fix these by hand before renaming:\n")
    for snake, originals in sorted(collisions.items()):
        print(f"  {' / '.join(sorted(originals))}  -->  both become '{snake}'")
        for name in sorted(originals):
            locations = sorted(occurrences[name])
            # sample = ", ".join(f"{p}:{l}" for p, l in locations[:3])
            # more = f"  (+{len(locations) - 3} more)" if len(locations) > 3 else ""
            sample = ", ".join(f"{p}:{l}" for p, l in locations)
            more = ""
            print(f"      {name}: {sample}{more}")
        print()


if __name__ == "__main__":
    main()
