"""Rendering for the password challenge shown to a visitor."""

from html import escape


CHALLENGE_ACTION = "/api/v1/links/verify-password"


def render_password_challenge(short_code: str, error: str | None = None) -> str:
    """Render the password form for one short code.

    The short code is escaped before it is written into the markup so a
    crafted code can never inject HTML into the challenge page.
    """

    safe_code = escape(short_code, quote=True)
    error_markup = ""
    if error:
        error_markup = f"<p>{escape(error)}</p>"

    return (
        "<form method=\"post\" action=\"" + CHALLENGE_ACTION + "\">"
        f"<input type=\"hidden\" name=\"short_code\" value=\"{safe_code}\" />"
        "<input type=\"password\" name=\"password\" "
        "placeholder=\"Enter Link Password\" required "
        "autocomplete=\"off\" />"
        "<button type=\"submit\">Access Destination</button>"
        "</form>"
        + error_markup
    )
