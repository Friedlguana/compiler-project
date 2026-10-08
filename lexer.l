%{
#include "tokens.h"
#define YY_NO_INPUT 1
#define YY_NO_UNPUT 1

int source_line = 1, source_column = 1;
int token_line = 1, token_column = 1;

/* Runs before every matched rule, including skipped whitespace/comments. */
#define YY_USER_ACTION token_line = source_line; token_column = source_column; source_column += yyleng;
%}

%%
[ \t\r]+                 ;
\n                       { source_line++; source_column = 1; }
"//"[^\n]*               ;
"if"                     { return TOK_IF; }
"else"                   { return TOK_ELSE; }
[a-zA-Z_][a-zA-Z0-9_]*    { return TOK_ID; }
[0-9]+                   { return TOK_NUMBER; }
"<="                     { return TOK_LE; }
">="                     { return TOK_GE; }
"=="                     { return TOK_EQ; }
"!="                     { return TOK_NE; }
[+*/=<>();{}-]            { return (unsigned char)yytext[0]; }
.                        { return TOK_INVALID; }
%%

int yywrap(void) { return 1; }
