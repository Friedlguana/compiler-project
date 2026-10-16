"""Language-specific syntax frontends and lowering into the C/Lex core."""
import ast
from dataclasses import dataclass
from functools import lru_cache
import importlib
import re
from tree_sitter import Language, Parser

NAMES = {"python":"Python", "java":"Java", "c":"C", "cpp":"C++",
         "javascript":"JavaScript", "shared":"Shared C-style"}
LANGUAGES = ("python", "java", "c", "cpp", "javascript")
COMMENT_TYPES = {"comment", "line_comment", "block_comment"}
INTEGER_TYPES = {"integer","number","number_literal","decimal_integer_literal"}
BLOCK_TYPES = {"block","compound_statement","statement_block"}
RELATIONS = {"<",">","<=",">=","==","!="}


@lru_cache
def grammar(name):
    module = importlib.import_module("tree_sitter_" + name)
    return Language(module.language())


def parse(source, language):
    # Parsers are request-local; Language objects can be reused across threads.
    return Parser(grammar(language)).parse(source.encode("ascii"))


def walk(root):
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.children))


def text(node):
    return node.text.decode("ascii") if node else ""


def named(node):
    return [child for child in node.named_children if child.type not in COMMENT_TYPES]


def token_stream(root, source):
    result = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in COMMENT_TYPES:
            continue
        if node.child_count and node.type not in {"string","string_literal","character_literal"}:
            stack.extend(reversed(node.children))
            continue
        if node.is_missing or not node.text:
            continue
        lexeme = text(node)
        kind = {"identifier":"ID", "type_identifier":"TYPE", **{key:"NUMBER" for key in INTEGER_TYPES}}.get(node.type, node.type.upper())
        result.append({"index":len(result)+1, "type":kind, "lexeme":lexeme,
                       "line":node.start_point.row+1, "column":node.start_point.column+1,
                       "start":node.start_byte,"end":node.end_byte})
    result.append({"index":len(result)+1,"type":"EOF","lexeme":"",
                   "line":source.count("\n")+1,"column":len(source.rsplit("\n",1)[-1])+1,
                   "start":len(source),"end":len(source)})
    return result


def syntax_error(root, source, language):
    if language == "python":
        try:
            ast.parse(source)
        except (SyntaxError, ValueError) as error:
            return {"stage":"syntax","line":getattr(error,"lineno",1) or 1,
                    "column":getattr(error,"offset",1) or 1,
                    "message":getattr(error,"msg",str(error))}
    if not root.has_error:
        return None
    failures = [node for node in walk(root) if node.is_error or node.is_missing]
    node = min(failures, key=lambda n:(n.start_byte, n.end_byte-n.start_byte))
    message = "Expected " + node.type if node.is_missing else "Unexpected or incomplete syntax near " + repr(text(node)[:70])
    return {"stage":"syntax","line":node.start_point.row+1,
            "column":node.start_point.column+1,"message":message}


def detect(source, override="auto"):
    if override != "auto":
        return {"id":override,"name":NAMES[override],"ambiguous":False,
                "candidates":[override],"reason":"Language selected by user."}
    # Strip comments and quoted literals so language names inside them aren't signals.
    clean = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', " ", source, flags=re.S)
    clean = re.sub(r"(?m)^\s*#(?!\s*include\b)[^\n]*", "", clean)
    signals = [
        ("python", r"(?m)^\s*(?:def |from |import |elif\b|if\b[^\n]*:|for\b[^\n]*:|while\b[^\n]*:|else\s*:)|\b(?:True|False|None)\b"),
        ("javascript", r"\b(?:let|const|var|function)\b|=>|\bconsole\s*\."),
        ("java", r"\b(?:public|private|protected)\s+(?:static\s+)?(?:class|void)|\b(?:package|import)\s+[\w.]+;|\bSystem\s*\."),
        ("cpp", r"\bstd\s*::|\b(?:cout|cin|namespace|template)\b|#\s*include\s*<\s*(?:iostream|vector|string|bits/stdc\+\+\.h)\s*>"),
        ("c", r"#\s*include\s*[<\"]|\b(?:int|void)\s+main\s*\("),
    ]
    # Python imports without semicolons are distinct from Java imports.
    for language, pattern in signals:
        if re.search(pattern, clean):
            if language == "python" and re.search(r"(?m)^\s*import\s+[\w.]+\s*;",clean):
                continue
            ambiguous = language == "c"
            return {"id":language,"name":NAMES[language],"ambiguous":ambiguous,
                    "candidates":["c","cpp"] if ambiguous else [language],
                    "reason":("C-style program; the same source may also be valid C++. Select C++ to override." if ambiguous else "Detected language-specific syntax.")}
    # Keep existing assignment/if snippets and their exact C/Lex diagnostics.
    if (not source.strip() or ";" in clean or "{" in clean) and not re.search(
            r"\b(?:while|for|class|return|switch|try|throw|new|int|float|double|char|bool|boolean)\b",clean):
        return {"id":"shared","name":NAMES["shared"],"ambiguous":True,
                "candidates":["c","cpp","java","javascript"],
                "reason":"This statement snippet has no unique language marker; using the original C/Lex grammar."}
    trees = {language:parse(source,language) for language in LANGUAGES}
    valid = [language for language,tree in trees.items() if not tree.root_node.has_error]
    if valid:
        chosen = valid[0]
        return {"id":chosen,"name":NAMES[chosen],"ambiguous":len(valid)>1,
                "candidates":valid,"reason":"Selected from grammars accepting the source; choose an override if needed."}
    # Invalid code still needs a useful diagnostic rather than a forced success.
    chosen = min(LANGUAGES, key=lambda language:sum(n.is_error or n.is_missing for n in walk(trees[language].root_node)))
    return {"id":chosen,"name":NAMES[chosen],"ambiguous":True,
            "candidates":list(LANGUAGES),"reason":"No grammar accepted the input. Best-effort detection; use the language override for a precise syntax check."}


class Unsupported(Exception):
    def __init__(self, node, reason):
        self.node = node
        self.reason = reason


@dataclass
class Lowered:
    source: str
    steps: list


class Lowerer:
    """Only well-defined assignment/arithmetic/branch constructs enter the core."""
    def __init__(self, language):
        self.language = language
        self.steps = []
        self.declarations = set()
        self.identifiers = set()

    def fail(self,node,reason=None):
        raise Unsupported(node, reason or ("TAC translation does not yet support " + node.type + "."))

    def note(self,node,detail):
        self.steps.append({"rule":self.language+" frontend: "+node.type,
                           "detail":f"Line {node.start_point.row+1}: {detail}"})

    def op(self,node,left,right):
        # Extract the operator token between operands, ignoring comment nodes.
        return "".join(text(c) for c in node.children
                       if c.start_byte >= left.end_byte and c.end_byte <= right.start_byte
                       and c.type not in COMMENT_TYPES).strip()

    def expression(self,node,condition=False):
        if node is None:
            raise ValueError("Missing expression")
        kind = node.type
        if kind == "parenthesized_expression":
            return "(" + self.expression(named(node)[0],condition) + ")"
        if kind == "identifier":
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",text(node)):
                self.fail(node,"Identifiers must use letters, digits and underscores for TAC.")
            return text(node)
        if kind in INTEGER_TYPES:
            raw = text(node)
            if not re.fullmatch(r"[0-9]+",raw) or (len(raw)>1 and raw.startswith("0")):
                self.fail(node,"TAC currently supports ordinary decimal integer literals only.")
            return raw
        if kind in {"binary_expression","binary_operator","comparison_operator"}:
            parts = named(node)
            left = node.child_by_field_name("left") or parts[0]
            right = node.child_by_field_name("right") or parts[-1]
            op = self.op(node,left,right)
            if op in ("===","!==") and self.language == "javascript":
                self.fail(node,"Strict equality requires type-aware TAC and is not translated yet.")
            if op in RELATIONS and condition:
                # Chained Python comparisons must not be flattened.
                if len(parts) != 2:
                    self.fail(node,"Chained comparisons are not supported by the TAC backend.")
                return self.expression(left) + " " + op + " " + self.expression(right)
            if op in {"+","-","*","/"} and not condition:
                return "(" + self.expression(left) + " " + op + " " + self.expression(right) + ")"
            self.fail(node,"TAC supports +, -, *, / and one comparison per condition; this operator is unsupported.")
        if kind in {"unary_expression","unary_operator"}:
            parts = named(node)
            operand = parts[-1]
            op = text(node)[:operand.start_byte-node.start_byte].strip()
            if op in ("+","-") and not condition:
                value = self.expression(operand)
                return value if op == "+" else "(0 - "+value+")"
        self.fail(node)

    def condition(self,node):
        # A single comparison is required; don't silently invent truthiness semantics.
        cursor = node
        if cursor.type == "condition_clause":
            if len(named(cursor)) != 1:
                self.fail(cursor,"Condition initializers are not supported by TAC.")
            cursor = cursor.child_by_field_name("value")
        while cursor.type == "parenthesized_expression":
            cursor = named(cursor)[0]
        return self.expression(cursor,True) if cursor.type in {"binary_expression","binary_operator","comparison_operator"} else self.fail(cursor,"TAC conditions must be a single numeric comparison.")

    def declare(self,node,name,value):
        if name.type != "identifier":
            self.fail(name,"Pointers, destructuring, arrays and references are outside TAC translation.")
        identifier = self.expression(name)
        if identifier in self.declarations:
            self.fail(name,"Redeclarations/shadowing require scope-aware TAC and are not translated yet.")
        self.declarations.add(identifier)
        if value is None:
            self.fail(node,"Initialize declarations explicitly to translate them.")
        self.note(node,"Lower initialized declaration to an assignment.")
        return identifier+" = "+self.expression(value)+";"

    def statements(self,nodes):
        return "\n".join(self.statement(node) for node in nodes if node.type not in COMMENT_TYPES)

    def statement(self,node):
        kind = node.type
        if kind in COMMENT_TYPES or kind in {"pass_statement","empty_statement"}:
            return ""
        if kind in BLOCK_TYPES:
            return self.statements(named(node))
        if kind == "expression_statement":
            children = named(node)
            if len(children) != 1:
                self.fail(node)
            return self.statement(children[0])
        if kind in {"assignment","assignment_expression"}:
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is None or right is None or left.type != "identifier" or self.op(node,left,right) != "=":
                self.fail(node,"Only simple variable assignments are translated.")
            self.note(node,"Lower assignment; expression.place will be synthesized in C.")
            return self.expression(left)+" = "+self.expression(right)+";"
        if kind in {"declaration","local_variable_declaration","lexical_declaration","variable_declaration"}:
            type_node = node.child_by_field_name("type")
            if self.language in {"c","cpp","java"}:
                if text(type_node) not in {"int","long","short"}:
                    self.fail(node,"TAC translation currently supports int, long and short declarations.")
            output=[]
            for child in named(node):
                if child.type in {"init_declarator","variable_declarator"}:
                    name = child.child_by_field_name("name") or child.child_by_field_name("declarator")
                    output.append(self.declare(child,name,child.child_by_field_name("value")))
                elif child.type == "identifier":
                    self.fail(child,"Initialize declarations explicitly to translate them.")
                elif child != type_node and child.type != "modifiers":
                    self.fail(child,"This declaration form is outside TAC translation.")
            if not output:
                self.fail(node)
            return "\n".join(output)
        if kind in {"if_statement","elif_clause"}:
            condition = self.condition(node.child_by_field_name("condition"))
            body = node.child_by_field_name("consequence")
            self.note(node,"Lower condition and branches; C constructs and patches jump lists.")
            code = "if ("+condition+") {\n"+self.statement(body)+"\n}"
            alternatives = node.children_by_field_name("alternative")
            if self.language == "python" and alternatives:
                def tail(index):
                    alternative = alternatives[index]
                    if alternative.type == "elif_clause":
                        clause = "if ("+self.condition(alternative.child_by_field_name("condition"))+") {\n"+self.statement(alternative.child_by_field_name("consequence"))+"\n}"
                        if index+1 < len(alternatives):
                            clause += " else {\n"+tail(index+1)+"\n}"
                        return clause
                    return self.statement(alternative.child_by_field_name("body"))
                code += " else {\n"+tail(0)+"\n}"
            elif alternatives:
                alternative = alternatives[0]
                if alternative.type == "else_clause":
                    alternative = named(alternative)[-1]
                code += " else {\n"+self.statement(alternative)+"\n}"
            return code
        self.fail(node)

    def lower(self,root):
        nodes = named(root)
        if self.language in {"c","cpp"}:
            functions = [node for node in nodes if node.type == "function_definition"]
            if functions:
                if len(functions)!=1 or any(node.type not in {"function_definition","preproc_include"} for node in nodes):
                    self.fail(root,"TAC supports one main entry point; extra functions/globals/macros are not translated.")
                function = functions[0]
                declarator = function.child_by_field_name("declarator")
                if text(declarator.child_by_field_name("declarator")) != "main":
                    self.fail(function,"Only a main entry-point wrapper can be translated.")
                nodes = named(function.child_by_field_name("body"))
                if nodes and nodes[-1].type=="return_statement" and text(nodes[-1]).replace(" ","").strip()=="return0;":
                    nodes = nodes[:-1]
                self.note(function,"Use main body as the TAC entry point; trailing return 0 becomes halt.")
            else:
                nodes = [node for node in nodes if node.type != "preproc_include"]
        elif self.language == "java":
            classes = [node for node in nodes if node.type == "class_declaration"]
            if classes:
                if len(classes)!=1 or any(node.type not in {"class_declaration","import_declaration","package_declaration"} for node in nodes):
                    self.fail(root,"TAC supports one Java class containing only a static main method.")
                members = named(classes[0].child_by_field_name("body"))
                if len(members)!=1 or members[0].type!="method_declaration":
                    self.fail(classes[0],"TAC supports one static main method; fields and other methods are not translated.")
                method=members[0]
                if text(method.child_by_field_name("name"))!="main" or not any(
                    child.type=="modifiers" and "static" in text(child).split() for child in method.children):
                    self.fail(method,"Only a static main entry-point wrapper can be translated.")
                nodes = named(method.child_by_field_name("body"))
                if nodes and text(nodes[-1]).strip()=="return;":
                    nodes=nodes[:-1]
                self.note(method,"Use static main body as the TAC entry point.")
        return Lowered(self.statements(nodes),self.steps)

