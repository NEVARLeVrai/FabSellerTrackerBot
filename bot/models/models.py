from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime

@dataclass
class Product:
    id: str
    name: str
    url: str
    price: Dict[str, str] = field(default_factory=dict)  # {"USD": "$39.99", "EUR": "33.95€"}
    image: Optional[str] = None
    ue_versions: Optional[str] = None
    last_update: Optional[str] = None
    published: Optional[str] = None
    changelog: Optional[str] = None
    description: Optional[str] = None
    reviews_count: int = 0
    rating: Optional[float] = None
    last_seen: Optional[str] = field(default_factory=lambda: datetime.now().isoformat())
    first_seen: Optional[str] = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self):
        return self.__dict__

    @classmethod
    def from_dict(cls, data: dict):
        # Handle cases where price might still be a string (migration)
        price = data.get("price", {})
        if isinstance(price, str):
            price = {"USD": price}
        
        return cls(
            id=data.get("id"),
            name=data.get("name"),
            url=data.get("url"),
            price=price,
            image=data.get("image"),
            ue_versions=data.get("ue_versions"),
            last_update=data.get("last_update"),
            published=data.get("published"),
            changelog=data.get("changelog"),
            description=data.get("description"),
            reviews_count=data.get("reviews_count", 0),
            rating=data.get("rating"),
            last_seen=data.get("last_seen"),
            first_seen=data.get("first_seen")
        )

@dataclass
class GuildConfig:
    guild_id: str
    sellers: List[str] = field(default_factory=list)
    timezone: str = "Europe/Paris"
    language: str = "en"
    currency: str = "USD"
    channel_new: Optional[int] = None
    channel_updated: Optional[int] = None
    mentions_enabled: bool = False
    mentions_new: List[int] = field(default_factory=list)
    mentions_updated: List[int] = field(default_factory=list)
    
    # Schedule
    schedule_day: str = "sunday"
    schedule_hour: int = 0
    schedule_minute: int = 0
