from dataclasses import dataclass
from collections.abc import Callable

from .collectors import search_github, search_gitlab, search_sherlock, search_stackexchange, search_wikidata
from .models import Evidence
from .search import search_web


@dataclass(frozen=True)
class SourceSpec:
    name: str
    collector: Callable[..., list[Evidence]]
    modes: frozenset[str]
    optional_bridge: bool = False
    max_limit: int = 10


SOURCE_SPECS = (
    SourceSpec("web search", search_web, frozenset({"fio", "username", "nickname", "phone", "email", "combined"}), max_limit=10),
    SourceSpec("GitHub public search", search_github, frozenset({"fio", "username", "nickname", "phone", "email", "combined"}), max_limit=10),
    SourceSpec("GitLab public user search", search_gitlab, frozenset({"fio", "email", "username", "nickname", "combined"}), max_limit=10),
    SourceSpec("Stack Overflow public user search", search_stackexchange, frozenset({"fio", "email", "username", "nickname", "combined"}), max_limit=10),
    SourceSpec("Wikidata public knowledge base", search_wikidata, frozenset({"fio", "combined"}), max_limit=10),
    SourceSpec("Sherlock public username search (optional bridge)", search_sherlock, frozenset({"username", "nickname", "combined"}), optional_bridge=True, max_limit=20),
)


def source_specs_for_mode(mode: str) -> list[SourceSpec]:
    return [spec for spec in SOURCE_SPECS if mode in spec.modes]
