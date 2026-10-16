import unittest
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from web.app import app, EXAMPLES, ROOT
from web.languages import detect
from test_translation import run_ir


class LanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context=TestClient(app)
        cls.client=cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None,None,None)

    def analyze(self,source,language="auto"):
        response=self.client.post("/api/analyze",json={"source":source,"language":language})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_all_five_examples_autodetect_and_translate(self):
        for language in ("python","java","c","cpp","javascript"):
            source=next(e["source"] for e in EXAMPLES if e["id"]==language)
            with self.subTest(language=language):
                result=self.analyze(source)
                self.assertEqual(result["language"]["id"],language)
                self.assertEqual(result["syntax"],"success")
                self.assertEqual(result["translation"],"success")
                self.assertEqual(run_ir(result["tac"])["result"],50)
                self.assertIn("if (",result["normalized_source"])
                for token in result["tokens"]:
                    if token["type"]!="EOF":
                        self.assertEqual(source[token["start"]:token["end"]],token["lexeme"])

    def test_each_language_reports_real_syntax_errors(self):
        cases={
            "python":"a = 1\nif a < 2\n    b = 1\n",
            "java":"public class Demo { public static void main(String[] args) { int a = ; } }",
            "c":"#include <stdio.h>\nint main(void) { int a = ; }",
            "cpp":"#include <iostream>\nint main() { int a = ; }",
            "javascript":"const a = ;",
        }
        for language,source in cases.items():
            with self.subTest(language=language):
                result=self.analyze(source)
                self.assertEqual(result["language"]["id"],language)
                self.assertEqual(result["syntax"],"error")
                self.assertEqual(result["tac"],[])
                self.assertEqual(result["translation"],"skipped")
                self.assertGreaterEqual(result["diagnostic"]["line"],1)

    def test_valid_unsupported_constructs_are_not_syntax_failures(self):
        cases={
            "python":"for i in range(3):\n    print(i)\n",
            "java":"public class Demo { public static void main(String[] args) { System.out.println(1); } }",
            "c":"#include <stdio.h>\nint main(void) { int a=0; while(a<3){a=a+1;} return 0; }",
            "cpp":"#include <iostream>\nint main() { std::cout << 1; return 0; }",
            "javascript":"const a = [1, 2, 3];",
        }
        for language,source in cases.items():
            with self.subTest(language=language):
                result=self.analyze(source)
                self.assertEqual(result["syntax"],"success")
                self.assertEqual(result["translation"],"skipped")
                self.assertTrue(result["translation_reason"])
                self.assertEqual(result["tac"],[])

    def test_ambiguous_snippets_and_override(self):
        result=self.analyze("a=1;")
        self.assertTrue(result["language"]["ambiguous"])
        self.assertEqual(result["language"]["id"],"shared")
        result=self.analyze("a=1;", "javascript")
        self.assertEqual(result["language"]["id"],"javascript")
        self.assertEqual(result["translation"],"success")
        self.assertFalse(result["language"]["ambiguous"])
        result=self.analyze("a=1", "python")
        self.assertEqual(result["translation"],"success")
        self.assertEqual(self.client.post("/api/analyze",json={"source":"","language":"ruby"}).status_code,422)

    def test_comments_and_literals_do_not_spoof_detection(self):
        self.assertEqual(detect('let a = "public class Java";')["id"],"javascript")
        self.assertEqual(detect("// public class Demo\nlet a=1;")["id"],"javascript")
        self.assertEqual(detect("# public class Demo\na = 1\nif a < 2:\n    a = 2\n")["id"],"python")
        self.assertEqual(detect("a=1; // let const function")["id"],"shared")

    def test_python_elif_multiple_paths(self):
        for a,expected in ((1,10),(2,20),(3,30),(4,40)):
            source=f"a={a}\nif a == 1:\n    result=10\nelif a == 2:\n    result=20\nelif a == 3:\n    result=30\nelse:\n    result=40\n"
            result=self.analyze(source)
            self.assertEqual(run_ir(result["tac"])["result"],expected)

    def test_unsupported_semantics_are_not_silently_dropped(self):
        cases=[
            ("python","a = 1 < 2 < 3\n"),
            ("python","a = 5 // 2\n"),
            ("javascript","let a=1; if(a === 1){a=2;}"),
            ("c","int main(){int a=1; {int a=2;} return 0;}"),
            ("c","int main(){int a=1,*p; return 0;}"),
            ("c","int main(){return 2;}"),
            ("c","int f(){return 1;} int main(){int a=2;return 0;}"),
            ("java","class Demo { static int a=1; public static void main(String[] args){} }"),
        ]
        for language,source in cases:
            with self.subTest(language=language,source=source):
                result=self.analyze(source,language)
                self.assertEqual(result["syntax"],"success")
                self.assertEqual(result["translation"],"skipped")
                self.assertTrue(result["translation_reason"])
                self.assertEqual(result["tac"],[])

    def test_parallel_native_languages(self):
        sources=[e["source"] for e in EXAMPLES if e["id"] in ("python","java","c","cpp","javascript")]
        with ThreadPoolExecutor(max_workers=5) as pool:
            results=list(pool.map(self.analyze,sources))
        self.assertTrue(all(r["translation"]=="success" for r in results))

    def test_multilanguage_cli(self):
        for language,suffix in (("python",".py"),("java",".java"),("c",".c"),("cpp",".cpp"),("javascript",".js")):
            with self.subTest(language=language):
                process=subprocess.run([sys.executable,str(ROOT/"analyze.py"),
                                        str(ROOT/"samples/languages"/(language+suffix))],
                                       capture_output=True,text=True,timeout=10)
                self.assertEqual(process.returncode,0,process.stdout+process.stderr)
                self.assertIn("DETECTED LANGUAGE",process.stdout)
                self.assertIn("THREE-ADDRESS CODE (FINAL)",process.stdout)


if __name__=="__main__":
    unittest.main()

