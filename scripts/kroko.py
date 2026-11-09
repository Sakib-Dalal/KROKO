#!/usr/bin/env python3
"""KROKO gate: enforce the NASA-grade coding limits, comments included.

This file obeys the limits it enforces. Run it on itself as the first check:

    python3 scripts/kroko.py scripts/kroko.py

Codes
    K000 the file could not be parsed
    K001 recursion          K002 function over 60 lines
    K003 nesting over 3     K004 more than 4 parameters
    K005 cognitive over 15  K006 blanket exception swallowed
    K007 module-level state K008 placeholder comment
    K009 commented-out code K010 banner comment
    K011 missing public docstring
    K012 docstring not a sentence        (strict only)
    K013 comment not a sentence          (strict only)
    K014 comment restates the next line  (strict only)

A call is treated as a recursion edge only when it is a bare function name, or a
self.name(...) call inside a method. An arbitrary object.name(...) call cannot be
resolved without type inference, and treating it as an edge flags every function
whose name happens to match an unrelated method elsewhere.
"""
import ast
import io
import sys
import tokenize

MAX_LINES = 60
MAX_DEPTH = 3
MAX_PARAMS = 4
MAX_COGNITIVE = 15
MAX_SHARED = 2
MIN_RATIO = 0.8
CONTROL_FLOW = (ast.If, ast.For, ast.While, ast.Try, ast.With)
MUTABLE = (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)
PLACEHOLDERS = ("TODO", "FIXME", "XXX", "HACK")
STOPWORDS = (
    "the", "a", "an", "is", "are", "was", "this", "that", "these", "to", "of",
    "in", "it", "its", "and", "or", "for", "with", "be", "by", "on", "at",
    "from", "as", "we", "you", "if", "so", "then", "than", "into",
)
SENTENCE_END = (".", "!", "?")


def walk_all(root):
    """Every node beneath root, in preorder, using an explicit stack."""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(ast.iter_child_nodes(node))


def walk_with_depth(root):
    """Every node paired with its control-flow nesting depth."""
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        yield node, depth
        for child in ast.iter_child_nodes(node):
            step = 1 if _opens_a_level(child, node) else 0
            stack.append((child, depth + step))


def _opens_a_level(child, parent):
    """True for a control-flow node that nests rather than continuing an elif chain."""
    if not isinstance(child, CONTROL_FLOW):
        return False
    sibling = isinstance(child, ast.If) and isinstance(parent, ast.If)
    return not (sibling and child in parent.orelse)


def _add_target(func, name, receiver, targets):
    """Record a call edge: bare names anywhere, self.name only inside a method."""
    if isinstance(func, ast.Name):
        targets.add(func.id)
        return
    if not (receiver and isinstance(func, ast.Attribute) and func.attr == name):
        return
    if isinstance(func.value, ast.Name) and func.value.id == receiver:
        targets.add(name)


def _function_stats(node, name, receiver):
    """One traversal yielding call targets, cognitive complexity and nesting depth."""
    targets = set()
    total = 0
    deepest = 0
    for sub, depth in walk_with_depth(node):
        deepest = max(deepest, depth)
        if isinstance(sub, ast.Call):
            _add_target(sub.func, name, receiver, targets)
        for child in ast.iter_child_nodes(sub):
            if isinstance(child, CONTROL_FLOW):
                total += 1 + depth
            elif isinstance(child, ast.BoolOp):
                total += len(child.values) - 1
    return targets, total, deepest


def _first_arg(node):
    """The receiver name of a method, or None when there are no parameters."""
    return node.args.args[0].arg if node.args.args else None


def _method_names(tree):
    """Names of functions defined directly inside a class body."""
    names = set()
    for node in walk_all(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(item.name)
    return names


def collect_functions(tree):
    """Every function definition as (name, node, receiver), in source order.

    Keyed by definition rather than by name: a name can be defined more than once
    under mutually exclusive branches, and collapsing them would leave the first
    definition unchecked.
    """
    methods = _method_names(tree)
    found = []
    for node in walk_all(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        receiver = _first_arg(node) if node.name in methods else None
        found.append((node.name, node, receiver))
    return found


def find_recursion(edges):
    """Names that reach themselves through the call graph, directly or mutually."""
    recursive = set()
    for start in edges:
        seen, pending = set(), list(edges[start])
        while pending:
            current = pending.pop()
            if current == start:
                recursive.add(start)
                break
            if current in edges and current not in seen:
                seen.add(current)
                pending.extend(edges[current])
    return recursive


def _arity(fn):
    """Named parameters, counting positional-only ones; variadic bindings are one each."""
    args = fn.args
    named = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
    variadic = bool(args.vararg) + bool(args.kwarg)
    return named + variadic


def size_problems(name, fn, score, depth):
    """Length, nesting, arity and complexity gates for one function."""
    span = (fn.end_lineno or fn.lineno) - fn.lineno + 1
    params = _arity(fn)
    pairs = (
        ("K002", span > MAX_LINES, f"{name} is {span} lines, limit {MAX_LINES}"),
        ("K003", depth > MAX_DEPTH, f"{name} nests {depth} deep, limit {MAX_DEPTH}"),
        ("K004", params > MAX_PARAMS, f"{name} takes {params} parameters, limit {MAX_PARAMS}"),
        ("K005", score > MAX_COGNITIVE, f"{name} scores {score}, limit {MAX_COGNITIVE}"),
    )
    return [(code, fn.lineno, message) for code, violated, message in pairs if violated]


def swallow_problems(tree):
    """Exceptions caught without naming a type convert a crash into corrupt state."""
    problems = []
    for node in walk_all(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        named = node.type is not None and getattr(node.type, "id", "") != "Exception"
        if not named:
            problems.append(("K006", node.lineno, "blanket exception swallowed"))
    return problems


def state_problems(tree):
    """Module-level containers and counters outlive the scope that should own them."""
    problems = []
    for node in tree.body:
        problems.extend(_one_state_problem(node))
    return problems


def _one_state_problem(node):
    """Module-scope state introduced by a single top-level statement."""
    if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
        return [("K007", node.lineno, f"{node.target.id} mutated at module scope")]
    if not isinstance(node, ast.Assign):
        return []
    flagged = [item for item in node.targets if _owns_module_state(item, node.value)]
    return [("K007", node.lineno, _describe_state(item)) for item in flagged]


def _owns_module_state(target, value):
    """True when this assignment target leaves mutable state at module scope."""
    if isinstance(target, ast.Subscript):
        return True
    return isinstance(target, ast.Name) and isinstance(value, MUTABLE)


def _describe_state(target):
    """Name the thing being left behind."""
    if isinstance(target, ast.Name):
        return f"{target.id} held at module scope"
    return "container mutated at module scope"


def _comment_tokens(source):
    """Every comment in the source as (line number, raw text). Strings are excluded."""
    found = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        if token.start[0] == 1 and token.string.startswith("#!"):
            continue
        found.append((token.start[0], token.string))
    return found


def _is_banner(body):
    """True for decoration such as a row of equals signs used as a separator."""
    squeezed = body.replace(" ", "")
    return len(squeezed) >= 6 and len(set(squeezed)) == 1


def _looks_like_code(body):
    """True when a comment body would parse as a Python statement, so it is dead code."""
    lowered = body.lower()
    if lowered.startswith(("e.g.", "i.e.", "example", "see ", "cf.")):
        return False
    try:
        ast.parse(body)
    except SyntaxError:
        return False
    return any(mark in body for mark in ("=", "(", ":", "[")) and len(body) > 3


def _words(text):
    """Lowercased content words, with identifiers split on underscores."""
    rough = text.replace("_", " ").replace(".", " ").replace(":", " ")
    parts = "".join(char if char.isalnum() else " " for char in rough).lower().split()
    return {part for part in parts if part not in STOPWORDS}


def _restates(text, line):
    """True when a comment is made of the same words as the code beneath it."""
    said, written = _words(text), _words(line)
    if not said or not written:
        return False
    shared = said & written
    return len(shared) >= MAX_SHARED and len(shared) / len(said) >= MIN_RATIO


def _strict_comment_problems(number, body, lines):
    """Sentence form, and the ban on comments that just read the code back."""
    problems = []
    if not body.endswith(SENTENCE_END):
        problems.append(("K013", number, body))
    following = lines[number] if number < len(lines) else ""
    if _restates(body, following):
        problems.append(("K014", number, body))
    return problems


def _body_problems(number, body):
    """Placeholder, banner and dead-code gates for one comment."""
    if any(marker in body for marker in PLACEHOLDERS):
        return [("K008", number, body)]
    if _is_banner(body):
        return [("K010", number, body)]
    if _looks_like_code(body):
        return [("K009", number, body)]
    return []


def _single_comment_problems(number, text, lines, strict):
    """All comment gates for one comment line.

    Sentence form is only judged when the line is otherwise legitimate. A banner or
    a placeholder is already a finding, and reporting it twice is noise that teaches
    people to ignore the gate.
    """
    body = text.lstrip("#").strip()
    if not body:
        return []
    problems = _body_problems(number, body)
    if strict and not problems:
        problems.extend(_strict_comment_problems(number, body, lines))
    return problems


def comment_problems(source, strict):
    """Every comment gate across one source string."""
    lines = source.splitlines()
    problems = []
    for number, text in _comment_tokens(source):
        problems.extend(_single_comment_problems(number, text, lines, strict))
    return problems


def _sentence_ok(text):
    """True when the first line of a docstring is punctuated as a sentence."""
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first.endswith(SENTENCE_END)


def docstring_problems(tree, strict):
    """Public API must be documented; under strict mode the summary must be a sentence."""
    problems = []
    if not ast.get_docstring(tree):
        problems.append(("K011", 1, "module has no docstring"))
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        documented = ast.get_docstring(node)
        if documented is None and not node.name.startswith("_"):
            problems.append(("K011", node.lineno, f"{node.name} is undocumented"))
            continue
        if strict and documented is not None and not _sentence_ok(documented):
            problems.append(("K012", node.lineno, f"{node.name} summary is not a sentence"))
    return problems


def code_problems(tree, strict):
    """Every structural gate across one parsed file."""
    definitions = collect_functions(tree)
    edges = {}
    problems = []
    for name, node, receiver in definitions:
        targets, score, depth = _function_stats(node, name, receiver)
        edges[name] = edges.get(name, set()) | targets
        problems.extend(size_problems(name, node, score, depth))
    recursive = find_recursion(edges)
    flagged = sorted({(node.lineno, name) for name, node, _ in definitions if name in recursive})
    problems.extend(("K001", line, f"{name} recurses") for line, name in flagged)
    problems.extend(swallow_problems(tree))
    problems.extend(state_problems(tree))
    problems.extend(docstring_problems(tree, strict))
    return problems


def _read_source(path):
    """Read source honouring PEP 263 cookies, falling back to latin-1 for odd bytes."""
    try:
        with tokenize.open(path) as handle:
            return handle.read()
    except (SyntaxError, UnicodeDecodeError):
        with open(path, encoding="latin-1") as handle:
            return handle.read()


def _parse(source, path):
    """Parse the source; an unparseable file becomes a K000 finding, never a crash."""
    try:
        return ast.parse(source, path), []
    except SyntaxError as error:
        return None, [("K000", error.lineno or 0, f"cannot parse: {error.msg}")]


def check(path, strict):
    """Every problem in one file, sorted for a stable report."""
    source = _read_source(path)
    tree, problems = _parse(source, path)
    if tree is None:
        return problems
    found = code_problems(tree, strict)
    found.extend(comment_problems(source, strict))
    return sorted(found, key=lambda item: (item[1], item[0]))


def report(path, problems):
    """Print one file's verdict."""
    verdict = "PASS" if not problems else "FAIL"
    print(f"{verdict}  {path}  ({len(problems)} findings)")
    for code, line, message in problems:
        print(f"        {code} line {line}: {message}")


def main(argv):
    """Run the gate over the given paths, returning a shell exit code."""
    strict = "--strict-comments" in argv
    paths = [item for item in argv if not item.startswith("--")]
    if not paths:
        print("usage: kroko.py [--strict-comments] FILE [FILE ...]")
        return 2
    failing = 0
    for path in paths:
        problems = check(path, strict)
        failing += bool(problems)
        report(path, problems)
    print(f"\n{len(paths)} file(s), {failing} failing, strict={strict}")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
