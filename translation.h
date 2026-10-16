/* Translation attributes and IR support, shared by all parser rules.
 * Included by syntax_checker.c only. Labels are one based; 0 means pending.
 */
#ifndef TRANSLATION_H
#define TRANSLATION_H
#include <stdarg.h>

typedef struct { size_t head, tail; } PatchList;
typedef struct { PatchList truelist, falselist; } Boolean;
typedef struct {
    const char *kind, *op, *arg1, *arg2, *result;
    size_t target, next;
} Instruction;
typedef struct { char *rule, *detail; } TranslationStep;
typedef struct { size_t instruction, target; } PatchStep;

static Instruction *code;
static size_t code_count, code_capacity, temporary_count;
static TranslationStep *steps;
static size_t step_count;
static PatchStep *patches;
static size_t patch_count;
static char **owned;
static size_t owned_count;

static char *format(const char *pattern, ...) {
    va_list args, copy;
    int length;
    char *text;
    char **grown;
    va_start(args, pattern);
    va_copy(copy, args);
    length = vsnprintf(NULL, 0, pattern, copy);
    va_end(copy);
    if (length < 0) exit(2);
    text = malloc((size_t)length + 1);
    if (!text) out_of_memory();
    vsnprintf(text, (size_t)length + 1, pattern, args);
    va_end(args);
    grown = realloc(owned, (owned_count + 1) * sizeof(*owned));
    if (!grown) out_of_memory();
    owned = grown;
    owned[owned_count++] = text;
    return text;
}

static void trace(const char *rule, char *detail) {
    TranslationStep *grown = realloc(steps, (step_count + 1) * sizeof(*steps));
    if (!grown) out_of_memory();
    steps = grown;
    steps[step_count].rule = format("%s", rule);
    steps[step_count++].detail = detail;
}

static size_t nextinstr(void) { return code_count + 1; }

static size_t emit(const char *kind, const char *op, const char *a,
                   const char *b, const char *result) {
    Instruction *grown;
    size_t label = nextinstr();
    if (code_count == code_capacity) {
        code_capacity = code_capacity ? code_capacity * 2 : 128;
        grown = realloc(code, code_capacity * sizeof(*code));
        if (!grown) out_of_memory();
        code = grown;
    }
    code[code_count++] = (Instruction){kind, op, a, b, result, 0, 0};
    return label;
}

static PatchList emptylist(void) { return (PatchList){0, 0}; }

static PatchList makelist(size_t label) {
    trace("makelist", format("makelist(%zu) creates a pending jump list.", label));
    return (PatchList){label, label};
}

/* O(1) concatenation through instruction links; patching later consumes it. */
static PatchList merge(PatchList a, PatchList b) {
    if (!a.head) return b;
    if (!b.head) return a;
    code[a.tail - 1].next = b.head;
    trace("merge", format("merge lists starting at %zu and %zu.", a.head, b.head));
    return (PatchList){a.head, b.tail};
}

static void backpatch(PatchList list, size_t target) {
    size_t label = list.head;
    while (label) {
        Instruction *instruction = &code[label - 1];
        PatchStep *grown = realloc(patches, (patch_count + 1) * sizeof(*patches));
        if (!grown) out_of_memory();
        patches = grown;
        patches[patch_count++] = (PatchStep){label, target};
        instruction->target = target;
        label = instruction->next;
    }
}

static const char *binary(const char *rule, const char *left,
                           const char *op, const char *right) {
    /* '$' cannot occur in an ID, so generated temporaries never alias user IDs. */
    const char *temporary = format("$t%zu", ++temporary_count);
    size_t label = emit("binary", op, left, right, temporary);
    trace(rule, format("place = %s; emit %zu: %s = %s %s %s",
                      temporary, label, temporary, left, op, right));
    return temporary;
}

static char *instruction_text(size_t index, int patched) {
    Instruction *instruction = &code[index];
    const char *target = patched ? format("%zu", instruction->target) : "_";
    if (!strcmp(instruction->kind, "binary"))
        return format("%s = %s %s %s", instruction->result, instruction->arg1,
                      instruction->op, instruction->arg2);
    if (!strcmp(instruction->kind, "assign"))
        return format("%s = %s", instruction->result, instruction->arg1);
    if (!strcmp(instruction->kind, "if"))
        return format("if %s %s %s goto %s", instruction->arg1,
                      instruction->op, instruction->arg2, target);
    if (!strcmp(instruction->kind, "goto")) return format("goto %s", target);
    return format("halt");
}

static void json_string(const char *text) {
    const unsigned char *p = (const unsigned char *)text;
    putchar('"');
    for (; *p; p++) {
        if (*p == '"' || *p == '\\') printf("\\%c", *p);
        else if (*p < 32 || *p >= 127) printf("\\u%04x", *p);
        else putchar(*p);
    }
    putchar('"');
}

static void print_translation(int web) {
    size_t i;
    if (!web) puts("\nSYNTAX-DIRECTED TRANSLATION");
    for (i = 0; i < step_count; i++) {
        if (web) {
            printf("@SDT {\"rule\":"); json_string(steps[i].rule);
            printf(",\"detail\":"); json_string(steps[i].detail); puts("}");
        } else printf("%zu. [%s] %s\n", i + 1, steps[i].rule, steps[i].detail);
    }
    if (!web) {
        puts("\nTHREE-ADDRESS CODE BEFORE BACKPATCHING (_ = unresolved)");
        for (i = 0; i < code_count; i++)
            printf("%zu: %s\n", i + 1, instruction_text(i, 0));
        puts("\nBACKPATCHING");
        if (!patch_count) puts("No pending jumps.");
    }
    for (i = 0; i < patch_count; i++) {
        if (web)
            printf("@PATCH {\"instruction\":%zu,\"target\":%zu}\n",
                   patches[i].instruction, patches[i].target);
        else printf("backpatch({%zu}, %zu): fill instruction %zu's target.\n",
                    patches[i].instruction, patches[i].target, patches[i].instruction);
    }
    if (!web) puts("\nTHREE-ADDRESS CODE (FINAL)");
    for (i = 0; i < code_count; i++) {
        Instruction *instruction = &code[i];
        char *text = instruction_text(i, 1);
        if (!web) { printf("%zu: %s\n", i + 1, text); continue; }
        printf("@TAC {\"id\":%zu,\"kind\":", i + 1); json_string(instruction->kind);
        printf(",\"op\":"); json_string(instruction->op);
        printf(",\"arg1\":"); json_string(instruction->arg1);
        printf(",\"arg2\":"); json_string(instruction->arg2);
        printf(",\"result\":"); json_string(instruction->result);
        printf(",\"target\":");
        if (instruction->target) printf("%zu", instruction->target); else printf("null");
        printf(",\"text\":"); json_string(text);
        printf(",\"unpatched_text\":"); json_string(instruction_text(i, 0));
        puts("}");
    }
}

static void release_translation(void) {
    size_t i;
    free(code); free(steps); free(patches);
    for (i = 0; i < owned_count; i++) free(owned[i]);
    free(owned);
}
#endif

