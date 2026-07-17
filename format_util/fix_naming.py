import argparse
import ast
import re
import sys
import typing
from pathlib import Path

import libcst as cst

EXCLUDED_DIRS = {".git", ".venv", "venv", "env", "__pycache__", "node_modules", "build", "dist", ".tox", ".mypy_cache", ".pytest_cache"}

CAMEL_RE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
DUNDER_RE = re.compile(r"^__[a-zA-Z0-9_]+__$")
KEEP_NAMES = {"self", "cls"}


def is_camel_case(name: str) -> bool:
    if name in KEEP_NAMES or DUNDER_RE.match(name):
        return False
    core = name.lstrip("_")
    if not core:
        return False
    if not CAMEL_RE.match(core):
        return False
    return any(c.isupper() for c in core)


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


def collect_candidates(root: Path) -> dict:
    """Build the global old_name -> new_name map by scanning every file
    for camelCase bindings."""
    names = set()
    for path in iter_py_files(root):
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            name = None
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
            elif isinstance(node, ast.arg):
                name = node.arg
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                name = node.id
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store) and isinstance(node.value, ast.Name) and node.value.id in ("self", "cls"):
                name = node.attr

            if name and is_camel_case(name):
                names.add(name)

    return {name: camel_to_snake(name) for name in names if camel_to_snake(name) != name}

class RenameTransformer(cst.CSTTransformer):
    def __init__(self, rename_map: dict):
        self.rename_map = rename_map
        self.changed = False

    @typing.override
    def leave_Name(self, original_node, updated_node):
        new = self.rename_map.get(updated_node.value)
        if new is not None:
            self.changed = True
            return updated_node.with_changes(value=new)
        return updated_node

    @typing.override
    def leave_Attribute(self, original_node, updated_node):
        new = self.rename_map.get(updated_node.attr.value)
        if new is not None:
            self.changed = True
            return updated_node.with_changes(attr=updated_node.attr.with_changes(value=new))
        return updated_node


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project_root", help="Path to the root of your Python project")
    parser.add_argument("--write", action="store_true", help="Actually apply renames (default is dry-run / list only)")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    rename_map = collect_candidates(root)
    if not rename_map:
        print("No camelCase names found. Nothing to do.")
        return

    print(f"Found {len(rename_map)} name(s) to rename:")
    for old, new in sorted(rename_map.items()):
        print(f"  {old} -> {new}")

    if not args.write:
        print("\nThis was a dry run -- re-run with --write to actually apply changes.")
        return

    print()
    files_changed = 0
    for path in iter_py_files(root):
        try:
            text = path.read_text(encoding="utf-8")
            module = cst.parse_module(text)
        except (cst.ParserSyntaxError, UnicodeDecodeError) as e:
            print(f"[skipped] {path.relative_to(root)}  ({e})", file=sys.stderr)
            continue

        transformer = RenameTransformer(rename_map)
        new_module = module.visit(transformer)

        if transformer.changed:
            path.write_text(new_module.code, encoding="utf-8")
            files_changed += 1
            print(f"[updated] {path.relative_to(root)}")

    print(f"\nDone. {files_changed} file(s) updated.")


if __name__ == "__main__":
    main()
