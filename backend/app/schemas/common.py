from __future__ import annotations

import re
from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


_PHONE_RE = re.compile(r"^\+?\d{7,15}$")


def normalize_phone(value: str) -> str:
    """Strip spaces/dashes/brackets and validate. Raises ValueError if it is not a phone number."""
    cleaned = re.sub(r"[\s\-().]", "", value)
    if not _PHONE_RE.fullmatch(cleaned):
        raise ValueError("Phone must contain 7-15 digits, optionally starting with +")
    return cleaned


PhoneNumber = Annotated[str, AfterValidator(normalize_phone)]
