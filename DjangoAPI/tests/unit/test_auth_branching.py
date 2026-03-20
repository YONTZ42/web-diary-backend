from __future__ import annotations

import pytest
from rest_framework.test import APIRequestFactory

from tests.factories import GalleryFactory, UserFactory
from tests.support._app import VIEWS_MODULE, import_attr


@pytest.fixture
def rf():
    return APIRequestFactory()


def _set_user(request, user):
    request.user = user
    return request


def test_view_prefers_authenticated_user_over_guest_header(rf, mocker):
    """
    Adjust `resolve_gallery_owner` to the helper your views actually use.
    This catches the core branch from the v5 spec: authenticated user wins,
    otherwise X-Guest-Id is used.
    """
    helper = import_attr(VIEWS_MODULE, "resolve_gallery_owner")
    user = UserFactory()
    request = _set_user(rf.get("/api/galleries/", HTTP_X_GUEST_ID="guest-123"), user)

    resolved = helper(request)

    assert resolved["owner"] == user
    assert resolved["guest_id"] is None


def test_view_uses_guest_header_for_anonymous_request(rf):
    helper = import_attr(VIEWS_MODULE, "resolve_gallery_owner")
    request = _set_user(rf.get("/api/guest/gallery/", HTTP_X_GUEST_ID="guest-123"), type("Anon", (), {"is_authenticated": False})())

    resolved = helper(request)

    assert resolved["owner"] is None
    assert resolved["guest_id"] == "guest-123"


def test_guest_gallery_lookup_rejects_other_guest_id(rf):
    permission_helper = import_attr(VIEWS_MODULE, "assert_guest_gallery_access")
    gallery = GalleryFactory(as_guest=True, guest_id="guest-a")
    request = _set_user(rf.get("/api/guest/gallery/", HTTP_X_GUEST_ID="guest-b"), type("Anon", (), {"is_authenticated": False})())

    with pytest.raises(Exception):
        permission_helper(request, gallery)
