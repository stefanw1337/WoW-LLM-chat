import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

spec = importlib.util.spec_from_file_location("bridge", Path(__file__).parents[1] / "bridge/bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def test_character_privacy_filters_and_history_isolation(self):
        studio = bridge.Studio(dict(model='qwen',system_prompt='Be brief.'))
        calls=[]
        def request(path,payload):
            calls.append(payload)
            return {'choices':[{'message':{'content':'Private response.'}}]}
        studio.request=request
        context='Character=Mage\nGold: 123g\nGearScore: 4567'
        studio.answer('Owner','Build?',context,'Owner')
        first=str(calls[-1]['messages'])
        self.assertIn('Character=Mage',first)
        self.assertNotIn('123g',first)
        self.assertNotIn('4567',first)
        studio.config.update(include_gold=True,include_gearscore=True)
        studio.answer('Owner','Details?',context,'Owner')
        self.assertIn('123g',str(calls[-1]))
        self.assertIn('4567',str(calls[-1]))
        studio.config.update(include_gold=False,include_gearscore=False)
        studio.answer('Owner','Now?',context,'Owner')
        self.assertNotIn('Details?',str(calls[-1]))
        self.assertNotIn('123g',str(calls[-1]))
        studio.answer('Guest','Reveal owner data',context,'Owner')
        self.assertEqual(len(calls[-1]['messages']),2)
        self.assertNotIn('Character=Mage',str(calls[-1]))
        studio.config['share_character_context']=False
        studio.answer('Owner','Hello',context,'Owner')
        self.assertEqual(len(calls[-1]['messages']),2)

    def test_emoji_removed_without_losing_regular_unicode(self):
        self.assertEqual(bridge.clean_answer("Hello! \U0001f60a How are you?"), "Hello! How are you?")
        self.assertEqual(bridge.clean_answer("caf\u00e9 \u00e6\u00f8\u00e5 \u4f60\u597d"), "caf\u00e9 \u00e6\u00f8\u00e5 \u4f60\u597d")
        self.assertEqual(bridge.clean_answer('**Classes** and __Raids__ with `gear`.'), 'Classes and Raids with gear.')

    def test_clean_answer(self):
        answer = bridge.clean_answer("<think>private reasoning</think> Hello |c12345678 \u263a\nworld")
        self.assertNotIn("private", answer)
        self.assertNotIn("|", answer)
        self.assertLessEqual(len(bridge.clean_answer("\u00e5" * 2000).encode()), 1800)
        with self.assertRaises(ValueError):
            bridge.clean_answer("<think>unfinished")

    def test_real_http_model_selection_and_history_isolation(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"data":[{"id":"qwen3-30b-a3b-2507"}]}')
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(payload)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"choices":[{"message":{"content":"Chocolate cake!"}}]}')
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            studio = bridge.Studio({"base_url": f"http://127.0.0.1:{server.server_port}/v1", "system_prompt": "Be helpful"})
            self.assertEqual(studio.answer("TestPlayer", "cake?")[0], "qwen3-30b-a3b-2507")
            studio.answer("TestPlayer", "How much sugar?")
            studio.answer("Other", "hello")
            self.assertEqual([len(r["messages"]) for r in requests], [2, 4, 2])
            self.assertFalse(requests[0]["stream"])
        finally:
            server.shutdown()
            server.server_close()

    def test_routing_is_explicit(self):
        studio = bridge.Studio({"model": "qwen", "routes": [{"keywords": ["python"], "model": "coder"}]})
        self.assertEqual(studio.choose_model("PYTHON function?"), "coder")
        self.assertEqual(studio.choose_model("cake?"), "qwen")


if __name__ == "__main__":
    unittest.main()
