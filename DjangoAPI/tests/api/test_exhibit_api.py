from __future__ import annotations

import pytest

from tests.factories import ExhibitFactory, GalleryFactory

pytestmark = pytest.mark.django_db


CREATE_PAYLOAD = {
    "gallery": None,
    "slot_index": 0,
    "title": "A",
    "image_original_url": "https://example.com/a.png",
}


def test_exhibit_post_requires_matching_guest_owner(guest_client):
    gallery = GalleryFactory(as_guest=True, guest_id="another-guest")

    payload = {**CREATE_PAYLOAD, "gallery": str(gallery.id)}
    response = guest_client.post(
        f"/api/galleries/{gallery.id}/exhibits/",
        data=payload,
        format="json",
    )

    assert response.status_code == 403


def test_exhibit_post_rejects_occupied_slot(user_client, user):
    gallery = GalleryFactory(owner=user)
    ExhibitFactory(gallery=gallery, slot_index=0, owner=user)

    payload = {**CREATE_PAYLOAD, "gallery": str(gallery.id)}
    response = user_client.post(
        f"/api/galleries/{gallery.id}/exhibits/",
        data=payload,
        format="json",
    )

    assert response.status_code == 409


def test_exhibit_post_creates_when_slot_is_empty(user_client, user):
    gallery = GalleryFactory(owner=user)

    payload = {**CREATE_PAYLOAD, "gallery": str(gallery.id)}
    response = user_client.post(
        f"/api/galleries/{gallery.id}/exhibits/",
        data=payload,
        format="json",
    )

    assert response.status_code == 201
    assert response.data["slot_index"] == 0
    assert response.data["gallery"] in {str(gallery.id), gallery.id}
    assert response.data["owner"] in {str(user.id), user.id}


def test_exhibit_put_creates_when_missing(user_client, user):
    gallery = GalleryFactory(owner=user)

    response = user_client.put(
        f"/api/galleries/{gallery.id}/exhibits/1/",
        data={"title": "A", "image_original_url": "https://example.com/a.png"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["slot_index"] == 1
    assert response.data["owner"] in {str(user.id), user.id}


def test_exhibit_put_updates_when_existing(user_client, user):
    gallery = GalleryFactory(owner=user)
    exhibit = ExhibitFactory(gallery=gallery, slot_index=1, owner=user, title="Before")

    response = user_client.put(
        f"/api/galleries/{gallery.id}/exhibits/1/",
        data={"title": "After", "image_original_url": exhibit.image_original_url},
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
    ExhibitFactory(gallery=gallery, slot_index=1, owner=user, soft_deleted=True)

    response = user_client.delete(f"/api/galleries/{gallery.id}/exhibits/1/")
    assert response.status_code == 404


def test_exhibit_payload_cannot_override_owner_or_guest(user_client, user, other_user):
    gallery = GalleryFactory(owner=user)

    response = user_client.put(
        f"/api/galleries/{gallery.id}/exhibits/2/",
        data={
            "title": "A",
            "image_original_url": "https://example.com/a.png",
            "owner": other_user.id,
            "guest_id": "evil",
            "user_style": "guest",
        },
        format="json",
    )

    assert response.status_code in {200, 201}
    assert str(response.data.get("owner") or response.data.get("owner_id")) != str(other_user.id)
    assert response.data.get("guest_id") in {None, "", }
    assert response.data.get("user_style") == "user"
