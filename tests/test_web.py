import unittest
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from web.app import app


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(app)
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def check_source(self, source):
        response = self.client.post("/api/analyze", json={"source": source})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_interface_and_examples(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        examples = self.client.get("/api/examples").json()
        self.assertGreaterEqual(len(examples), 7)
        for example in examples:
            with self.subTest(example=example["id"]):
                result = self.check_source(example["source"])
                expected = "error" if example["id"] in ("semicolon", "character", "brace") else "success"
                self.assertEqual(result["syntax"], "skipped" if example["id"] == "character" else expected)

    def test_longest_match_and_source_offsets(self):
        result = self.check_source("// ignored\niffy=10;\nif(iffy<=20){iffy=(iffy+1)*2;}")
        self.assertEqual(result["syntax"], "success")
        self.assertIn("LE", [token["type"] for token in result["tokens"]])
        for token in result["tokens"]:
            if token["type"] != "EOF":
                self.assertEqual(result["source"][token["start"]:token["end"]], token["lexeme"])

    def test_positions_and_skipped_syntax(self):
        result = self.check_source("a=1;\nb=@;")
        self.assertEqual(result["syntax"], "skipped")
        self.assertEqual((result["diagnostic"]["line"], result["diagnostic"]["column"]), (2,3))
        result = self.check_source("a=1\nb=2;")
        self.assertEqual(result["diagnostic"]["stage"], "syntax")
        self.assertEqual(result["diagnostic"]["line"], 2)

    def test_empty_and_long_identifier(self):
        self.assertEqual(self.check_source("")["syntax"], "success")
        result = self.check_source("x"*100 + "=1;")
        self.assertEqual(result["tokens"][0]["lexeme"], "x"*100)

    def test_invalid_request_and_line_endings(self):
        for source in ("a=1;\x00", "é=1;", "a"*20001):
            self.assertEqual(self.client.post("/api/analyze", json={"source":source}).status_code, 422)
        result = self.check_source("a=1;\r\nb=2;")
        self.assertEqual(result["tokens"][4]["line"], 2)

    def test_concurrent_requests(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(self.check_source, ["a=1;", "b=2;", "c=;", "d=@;"]))
        self.assertEqual([r["syntax"] for r in results], ["success","success","error","skipped"])


if __name__ == "__main__":
    unittest.main()

