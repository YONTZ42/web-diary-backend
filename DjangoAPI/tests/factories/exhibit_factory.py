from __future__ import annotations

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from tests.factories.gallery_factory import GalleryFactory
from tests.factories.user_factory import UserFactory
from tests.support._app import get_model


Exhibit = get_model("Exhibit")


class ExhibitFactory(DjangoModelFactory):
    class Meta:
        model = Exhibit

    gallery = factory.SubFactory(GalleryFactory)
    owner = factory.LazyAttribute(lambda obj: obj.gallery.owner or UserFactory())
    guest_id = factory.LazyAttribute(lambda obj: obj.gallery.guest_id)
    slot_index = factory.Sequence(lambda n: n % 12)
    title = factory.Sequence(lambda n: f"Exhibit {n}")
    description = "desc"
    image_original_url = "https://example.com/image.png"
    deleted_at = None

    class Params:
        soft_deleted = factory.Trait(deleted_at=factory.LazyFunction(timezone.now))
