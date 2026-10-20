"""The database URL has to work when a provider hands it out as it is.

Neon, Supabase and Render all give out libpq style connection strings that
end in ``?sslmode=require``. The asyncpg driver does not know that option
and refuses the connection, so the URL is translated before it is used.
"""

import pytest

from app.core.config import Settings


def build_settings(database_url: str) -> Settings:
    return Settings(_env_file=None, database_url=database_url)


def test_a_neon_url_is_translated_for_the_asyncpg_driver() -> None:
    configuration = build_settings(
        "postgresql+asyncpg://user:password@ep-cool-name.us-east-2.aws.neon.tech/neondb"
        "?sslmode=require"
    )

    assert configuration.normalized_database_url == (
        "postgresql+asyncpg://user:password@ep-cool-name.us-east-2.aws.neon.tech"
        "/neondb?ssl=require"
    )


def test_a_url_without_ssl_options_is_left_alone() -> None:
    configuration = build_settings(
        "postgresql+asyncpg://linkpulse:linkpulse@127.0.0.1:5432/linkpulse"
    )

    assert configuration.normalized_database_url == configuration.database_url


def test_other_query_parameters_are_preserved() -> None:
    configuration = build_settings(
        "postgresql+asyncpg://user:password@host:5432/db?sslmode=require&application_name=linkpulse"
    )

    translated = configuration.normalized_database_url

    assert "ssl=require" in translated
    assert "application_name=linkpulse" in translated
    assert "sslmode" not in translated


def test_an_explicit_ssl_option_wins_over_sslmode() -> None:
    configuration = build_settings(
        "postgresql+asyncpg://user:password@host:5432/db?ssl=require&sslmode=disable"
    )

    assert configuration.normalized_database_url == configuration.database_url


def test_the_credentials_and_the_port_survive_the_translation() -> None:
    configuration = build_settings(
        "postgresql+asyncpg://user:pa%40ss@ep-xyz.us-east-2.aws.neon.tech:5432/neondb"
        "?sslmode=require"
    )

    translated = configuration.normalized_database_url

    assert "pa%40ss" in translated
    assert ":5432" in translated
    assert "neondb" in translated


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://user:password@host/db?sslmode=verify-full",
        "postgresql+asyncpg://user:password@host/db?sslmode=require",
    ],
)
def test_every_sslmode_value_becomes_an_ssl_value(url: str) -> None:
    configuration = build_settings(url)

    assert "sslmode" not in configuration.normalized_database_url
    assert "ssl=" in configuration.normalized_database_url
