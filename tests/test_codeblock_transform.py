import pytest
from src.api.routes import _clean_chat_reply_text


def test_convert_single_codeblock():
    raw = '下面是一个 HTML 文件：\n\n<CodeBlock language="html" editable>\n<!DOCTYPE html>\n<html><body>Hi</body></html>\n</CodeBlock>\n\n可以保存后打开。'
    cleaned = _clean_chat_reply_text(raw)
    assert '<CodeBlock' not in cleaned
    assert '</CodeBlock>' not in cleaned
    assert '```html\n<!DOCTYPE html>' in cleaned
    assert '</html>\n```' in cleaned


def test_convert_multiple_codeblocks_and_no_lang():
    raw = '<CodeBlock>\ndef foo(): pass\n</CodeBlock>\n<CodeBlock language="python">\nprint("bar")\n</CodeBlock>'
    cleaned = _clean_chat_reply_text(raw)
    assert '```text\ndef foo(): pass\n```' in cleaned or '```\ndef foo(): pass\n```' in cleaned
    assert '```python\nprint("bar")\n```' in cleaned
