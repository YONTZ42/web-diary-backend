from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from tests.factories.user_factory import UserFactory
from tests.support._app import get_model


UploadSession = get_model("UploadSession")


class UploadSessionFactory(DjangoModelFactory):
    class Meta:
        model = UploadSession

    user = factory.SubFactory(UserFactory)
    guest_id = None
    purpose = "exhibit_image"
    object_key = factory.Sequence(lambda n: f"uploads/test-{n}.png")
    bucket = "test-bucket"
    content_type = "image/png"
    file_name = "image.png"
    file_size = 12345
    confirmed_at = None

    class Params:
        as_guest = factory.Trait(
            user=None,
            guest_id=factory.Sequence(lambda n: f"guest-{n}"),
        )
