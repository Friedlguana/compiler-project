# Phase 1 compiler in C using Lex/Flex

The tokenizer is defined in **lexer.l**. Lex/Flex generates C scanner code
(`lex.yy.c`), which is compiled together with **syntax_checker.c**.
The syntax checker is a handwritten recursive-descent parser in C.
No Python, Yacc, or Bison is required.

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

Exit status: 0 = valid syntax, 1 = lexical/syntax error, 2 = usage/file error.

For Review 1, show the grammar below, run the valid example, show nested
if/else, then distinguish the missing-semicolon error from the invalid-character
error. Explain that the scanner classifies characters into tokens and the
parser checks their structure.

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

Only tokenization and syntax checking are implemented. The checker does not
execute programs, check variable definitions, build an AST, generate TAC, or
perform backpatching. Unary minus, floats, declarations, loops, logical
operators and block comments are outside the grammar.
Errors stop at the first failure; deeply nested classroom-exceeding inputs may
exhaust the C call stack.

