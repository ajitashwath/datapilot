import ast
import contextlib
import io
import json
import sys
import types

BLOCKED_NAMES = {
    "open", "exec", "eval", "compile", "getattr", "setattr", "delattr", "globals", "locals", "vars",
    "input", "breakpoint", "exit", "quit", "help", "dir", "memoryview", "super", "type", "object",
}
BLOCKED_ATTRIBUTES = {
    "io", "eval", "query", "style", "plotting", "testing", "api", "pipe", "load", "save", "savez", "savetxt",
    "loadtxt", "genfromtxt", "fromfile", "tofile", "memmap", "ctypeslib", "lib", "f2py", "fromregex", "DataSource",
    "system", "popen", "environ", "modules", "builtins", "format", "format_map", "show_versions", "show_config",
    "os", "sys", "subprocess", "importlib", "ctypes", "socket", "shutil", "pathlib", "compat", "core",
}
SAFE_SUBMODULES = {"random", "linalg"}
ALLOWED_TO_METHODS = {
    "to_dict", "to_list", "to_numpy", "to_frame", "to_datetime", "to_numeric", "to_period", "to_timestamp",
    "to_timedelta", "to_string", "to_series", "to_records", "to_pydatetime",
}
BLOCKED_NODES = (ast.Import, ast.ImportFrom, ast.ClassDef, ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.Await)
SAFE_BUILTINS = [
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float", "int", "isinstance", "len",
    "list", "map", "max", "min", "pow", "print", "range", "reversed", "round", "set", "sorted", "str", "sum",
    "tuple", "zip", "Exception", "ValueError", "KeyError", "TypeError", "ZeroDivisionError", "True", "False", "None",
]


class ModuleGuard:
    __slots__ = ("_module",)

    def __init__(self, module):
        object.__setattr__(self, "_module", module)

    def __getattr__(self, name):
        value = getattr(self._module, name)
        if isinstance(value, types.ModuleType):
            if name in SAFE_SUBMODULES:
                return ModuleGuard(value)
            raise AttributeError(f"Access to the module '{name}' is not allowed.")
        return value

    def __setattr__(self, name, value):
        raise AttributeError("Modules are read-only.")


def check_code(code: str) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"Syntax error on line {exc.lineno}: {exc.msg}"
    for node in ast.walk(tree):
        if isinstance(node, BLOCKED_NODES):
            return f"{type(node).__name__} statements are not allowed. pandas as pd, numpy as np, math and statistics are already available."
        if isinstance(node, ast.Name) and (node.id in BLOCKED_NAMES or node.id.startswith("_")):
            return f"The name '{node.id}' is not allowed."
        if isinstance(node, ast.Attribute):
            name = node.attr
            if name.startswith("_") or name in BLOCKED_ATTRIBUTES or name.startswith("read_"):
                return f"The attribute '{name}' is not allowed."
            if name.startswith("to_") and name not in ALLOWED_TO_METHODS:
                return f"The attribute '{name}' is not allowed."
    return None


def table_from_value(value, max_rows: int) -> dict:
    import numpy as np
    import pandas as pd

    if isinstance(value, pd.Series):
        value = value.reset_index() if value.name is not None or value.index.name is not None else value.to_frame("value")
    if isinstance(value, (list, tuple)) and value and all(isinstance(v, dict) for v in value):
        value = pd.DataFrame(list(value))
    if isinstance(value, pd.DataFrame):
        if not isinstance(value.index, pd.RangeIndex):
            value = value.reset_index()
        value.columns = [str(c) for c in value.columns]
        head = value.head(max_rows)
        rows = json.loads(head.to_json(orient="values", date_format="iso"))
        return {"kind": "table", "columns": list(value.columns), "rows": rows, "row_count": len(head), "truncated": len(value) > max_rows}
    if isinstance(value, np.generic):
        value = value.item()
    return {"kind": "value", "value": value}


def run(payload: dict) -> dict:
    import math
    import statistics

    import numpy as np
    import pandas as pd

    problem = check_code(payload["code"])
    if problem:
        return {"ok": False, "error": problem, "stdout": ""}
    namespace = {name: pd.read_parquet(path) for name, path in payload["tables"].items()}
    safe = {name: __builtins__[name] if isinstance(__builtins__, dict) else getattr(__builtins__, name) for name in SAFE_BUILTINS}
    namespace.update({
        "pd": ModuleGuard(pd), "np": ModuleGuard(np), "math": ModuleGuard(math), "statistics": ModuleGuard(statistics),
        "__builtins__": safe,
    })
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            exec(compile(payload["code"], "<analysis>", "exec"), namespace)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:400]}", "stdout": buffer.getvalue()[:4000]}
    if "result" not in namespace:
        return {"ok": False, "error": "The code must assign its final answer to a variable named result.", "stdout": buffer.getvalue()[:4000]}
    try:
        output = table_from_value(namespace["result"], payload["max_rows"])
    except Exception as exc:
        return {"ok": False, "error": f"The result could not be converted: {type(exc).__name__}", "stdout": buffer.getvalue()[:4000]}
    return {"ok": True, "result": output, "stdout": buffer.getvalue()[:4000]}


def main() -> None:
    payload = json.loads(sys.stdin.read())
    sys.stdout.write("\n@@RESULT@@" + json.dumps(run(payload), default=str))


if __name__ == "__main__":
    main()
