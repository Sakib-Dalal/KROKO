#!/usr/bin/env python3
"""KROKO benchmark: reproduce the performance and robustness figures.

Runs the gate over the Python standard library, times it, compares against bare
parsing, and probes the awkward inputs. Usage:

    python3 tests/benchmark.py [CORPUS_DIR]
"""
import ast
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PROJECT, "scripts"))

import kroko


def default_corpus():
    """The Python standard library shipped with the running interpreter."""
    return os.path.join(sys.prefix, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}")


def collect(root):
    """Every .py file beneath root, sorted for reproducibility."""
    found = []
    for directory, _, names in os.walk(root):
        for name in names:
            if name.endswith(".py"):
                found.append(os.path.join(directory, name))
    return sorted(found)


def count_lines(files):
    """Total physical lines across the corpus."""
    total = 0
    for path in files:
        total += len(kroko._read_source(path).splitlines())
    return total


def bench_mode(files, strict):
    """Time one mode over the corpus, returning seconds and per-code counts."""
    counts = {}
    crashes = []
    started = time.perf_counter()
    for path in files:
        try:
            problems = kroko.check(path, strict)
        except (SyntaxError, UnicodeDecodeError, OSError, MemoryError) as error:
            crashes.append((path, type(error).__name__))
            continue
        for code, _, _ in problems:
            counts[code] = counts.get(code, 0) + 1
    return time.perf_counter() - started, counts, crashes


def bench_parse(files):
    """Time bare ast.parse, so the gate's own overhead is measurable."""
    started = time.perf_counter()
    failed = 0
    for path in files:
        try:
            ast.parse(kroko._read_source(path), path)
        except SyntaxError:
            failed += 1
    return time.perf_counter() - started, failed


def bench_suite():
    """Time the regression suite as a user runs it."""
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, os.path.join(PROJECT, "scripts", "kroko_selftest.py")],
        capture_output=True, text=True)
    return time.perf_counter() - started, proc.returncode, proc.stdout.strip().splitlines()[-1]


def probe(label, content):
    """Run the gate over one crafted file and report the verdict."""
    path = os.path.join("/tmp", f"kroko_bench_{label}.py")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    try:
        problems = kroko.check(path, False)
        verdict = ",".join(sorted({code for code, _, _ in problems})) or "clean"
    except (SyntaxError, UnicodeDecodeError, OSError) as error:
        verdict = f"CRASH {type(error).__name__}"
    os.remove(path)
    return label, verdict


def report(label, seconds, stats):
    """Print one mode's timing block from (file count, line count, crashes, counts)."""
    files, lines, crashes, counts = stats
    print(f"{label}: {seconds:.2f}s, {seconds / files * 1000:.1f} ms/file, "
          f"{files / seconds:.0f} files/s, {lines / seconds / 1000:.0f}k lines/s, "
          f"crashes={len(crashes)}, findings={sum(counts.values())}")
    for code in sorted(counts):
        print(f"   {code}  {counts[code]}")


def main(argv):
    """Run the benchmark and return a shell exit code."""
    corpus = argv[0] if argv else default_corpus()
    if not os.path.isdir(corpus):
        print(f"no such corpus directory: {corpus}")
        return 2
    files = collect(corpus)
    lines = count_lines(files)
    print(f"corpus: {len(files)} files, {lines:,} lines under {corpus}")

    suite_seconds, suite_code, suite_line = bench_suite()
    print(f"\nregression suite: {suite_seconds:.2f}s, exit={suite_code}, {suite_line}")

    default_seconds, counts, crashes = bench_mode(files, False)
    report("default mode", default_seconds, (len(files), lines, crashes, counts))
    strict_seconds, strict_counts, strict_crashes = bench_mode(files, True)
    report("strict mode", strict_seconds, (len(files), lines, strict_crashes, strict_counts))

    parse_seconds, failed = bench_parse(files)
    print(f"\nbare ast.parse: {parse_seconds:.2f}s ({parse_seconds / default_seconds * 100:.0f}% of gate time), "
          f"unparseable={failed}")
    print(f"gate overhead beyond parsing: {default_seconds - parse_seconds:.2f}s "
          f"({(default_seconds - parse_seconds) / len(files) * 1000:.1f} ms/file)")

    print("\nrobustness probes:")
    probes = (
        ("clean", '"""Module."""\n\n\ndef run(value):\n    """Return it."""\n    return value\n'),
        ("empty", ""),
        ("py310_match", '"""Module."""\n\n\ndef go(kind):\n    """Route."""\n    match kind:\n        case 1:\n            return 1\n    return 0\n'),
        ("syntax_error", '"""Module."""\n\ndef broken(:\n    return 1\n'),
    )
    for label, content in probes:
        name, verdict = probe(label, content)
        print(f"   {name:<14} {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
