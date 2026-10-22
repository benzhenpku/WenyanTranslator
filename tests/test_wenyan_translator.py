"""测试：接口地址规范化、提示词构造、异常处理、配置读写。"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# 把项目根目录加入 path，以便导入 src 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import (
    normalize_endpoint,
    STYLES,
    SYSTEM_PROMPT,
    TranslationError,
    request_translation,
)
from src.config_store import load_config, write_config


class TestNormalizeEndpoint(unittest.TestCase):
    """测试接口地址补全逻辑。"""

    def test_完整地址不变(self):
        url = "https://api.example.com/chat/completions"
        self.assertEqual(normalize_endpoint(url), url)

    def test_base_url_自动补全(self):
        url = "https://api.example.com/v1"
        self.assertEqual(
            normalize_endpoint(url),
            "https://api.example.com/v1/chat/completions",
        )

    def test_末尾斜杠被去掉(self):
        url = "https://api.example.com/"
        self.assertEqual(
            normalize_endpoint(url),
            "https://api.example.com/chat/completions",
        )

    def test_空白被去掉(self):
        url = "  https://api.example.com  "
        self.assertEqual(
            normalize_endpoint(url),
            "https://api.example.com/chat/completions",
        )


class TestStyles(unittest.TestCase):
    """测试文风字典。"""

    def test_四种文风都存在(self):
        expected = {"浅易文言", "典雅文言", "庄重文言", "艰深古奥"}
        self.assertEqual(set(STYLES.keys()), expected)

    def test_文风说明非空(self):
        for name, desc in STYLES.items():
            self.assertTrue(len(desc) > 0, f"{name} 的说明为空")


class TestRequestTranslation(unittest.TestCase):
    """测试 HTTP 请求与响应解析（使用 mock）。"""

    def _make_response(self, content):
        """构造一个模拟的 HTTP 响应。"""
        body = json.dumps({
            "choices": [{"message": {"content": content}}]
        }).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("src.core.urllib.request.urlopen")
    def test_正常请求返回译文(self, mock_urlopen):
        mock_urlopen.return_value = self._make_response("  吾今夕不食矣。  ")
        result = request_translation(
            "https://api.example.com",
            "test-model",
            "test-key",
            "浅易文言",
            "",
            "我今晚不吃饭了。",
        )
        self.assertEqual(result, "吾今夕不食矣。")

    @patch("src.core.urllib.request.urlopen")
    def test_请求体包含正确字段(self, mock_urlopen):
        mock_urlopen.return_value = self._make_response("译文")
        request_translation(
            "https://api.example.com",
            "test-model",
            "test-key",
            "典雅文言",
            "保留人名",
            "你好",
        )
        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]
        body = json.loads(request_obj.data.decode("utf-8"))
        self.assertEqual(body["model"], "test-model")
        self.assertEqual(body["reasoning_effort"], "high")
        self.assertEqual(len(body["messages"]), 2)

    @patch("src.core.urllib.request.urlopen")
    def test_空译文抛出异常(self, mock_urlopen):
        mock_urlopen.return_value = self._make_response("   ")
        with self.assertRaises(TranslationError):
            request_translation(
                "https://api.example.com", "test-model", "test-key",
                "浅易文言", "", "测试",
            )

    @patch("src.core.urllib.request.urlopen")
    def test_响应格式错误抛出异常(self, mock_urlopen):
        body = json.dumps({"error": "bad"}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        with self.assertRaises(TranslationError):
            request_translation(
                "https://api.example.com", "test-model", "test-key",
                "浅易文言", "", "测试",
            )

    @patch("src.core.urllib.request.urlopen")
    def test_http_401_抛出异常(self, mock_urlopen):
        import urllib.error
        error_body = json.dumps({"error": {"message": "invalid key"}}).encode("utf-8")
        http_error = urllib.error.HTTPError(
            "https://api.example.com/chat/completions",
            401, "Unauthorized", {}, None,
        )
        http_error.read = lambda: error_body
        mock_urlopen.side_effect = http_error
        with self.assertRaises(TranslationError) as ctx:
            request_translation(
                "https://api.example.com", "test-model", "bad-key",
                "浅易文言", "", "测试",
            )
        self.assertIn("401", str(ctx.exception))

    @patch("src.core.urllib.request.urlopen")
    def test_网络不可达抛出异常(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        with self.assertRaises(TranslationError) as ctx:
            request_translation(
                "https://api.example.com", "test-model", "test-key",
                "浅易文言", "", "测试",
            )
        self.assertIn("无法连接", str(ctx.exception))


class TestConfigStore(unittest.TestCase):
    """测试配置读写。"""

    def test_默认配置(self):
        # 指向不存在的文件，避免读到本机真实的 config.json
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("src.config_store.CONFIG_PATH", Path(tmp_dir) / "config.json"):
                config = load_config()
        self.assertEqual(config["api_key"], "")
        self.assertEqual(config["default_style"], "浅易文言")
        self.assertIn("api_url", config)
        self.assertIn("model", config)

    def test_写入后读取一致(self):
        test_config = {
            "api_url": "https://test.example.com/chat/completions",
            "model": "test-model",
            "api_key": "test-key-123",
            "default_style": "典雅文言",
            "default_requirements": "保留数字",
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("src.config_store.CONFIG_PATH", Path(tmp_dir) / "config.json"):
                write_config(test_config)
                loaded = load_config()
        self.assertEqual(loaded, test_config)


class TestSystemPrompt(unittest.TestCase):
    """测试系统提示词包含关键约束。"""

    def test_要求只返回译文(self):
        self.assertIn("只返回译文", SYSTEM_PROMPT)

    def test_要求保留人名地名(self):
        self.assertIn("人名", SYSTEM_PROMPT)

    def test_要求保留换行(self):
        self.assertIn("换行", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
