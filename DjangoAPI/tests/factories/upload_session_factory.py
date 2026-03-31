from __future__ import annotations

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from tests.factories.user_factory import UserFactory
from tests.support._app import get_model


from core.models import UploadSession 

class UploadSessionFactory(DjangoModelFactory):
    class Meta:
        model = UploadSession

    user = factory.SubFactory(UserFactory)
    guest_id = None
    purpose = "exhibit_image"
    s3_key = factory.Sequence(lambda n: f"uploads/test-{n}.png")
    mime = "image/png"
    expires_at = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(hours=1))
    status = "issued"

    class Params:
        as_guest = factory.Trait(
            user=None,
            guest_id=factory.Sequence(lambda n: f"guest-{n}"),
        )
