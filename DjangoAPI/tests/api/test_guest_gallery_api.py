from __future__ import annotations

import pytest
from django.utils import timezone

from tests.factories import GalleryFactory

pytestmark = pytest.mark.django_db


ENDPOINT = "/api/guest/gallery/"


def test_guest_gallery_requires_header(api_client):
    response = api_client.get(ENDPOINT)
    assert response.status_code in {400, 401}


def test_guest_gallery_post_creates_on_first_call(api_client, guest_headers):
    response = api_client.post(ENDPOINT, data={"title": "Guest Gallery"}, format="json", **guest_headers)

    assert response.status_code == 201
    assert response.data["title"] == "Guest Gallery"


def test_guest_gallery_post_returns_existing_on_second_call(api_client, guest_headers, guest_id):
    GalleryFactory(as_guest=True, guest_id=guest_id, title="Existing")

    response = api_client.post(ENDPOINT, data={"title": "Ignored"}, format="json", **guest_headers)

    assert response.status_code == 200
    assert response.data["title"] == "Existing"


def test_guest_gallery_get_returns_only_active_gallery(api_client, guest_headers, guest_id):
    GalleryFactory(as_guest=True, guest_id=guest_id, title="Active")
    GalleryFactory(as_guest=True, guest_id=guest_id, title="Deleted", deleted_at=timezone.now())

    response = api_client.get(ENDPOINT, **guest_headers)

    assert response.status_code == 200
    assert response.data["title"] == "Active"


def test_guest_gallery_patch_updates_allowed_fields_only(api_client, guest_headers, guest_id):
    gallery = GalleryFactory(as_guest=True, guest_id=guest_id, title="Before")

    response = api_client.patch(
        ENDPOINT,
        data={"title": "After", "guestId": "evil", "owner": "evil"},
        format="json",
        **guest_headers,
    )
    gallery.refresh_from_db()

    assert response.status_code == 200
    assert gallery.title == "After"
    assert gallery.guest_id == guest_id
    assert gallery.owner is None


def test_guest_gallery_delete_soft_deletes(api_client, guest_headers, guest_id):
    gallery = GalleryFactory(as_guest=True, guest_id=guest_id)

    response = api_client.delete(ENDPOINT, **guest_headers)
    gallery.refresh_from_db()

    assert response.status_code == 204
    assert gallery.deleted_at is not None


def test_guest_gallery_get_returns_404_after_delete(api_client, guest_headers, guest_id):
    GalleryFactory(as_guest=True, guest_id=guest_id, deleted_at=timezone.now())

    response = api_client.get(ENDPOINT, **guest_headers)
    assert response.status_code == 404


def test_guest_gallery_can_recreate_after_soft_delete(api_client, guest_headers, guest_id):
    GalleryFactory(as_guest=True, guest_id=guest_id, deleted_at=timezone.now())

    response = api_client.post(ENDPOINT, data={"title": "Recreated"}, format="json", **guest_headers)

    assert response.status_code == 201
    assert response.data["title"] == "Recreated"
