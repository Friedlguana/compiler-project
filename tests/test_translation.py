"""Tests execute IR only inside this test suite to validate control flow."""
import operator
import random
import subprocess
import unittest
from fastapi.testclient import TestClient
from web.app import app, BINARY, ROOT

RELATIONS = {"<": operator.lt, ">": operator.gt, "<=": operator.le,
             ">=": operator.ge, "==": operator.eq, "!=": operator.ne}


def run_ir(code):
    values = {}
    pc = 0
    def value(operand):
        return int(operand) if operand.isdigit() else values[operand]
    for _ in range(len(code) * 2 + 1):
        instruction = code[pc]
        kind = instruction["kind"]
        if kind == "halt":
            return {key: val for key, val in values.items() if not key.startswith("$")}
        if kind == "assign":
            values[instruction["result"]] = value(instruction["arg1"])
        elif kind == "binary":
            a, b = value(instruction["arg1"]), value(instruction["arg2"])
            op = instruction["op"]
            values[instruction["result"]] = {
                "+": lambda: a+b, "-": lambda: a-b, "*": lambda: a*b,
                "/": lambda: (abs(a)//abs(b)) * (-1 if (a < 0) != (b < 0) else 1),
            }[op]()
        elif kind == "goto":
            pc = instruction["target"] - 1
            continue
        elif kind == "if" and RELATIONS[instruction["op"]](
                value(instruction["arg1"]), value(instruction["arg2"])):
            pc = instruction["target"] - 1
            continue
        pc += 1
    raise AssertionError("IR failed to terminate")


class TranslationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(app)
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def compile(self, source):
        response = self.client.post("/api/analyze", json={"source": source})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["translation"], "success")
        code = result["tac"]
        self.assertEqual([item["id"] for item in code], list(range(1, len(code)+1)))
        self.assertEqual(code[-1]["kind"], "halt")
        jumps = {item["id"]: item for item in code if item["kind"] in ("if", "goto")}
        self.assertEqual(len(result["backpatches"]), len(jumps))
        self.assertEqual({p["instruction"] for p in result["backpatches"]}, set(jumps))
        for patch in result["backpatches"]:
            item = jumps[patch["instruction"]]
            self.assertEqual(item["target"], patch["target"])
            self.assertGreater(item["target"], item["id"])
            self.assertLessEqual(item["target"], len(code))
            self.assertTrue(item["unpatched_text"].endswith("goto _"))
            self.assertTrue(item["text"].endswith("goto " + str(item["target"])))
        self.assertTrue(result["translation_steps"])
        return result

    def test_precedence_associativity_and_temporary_names(self):
        result = self.compile("t1=5; x=2+3*4; y=(2+3)*4; z=20-6-3; q=24/4/2; n=(0-7)/2;")
        self.assertEqual(run_ir(result["tac"]), {"t1":5, "x":14, "y":20, "z":11, "q":3, "n":-3})
        self.assertTrue(all(item["result"].startswith("$t")
                            for item in result["tac"] if item["kind"] == "binary"))

    def test_true_false_paths_and_all_comparisons(self):
        for op, compare in RELATIONS.items():
            for a, b in ((2,1), (1,2), (2,2)):
                with self.subTest(op=op, a=a, b=b):
                    source = f"a={a};b={b};if(a{op}b){{x=10;}}else{{x=20;}}done=1;"
                    result = self.compile(source)
                    self.assertEqual(run_ir(result["tac"])["x"], 10 if compare(a,b) else 20)
                    self.assertEqual(run_ir(result["tac"])["done"], 1)

    def test_nested_nextlists_and_empty_blocks(self):
        bodies = [
            "if(a>0){if(b>0){x=1;}}else{x=2;}",
            "if(a>0){if(b>0){}else{x=3;}}else{if(b>0){x=4;}}",
            "if(a>0){}else{} if(b>0){}",
            "if(a>0){if(b>0){x=3;}else{}}else{if(b>0){}else{x=4;}}",
        ]
        expected = [[0,2,2,1], [3,4,0,0], [0,0,0,0], [0,0,4,3]]
        for body, outcomes in zip(bodies,expected):
            for (a,b), x in zip(((1,0),(0,1),(0,0),(1,1)),outcomes):
                result = self.compile(f"a={a};b={b};x=0;{body} done=7;")
                values = run_ir(result["tac"])
                self.assertEqual((values["x"],values["done"]), (x,7), body)

    def test_no_partial_translation_on_errors(self):
        for source in ("a=2+3; if(a<4){b=1;", "a=1; b=@;", "a=1;}"):
            result = self.client.post("/api/analyze", json={"source":source}).json()
            self.assertEqual(result["translation"], "skipped")
            for name in ("tac","translation_steps","backpatches"):
                self.assertEqual(result[name], [])
            self.assertNotIn("@TAC", result["output"])

    def test_empty_program_and_no_branch(self):
        result = self.compile("")
        self.assertEqual([item["text"] for item in result["tac"]], ["halt"])
        self.assertEqual(result["backpatches"], [])

    def test_random_nested_programs_against_reference(self):
        rng = random.Random(16)
        # Build a small independent source AST and evaluate it directly.
        def generate(depth):
            if depth == 0 or rng.random() < .45:
                return ("assign", rng.choice("abc"), rng.choice("abc"), rng.choice(("+","-")), rng.randrange(4))
            return ("if", rng.choice("abc"), rng.choice(tuple(RELATIONS)), rng.randrange(5),
                    [generate(depth-1) for _ in range(rng.randrange(3))],
                    [generate(depth-1) for _ in range(rng.randrange(3))] if rng.random() < .7 else None)
        def render(node):
            if node[0] == "assign":
                _, name, left, op, right = node
                return f"{name}={left}{op}{right};"
            _, name, op, right, yes, no = node
            source = f"if({name}{op}{right}){{" + "".join(map(render,yes)) + "}"
            return source + ("else{" + "".join(map(render,no)) + "}" if no is not None else "")
        def evaluate(nodes, state):
            for node in nodes:
                if node[0] == "assign":
                    _, name, left, op, right = node
                    state[name] = state[left] + right if op == "+" else state[left] - right
                else:
                    _, name, op, right, yes, no = node
                    evaluate(yes if RELATIONS[op](state[name],right) else (no or []),state)
        for index in range(80):
            nodes = [generate(3) for _ in range(3)]
            expected = {"a":1,"b":2,"c":3}
            evaluate(nodes,expected)
            source = "a=1;b=2;c=3;" + "".join(map(render,nodes))
            with self.subTest(case=index):
                self.assertEqual(run_ir(self.compile(source)["tac"]), expected)

    def test_cli_human_output_and_invalid_exit(self):
        result = subprocess.run([str(BINARY), str(ROOT/"samples/valid.txt")], capture_output=True,text=True)
        self.assertEqual(result.returncode, 0)
        for heading in ("SYNTAX-DIRECTED TRANSLATION","BEFORE BACKPATCHING","BACKPATCHING","THREE-ADDRESS CODE (FINAL)"):
            self.assertIn(heading,result.stdout)
        self.assertNotIn("@TAC",result.stdout)
        result = subprocess.run([str(BINARY), str(ROOT/"samples/invalid_syntax.txt")], capture_output=True,text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("THREE-ADDRESS CODE",result.stdout)


if __name__ == "__main__":
    unittest.main()

