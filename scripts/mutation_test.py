"""Small AST-based mutation tester for the price tool (dev only, standard library only).

Why not mutmut: mutmut 3 maps file paths to module names by stripping a ``src/`` prefix
(this repo uses ``backend/``) and only mutates code inside functions, so it would skip the
module-level band constants (LEASE_BANDS, STOREY_BANDS, MIN_SUMMARY_VOLUME) that matter most.

How it works:
1. Parse each target module and collect one mutant per (node, operator) below.
2. For each mutant, write the mutated module into a private copy of ``backend/`` and run
   the listed test files once in a fresh ``pytest -x`` subprocess, with that copy first on
   PYTHONPATH. A non-zero exit (failure, error or timeout) = killed; exit 0 = survived.
3. Print the score and every survivor (line, original -> mutated source).

Out of scope (never mutated): docstrings, type annotations, the ``main()`` CLI and the
``if __name__ == "__main__"`` block, exception class bodies, and ``Protocol`` stubs.

Usage:
    python scripts/mutation_test.py                # all mutants, parallel
    python scripts/mutation_test.py --list         # list mutants without running tests
    python scripts/mutation_test.py --json out.json
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    "backend/kopi_keys/components/price_query.py",
    "backend/kopi_keys/components/price_display.py",
]
# tests/test_price_*.py plus the importer tests, which build the databases the price tests use.
TESTS = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("test_price_*.py")) + [
    "tests/test_resale_db.py",
]
SKIP_FUNCTIONS = {"main"}
TIMEOUT_SECONDS = 60

CMP_SWAPS = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In,
    ast.Is: ast.IsNot, ast.IsNot: ast.Is,
}
BINOP_SWAPS = {
    ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult,
    ast.FloorDiv: ast.Div, ast.Mod: ast.Mult,
}
NAME_SWAPS = {"min": "max", "max": "min"}


@dataclass
class Mutant:
    id: int
    file: str
    line: int
    operator: str
    original: str
    mutated: str
    status: str = "pending"


def _skipped_ranges(tree: ast.Module) -> list[tuple[int, int]]:
    """Line ranges never mutated: main(), __main__ guard, exception classes, Protocols."""
    ranges = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in SKIP_FUNCTIONS:
            ranges.append((node.lineno, node.end_lineno))
        elif isinstance(node, ast.If) and "__name__" in ast.unparse(node.test):
            ranges.append((node.lineno, node.end_lineno))
        elif isinstance(node, ast.ClassDef):
            bases = {ast.unparse(b) for b in node.bases}
            if "Protocol" in bases or any(b.endswith("Error") for b in bases):
                ranges.append((node.lineno, node.end_lineno))
    return ranges


def _docstring_and_annotation_ids(tree: ast.Module) -> set[int]:
    """ids of nodes inside docstrings or annotations, which are never mutated."""
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                skip.add(id(body[0].value))
        annotations = []
        if isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotations.append(node.returns)
            for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
                annotations.append(arg.annotation)
        for annotation in filter(None, annotations):
            skip.update(id(n) for n in ast.walk(annotation))
    return skip


def _candidates(node: ast.AST):
    """(operator name, function that mutates a deep copy of `node` in place) pairs."""
    if isinstance(node, ast.Compare):
        for i, op in enumerate(node.ops):
            if type(op) in CMP_SWAPS:
                new = CMP_SWAPS[type(op)]
                yield f"cmp {type(op).__name__}->{new.__name__}", \
                    (lambda n, i=i, new=new: n.ops.__setitem__(i, new()))
    elif isinstance(node, ast.BinOp) and type(node.op) in BINOP_SWAPS:
        new = BINOP_SWAPS[type(node.op)]
        yield f"binop {type(node.op).__name__}->{new.__name__}", (lambda n, new=new: setattr(n, "op", new()))
    elif isinstance(node, ast.BoolOp):
        new = ast.Or if isinstance(node.op, ast.And) else ast.And
        yield f"boolop ->{new.__name__}", (lambda n, new=new: setattr(n, "op", new()))
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        yield "drop not", None  # handled by replacing the node with its operand
    elif isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool):
            yield f"const {value}->{not value}", (lambda n: setattr(n, "value", not n.value))
        elif isinstance(value, int):
            yield f"const {value}->{value + 1}", (lambda n: setattr(n, "value", n.value + 1))
            yield f"const {value}->{value - 1}", (lambda n: setattr(n, "value", n.value - 1))
        elif isinstance(value, str) and value:
            yield "str XX", (lambda n: setattr(n, "value", "XX" + n.value + "XX"))
    elif isinstance(node, ast.Name) and node.id in NAME_SWAPS and isinstance(node.ctx, ast.Load):
        yield f"name {node.id}->{NAME_SWAPS[node.id]}", (lambda n: setattr(n, "id", NAME_SWAPS[n.id]))


class _Replace(ast.NodeTransformer):
    """Apply one mutation to the node at position `index` in a fixed walk order."""

    def __init__(self, index: int, operator: str, apply):
        self.index, self.operator, self.apply = index, operator, apply
        self.position = -1

    def generic_visit(self, node):
        self.position += 1
        if self.position == self.index:
            if self.operator == "drop not":
                return node.operand
            self.apply(node)
            return node
        return super().generic_visit(node)


def _walk_order(tree: ast.AST) -> list[ast.AST]:
    """Nodes in the same pre-order _Replace visits them."""
    order: list[ast.AST] = []

    def visit(node):
        order.append(node)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return order


def collect(path: str) -> list[tuple[Mutant, str]]:
    """Every mutant in `path`, with the full mutated source."""
    source = (ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    skip_ranges = _skipped_ranges(tree)
    skip_ids = _docstring_and_annotation_ids(tree)
    out = []
    for index, node in enumerate(_walk_order(tree)):
        line = getattr(node, "lineno", None)
        if line is None or id(node) in skip_ids or any(a <= line <= b for a, b in skip_ranges):
            continue
        # f-string pieces are Constants too; mutating them is fine. Skip format specs like ":,".
        for operator, apply in _candidates(node):
            mutated_tree = copy.deepcopy(tree)
            _Replace(index, operator, apply).visit(mutated_tree)
            mutated_source = ast.unparse(mutated_tree)
            if mutated_source == ast.unparse(tree):
                continue
            before = ast.unparse(node)
            after_node = _walk_order(mutated_tree)[index] if operator != "drop not" else node.operand
            after = ast.unparse(after_node)
            out.append((Mutant(0, path, line, operator, before, after), mutated_source))
    return out


def _make_workspace() -> Path:
    """A private copy of backend/ plus links to the rest of the repo the tests read."""
    work = Path(tempfile.mkdtemp(prefix="mut-"))
    shutil.copytree(ROOT / "backend", work / "backend",
                    ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
    for name in ("data", "tests", "scripts", "frontend"):
        if (ROOT / name).exists():
            (work / name).symlink_to(ROOT / name)
    return work


def _run_tests(work: Path) -> tuple[int, str]:
    env = {**os.environ, "PYTHONPATH": str(work / "backend"), "PYTHONDONTWRITEBYTECODE": "1"}
    command = [sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider",
               *[str(ROOT / t) for t in TESTS]]
    try:
        done = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                              timeout=TIMEOUT_SECONDS)
        return done.returncode, done.stdout[-400:]
    except subprocess.TimeoutExpired:
        return -1, "timeout"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="list mutants, don't run tests")
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    parser.add_argument("--json", type=Path, help="write all mutants and results here")
    args = parser.parse_args()

    mutants: list[tuple[Mutant, str]] = []
    for target in TARGETS:
        mutants.extend(collect(target))
    for number, (mutant, _) in enumerate(mutants, start=1):
        mutant.id = number
    if args.list:
        for mutant, _ in mutants:
            print(f"#{mutant.id:3d} {mutant.file}:{mutant.line} {mutant.operator}: "
                  f"{mutant.original!r} -> {mutant.mutated!r}")
        print(f"{len(mutants)} mutants")
        return

    baseline = _make_workspace()
    code, tail = _run_tests(baseline)
    if code != 0:
        raise SystemExit(f"Tests fail before any mutation; fix them first.\n{tail}")

    workspaces = [baseline] + [_make_workspace() for _ in range(args.jobs - 1)]
    free = list(workspaces)

    def run(item):
        mutant, source = item
        work = free.pop()
        target = work / mutant.file
        original = (ROOT / mutant.file).read_text(encoding="utf-8")
        try:
            target.write_text(source, encoding="utf-8")
            code, _ = _run_tests(work)
            mutant.status = "survived" if code == 0 else ("timeout" if code == -1 else "killed")
        finally:
            target.write_text(original, encoding="utf-8")
            free.append(work)
        return mutant

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(run, mutants))
    for work in workspaces:
        shutil.rmtree(work, ignore_errors=True)

    killed = sum(m.status != "survived" for m in results)
    print(f"\nMutation score: {killed}/{len(results)} killed = {100 * killed / len(results):.1f}%")
    for target in TARGETS:
        part = [m for m in results if m.file == target]
        dead = sum(m.status != "survived" for m in part)
        print(f"  {target}: {dead}/{len(part)}")
    survivors = [m for m in results if m.status == "survived"]
    print(f"\n{len(survivors)} survivors:")
    for m in survivors:
        print(f"  #{m.id:3d} {Path(m.file).name}:{m.line} [{m.operator}] {m.original!r} -> {m.mutated!r}")
    if args.json:
        args.json.write_text(json.dumps([asdict(m) for m in results], indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
