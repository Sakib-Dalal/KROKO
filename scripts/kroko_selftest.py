#!/usr/bin/env python3
"""KROKO self-test: prove every gate fires exactly where it should, and nowhere else.

Each case names a fixture, a mode and the exact set of codes expected. A case
passes only when the gate's reported code set equals the expected set, so an
extra finding is a failure just as a missing one is.

    python3 scripts/kroko_selftest.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import kroko

CASES = (
    ("good_clean.py", "default", frozenset()),
    ("good_clean.py", "strict", frozenset()),
    ("bad_recursion.py", "default", frozenset({"K001"})),
    ("bad_mutual.py", "default", frozenset({"K001"})),
    ("bad_long.py", "default", frozenset({"K002"})),
    ("bad_nesting.py", "default", frozenset({"K003"})),
    ("bad_params.py", "default", frozenset({"K004"})),
    ("bad_params_posonly.py", "default", frozenset({"K004"})),
    ("bad_cognitive.py", "default", frozenset({"K005"})),
    ("bad_swallow.py", "default", frozenset({"K006"})),
    ("bad_state.py", "default", frozenset({"K007"})),
    ("bad_state_items.py", "default", frozenset({"K007"})),
    ("bad_todo.py", "default", frozenset({"K008"})),
    ("bad_commented_code.py", "default", frozenset({"K009"})),
    ("bad_banner.py", "default", frozenset({"K010"})),
    ("bad_nodoc.py", "default", frozenset({"K011"})),
    ("bad_sentence.py", "default", frozenset()),
    ("bad_sentence.py", "strict", frozenset({"K012", "K013"})),
    ("bad_restate.py", "default", frozenset()),
    ("bad_restate.py", "strict", frozenset({"K014"})),
    ("bad_restate_short.py", "strict", frozenset({"K014"})),
    ("bad_method_recursion.py", "default", frozenset({"K001"})),
    ("good_method_calls.py", "default", frozenset()),
    ("bad_unparseable.py", "default", frozenset({"K000"})),
    ("bad_latin1.py", "default", frozenset()),
    ("bad_latin1.py", "strict", frozenset()),
)

SELF = ("kroko.py", "kroko_selftest.py")


def codes_for(path, mode):
    """The exact set of rule codes the gate reports for one file."""
    return frozenset(code for code, _, _ in kroko.check(path, mode == "strict"))


def fixture_path(name):
    """Absolute path to one fixture."""
    return os.path.join(os.path.dirname(HERE), "tests", "fixtures", name)


def run_cases():
    """Check every fixture against its expected codes, returning a failure count."""
    failures = 0
    for name, mode, expected in CASES:
        actual = codes_for(fixture_path(name), mode)
        matched = actual == expected
        failures += not matched
        print(f"{'ok  ' if matched else 'FAIL'} {name:<24} {mode:<8} want={sorted(expected)} got={sorted(actual)}")
    return failures


def run_self():
    """Both gate scripts must pass on themselves, in both modes."""
    failed = 0
    for name in SELF:
        target = os.path.join(HERE, name)
        for mode in ("default", "strict"):
            problems = kroko.check(target, mode == "strict")
            print(f"{'ok  ' if not problems else 'FAIL'} {name:<24} {mode:<8} findings={len(problems)}")
            for code, line, message in problems:
                print(f"        {code} line {line}: {message}")
            failed += bool(problems)
    return failed


def main():
    """Run the whole suite and return a shell exit code."""
    failures = run_cases()
    failures += run_self()
    print(f"\n{len(CASES)} fixture cases plus {len(SELF) * 2} self-checks, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
