from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Game:
    id: int
    name: str
    year: Optional[int]
    description: str
    publishers: list[str] = field(default_factory=list)

    @property
    def publisher(self) -> str:
        return ", ".join(self.publishers) if self.publishers else "Unknown"

    def display(self, desc_limit: int = 300) -> str:
        desc = self.description.strip()
        if len(desc) > desc_limit:
            desc = desc[:desc_limit].rstrip() + "..."
        return (
            f"Title:       {self.name}\n"
            f"Publisher:   {self.publisher}\n"
            f"Year:        {self.year}\n"
            f"Description: {desc}"
        )
