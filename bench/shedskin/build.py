# Builds the benchmark driver bench/core.py with Shedskin, into
# OUT/src/core (default __tpyc__/bench/shedskin-VARIANT). Shedskin reads a
# subset of Python, and the game steps outside it in a few mechanical ways,
# so this copies the sources into the build directory rewritten (see
# _ForShedskin) and compiles the copy; another_world/ stays as it is. The
# `tpy` helpers and the modules Shedskin lacks come from stubs/.
#
# Variants, both with Shedskin's generated Makefile, -march=native (its
# default) and the system Boehm GC (libgc-dev):
#   O3            -O3; index bounds checks and negative-index normalisation
#                 on
#   O3-unchecked  -O3, translated with --nobounds --nowrap (__SS_NOBOUNDS,
#                 __SS_NOWRAP): no index bounds checks and no negative-index
#                 normalisation, a different safety contract
#
# Writes OUT/build.json: the commands, flags, versions and binary SHA-256.
#
# Usage: python3 bench/shedskin/build.py [--variant V] [--shedskin CMD]
#            [--out DIR] [--cxx CXX]
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
from bench import reached_modules  # noqa: E402

FIXED_INTS = {"int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64"}
# variant -> (optimization flags, extra translate options)
VARIANTS = {
    "O3": ("-O3", []),
    "O3-unchecked": ("-O3", ["--nobounds", "--nowrap"]),
}


class _ForShedskin(ast.NodeTransformer):
    """The rewrites, each the same program for Shedskin: `match` on literal
    patterns -> if/elif/else on `==` (Shedskin has no `match`); `gzip.open` ->
    `gzip.gzopen`, as Shedskin takes no module function named like a builtin;
    relative imports -> absolute ones (Shedskin misreads `from ..x`); an
    f-string with format specs -> the same format as `%`, since Shedskin
    drops f-string specs (the DOS bank names are `bank{n:02x}`); `int32(x)`
    -> `int32(int(x))` (and the other widths), so each stays a function of
    int where the game also converts floats and bools."""

    def __init__(self, path: str, package: str) -> None:
        self.path = path
        self.package = package
        self.n = 0

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:
        if node.level > 0:
            parts = self.package.split(".")
            base = parts[:len(parts) - node.level + 1]
            node.module = ".".join(base + ([node.module] if node.module else []))
            node.level = 0
        return node

    def _test(self, subject: ast.expr, pattern: ast.pattern, line: int) -> ast.expr | None:
        if isinstance(pattern, ast.MatchValue):
            return ast.Compare(left=subject, ops=[ast.Eq()], comparators=[pattern.value])
        if isinstance(pattern, ast.MatchOr):
            tests = [self._test(subject, p, line) for p in pattern.patterns]
            return ast.BoolOp(op=ast.Or(), values=tests)
        if isinstance(pattern, ast.MatchAs) and pattern.pattern is None and pattern.name is None:
            return None
        raise SystemExit(f"{self.path}:{line}: only literal match patterns are rewritten")

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.expr:
        self.generic_visit(node)
        if not any(isinstance(v, ast.FormattedValue) and v.format_spec is not None
                   for v in node.values):
            return node
        fmt = ""
        args: list[ast.expr] = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                fmt += str(v.value).replace("%", "%%")
                continue
            assert isinstance(v, ast.FormattedValue)
            spec = ""
            if v.format_spec is not None:
                parts = v.format_spec.values  # type: ignore[attr-defined]
                if len(parts) != 1 or not isinstance(parts[0], ast.Constant) \
                        or not str(parts[0].value)[-1:] in "dxXs":
                    raise SystemExit(f"{self.path}:{node.lineno}: f-string spec not rewritten")
                spec = str(parts[0].value)
            fmt += "%" + (spec if spec else ("r" if v.conversion == ord("r") else "s"))
            args.append(v.value)
        return ast.BinOp(left=ast.Constant(fmt), op=ast.Mod(), right=ast.Tuple(args, ast.Load()))

    def visit_Call(self, node: ast.Call) -> ast.expr:
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id in FIXED_INTS and len(node.args) == 1:
            node.args = [ast.Call(func=ast.Name("int", ast.Load()), args=node.args, keywords=[])]
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.expr:
        self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == "gzip" and node.attr == "open":
            node.attr = "gzopen"
        return node

    def visit_Match(self, node: ast.Match) -> list[ast.stmt]:
        self.generic_visit(node)
        out: list[ast.stmt] = []
        subject = node.subject
        if not isinstance(subject, ast.Name):
            self.n += 1
            name = f"_match{self.n}"
            out.append(ast.Assign(targets=[ast.Name(id=name, ctx=ast.Store())], value=subject))
            subject = ast.Name(id=name, ctx=ast.Load())
        chain: list[ast.stmt] = []
        for case in reversed(node.cases):
            if case.guard is not None:
                raise SystemExit(f"{self.path}:{node.lineno}: match guards are not rewritten")
            test = self._test(subject, case.pattern, node.lineno)
            if test is None:
                chain = case.body
            else:
                chain = [ast.If(test=test, body=case.body, orelse=chain)]
        out.extend(chain)
        return out


def lower(path: str, package: str = "") -> str:
    tree = ast.parse(open(path).read(), path)
    # Shedskin rejects the future import; the annotations it defers are unused.
    tree.body = [s for s in tree.body
                 if not (isinstance(s, ast.ImportFrom) and s.module == "__future__")]
    tree = ast.fix_missing_locations(_ForShedskin(path, package).visit(tree))
    return ast.unparse(tree) + "\n"


def copy_sources(out: str) -> str:
    src = os.path.join(out, "src")
    if os.path.isdir(src):
        shutil.rmtree(src)
    for rel in reached_modules():
        dest = "core.py" if rel == os.path.join("bench", "core.py") else rel
        os.makedirs(os.path.join(src, os.path.dirname(dest)), exist_ok=True)
        with open(os.path.join(src, dest), "w") as f:
            f.write(lower(os.path.join(REPO, rel), os.path.dirname(rel).replace(os.sep, ".")))
    stubs = os.path.join(HERE, "stubs")
    for name in sorted(os.listdir(stubs)):
        if name.endswith(".py"):
            with open(os.path.join(src, name), "w") as f:
                f.write(lower(os.path.join(stubs, name)))
    return src


def first_line(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except OSError:
        return ""
    text = (r.stdout or r.stderr).strip()
    return text.splitlines()[0] if text else ""


def checkout_commit(command: str) -> str:
    """The short commit of the git checkout the shedskin command's package
    is imported from (an editable install of a clone), else ""."""
    exe = shutil.which(command)
    if exe is None:
        return ""
    with open(exe, "rb") as f:
        line = f.readline().decode(errors="replace")
    if not line.startswith("#!"):
        return ""
    where = subprocess.run(line[2:].split()[:1] + ["-c", "import os, shedskin; "
                           "print(os.path.dirname(shedskin.__file__))"],
                           capture_output=True, text=True).stdout.strip()
    r = subprocess.run(["git", "-C", where or "/", "rev-parse", "--short=8", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() if where and r.returncode == 0 else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Builds bench/core.py with Shedskin.")
    parser.add_argument("--variant", default="O3", choices=sorted(VARIANTS))
    parser.add_argument("--shedskin", default="shedskin", help="the shedskin command")
    parser.add_argument("--out", default="",
                        help="build directory (default __tpyc__/bench/shedskin-VARIANT)")
    parser.add_argument("--cxx", default="g++-14", help="the C++ compiler (default g++-14)")
    args = parser.parse_args()
    out = os.path.abspath(args.out or os.path.join(REPO, "__tpyc__", "bench",
                                                   "shedskin-" + args.variant))
    opt, options = VARIANTS[args.variant]
    src = copy_sources(out)
    # Replaces the platform's default flags file (shedskin/resources/flags),
    # which differs only in the -O level.
    flags = os.path.join(out, "flags")
    with open(flags, "w") as f:
        f.write(f"CXX?={args.cxx}\nCXXFLAGS?={opt} -std=c++20 -march=native $(CPPFLAGS)\n"
                "LDLIBS?=-lgc -lutil\n")
    translate = shlex.split(args.shedskin) + ["translate"] + options + ["-F", flags, "core.py"]
    print("+", shlex.join(translate), f"(in {src})", file=sys.stderr)
    r = subprocess.run(translate, cwd=src, capture_output=True, text=True)
    sys.stderr.write(r.stdout + r.stderr)
    if r.returncode != 0:
        return 1
    m = re.search(r"Compiler (\S+)", r.stdout)
    commit = checkout_commit(shlex.split(args.shedskin)[0])
    version = f"Shedskin {m.group(1) if m else '?'}" + (f" ({commit})" if commit else "")
    make = ["make", f"CXX={args.cxx}"]
    dry = subprocess.run(make + ["-n"], cwd=src, capture_output=True, text=True).stdout
    print("+", shlex.join(make), f"(in {src})", file=sys.stderr)
    if subprocess.run(make, cwd=src).returncode != 0:
        return 1
    binary = os.path.join(src, "core")
    with open(binary, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    record = {"variant": args.variant, "version": version,
              "cxx": first_line([args.cxx, "--version"]), "translate": shlex.join(translate),
              "flags_file": open(flags).read(),
              "compile": [line for line in dry.splitlines() if line.strip()],
              "binary": binary, "sha256": digest}
    with open(os.path.join(out, "build.json"), "w") as f:
        json.dump(record, f, indent=1)
    print(binary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
