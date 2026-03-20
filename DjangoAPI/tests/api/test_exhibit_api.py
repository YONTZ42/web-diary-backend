from __future__ import annotations

import pytest

from tests.factories import ExhibitFactory, GalleryFactory

pytestmark = pytest.mark.django_db


def test_exhibit_post_requires_matching_guest_owner(guest_client, other_user):
    gallery = GalleryFactory(as_guest=True, guest_id="another-guest")

    response = guest_client.post(
        f"/api/galleries/{gallery.id}/exhibits/",
        data={"slotIndex": 0, "title": "A", "imageOriginalUrl": "https://example.com/a.png"},
        format="json",
    )

    assert response.status_code in {403, 404}


def test_exhibit_post_rejects_occupied_slot(user_client, user):
    gallery = GalleryFactory(owner=user)
    ExhibitFactory(gallery=gallery, slot_index=0, owner=user)

    response = user_client.post(
        f"/api/galleries/{gallery.id}/exhibits/",
        data={"slotIndex": 0, "title": "A", "imageOriginalUrl": "https://example.com/a.png"},
        format="json",
    )

    assert response.status_code == 409


def test_exhibit_put_creates_when_missing(user_client, user):
    gallery = GalleryFactory(owner=user)

    response = user_client.put(
        f"/api/galleries/{gallery.id}/exhibits/1/",
        data={"title": "A", "imageOriginalUrl": "https://example.com/a.png"},
        format="json",
    )

    assert response.status_code == 201


def test_exhibit_put_updates_when_existing(user_client, user):
    gallery = GalleryFactory(owner=user)
    exhibit = ExhibitFactory(gallery=gallery, slot_index=1, owner=user, title="Before")

    response = user_client.put(
        f"/api/galleries/{gallery.id}/exhibits/1/",
        data={"title": "After", "imageOriginalUrl": exhibit.image_original_url},
        format="json",
    )
    exhibit.refresh_from_db()

    assert response.status_code == 200
    assert exhibit.title == "After"


def test_exhibit_delete_returns_204(user_client, user):
    gallery = GalleryFactory(owner=user)
    ExhibitFactory(gallery=gallery, slot_index=1, owner=user)

    response = user_client.delete(f"/api/galleries/{gallery.id}/exhibits/1/")
    assert response.status_code == 204


def test_exhibit_delete_returns_404_when_already_deleted(user_client, user):
    gallery = GalleryFactory(owner=user)
    ExhibitFactory(gallery=gallery, slot_index=1, owner=user, deleted_at="2026-01-01T00:00:00Z")

    response = user_client.delete(f"/api/galleries/{gallery.id}/exhibits/1/")
    assert response.status_code == 404


def test_exhibit_payload_cannot_override_owner_or_guest(user_client, user, other_user):
    gallery = GalleryFactory(owner=user)

    response = user_client.put(
        f"/api/galleries/{gallery.id}/exhibits/2/",
        data={
            "title": "A",
            "imageOriginalUrl": "https://example.com/a.png",
            "owner": other_user.id,
            "guestId": "evil",
        },
        format="json",
    )

    assert response.status_code in {200, 201}
    assert str(response.data.get("owner") or response.data.get("ownerId")) != str(other_user.id)
