from __future__ import annotations

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from tests.factories.gallery_factory import GalleryFactory
from tests.support._app import get_model


from MiniatureMuseum.models import Exhibit

class ExhibitFactory(DjangoModelFactory):
    class Meta:
        model = Exhibit

    gallery = factory.SubFactory(GalleryFactory)
    owner = factory.LazyAttribute(lambda obj: obj.gallery.owner or None)
    guest_id = factory.LazyAttribute(lambda obj: obj.gallery.guest_id)
    user_style = factory.LazyAttribute(lambda obj: obj.gallery.user_style)
    slot_index = factory.Sequence(lambda n: n % 12)
    title = factory.Sequence(lambda n: f"Exhibit {n}")
    description = "desc"
    image_original_url = "https://example.com/image.png"
    image_background_url = "https://example.com/bg.png"
    image_foreground_url = "https://example.com/fg.png"
    material_params = factory.LazyFunction(dict)
    style_config = factory.LazyFunction(dict)
    deleted_at = None

    class Params:
        soft_deleted = factory.Trait(deleted_at=factory.LazyFunction(timezone.now))
