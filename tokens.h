#ifndef TOKENS_H
#define TOKENS_H

enum TokenKind {
    TOK_ID = 256, TOK_NUMBER, TOK_IF, TOK_ELSE,
    TOK_LE, TOK_GE, TOK_EQ, TOK_NE, TOK_INVALID
};
extern int source_line, source_column, token_line, token_column;
int yylex(void);
const char *token_name(int kind);
#endif

