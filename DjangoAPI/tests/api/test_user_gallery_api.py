from __future__ import annotations

import pytest
from django.utils import timezone

from tests.factories import GalleryFactory

pytestmark = pytest.mark.django_db


LIST_ENDPOINT = "/api/galleries/"


def test_user_gallery_list_returns_only_owned_galleries(user_client, user, other_user):
    mine = GalleryFactory(owner=user)
    GalleryFactory(owner=other_user)

    response = user_client.get(LIST_ENDPOINT)

    assert response.status_code == 200
    ids = {str(item["id"]) for item in response.data if isinstance(response.data, list)}
    assert str(mine.id) in ids


def test_user_gallery_create_succeeds(user_client):
    response = user_client.post(LIST_ENDPOINT, data={"title": "Mine"}, format="json")
    assert response.status_code == 201


def test_user_gallery_detail_blocks_other_user(user_client, other_user):
    gallery = GalleryFactory(owner=other_user)

    response = user_client.get(f"/api/galleries/{gallery.id}/")
    assert response.status_code in {403, 404}


def test_user_gallery_patch_blocks_other_user(user_client, other_user):
    gallery = GalleryFactory(owner=other_user)

    response = user_client.patch(f"/api/galleries/{gallery.id}/", data={"title": "Nope"}, format="json")
    assert response.status_code in {403, 404}


def test_user_gallery_delete_soft_deletes(user_client, user):
    gallery = GalleryFactory(owner=user)

    response = user_client.delete(f"/api/galleries/{gallery.id}/")
    gallery.refresh_from_db()

    assert response.status_code == 204
    assert gallery.deleted_at is not None


def test_user_gallery_list_excludes_soft_deleted(user_client, user):
    active = GalleryFactory(owner=user)
    GalleryFactory(owner=user, deleted_at=timezone.now())

    response = user_client.get(LIST_ENDPOINT)
    assert response.status_code == 200
    body = response.data["results"] if isinstance(response.data, dict) and "results" in response.data else response.data
    ids = {str(item["id"]) for item in body}
    assert str(active.id) in ids
