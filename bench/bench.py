# The benchmark harness: builds every runner of bench/core.py, times them
# and prints a markdown table. Standard library only; any Python 3.10+.
#
#     python3 bench/bench.py build [--only tpy,shedskin,nuitka,mypyc]
#     python3 bench/bench.py run [--processes R] [--batches B] [--cpu N]
#
# A run is R rounds; each round starts every runner once, in an order
# rotated by one place per round, and each process times B batches of the
# scenes. Every scene's end-state digest must be core.py's, and a process
# that fails fails the run. Raw results go to __tpyc__/bench/results/.
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import modulefinder
import os
import platform
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, "__tpyc__", "bench")
CORE = os.path.join(HERE, "core.py")
BUILDS = ["tpy", "shedskin", "nuitka", "mypyc"]


def reached_modules() -> list[str]:
    """bench/core.py and the another_world modules it imports, directly or
    not, as paths relative to the repository."""
    finder = modulefinder.ModuleFinder(path=[REPO])
    finder.run_script(CORE)
    return sorted([os.path.join("bench", "core.py")] + [
        os.path.relpath(m.__file__, REPO) for name, m in finder.modules.items()
        if name.startswith("another_world") and m.__file__])


def scenes() -> dict[str, str]:
    """core.py's SCENES: name -> end-state digest as core.py prints it."""
    for node in ast.parse(open(CORE).read()).body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "SCENES":
            calls = [[ast.literal_eval(a) for a in c.args] for c in node.value.elts]
            return {c[0]: f"{c[4]:08x}" for c in calls}
    sys.exit("bench.py: no SCENES in core.py")


def tpy_package(lib: str) -> list[str]:
    """The tpy package's sources under LIB, relative to it."""
    root = os.path.join(lib, "tpy")
    return sorted(os.path.relpath(os.path.join(d, n), lib) for d, _, names in os.walk(root)
                  for n in names if n.endswith(".py"))


def sources_hash(build: str, tpy_lib: str) -> str:
    """The sources a build compiles, so `run` can tell a stale build."""
    files = [os.path.join(REPO, rel) for rel in reached_modules()]
    if build in ("nuitka", "mypyc"):
        files += [os.path.join(tpy_lib, rel) for rel in tpy_package(tpy_lib)]
    if build == "shedskin":
        stubs = os.path.join("bench", "shedskin", "stubs")
        files += [os.path.join(REPO, "bench", "shedskin", "build.py")] + [
            os.path.join(REPO, stubs, n) for n in sorted(os.listdir(os.path.join(REPO, stubs)))
            if n.endswith(".py")]
    h = hashlib.sha256()
    for path in files:
        name = os.path.relpath(path, REPO if path.startswith(REPO + os.sep) else tpy_lib)
        h.update(name.encode() + b"\0" + open(path, "rb").read())
    return h.hexdigest()


def first_line(cmd: list[str], cwd: str = REPO) -> str:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except OSError:
        return ""
    lines = r.stdout.strip().splitlines()
    return lines[0] if r.returncode == 0 and lines else ""


def check(cmd: list[str], cwd: str = REPO, env: dict[str, str] | None = None) -> None:
    print("+", shlex.join(cmd), file=sys.stderr)
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"{r.stdout[-4000:]}{r.stderr[-4000:]}bench.py: failed: {shlex.join(cmd)}")


def python_env(paths: list[str]) -> dict[str, str]:
    # Fast mode: tpy's fixed-width types are int (see docs/DEVELOPMENT.md#fairness).
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(paths), TPY_CPYTHON_FAST="1")
    env.pop("PYTHONHOME", None)
    return env


def nuitka_env(build: str) -> dict[str, str]:
    """What Nuitka's core.sh sets, minus the source directories, so the
    compiled modules are the only ones there are."""
    env = python_env([])
    sh = os.path.join(build, "core.sh")
    script = open(sh).read() if os.path.exists(sh) else ""
    for key in ("PYTHONHOME", "PYTHONPATH"):
        m = re.search(rf'^{key}="?([^"\n]*)"?$', script, re.M)
        if m:
            env[key] = os.pathsep.join(p for p in m.group(1).split(os.pathsep)
                                       if p and not p.startswith(REPO))
    return env


def find_tpy_lib(arg: str) -> str:
    """The directory tpy-lang's `tpy` package is in: ARG, or where the Python
    behind the `tpy` command imports it from."""
    lib = os.path.abspath(arg) if arg else ""
    if not lib:
        cmd = shutil.which("tpy") or ""
        try:
            shebang = open(cmd, "rb").readline().decode()
        except (OSError, UnicodeDecodeError):
            shebang = ""
        if shebang.startswith("#!"):
            lib = first_line(shlex.split(shebang[2:]) + [
                "-c", "import os, tpy; print(os.path.dirname(os.path.dirname(tpy.__file__)))"],
                cwd="/")
    init = os.path.join(lib, "tpy", "__init__.py")
    if not lib or not os.path.exists(init) or "TPY_CPYTHON_FAST" not in open(init).read():
        sys.exit("bench.py: no tpy package with fast mode (tpy-lang after 0.7.0.dev0's "
                 "de3f644fa6); name its directory with --tpy-lib")
    return lib


class Tools:
    def __init__(self, args: argparse.Namespace) -> None:
        self.tpy_lib = find_tpy_lib(args.tpy_lib)
        uv = lambda spec: first_line(["uv", "python", "find", "--no-project", spec], cwd="/")
        self.cpython = args.cpython or uv("cpython3.14")
        self.pypy311 = args.pypy311 or uv("pypy3.11")
        self.pypy312 = args.pypy312 or uv("pypy3.12")
        venvs = os.path.abspath(args.venvs)
        self.nuitka = os.path.join(venvs, "venv-nuitka", "bin", "python")
        self.mypyc = os.path.join(venvs, "venv-mypyc", "bin", "python")

    def runners(self) -> list[tuple[str, str, str, list[str], dict[str, str], str]]:
        """(name, label, build directory or "", argv, env, cwd), in table order."""
        py = python_env([self.tpy_lib, REPO])
        mypyc = os.path.join(OUT, "mypyc")
        ss = lambda v: [os.path.join(OUT, f"shedskin-{v}", "src", "core")]
        return [("tpy", "TPy", "tpy", [os.path.join(OUT, "tpy", "release", "core")],
                 python_env([]), REPO),
                ("cpython", "CPython 3.14", "", [self.cpython, "-s", CORE], py, REPO),
                ("pypy311", "PyPy 3.11", "", [self.pypy311, "-s", CORE], py, REPO),
                ("pypy312", "PyPy 3.12", "", [self.pypy312, "-s", CORE], py, REPO),
                ("nuitka", "Nuitka (CPython 3.14)", "nuitka",
                 [os.path.join(OUT, "nuitka", "core.bin")], nuitka_env(os.path.join(OUT, "nuitka")),
                 REPO),
                # -P: the compiled tree is where the modules come from.
                ("mypyc", "mypyc (CPython 3.14)", "mypyc",
                 [self.mypyc, "-P", "-s", "-c", "import sys, core; sys.exit(core.main())"],
                 python_env([mypyc, self.tpy_lib]), mypyc),
                ("shedskin", "Shedskin -O3", "shedskin-O3", ss("O3"), python_env([]), REPO),
                ("shedskin-unchecked", "Shedskin -O3 --nobounds --nowrap (unchecked)",
                 "shedskin-O3-unchecked", ss("O3-unchecked"), python_env([]), REPO)]

    def interpreter(self, python: str) -> str:
        code = "import platform, sys; v = getattr(sys, 'pypy_version_info', None); " \
               "print(('PyPy %d.%d.%d' % v[:3]) if v else 'CPython ' + platform.python_version())"
        return first_line([python, "-c", code]) or python


def record(build: str, sources: str, version: str) -> None:
    with open(os.path.join(OUT, build, "bench-build.json"), "w") as f:
        json.dump({"sources": sources, "version": version}, f)


def cmd_build(args: argparse.Namespace) -> int:
    tools = Tools(args)
    only = args.only.split(",")
    if unknown := [b for b in only if b not in BUILDS]:
        sys.exit(f"bench.py: unknown build {', '.join(unknown)}; known: {', '.join(BUILDS)}")
    tpy = shlex.split(args.tpy)
    if "tpy" in only:
        check(tpy + ["--rebuild", "-L", REPO, "-o", os.path.join(OUT, "tpy"), "-b", CORE])
        record("tpy", sources_hash("tpy", tools.tpy_lib), first_line(tpy + ["--version"]))
    if "shedskin" in only:
        cxx = first_line([args.cxx, "--version"])
        for v in ("O3", "O3-unchecked"):
            out = os.path.join(OUT, f"shedskin-{v}")
            check([sys.executable, os.path.join(HERE, "shedskin", "build.py"), "--variant", v,
                   "--shedskin", args.shedskin, "--cxx", args.cxx, "--out", out])
            version = json.load(open(os.path.join(out, "build.json")))["version"]
            record(f"shedskin-{v}", sources_hash("shedskin", tools.tpy_lib), f"{version} with {cxx}")
    if "nuitka" in only:
        out = os.path.join(OUT, "nuitka")
        shutil.rmtree(out, ignore_errors=True)
        report = os.path.join(out, "report.xml")
        check([tools.nuitka, "-m", "nuitka", "--follow-imports", f"--output-dir={out}",
               f"--report={report}", CORE], env=python_env([tools.tpy_lib, REPO]))
        kinds = {m.get("name", ""): m.get("kind", "")
                 for m in ET.parse(report).getroot().iter("module")}
        ours = [n for n in kinds if n == "tpy" or n.startswith("another_world")]
        if "another_world.vm" not in ours or any(
                not kinds[n].startswith("Compiled") for n in ours):
            sys.exit(f"bench.py: Nuitka left some of the game uncompiled: {kinds}")
        record("nuitka", sources_hash("nuitka", tools.tpy_lib),
               "Nuitka " + first_line([tools.nuitka, "-m", "nuitka", "--version"]))
    if "mypyc" in only:
        # Only the modules core.py reaches: mypy rejects some it does not.
        # tpy stays interpreted; mypy reads its static view from MYPYPATH,
        # and from there reports errors in the package's own body, which it
        # would not for an installed package.
        out = os.path.join(OUT, "mypyc")
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        with open(os.path.join(out, "mypy.ini"), "w") as f:
            f.write("[mypy]\n[mypy-tpy.*]\nignore_errors = True\n")
        files = []
        for rel in reached_modules():
            dest = os.path.basename(rel) if rel.startswith("bench") else rel
            os.makedirs(os.path.join(out, os.path.dirname(dest)), exist_ok=True)
            shutil.copy(os.path.join(REPO, rel), os.path.join(out, dest))
            files.append(dest)
        check([os.path.join(os.path.dirname(tools.mypyc), "mypyc")] + files, cwd=out,
              env=dict(os.environ, MYPYPATH=tools.tpy_lib))
        mypy = first_line([tools.mypyc, "-c", "import mypy.version as v; print(v.__version__)"])
        record("mypyc", sources_hash("mypyc", tools.tpy_lib), f"mypy {mypy}")
    return 0


class Failed(Exception):
    pass


def run_process(argv: list[str], env: dict[str, str], cwd: str, batches: int,
                want: dict[str, str]) -> list[list[int]]:
    """Nanoseconds per batch and scene, after checking every end state."""
    r = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True)
    got: dict[tuple[int, str], int] = {}
    problems = [] if r.returncode == 0 else [f"exit status {r.returncode}"]
    for line in r.stdout.splitlines():
        f = line.split()
        if len(f) != 5 or f[0] != "end":
            continue
        _, name, batch, ns, state = f
        if name not in want or not 1 <= int(batch) <= batches or (int(batch), name) in got \
                or state != want[name]:
            problems.append(f"unexpected record: {line}")
        got[(int(batch), name)] = int(ns)
    if len(got) != batches * len(want):
        problems.append(f"{len(got)} records, not {batches} for each of {', '.join(want)}")
    if problems:
        raise Failed(f"{r.stderr[-4000:]}bench.py: FAILED: {shlex.join(argv)}: "
                     + "; ".join(problems[:5]))
    return [[got[(b, name)] for name in want] for b in range(1, batches + 1)]


def ms(ns: float) -> str:
    v = ns / 1e6
    return f"{v:.0f} ms" if v >= 100 else f"{v:.1f} ms"


def cmd_run(args: argparse.Namespace) -> int:
    if args.processes < 1 or not 1 <= args.steady_from <= args.batches:
        sys.exit("bench.py: need --processes >= 1 and 1 <= --steady-from <= --batches")
    tools = Tools(args)
    runners = tools.runners()
    if args.runners:
        wanted = args.runners.split(",")
        if unknown := [n for n in wanted if n not in [r[0] for r in runners]]:
            sys.exit(f"bench.py: unknown runner {', '.join(unknown)}; "
                     f"known: {', '.join(r[0] for r in runners)}")
        runners = [r for r in runners if r[0] in wanted]
    versions: list[str] = []
    for name, _, build, argv, _, cwd in runners:
        if not os.path.exists(argv[0]) or not os.path.isdir(cwd):
            sys.exit(f"bench.py: no {name} " + ("(bench.py build)" if build else
                                                 f"(--{name} names its interpreter)"))
        if not build:
            versions.append(tools.interpreter(argv[0]))
            continue
        path = os.path.join(OUT, build, "bench-build.json")
        info = json.load(open(path)) if os.path.exists(path) else {}
        if info.get("sources") != sources_hash(build.split("-")[0], tools.tpy_lib):
            sys.exit(f"bench.py: the {name} build is stale or unrecorded (bench.py build)")
        versions.append(info["version"])
    want = scenes()
    pin = ["taskset", "-c", str(args.cpu)] if args.cpu >= 0 else []
    data = os.path.abspath(args.data)
    samples: dict[str, list[list[list[int]]]] = {r[0]: [] for r in runners}
    os.makedirs(os.path.join(OUT, "results"), exist_ok=True)
    out = os.path.join(OUT, "results", time.strftime("%Y%m%d-%H%M%S") + ".json")

    def save() -> None:
        with open(out, "w") as f:
            json.dump({"processes": args.processes, "batches": args.batches,
                       "scenes": list(want), "ns": samples}, f)
        print(f"raw results: {os.path.relpath(out, REPO)}", file=sys.stderr)

    for rnd in range(args.processes):
        k = rnd % len(runners)
        for name, _, _, argv, env, cwd in runners[k:] + runners[:k]:
            try:
                ns = run_process(pin + argv + [data, str(args.batches)], env, cwd,
                                 args.batches, want)
            except Failed as e:
                save()
                sys.exit(str(e))
            samples[name].append(ns)
            print(f"round {rnd + 1} {name:18} {ms(sum(map(sum, ns)) / len(ns))} per batch",
                  file=sys.stderr)
    save()

    # A process's steady state: the median of its batches from --steady-from on.
    steady = {name: [statistics.median(sum(b) for b in p[args.steady_from - 1:]) for p in procs]
              for name, procs in samples.items()}
    try:
        cpu = re.search(r"model name\s*:\s*(.*)", open("/proc/cpuinfo").read())
    except OSError:  # no /proc outside Linux
        cpu = None
    pinned = f"pinned to CPU {args.cpu}" if pin else "not pinned"
    print(f"{cpu.group(1) if cpu else platform.processor()}, "
          f"{platform.system()} {platform.release()}, "
          f"{pinned}; {', '.join(dict.fromkeys(versions))}.\n\n{args.processes} processes x "
          f"{args.batches} batches; a process's batch time is the median of its batches "
          f"{args.steady_from}-{args.batches}; median [min-max] over the processes.\n")
    print("| runner | ms per batch | vs TPy (slower) |\n|---|---:|---:|")
    base = statistics.median(steady["tpy"]) if "tpy" in steady else 0.0
    for name, label, *_ in runners:
        v = steady[name]
        ratio = f"{statistics.median(v) / base:.1f}x" if base else "-"
        print(f"| {label} | {ms(statistics.median(v))} [{ms(min(v))}-{ms(max(v))}] | {ratio} |")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="The Another World engine benchmark.")
    parser.add_argument("--cpython", default="", help="default: uv's cpython3.14")
    parser.add_argument("--pypy311", default="", help="default: uv's pypy3.11")
    parser.add_argument("--pypy312", default="", help="default: uv's pypy3.12")
    parser.add_argument("--venvs", default=os.path.join(OUT, "venvs"), metavar="DIR",
                        help="where venv-nuitka and venv-mypyc are")
    parser.add_argument("--tpy-lib", default="", metavar="DIR",
                        help="the directory of tpy-lang's tpy package, for the Python runners "
                             "(default: the tpy command's)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build", help="build the runners")
    p.add_argument("--only", default=",".join(BUILDS))
    p.add_argument("--tpy", default="tpy", help="the tpy command (default tpy)")
    p.add_argument("--shedskin", default="shedskin", help="the shedskin command")
    p.add_argument("--cxx", default="g++-14", help="the C++ compiler for Shedskin")
    p.set_defaults(func=cmd_build)
    p = sub.add_parser("run", help="time the runners")
    p.add_argument("--data", default=os.path.join(REPO, "data", "pc"))
    p.add_argument("--processes", type=int, default=5)
    p.add_argument("--batches", type=int, default=20)
    p.add_argument("--steady-from", type=int, default=11)
    p.add_argument("--cpu", type=int, default=-1, help="the CPU to pin to (default: none)")
    p.add_argument("--runners", default="", help="comma-separated runner names")
    p.set_defaults(func=cmd_run)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
