import os
from unittest.mock import patch

from utils.validate_config import validate


def test_scrape_requires_database_and_search_provider():
    with patch.dict(os.environ, {}, clear=True):
        errors = validate("scrape")
    assert "SUPABASE_URL" in errors
    assert any("SERPAPI_KEY" in error for error in errors)


def test_scrape_accepts_service_key_and_serpapi():
    env = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_KEY": "service-key",
        "SERPAPI_KEY": "search-key",
    }
    with patch.dict(os.environ, env, clear=True):
        assert validate("scrape") == []


def test_match_requires_groq():
    env = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_KEY": "anon-key",
    }
    with patch.dict(os.environ, env, clear=True):
        assert validate("match") == ["GROQ_API_KEY"]


def test_notify_requires_mail_configuration():
    env = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_KEY": "anon-key",
    }
    with patch.dict(os.environ, env, clear=True):
        errors = validate("notify")
    assert errors == ["SMTP_USER", "SMTP_PASSWORD", "NOTIFICATION_EMAIL"]


def test_database_stage_only_requires_supabase():
    env = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_KEY": "service-key",
    }
    with patch.dict(os.environ, env, clear=True):
        assert validate("database") == []
