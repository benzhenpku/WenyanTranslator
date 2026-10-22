"""基础功能测试：接口地址规范化、提示词构造、异常处理。"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import json

# 把项目根目录加入 path，以便导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wenyan_translator import (
    normalize_endpoint,
    STYLES,
    SYSTEM_PROMPT,
    TranslationError,
    request_translation,
)


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

    @patch("wenyan_translator.urllib.request.urlopen")
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

    @patch("wenyan_translator.urllib.request.urlopen")
    def test_空译文抛出异常(self, mock_urlopen):
        mock_urlopen.return_value = self._make_response("   ")
        with self.assertRaises(TranslationError):
            request_translation(
                "https://api.example.com", "test-model", "test-key",
                "浅易文言", "", "测试",
            )

    @patch("wenyan_translator.urllib.request.urlopen")
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

    @patch("wenyan_translator.urllib.request.urlopen")
    def test_http_401_抛出异常(self, mock_urlopen):
        import urllib.error
        error_body = json.dumps({"error": {"message": "invalid key"}}).encode("utf-8")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://api.example.com/chat/completions",
            401, "Unauthorized", {}, None,
        )
        mock_urlopen.side_effect.read = lambda: error_body
        with self.assertRaises(TranslationError) as ctx:
            request_translation(
                "https://api.example.com", "test-model", "bad-key",
                "浅易文言", "", "测试",
            )
        self.assertIn("401", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
