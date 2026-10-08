/* Phase 1: Lex-generated tokenizer + recursive-descent syntax checker. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
#include "tokens.h"

extern FILE *yyin;
extern char *yytext;
extern int yyleng;

typedef struct {
    int kind, line, column;
    char *text;
} Token;

static Token *tokens = NULL;
static size_t count = 0, capacity = 0, position = 0;
static jmp_buf syntax_failure;

static void out_of_memory(void) {
    fprintf(stderr, "ERROR: out of memory.\n");
    exit(2);
}

static void append_token(int kind, const char *text, size_t length,
                         int line, int column) {
    Token *grown;
    char *copy;
    if (count == capacity) {
        capacity = capacity ? capacity * 2 : 128;
        grown = realloc(tokens, capacity * sizeof(*tokens));
        if (!grown) out_of_memory();
        tokens = grown;
    }
    copy = malloc(length + 1);
    if (!copy) out_of_memory();
    memcpy(copy, text, length);
    copy[length] = '\0';
    tokens[count].kind = kind;
    tokens[count].line = line;
    tokens[count].column = column;
    tokens[count].text = copy;
    count++;
}

const char *token_name(int kind) {
    switch (kind) {
        case 0: return "EOF";
        case TOK_ID: return "ID";
        case TOK_NUMBER: return "NUMBER";
        case TOK_IF: return "IF";
        case TOK_ELSE: return "ELSE";
        case TOK_LE: return "LE";
        case TOK_GE: return "GE";
        case TOK_EQ: return "EQ";
        case TOK_NE: return "NE";
        case TOK_INVALID: return "INVALID";
        case '+': return "PLUS";
        case '-': return "MINUS";
        case '*': return "STAR";
        case '/': return "SLASH";
        case '=': return "ASSIGN";
        case '<': return "LT";
        case '>': return "GT";
        case '(': return "LPAREN";
        case ')': return "RPAREN";
        case '{': return "LBRACE";
        case '}': return "RBRACE";
        case ';': return "SEMICOLON";
        default: return "UNKNOWN";
    }
}

static int current(void) { return tokens[position].kind; }

static void expected(const char *description) {
    Token *token = &tokens[position];
    printf("\nSYNTAX ERROR at line %d, column %d: expected %s, ",
           token->line, token->column, description);
    if (token->kind == 0) printf("found end of file.\n");
    else printf("found '%s'.\n", token->text);
    longjmp(syntax_failure, 1);
}

static int accept(int kind) {
    if (current() != kind) return 0;
    position++;
    return 1;
}

static void expect(int kind, const char *description) {
    if (!accept(kind)) expected(description);
}

static void expression(void);
static void statement(void);

static void factor(void) {
    if (current() == TOK_ID || current() == TOK_NUMBER) position++;
    else if (accept('(')) {
        expression();
        expect(')', "')'");
    } else expected("an identifier, integer, or '('");
}

static void term(void) {
    factor();
    while (current() == '*' || current() == '/') {
        position++;
        factor();
    }
}

static void expression(void) {
    term();
    while (current() == '+' || current() == '-') {
        position++;
        term();
    }
}

static void condition(void) {
    int kind;
    expression();
    kind = current();
    if (kind != '<' && kind != '>' && kind != TOK_LE &&
        kind != TOK_GE && kind != TOK_EQ && kind != TOK_NE)
        expected("a comparison operator (<, >, <=, >=, ==, !=)");
    position++;
    expression();
}

static void block(void) {
    expect('{', "'{'");
    while (current() != '}' && current() != 0) statement();
    expect('}', "'}'");
}

static void statement(void) {
    if (accept(TOK_ID)) {
        expect('=', "'='");
        expression();
        expect(';', "';'");
    } else if (accept(TOK_IF)) {
        expect('(', "'('");
        condition();
        expect(')', "')'");
        block();
        if (accept(TOK_ELSE)) block();
    } else expected("an assignment or 'if' statement");
}

static void release_tokens(void) {
    size_t i;
    for (i = 0; i < count; i++) free(tokens[i].text);
    free(tokens);
}

int main(int argc, char **argv) {
    int kind, lexical_failure = 0;
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <source-file>\n", argv[0]);
        return 2;
    }
    yyin = fopen(argv[1], "r");
    if (!yyin) {
        perror(argv[1]);
        return 2;
    }
    printf("=== PHASE 1: LEX TOKENIZER + C SYNTAX CHECKER ===\n");
    printf("Input: %s\n\nTOKENS\n", argv[1]);
    printf("%-5s %-14s %-18s %s\n", "No.", "Type", "Lexeme", "Line:Column");
    while ((kind = yylex()) != 0) {
        append_token(kind, yytext, (size_t)yyleng, token_line, token_column);
        printf("%-5zu %-14s %-18s %d:%d\n", count, token_name(kind),
               tokens[count - 1].text, token_line, token_column);
        if (kind == TOK_INVALID) {
            printf("\nLEXICAL ERROR at line %d, column %d: unexpected character '%s'.\n",
                   token_line, token_column, tokens[count - 1].text);
            lexical_failure = 1;
            break;
        }
    }
    /* Flex can report input failures itself; also handle a stream error. */
    if (ferror(yyin)) {
        fprintf(stderr, "ERROR: could not read source file.\n");
        fclose(yyin);
        release_tokens();
        return 2;
    }
    fclose(yyin);
    if (lexical_failure) {
        release_tokens();
        return 1;
    }
    append_token(0, "", 0, source_line, source_column);
    printf("%-5zu %-14s %-18s %d:%d\n", count, "EOF", "",
           source_line, source_column);
    if (setjmp(syntax_failure) != 0) {
        release_tokens();
        return 1;
    }
    while (current() != 0) statement();
    printf("\nSYNTAX SUCCESS: the entire input follows the grammar.\n");
    release_tokens();
    return 0;
}
