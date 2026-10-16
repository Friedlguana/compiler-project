/* Lex scanner, recursive-descent translation, backpatching, and TAC. */
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

#include "translation.h"

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

static const char *expression(void);
static PatchList statement(void);

static const char *factor(void) {
    const char *place;
    if (current() == TOK_ID || current() == TOK_NUMBER) {
        place = tokens[position++].text;
        trace("factor -> ID | NUMBER", format("factor.place = %s", place));
        return place;
    }
    if (accept('(')) {
        place = expression();
        expect(')', "')'");
        trace("factor -> ( expression )", format("factor.place = %s", place));
        return place;
    }
    expected("an identifier, integer, or '('");
    return ""; /* expected() transfers control to the failure handler. */
}

static const char *term(void) {
    const char *place = factor();
    while (current() == '*' || current() == '/') {
        const char *op = tokens[position++].text;
        const char *right = factor();
        place = binary("term -> term op factor", place, op, right);
    }
    return place;
}

static const char *expression(void) {
    const char *place = term();
    while (current() == '+' || current() == '-') {
        const char *op = tokens[position++].text;
        const char *right = term();
        place = binary("expression -> expression op term", place, op, right);
    }
    return place;
}

static Boolean condition(void) {
    const char *left = expression(), *op, *right;
    size_t yes, no;
    int kind = current();
    Boolean attributes;
    if (kind != '<' && kind != '>' && kind != TOK_LE &&
        kind != TOK_GE && kind != TOK_EQ && kind != TOK_NE)
        expected("a comparison operator (<, >, <=, >=, ==, !=)");
    op = tokens[position++].text;
    right = expression();
    yes = emit("if", op, left, right, "");
    no = emit("goto", "", "", "", "");
    attributes.truelist = makelist(yes);
    attributes.falselist = makelist(no);
    trace("condition -> expression relop expression",
          format("truelist = {%zu}; falselist = {%zu}; emit conditional and false jumps.", yes, no));
    return attributes;
}

/* S1 ; M S2: patch S1.nextlist to M.instr before translating S2. */
static PatchList statement_list(void) {
    PatchList pending = emptylist();
    while (current() != '}' && current() != 0) {
        backpatch(pending, nextinstr());
        pending = statement();
    }
    return pending;
}

static PatchList block(void) {
    PatchList pending;
    expect('{', "'{'");
    pending = statement_list();
    expect('}', "'}'");
    return pending;
}

static PatchList statement(void) {
    if (current() == TOK_ID) {
        const char *name = tokens[position++].text, *value;
        size_t label;
        expect('=', "'='");
        value = expression();
        expect(';', "';'");
        label = emit("assign", "", value, "", name);
        trace("assignment -> ID = expression ;",
              format("emit %zu: %s = %s; nextlist = empty.", label, name, value));
        return emptylist();
    }
    if (accept(TOK_IF)) {
        Boolean test;
        PatchList then_next, else_next, skip;
        expect('(', "'('");
        test = condition();
        expect(')', "')'");
        trace("marker M_then", format("M_then.instr = %zu", nextinstr()));
        backpatch(test.truelist, nextinstr());
        then_next = block();
        if (accept(TOK_ELSE)) {
            skip = makelist(emit("goto", "", "", "", ""));
            trace("marker N", format("Emit jump %zu to skip the else branch.", skip.head));
            trace("marker M_else", format("M_else.instr = %zu", nextinstr()));
            backpatch(test.falselist, nextinstr());
            else_next = block();
            trace("if -> if ( B ) M S N else M S",
                  format("nextlist = merge(then.nextlist, N.nextlist, else.nextlist)."));
            return merge(merge(then_next, skip), else_next);
        }
        trace("if -> if ( B ) M S",
              format("nextlist = merge(B.falselist, then.nextlist)."));
        return merge(test.falselist, then_next);
    }
    expected("an assignment or 'if' statement");
    return emptylist();
}

static void release_tokens(void) {
    size_t i;
    for (i = 0; i < count; i++) free(tokens[i].text);
    free(tokens);
}

int main(int argc, char **argv) {
    int kind, lexical_failure = 0;
    int web = argc == 3 && !strcmp(argv[1], "--web");
    const char *path = web ? argv[2] : argc == 2 ? argv[1] : NULL;
    PatchList pending;
    if (!path) {
        fprintf(stderr, "Usage: %s [--web] <source-file>\n", argv[0]);
        return 2;
    }
    yyin = fopen(path, "r");
    if (!yyin) {
        perror(path);
        return 2;
    }
    printf("=== COMPILER: LEX + SDT + BACKPATCHING + TAC ===\n");
    printf("Input: %s\n\nTOKENS\n", path);
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
        puts("Translation discarded: no TAC generated for invalid syntax.");
        release_translation();
        release_tokens();
        return 1;
    }
    pending = statement_list();
    if (current() != 0) expected("end of file");
    backpatch(pending, nextinstr());
    emit("halt", "", "", "", "");
    trace("program -> statement_list",
          format("Patch program.nextlist to halt; all jump targets are resolved."));
    printf("\nSYNTAX SUCCESS: the entire input follows the grammar.\n");
    print_translation(web);
    release_translation();
    release_tokens();
    return 0;
}
