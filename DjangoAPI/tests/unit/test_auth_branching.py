from __future__ import annotations

import pytest
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.test import APIRequestFactory

from tests.factories import GalleryFactory, UserFactory
from tests.support._app import VIEWS_CORE_MODULE, VIEWS_UPLOAD_MODULE, import_attr


@pytest.fixture
def rf():
    return APIRequestFactory()


class AnonUser:
    is_authenticated = False


class _DummyMixin(import_attr(VIEWS_CORE_MODULE, "_GalleryActorMixin")):
    pass


def _set_user(request, user):
    request.user = user
    return request


def test_gallery_actor_prefers_authenticated_user_over_guest_header(rf):
    mixin = _DummyMixin()
    user = UserFactory()
    request = _set_user(rf.get("/api/galleries/", HTTP_X_GUEST_ID="guest-123"), user)

    mode, ident = mixin._actor(request)

    assert mode == "user"
    assert ident == user


def test_gallery_actor_uses_guest_header_for_anonymous_request(rf):
    mixin = _DummyMixin()
    request = _set_user(rf.get("/api/guest/gallery/", HTTP_X_GUEST_ID="guest-123"), AnonUser())

    mode, ident = mixin._actor(request)

    assert mode == "guest"
    assert ident == "guest-123"


def test_gallery_owned_lookup_rejects_other_guest_id(rf):
    mixin = _DummyMixin()
    gallery = GalleryFactory(as_guest=True, guest_id="guest-a")
    request = _set_user(rf.get("/api/guest/gallery/", HTTP_X_GUEST_ID="guest-b"), AnonUser())

    with pytest.raises(PermissionDenied):
        mixin._get_owned_gallery_or_404(request, gallery.id)


def test_gallery_owned_lookup_requires_login_for_user_gallery(rf):
    mixin = _DummyMixin()
    gallery = GalleryFactory()
    request = _set_user(rf.get(f"/api/galleries/{gallery.id}/", HTTP_X_GUEST_ID="guest-123"), AnonUser())

    with pytest.raises(NotAuthenticated):
        mixin._get_owned_gallery_or_404(request, gallery.id)


def test_upload_get_uploader_prefers_authenticated_user_over_guest_header(rf):
    upload_view = import_attr(VIEWS_UPLOAD_MODULE, "UploadView")()
    user = UserFactory()
    request = _set_user(rf.post("/api/uploads/issue/", HTTP_X_GUEST_ID="guest-123"), user)

    kind, ident = upload_view._get_uploader(request)

    assert kind == "user"
    assert ident == user
