# Multi-language Compiler Lab

## Automatic language detection

Click **Analyze code** with **Auto-detect** selected. The app recognizes Python,
Java, C, C++, and JavaScript, shows the detected language, tokenizes the
original source, checks its grammar, and generates TAC for supported constructs.
Each language has a quick-load example in the selector.

Language detection combines syntax signals and grammar acceptance. It cannot
uniquely identify identical source such as `a = 1;`. The interface reports
ambiguity and provides a language override. C programs are often also valid
C++; an override is available for that case. The original statement-only
C-style language remains available as the shared-snippet fallback.

Native-language syntax is parsed using separate Tree-sitter grammars; Python
also uses `ast.parse` to check indentation and Python syntax. These are grammar
checks, not the official language compilers or type/semantic checking.
Source code is never executed. Native tokens and their highlights refer to
the original source, not the normalized C/Lex input. Tree-sitter syntax
errors are reported as syntax diagnostics; only the original Lex path
distinguishes a separate lexical-error stage.

| Language | TAC frontend support |
| --- | --- |
| Python | Assignments, decimal integers, arithmetic, unary signs, if/elif/else, pass. |
| JavaScript | Assignments, initialized let/const/var declarations, arithmetic, numeric comparisons, if/else. |
| C and C++ | Initialized int/long/short declarations, assignments, arithmetic, comparisons, if/else in a single main wrapper. |
| Java | The same numeric subset in a single class with a static main method. |

TAC requires a single numeric comparison per condition. Other syntactically
valid features (loops, calls/printing, extra functions, objects, arrays,
strings, strict equality, Python floor division, chained comparisons,
shadowed declarations, etc.) get **syntax success with translation skipped**,
including a reason. Unsupported constructs are never silently removed.
This is not a full compiler implementation of all five languages.
The TAC is educational, untyped IR; runtime coercions, numeric widths,
overflow and language-specific execution semantics are not implemented.
Input remains limited to 20,000 ASCII characters.

The native frontends lower supported constructs into the original common
grammar. Lex/Flex and the C backend then perform SDT, backpatching and TAC.
Expand **Normalized C/Lex input** to inspect that boundary. Simple C/C++/Java
examples should use their main wrappers; the original common language accepts
bare statement snippets.

After updating, install the parser dependencies and restart FastAPI:

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn web.app:app --reload
```

For automatic language detection from the CLI:

```sh
.venv/bin/python analyze.py samples/languages/python.py
.venv/bin/python analyze.py samples/languages/cpp.cpp
.venv/bin/python analyze.py myfile.txt --language javascript
```

On Windows use `.venv\Scripts\python.exe` instead of `.venv/bin/python`.
Multi-language CLI exit codes: 0 = translated, 1 = syntax/lexical error,
2 = usage/file/setup error, 3 = valid syntax but unsupported TAC construct.
The C executable still accepts the original shared grammar directly.
Parser integration follows the [official Python Tree-sitter documentation](https://tree-sitter.github.io/py-tree-sitter/).

## Web interface (FastAPI)

Requires Python 3.10+, Flex/Lex, and a C compiler on PATH. Python serves the
interface and native-language frontends; the common SDT, backpatching and TAC
backend runs in C, with Lex tokenizing normalized input.

From this repository folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn web.app:app --reload --host 127.0.0.1 --port 8000
```

On Windows, use `py -3 -m venv .venv`, then `.venv\\Scripts\\activate` instead
of the first two commands. Use the same pip and uvicorn commands afterwards.

Open http://127.0.0.1:8000. Select an example or enter your own code,
then click **Analyze code** (Ctrl/Cmd+Enter also works). The interface shows
token types and positions, the syntax result, and positioned errors. Click a
token or use Play/arrow buttons to highlight its source text. This is a replay
of the actual Lex token sequence, not a display of the scanner's internal DFA.
Lexical failures skip syntax checking. Whitespace and // comments are skipped.
The interface shows the first error; grammar details and terminal output can
be expanded. Editing source clears old results.

For valid input, the new panels show syntax-directed semantic actions,
backpatch operations, and final three-address code. **Apply next patch**
resolves one pending jump at a time; **Reset** returns to the original emitted
form with unresolved targets shown as `_`. This is a replay of C-generated
patch operations. **Download TAC** saves the final instruction listing.
Nested-branch/join and empty-branch examples demonstrate backpatching.

At startup the app builds a separate compiler under `.build/` if needed.
It runs each analysis in a temporary file with a three-second timeout; submitted
programs are checked, not executed. Input is limited to 20,000 ASCII characters.
The existing terminal compiler commands below still work.

Run web checks:

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

API endpoints: `GET /api/examples`, `POST /api/analyze` with
`{"source": "a = 10;"}`. Interactive API documentation is at `/docs`.
FastAPI setup follows its [static file](https://fastapi.tiangolo.com/tutorial/static-files/)
and [lifespan](https://fastapi.tiangolo.com/advanced/events/) documentation.

The tokenizer is defined in **lexer.l**. Lex/Flex generates C scanner code
(`lex.yy.c`), which is compiled together with **syntax_checker.c**.
The parser is handwritten recursive descent in C. Semantic actions produce
translation attributes while parsing; `translation.h` holds the IR, patch-list,
trace, and output helpers and is included by `syntax_checker.c` only.
The CLI requires neither Python, Yacc, nor Bison.

## Build on macOS/Linux

You need Flex (or a compatible Lex implementation), a C compiler, and optionally
Make. From this project folder:

```sh
flex lexer.l
cc -std=c99 -Wall -Wextra syntax_checker.c lex.yy.c -o compiler
./compiler samples/valid.txt
```

You can use `lex lexer.l` instead of `flex lexer.l` with a compatible Lex.
The source provides `yywrap()`, so no `-lfl` or `-ll` link flag is needed.

Alternatively, use `make` followed by `make demo`.
For Lex rather than Flex with Make, use `make LEX=lex`.

## Build on Windows

Use a Windows environment with Flex and GCC on PATH, such as an MSYS2
development environment. From Command Prompt in this folder:

```text
build_windows.bat
compiler.exe samples\valid.txt
```

Double-click `run_demo.bat` once those tools are configured. It builds if
necessary, then runs two valid examples and two intentional error examples.

If your scanner generator is named `win_flex`, use:

```text
win_flex lexer.l
gcc -std=c99 -Wall -Wextra syntax_checker.c lex.yy.c -o compiler.exe
compiler.exe samples\valid.txt
```

The included batch build launcher expects the executable name `flex`.
The portable C source can be rebuilt on each OS; a macOS executable cannot run
directly on Windows.

## Run and demonstrate

```sh
./compiler samples/valid.txt
./compiler samples/nested.txt
./compiler samples/invalid_syntax.txt
./compiler samples/invalid_lexical.txt
```

On Windows replace `./compiler` with `compiler.exe`.
Supply your own source-file path to check another program.
The terminal displays token types, lexemes, line/column positions, and syntax
success or the first error. Lexical errors stop scanning; syntax errors are
checked only after successful tokenization.
Successful input also prints translation actions, emitted TAC with pending
targets, backpatch operations, and the final resolved TAC. The CLI and web
interface use the same C implementation.

Exit status: 0 = valid syntax, 1 = lexical/syntax error, 2 = usage/file error.

For the translation demo, run `./compiler samples/backpatching.txt`. Show the
arithmetic temporaries, true/false lists, nested branch joins, and the pending
jumps becoming concrete instruction labels. Then run an invalid sample to
show that no partial translation is published.

## Grammar (EBNF)

```text
program      = { statement }, EOF ;
statement    = assignment | if_statement ;
assignment   = ID, "=", expression, ";" ;
if_statement = "if", "(", condition, ")", block, [ "else", block ] ;
block        = "{", { statement }, "}" ;
condition    = expression, relop, expression ;
relop        = "<" | ">" | "<=" | ">=" | "==" | "!=" ;
expression   = term, { ("+" | "-"), term } ;
term         = factor, { ("*" | "/"), factor } ;
factor       = ID | NUMBER | "(", expression, ")" ;
```

Identifiers match `[a-zA-Z_][a-zA-Z0-9_]*`; integers match `[0-9]+`.
Keywords are case sensitive. Spaces, tabs, line breaks and // comments are
ignored. Columns are one based, with a tab counted as one character.
Braces are required around every branch. Empty input and empty blocks are
permitted. Arithmetic precedence follows expression/term/factor.
Lex/Flex chooses the longest match, then the earliest rule when tied:
`if` is a keyword while `iffy` is an identifier.

## Scope

Lexical analysis, syntax checking, syntax-directed translation, backpatching,
and TAC generation are implemented. The compiler does not execute programs,
check variable definitions or types, or build an AST. Unary minus, floats,
declarations, loops, logical
operators and block comments are outside the grammar.
Errors stop at the first failure; deeply nested classroom-exceeding inputs may
exhaust the C call stack.

## Translation and backpatching

Expressions synthesize a `place` attribute. Binary arithmetic rules allocate
temporaries and emit `temporary = left.place op right.place`. Multiplication
and division bind more tightly than addition and subtraction; operations at
the same level associate left to right. Assignments emit `ID = expression.place`.

A comparison emits `if left relop right goto _` and `goto _`. Their labels
become `B.truelist` and `B.falselist`. Statements carry a `nextlist` of exits
whose destinations are not yet known. Helpers implement `makelist`,
linked-list `merge`, and `backpatch`.

| Construct | Semantic action |
| --- | --- |
| Sequence | Patch the previous nextlist to the next statement's first instruction. |
| If without else | Patch truelist to then; merge falselist and then.nextlist. |
| If with else | Patch truelist to then and falselist to else; emit a pending jump over else and merge both branch nextlists with that jump. |
| End of program | Patch the remaining nextlist to an explicit halt instruction. |

For example, `if (a < b) { x = a + b; } else { x = 0; }` produces:

```text
1: if a < b goto 3
2: goto 6
3: $t1 = a + b
4: x = $t1
5: goto 7
6: x = 0
7: halt
```

Labels start at 1. Every final jump points to an instruction, including the
explicit `halt` exit. Generated `$t1`, `$t2`, etc. cannot collide with source
identifiers because `$` is not allowed in the source grammar. The before-patch
listing shows the original emission form of all jump instructions.
Malformed input discards all translation steps, patch records, and TAC.
Syntactically valid but semantically invalid expressions (e.g. division by
zero or an undefined identifier) are still translated. There is no evaluation
or semantic/type checking.

The web adapter invokes the CLI's internal `--web` mode. Tokens and diagnostics
remain readable; `@SDT`, `@PATCH`, and `@TAC` lines contain JSON records emitted
by C. FastAPI decodes those records and JavaScript displays them. Python and
JavaScript do not implement another TAC generator or backpatcher. The native
language normalizer is in `web/languages.py`.

Tests validate arithmetic precedence/associativity, each comparison's true
and false paths, empty/nested branches, statement joins, and complete jump
resolution. A test-only TAC interpreter compares generated code with a
reference evaluator for 80 seeded, randomly generated nested programs.

With the server running, a dependency-free Node.js check exercises frontend
DOM logic against the real API (it does not substitute for a visual browser check):

```sh
node tests/test_frontend.cjs http://127.0.0.1:8000
```
