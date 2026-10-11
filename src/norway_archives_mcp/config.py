"""Configuration from environment variables.

===================================  ===========================================
``NORWAY_ARCHIVES_CACHE_DIR``        Directory for the on-disk response cache.
``NORWAY_ARCHIVES_TIMEOUT``          HTTP timeout in seconds for one request.
``NORWAY_ARCHIVES_DA_INTERVAL``      Least seconds between two requests to
                                     Digitalarkivet. Never below 5.
``NORWAY_ARCHIVES_DA_DAILY_BUDGET``  Most live requests to Digitalarkivet in
                                     one day (UTC); cached answers are free.
``NORWAY_ARCHIVES_CONTACT``          An email address or URL appended to the
                                     User-Agent, so an archive can reach
                                     whoever runs this server.
``NORWAY_ARCHIVES_DOWNLOAD_DIR``     When set, the folder every downloaded
                                     page image must lie inside.
===================================  ===========================================

None is required: none of the three services needs a key or an account. A
``.env`` file in the working directory supplies any of these that the
environment does not. The last one is the operator's to set, never a model's:
it narrows where a tool writes.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

#: Least seconds between requests to Digitalarkivet, and the floor on the
#: setting. The archive asks every crawler for a 5-second delay in its
#: robots.txt; this server keeps to that whatever it is configured to do.
DA_MIN_INTERVAL = 5.0

#: Live Digitalarkivet requests allowed in one UTC day, unless configured.
#: A research session reading one church book page by page uses about 60.
DEFAULT_DA_DAILY_BUDGET = 600


class ConfigError(RuntimeError):
    """Raised when a setting is present but unusable."""


@dataclass
class Config:
    """Resolved server configuration.

    Attributes
    ----------
    cache_dir : Path
        Directory holding cached responses and the daily request count.
    timeout : float
        HTTP timeout in seconds for one request. Image downloads get longer.
    da_interval : float
        Least seconds between the start of one Digitalarkivet request and the next.
    da_daily_budget : int
        Live Digitalarkivet requests allowed per UTC day.
    contact : str
        Appended to the User-Agent when set. Empty by default.
    download_dir : Path or None
        When set, the image tools write only inside this folder.
    """

    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "norway-archives-mcp")
    timeout: float = 30.0
    da_interval: float = DA_MIN_INTERVAL
    da_daily_budget: int = DEFAULT_DA_DAILY_BUDGET
    contact: str = ""
    download_dir: Path | None = None


def load_config() -> Config:
    """Load configuration from the environment.

    A ``.env`` file in the working directory is read if present; real
    environment variables win. Only the working directory is consulted.
    ``load_dotenv()`` with no path searches upward from the *calling
    module's* location instead, which for an installed package is
    ``site-packages``.

    Raises
    ------
    ConfigError
        If a number is unusable or a contact string could break the header.
        The server loads its configuration on the first tool call, so this
        surfaces there as a ``not_configured`` result rather than as a crash.
    """
    load_dotenv(Path.cwd() / ".env")

    cfg = Config()
    if raw := os.environ.get("NORWAY_ARCHIVES_CACHE_DIR"):
        cfg.cache_dir = Path(raw).expanduser()
    if raw := os.environ.get("NORWAY_ARCHIVES_TIMEOUT"):
        cfg.timeout = _positive("NORWAY_ARCHIVES_TIMEOUT", raw)
    if raw := os.environ.get("NORWAY_ARCHIVES_DA_INTERVAL"):
        value = _positive("NORWAY_ARCHIVES_DA_INTERVAL", raw)
        if value < DA_MIN_INTERVAL:
            raise ConfigError(
                f"NORWAY_ARCHIVES_DA_INTERVAL must be at least {DA_MIN_INTERVAL:g}; got {raw!r}."
            )
        cfg.da_interval = value
    if raw := os.environ.get("NORWAY_ARCHIVES_DA_DAILY_BUDGET"):
        value = _positive("NORWAY_ARCHIVES_DA_DAILY_BUDGET", raw)
        if value != int(value):
            raise ConfigError(
                f"NORWAY_ARCHIVES_DA_DAILY_BUDGET must be a whole number; got {raw!r}."
            )
        cfg.da_daily_budget = int(value)
    if raw := os.environ.get("NORWAY_ARCHIVES_CONTACT"):
        cfg.contact = _contact(raw)
    if raw := os.environ.get("NORWAY_ARCHIVES_DOWNLOAD_DIR"):
        cfg.download_dir = _download_dir(raw)
    return cfg


def _positive(name: str, raw: str) -> float:
    """Parse one numeric setting, naming the variable if it is unusable."""
    try:
        value = float(raw.strip())
    except ValueError:
        raise ConfigError(f"{name} must be a number; got {raw!r}.") from None
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"{name} must be greater than zero; got {raw!r}.")
    return value


def _contact(raw: str) -> str:
    """Keep a contact string safe to place inside a User-Agent header.

    A newline would let the value inject a second header, and parentheses
    would close the comment it sits in.
    """
    text = raw.strip()
    if any(ch in text for ch in "\r\n()") or not text.isprintable():
        raise ConfigError(
            "NORWAY_ARCHIVES_CONTACT must be one line with no parentheses, such as an "
            f"email address or a URL; got {raw!r}."
        )
    return text


def _download_dir(raw: str) -> Path:
    """The folder the image tools are confined to: absolute, and already there.

    A folder that does not exist yet is refused rather than created, so a
    typing slip cannot confine downloads to somewhere unintended.
    """
    path = Path(raw.strip()).expanduser()
    if not path.is_absolute():
        raise ConfigError(f"NORWAY_ARCHIVES_DOWNLOAD_DIR must be an absolute path; got {raw!r}.")
    if not path.is_dir():
        raise ConfigError(
            f"NORWAY_ARCHIVES_DOWNLOAD_DIR must be a folder that exists; got {raw!r}."
        )
    return path
