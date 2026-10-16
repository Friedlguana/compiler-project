CC = cc
LEX = flex
CFLAGS = -std=c99 -Wall -Wextra

all: compiler

lex.yy.c: lexer.l tokens.h
	$(LEX) lexer.l

compiler: lex.yy.c syntax_checker.c tokens.h translation.h
	$(CC) $(CFLAGS) syntax_checker.c lex.yy.c -o compiler

demo: compiler
	./compiler samples/valid.txt
	./compiler samples/nested.txt
	./compiler samples/invalid_syntax.txt; test $$? -eq 1
	./compiler samples/invalid_lexical.txt; test $$? -eq 1

.PHONY: all demo

