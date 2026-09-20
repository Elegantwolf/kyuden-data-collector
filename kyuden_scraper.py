"""Compatibility imports; use python -m kyuden for command-line collection."""
from kyuden.scraper import AuthenticationRequiredError, KyudenScraper

if __name__ == "__main__":
    from kyuden.cli import main
    raise SystemExit(main())
