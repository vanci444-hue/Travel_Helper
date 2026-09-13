"""目的地灵感 DTO。"""

from src.models.common import CamelModel


class InspirationPublic(CamelModel):
    id: str
    city: str
    title: str
    description: str
    image_url: str
