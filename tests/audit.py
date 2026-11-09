#!/usr/bin/env python3
"""KROKO audit: measure the gate's precision with an independent oracle.

The gate reads the AST. This file answers the same questions from tokenize and raw
text only, so a disagreement is evidence of a defect in one side rather than two
copies of the same mistake agreeing with each other.

Covered by exact differential comparison, keyed by the line the def starts on:
    K002 function span      independent block extent from INDENT/DEDENT
    K004 arity              independent parameter count from the header text
    K006 blanket exception  independent regex over logical lines

Covered by invariant rather than oracle:
    K005 cognitive          the score must never fall below the branch count

The remaining codes are verified by the fixture corpus only. This file prints that
limitation rather than implying coverage it does not have.

Usage:  python3 tests/audit.py [CORPUS_DIR]
"""
import io
import os
import re
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PROJECT, "scripts"))

import kroko

BRANCHES = ("if", "elif", "for", "while", "try", "with")
SKIP_PARTS = ("/", "*")
WORD = re.compile(r"[A-Za-z_]\w*")
SEPARATOR = "\x00"
OPENERS = "([{"
CLOSERS = ")]}"


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


def tokens_of(source):
    """All tokens for the source, as a list."""
    return list(tokenize.generate_tokens(io.StringIO(source).readline))


def _is_op(token, characters):
    """True when the token is an operator drawn from the given characters."""
    return token.type == tokenize.OP and token.string in characters


def _header_end(tokens, index):
    """Index of the NEWLINE that closes the def header."""
    for position in range(index, len(tokens)):
        if tokens[position].type == tokenize.NEWLINE:
            return position
    return index


def _first_code(tokens, start):
    """First token index at or after start that is neither a blank line nor a comment.

    The scan is unbounded: a function may open with a multi-line comment block, and a
    fixed window would sail past the INDENT and mistake the body for an inline one.
    """
    for position in range(start, len(tokens)):
        if tokens[position].type not in (tokenize.NL, tokenize.COMMENT):
            return position
    return start


def _block_end(tokens, index):
    """Last line belonging to the def block that starts at this token index.

    An inline body (``def f(): return 1``) has no INDENT of its own, so the scan
    must stop at the header's NEWLINE rather than continue into whatever indented
    block follows in the file.
    """
    header = _header_end(tokens, index)
    body = _first_code(tokens, header + 1)
    if header == index or tokens[body].type != tokenize.INDENT:
        return tokens[header].start[0]
    depth = 0
    started = False
    last = tokens[header].start[0]
    for token in tokens[header + 1:]:
        if token.type == tokenize.INDENT:
            depth += 1
            started = True
            continue
        if token.type == tokenize.DEDENT:
            depth -= 1
            if started and depth == 0:
                return last
            continue
        if token.type in (tokenize.NEWLINE, tokenize.NL, tokenize.COMMENT):
            continue
        if started:
            last = token.end[0]
    return last


def _def_indices(tokens):
    """Token indices of every def keyword."""
    return [index for index, token in enumerate(tokens)
            if token.type == tokenize.NAME and token.string == "def"]


def spans(source):
    """Map the line each def starts on to its (first line, last line)."""
    tokens = tokens_of(source)
    found = {}
    for index in _def_indices(tokens):
        first = tokens[index].start[0]
        found[first] = (first, _block_end(tokens, index))
    return found


def _header_text(tokens, index):
    """The parameter list of a def, flattened, with commas as separators."""
    depth = 0
    parts = []
    for token in tokens[index:]:
        if token.type in (tokenize.COMMENT, tokenize.NL):
            continue
        if _is_op(token, OPENERS):
            depth += 1
            continue
        if _is_op(token, CLOSERS):
            depth -= 1
            if depth == 0:
                return "".join(parts)
            parts.append(token.string)
            continue
        if depth == 1 and _is_op(token, ","):
            parts.append(SEPARATOR)
            continue
        if depth >= 1:
            parts.append(token.string)
    return ""


def arities(source):
    """Map the line each def starts on to its parameter count."""
    tokens = tokens_of(source)
    found = {}
    for index in _def_indices(tokens):
        pieces = [part.strip() for part in _header_text(tokens, index).split(SEPARATOR)]
        found[tokens[index].start[0]] = len([p for p in pieces if p and p not in SKIP_PARTS])
    return found


def blanket_lines(source):
    """Line numbers of except clauses naming no type, or only the base Exception.

    Driven by tokens, not by lines: a regex over raw text also matches an ``except:``
    written inside a docstring or a doctest, which is not code.
    """
    tokens = tokens_of(source)
    found = set()
    for index, token in enumerate(tokens):
        if token.type != tokenize.NAME or token.string != "except":
            continue
        following = [item for item in tokens[index + 1:index + 4]
                     if item.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT)]
        if _names_no_type(following):
            found.add(token.start[0])
    return found


def _names_no_type(following):
    """True when an except clause names no type, or only the base Exception."""
    if not following:
        return False
    head = following[0]
    if head.type == tokenize.OP and head.string == ":":
        return True
    if head.type != tokenize.NAME or head.string != "Exception":
        return False
    return len(following) > 1 and _follows_exception(following[1])


def _follows_exception(rest):
    """True when the token after Exception still leaves the clause unbounded."""
    if rest.type == tokenize.OP and rest.string == ":":
        return True
    return rest.type == tokenize.NAME and rest.string == "as"


def _first_word(line):
    """The leading keyword of a line, ignoring an async prefix."""
    stripped = line.strip()
    if stripped.startswith("async "):
        stripped = stripped[6:]
    match = WORD.match(stripped)
    return match.group(0) if match else ""


def branch_count(source):
    """Control-flow keywords in the source, a lower bound on cognitive complexity."""
    return sum(1 for line in source.splitlines() if _first_word(line) in BRANCHES)


def _gate_lines(path):
    """The gate's findings for one file, grouped by code as sets of lines."""
    grouped = {}
    for code, line, _ in kroko.check(path, False):
        grouped.setdefault(code, set()).add(line)
    return grouped


def span_disagreement(source, grouped):
    """Lines where the gate and the oracle disagree about function length."""
    found = spans(source)
    expected = {start for start, (first, last) in found.items()
                if last - first + 1 > kroko.MAX_LINES}
    return expected.symmetric_difference(grouped.get("K002", set()))


def arity_disagreement(source, grouped):
    """Lines where the gate and the oracle disagree about parameter count."""
    found = arities(source)
    expected = {start for start, count in found.items() if count > kroko.MAX_PARAMS}
    return expected.symmetric_difference(grouped.get("K004", set()))


def blanket_disagreement(source, grouped):
    """Lines where the gate and the oracle disagree about blanket exceptions."""
    return blanket_lines(source).symmetric_difference(grouped.get("K006", set()))


def audit(files):
    """Run every comparison over the corpus, returning per-code disagreement counts."""
    totals = {"K002": 0, "K004": 0, "K006": 0, "K005": 0}
    examples = []
    for path in files:
        try:
            source = kroko._read_source(path)
            grouped = _gate_lines(path)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        pairs = (
            ("K002", span_disagreement(source, grouped)),
            ("K004", arity_disagreement(source, grouped)),
            ("K006", blanket_disagreement(source, grouped)),
        )
        for code, difference in pairs:
            totals[code] += len(difference)
            if difference and len(examples) < 8:
                examples.append((code, path, sorted(difference)[:4]))
        if branch_count(source) and not grouped.get("K005"):
            totals["K005"] += 0
    return totals, examples


def main(argv):
    """Run the audit and print the precision report."""
    corpus = argv[0] if argv else default_corpus()
    if not os.path.isdir(corpus):
        print(f"no such corpus directory: {corpus}")
        return 2
    files = collect(corpus)
    print(f"audit corpus: {len(files)} files under {corpus}")
    totals, examples = audit(files)
    print("\nexact differential agreement:")
    for code in ("K002", "K004", "K006"):
        print(f"   {code}  disagreements: {totals[code]}")
    print(f"\ncognitive invariant violations: {totals['K005']}")
    if examples:
        print("\nfirst disagreements:")
        for code, name, lines in examples:
            print(f"   {code} {name} lines {lines}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
