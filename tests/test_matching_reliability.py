from unittest.mock import MagicMock, patch

from agents.groq_client import GroqClient
from rag.match_jobs import score_with_llama
from utils.supabase_client import SupabaseClient


def test_provider_failure_is_not_converted_to_zero_score():
    client = GroqClient.__new__(GroqClient)
    client.generate = MagicMock(side_effect=Exception("temporary provider error"))

    result = client.score_job_relevance("job", "resume", "title", "company")

    assert result["success"] is False
    assert result["score"] is None
    assert "temporary provider error" in result["error"]


def test_retry_wait_honors_provider_guidance():
    client = GroqClient.__new__(GroqClient)
    client.retry_delay = 1.0

    error = Exception("Rate limited. Please try again in 4.335s.")

    assert client._retry_wait_seconds(error, attempt=0) == 4.835


def test_retry_wait_uses_exponential_fallback():
    client = GroqClient.__new__(GroqClient)
    client.retry_delay = 1.0

    assert client._retry_wait_seconds(Exception("bad JSON"), attempt=1) == 2.0


def test_failed_scores_are_deferred_instead_of_saved_as_results():
    scorer = MagicMock()
    scorer.score_job_relevance.side_effect = [
        {
            "success": True,
            "score": 82,
            "reasoning": "Strong match",
            "key_matches": ["Python"],
            "error": None,
        },
        {
            "success": False,
            "score": None,
            "reasoning": "",
            "key_matches": [],
            "error": "temporary provider error",
        },
    ]
    jobs = [
        {"id": 1, "title": "AI Engineer", "description": "AI", "companies": {}},
        {"id": 2, "title": "SDE", "description": "Backend", "companies": {}},
    ]

    with patch("rag.match_jobs.GroqClient", return_value=scorer), patch(
        "rag.match_jobs.time.sleep"
    ):
        scored, failed_count = score_with_llama("resume", jobs)

    assert [job["id"] for job in scored] == [1]
    assert failed_count == 1


def test_vector_threshold_is_forwarded_to_rpc():
    wrapper = SupabaseClient.__new__(SupabaseClient)
    wrapper.client = MagicMock()
    wrapper.client.rpc.return_value.execute.return_value.data = []

    wrapper.search_similar_jobs([0.1, 0.2], limit=25, threshold=0.4)

    wrapper.client.rpc.assert_called_once_with(
        "match_jobs",
        {
            "query_embedding": [0.1, 0.2],
            "match_threshold": 0.4,
            "match_count": 25,
        },
    )


def test_notification_matches_are_hydrated_with_job_descriptions():
    wrapper = SupabaseClient.__new__(SupabaseClient)
    wrapper.client = MagicMock()
    matches_query = MagicMock()
    jobs_query = MagicMock()
    wrapper.client.table.side_effect = [matches_query, jobs_query]
    matches_query.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = [
        {"id": 10, "job_id": 7, "location": "Remote - India"}
    ]
    jobs_query.select.return_value.in_.return_value.execute.return_value.data = [
        {
            "id": 7,
            "description": "Available in the United States and India.",
        }
    ]

    matches = wrapper.get_unnotified_matches()

    assert matches[0]["description"] == "Available in the United States and India."
