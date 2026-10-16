"""Language syntax frontends, normalized C/Lex translation, and web interface."""
from contextlib import asynccontextmanager
from pathlib import Path
import os
import json
import re
import shutil
import subprocess
import tempfile
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from web.languages import detect, parse, token_stream, syntax_error, Lowerer, Unsupported

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / ".build"
BINARY = BUILD / ("compiler.exe" if os.name == "nt" else "compiler")
TOKEN_ROW = re.compile(r"^\s*(\d+)\s+(\w+)\s+(.*?)\s+(\d+):(\d+)\s*$")
ERROR = re.compile(r"^(LEXICAL|SYNTAX) ERROR at line (\d+), column (\d+): (.*)$", re.M)

EXAMPLES = [
    {"id": "assignments", "name": "Assignments & arithmetic", "source": "a = 10;\nb = 20;\nc = (a + b) * 2;\n"},
    {"id": "branches", "name": "If / else", "source": (ROOT / "samples/valid.txt").read_text()},
    {"id": "nested", "name": "Nested if / else", "source": (ROOT / "samples/nested.txt").read_text()},
    {"id": "optional", "name": "If without else", "source": "score = 75;\nif (score >= 50) {\n    passed = 1;\n}\n"},
    {"id": "semicolon", "name": "Error: missing semicolon", "source": (ROOT / "samples/invalid_syntax.txt").read_text()},
    {"id": "character", "name": "Error: unsupported character", "source": (ROOT / "samples/invalid_lexical.txt").read_text()},
    {"id": "brace", "name": "Error: missing closing brace", "source": "a = 10;\nif (a != 0) {\n    b = a / 2;\n"},
    {"id": "joins", "name": "Backpatching: nested branches & join", "source": "a = 4;\nb = 2;\nif (a > b) {\n    if (a == 4) {\n        result = a * b + 1;\n    }\n} else {\n    result = a - b;\n}\nfinished = 1;\n"},
    {"id": "empty-branches", "name": "Backpatching: empty branches", "source": "a = 1;\nif (a == 1) {\n} else {\n}\nresult = a + 2 * 3;\n"},
]
for _language, _name, _suffix in [
    ("python", "Python", ".py"), ("java", "Java", ".java"),
    ("c", "C", ".c"), ("cpp", "C++", ".cpp"), ("javascript", "JavaScript", ".js")
]:
    EXAMPLES.append({"id":_language, "name":_name + ": assignments & branches",
                     "source":(ROOT/"samples/languages"/(_language+_suffix)).read_text()})


def build_compiler():
    sources = [ROOT / name for name in ("lexer.l", "syntax_checker.c", "tokens.h", "translation.h")]
    if BINARY.exists() and all(p.stat().st_mtime <= BINARY.stat().st_mtime for p in sources):
        return
    scanner = next((shutil.which(name) for name in ("flex", "win_flex", "lex")
                    if shutil.which(name)), None)
    cc = next((shutil.which(name) for name in ("cc", "gcc", "clang")
               if shutil.which(name)), None)
    if not scanner or not cc:
        raise RuntimeError("Install Flex (or Lex) and a C compiler, and put them on PATH.")
    BUILD.mkdir(exist_ok=True)
    # Keep generated files separate from the existing terminal build.
    with tempfile.TemporaryDirectory(dir=BUILD) as folder:
        directory = Path(folder)
        commands = [
            [scanner, str(ROOT / "lexer.l")],
            [cc, "-std=c99", "-Wall", "-Wextra", "-I", str(ROOT),
             str(ROOT / "syntax_checker.c"), str(directory / "lex.yy.c"),
             "-o", str(directory / BINARY.name)],
        ]
        for command in commands:
            result = subprocess.run(command, cwd=directory, capture_output=True,
                                    text=True, timeout=30)
            if result.returncode:
                raise RuntimeError("Compiler build failed:\n" + result.stderr)
        shutil.copy2(directory / BINARY.name, BINARY)


@asynccontextmanager
async def lifespan(app):
    build_compiler()
    yield


app = FastAPI(title="Compiler Lab", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "web/static"), name="static")


class AnalyzeRequest(BaseModel):
    source: str = Field(max_length=20000)
    language: Literal["auto", "python", "java", "c", "cpp", "javascript", "shared"] = "auto"

    @field_validator("source")
    @classmethod
    def supported_characters(cls, value):
        # Lex rules use ASCII identifiers. Also prevent embedded NUL/control bytes.
        if any(ord(c) > 126 or (ord(c) < 32 and c not in "\n\r\t") for c in value):
            raise ValueError("Use ASCII source text; only tabs and line breaks are allowed control characters.")
        return value.replace("\r\n", "\n").replace("\r", "\n")


@app.get("/")
def index():
    return FileResponse(ROOT / "web/static/index.html")


@app.get("/api/examples")
def examples():
    return EXAMPLES


def analyze_core(payload: AnalyzeRequest):
    if not BINARY.exists():
        raise HTTPException(503, "Compiler is unavailable. Restart the server to build it.")
    try:
        with tempfile.TemporaryDirectory(prefix="compiler-input-") as folder:
            path = Path(folder) / "input.txt"
            path.write_text(payload.source, encoding="ascii")
            result = subprocess.run([str(BINARY), "--web", str(path)], capture_output=True,
                                    text=True, timeout=3)
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "Analysis timed out. Try a smaller or less deeply nested program.")
    except OSError:
        raise HTTPException(503, "Could not launch the compiler.")
    if result.returncode not in (0, 1):
        raise HTTPException(500, "The compiler could not analyze this input. Try reducing nesting.")
    tokens = []
    lines = payload.source.split("\n")
    line_offsets = []
    offset = 0
    for line in lines:
        line_offsets.append(offset)
        offset += len(line) + 1
    for line in result.stdout.splitlines():
        match = TOKEN_ROW.match(line)
        if not match:
            continue
        number, kind, lexeme, row, column = match.groups()
        row, column = int(row), int(column)
        offset = line_offsets[row - 1] + column - 1
        tokens.append({"index": int(number), "type": kind, "lexeme": lexeme,
                       "line": row, "column": column, "start": offset,
                       "end": offset + len(lexeme)})
    error_match = ERROR.search(result.stdout)
    diagnostic = None
    if error_match:
        stage, row, column, message = error_match.groups()
        diagnostic = {"stage": stage.lower(), "line": int(row),
                      "column": int(column), "message": message}
    if not tokens or (result.returncode == 1 and diagnostic is None):
        raise HTTPException(500, "Unexpected output from the C compiler.")
    lexical_ok = not diagnostic or diagnostic["stage"] != "lexical"
    translation_steps, backpatches, tac = [], [], []
    collections = {"@SDT ": translation_steps, "@PATCH ": backpatches, "@TAC ": tac}
    terminal = []
    try:
        for line in result.stdout.splitlines():
            prefix = next((tag for tag in collections if line.startswith(tag)), None)
            if prefix:
                collections[prefix].append(json.loads(line[len(prefix):]))
            else:
                terminal.append(line)
    except (ValueError, TypeError):
        raise HTTPException(500, "Unexpected translation output from the C compiler.")
    if result.returncode == 0:
        if not tac or tac[-1]["kind"] != "halt":
            raise HTTPException(500, "Incomplete TAC output from the C compiler.")
        terminal += ["", "SYNTAX-DIRECTED TRANSLATION"]
        terminal += [f'{i}. [{step["rule"]}] {step["detail"]}' for i, step in enumerate(translation_steps, 1)]
        terminal += ["", "TAC BEFORE BACKPATCHING"]
        terminal += [f'{item["id"]}: {item["unpatched_text"]}' for item in tac]
        terminal += ["", "BACKPATCHING"]
        terminal += [f'backpatch({{{step["instruction"]}}}, {step["target"]})' for step in backpatches] or ["No pending jumps."]
        terminal += ["", "THREE-ADDRESS CODE (FINAL)"]
        terminal += [f'{item["id"]}: {item["text"]}' for item in tac]
    return {"tokens": tokens, "lexical": "success" if lexical_ok else "error",
            "syntax": ("success" if result.returncode == 0 else
                       "error" if lexical_ok else "skipped"),
            "diagnostic": diagnostic,
            "translation": "success" if result.returncode == 0 else "skipped",
            "translation_steps": translation_steps, "backpatches": backpatches,
            "tac": tac,
            "output": "\n".join(terminal).replace(str(path), "editor"),
            "source": payload.source}


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest):
    detection = detect(payload.source, payload.language)
    if detection["id"] == "shared":
        result = analyze_core(payload)
        result.update(language=detection, normalized_source=payload.source,
                      translation_reason=None)
        return result
    language = detection["id"]
    tree = parse(payload.source, language)
    tokens = token_stream(tree.root_node, payload.source)
    diagnostic = syntax_error(tree.root_node, payload.source, language)
    result = {"source":payload.source, "language":detection, "tokens":tokens,
              "lexical":"success", "syntax":"error" if diagnostic else "success",
              "diagnostic":diagnostic, "translation":"skipped", "translation_steps":[],
              "backpatches":[], "tac":[], "translation_reason":None,
              "normalized_source":None}
    lines = [f'LANGUAGE: {detection["name"]}', detection["reason"], "", "SOURCE TOKENS"]
    lines += [f'{t["index"]}: {t["type"]} {t["lexeme"]!r} ({t["line"]}:{t["column"]})' for t in tokens]
    if diagnostic:
        lines += [f'SYNTAX ERROR at line {diagnostic["line"]}, column {diagnostic["column"]}: {diagnostic["message"]}']
    else:
        lines += ["SYNTAX SUCCESS: accepted by the language grammar (not a type/semantic check)."]
        try:
            lowered = Lowerer(language).lower(tree.root_node)
            if len(lowered.source) > 20000:
                raise Unsupported(tree.root_node, "Normalized code exceeds the 20,000-character backend limit. Use a smaller program.")
        except Unsupported as error:
            result["translation_reason"] = (f'Line {error.node.start_point.row+1}: {error.reason}')
            lines += ["TRANSLATION SKIPPED: " + result["translation_reason"]]
        except RecursionError:
            raise HTTPException(422, "Source nesting is too deep for translation.")
        else:
            translated = analyze_core(AnalyzeRequest(source=lowered.source, language="shared"))
            if translated["syntax"] != "success":
                raise HTTPException(500, "The language frontend generated invalid core code.")
            result.update(translation="success",
                          translation_steps=lowered.steps + translated["translation_steps"],
                          backpatches=translated["backpatches"], tac=translated["tac"],
                          normalized_source=lowered.source)
            lines += ["", "LANGUAGE NORMALIZATION"]
            lines += [f'[{step["rule"]}] {step["detail"]}' for step in lowered.steps]
            lines += ["", "NORMALIZED C/LEX INPUT", lowered.source, "", translated["output"]]
    result["output"] = "\n".join(lines)
    return result
