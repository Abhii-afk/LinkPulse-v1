from dataclasses import dataclass


KNOWN_BOT_TOKENS = (
    "bot",
    "spider",
    "crawl",
    "curl",
    "postman",
    "python-requests",
    "headlesschrome",
    "wget",
)


@dataclass(frozen=True, slots=True)
class UserAgentInfo:
    browser: str
    os: str
    device_type: str
    is_bot: bool


def _browser_family(user_agent: str) -> str:
    lower = user_agent.lower()
    if "googlebot" in lower:
        return "Googlebot"
    if "headlesschrome" in lower:
        return "Headless Chrome"
    if "edg/" in lower or "edge/" in lower:
        return "Edge"
    if "opr/" in lower or "opera" in lower:
        return "Opera"
    if "firefox" in lower or "fxios" in lower:
        return "Firefox"
    if "crios" in lower or "chrome" in lower:
        return "Chrome"
    if "safari" in lower:
        return "Safari"
    if "msie" in lower or "trident/" in lower:
        return "Internet Explorer"
    if "python-requests" in lower:
        return "Python Requests"
    if "curl" in lower:
        return "curl"
    if "postman" in lower:
        return "Postman"
    if "wget" in lower:
        return "Wget"
    return "Other"


def _operating_system(user_agent: str) -> str:
    lower = user_agent.lower()
    if "windows" in lower:
        return "Windows"
    if "iphone" in lower or "ipad" in lower or "ipod" in lower:
        return "iOS"
    if "android" in lower:
        return "Android"
    if "cros" in lower:
        return "Chrome OS"
    if "mac os x" in lower or "macintosh" in lower:
        return "macOS"
    if "linux" in lower:
        return "Linux"
    return "Other"


def _device_type(user_agent: str) -> str:
    lower = user_agent.lower()
    if "ipad" in lower or "tablet" in lower or ("android" in lower and "mobile" not in lower):
        return "Tablet"
    if "iphone" in lower or "ipod" in lower or "mobile" in lower or "android" in lower:
        return "Mobile"
    return "Desktop"


def parse_user_agent(user_agent: str | None) -> UserAgentInfo:
    """Extract stable analytics fields without a network or parser dependency."""

    normalized = (user_agent or "").strip()
    lower = normalized.lower()
    is_bot = not normalized or any(token in lower for token in KNOWN_BOT_TOKENS)
    return UserAgentInfo(
        browser=_browser_family(normalized),
        os=_operating_system(normalized),
        device_type=_device_type(normalized),
        is_bot=is_bot,
    )
