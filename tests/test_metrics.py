from core.metrics import MetricsCollector
from core.schemas import AnswerResult


def test_unsupported_citation_rate_counts_unsupported_claims():
    collector = MetricsCollector()
    collector.record_answer(
        AnswerResult(answer="An unsupported answer.", grounded=False)
    )

    metrics = collector.snapshot()

    assert metrics.unsupported_citation_rate == 1.0
    assert metrics.unsupported_claims == 1
