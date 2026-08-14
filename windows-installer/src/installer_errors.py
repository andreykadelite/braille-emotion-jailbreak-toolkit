from __future__ import annotations

from typing import Iterable, Optional


class InstallerError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        technical: str = "",
        remedies: Optional[Iterable[str]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.technical = technical.strip()
        self.remedies = tuple(remedies or ())

    def full_text(self) -> str:
        parts = [self.message]
        if self.remedies:
            parts.append("Что сделать:\n" + "\n".join(f"• {item}" for item in self.remedies))
        if self.technical:
            parts.append("Технические сведения:\n" + self.technical)
        return "\n\n".join(parts)
