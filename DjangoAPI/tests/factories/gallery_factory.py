from __future__ import annotations

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from tests.factories.user_factory import UserFactory
from tests.support._app import get_model


Gallery = get_model("Gallery")


class GalleryFactory(DjangoModelFactory):
    class Meta:
        model = Gallery

    title = factory.Sequence(lambda n: f"Gallery {n}")
    slug = factory.Sequence(lambda n: f"gallery-{n}")
    is_public = False
    layout_cols = 3
    layout_rows = 4
    cover_render_url = ""
    deleted_at = None

    user_style = "user"
    owner = factory.SubFactory(UserFactory)
    guest_id = None

    class Params:
        as_guest = factory.Trait(
            user_style="guest",
            owner=None,
            guest_id=factory.Sequence(lambda n: f"guest-{n}"),
        )
        soft_deleted = factory.Trait(deleted_at=factory.LazyFunction(timezone.now))
