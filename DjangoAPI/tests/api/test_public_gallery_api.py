from __future__ import annotations

import pytest
from django.utils import timezone

from tests.factories import ExhibitFactory, GalleryFactory

pytestmark = pytest.mark.django_db


def test_public_gallery_returns_only_public_active(api_client):
    gallery = GalleryFactory(is_public=True)

    response = api_client.get(f"/api/galleries/g/{gallery.slug}/")
    assert response.status_code == 200


def test_public_gallery_returns_404_for_private(api_client):
    gallery = GalleryFactory(is_public=False)

    response = api_client.get(f"/api/galleries/g/{gallery.slug}/")
    assert response.status_code == 404


def test_public_gallery_excludes_deleted_exhibits(api_client):
    gallery = GalleryFactory(is_public=True)
    active = ExhibitFactory(gallery=gallery, slot_index=0)
    ExhibitFactory(gallery=gallery, slot_index=1, deleted_at=timezone.now())

    response = api_client.get(f"/api/galleries/g/{gallery.slug}/")

    assert response.status_code == 200
    exhibits = response.data.get("exhibits", [])
    ids = {str(item["id"]) for item in exhibits}
    assert str(active.id) in ids
    assert all(item.get("slotIndex") != 1 and item.get("slot_index") != 1 for item in exhibits)


def test_public_gallery_does_not_leak_owner_or_guest(api_client):
    gallery = GalleryFactory(is_public=True, as_guest=True)

    response = api_client.get(f"/api/galleries/g/{gallery.slug}/")

    assert response.status_code == 200
    assert "owner" not in response.data
    assert "guestId" not in response.data
    assert "guest_id" not in response.data


def test_public_gallery_returns_404_when_gallery_soft_deleted(api_client):
    gallery = GalleryFactory(is_public=True, deleted_at=timezone.now())

    response = api_client.get(f"/api/galleries/g/{gallery.slug}/")
    assert response.status_code == 404
