"""Web interface for the existing C/Lex compiler; no duplicate Python parser."""
from contextlib import asynccontextmanager
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

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
]


def build_compiler():
    sources = [ROOT / name for name in ("lexer.l", "syntax_checker.c", "tokens.h")]
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


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest):
    if not BINARY.exists():
        raise HTTPException(503, "Compiler is unavailable. Restart the server to build it.")
    try:
        with tempfile.TemporaryDirectory(prefix="compiler-input-") as folder:
            path = Path(folder) / "input.txt"
            path.write_text(payload.source, encoding="ascii")
            result = subprocess.run([str(BINARY), str(path)], capture_output=True,
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
    return {"tokens": tokens, "lexical": "success" if lexical_ok else "error",
            "syntax": ("success" if result.returncode == 0 else
                       "error" if lexical_ok else "skipped"),
            "diagnostic": diagnostic,
            "output": result.stdout.replace(str(path), "editor"),
            "source": payload.source}
