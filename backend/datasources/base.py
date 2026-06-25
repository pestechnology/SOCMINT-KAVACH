"""Abstract base class for all data sources."""

from abc import ABC, abstractmethod

from backend.schemas import Identifier, RawProfile


class BaseDataSource(ABC):
    """Every scraper inherits this. Subclasses implement resolve()."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable scraper name, e.g. 'maigret'."""
        ...

    @abstractmethod
    async def resolve(self, identifier: Identifier) -> list[RawProfile]:
        """Run the scraper and return profiles. Must return empty list on failure — never raise."""
        ...
