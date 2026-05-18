"""query_service 单元测试。"""
from app.services.query_service import _score_text, _tokenize


def test_tokenize_splits_chinese_phrase():
    tokens = _tokenize("活塞销 压力")
    assert "活塞销" in tokens
    assert "压力" in tokens


def test_score_text_increases_with_hits():
    low = _score_text("hello world", ["missing"])
    high = _score_text("活塞销存在气孔", ["活塞销", "气孔"])
    assert high > low
