from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    GalleryViewSet,
    ExhibitViewSet,
    GalleryPublicView,
    GalleryExhibitCreateView,
    GalleryExhibitSlotUpsertView,
    GuestGalleryView,
)

router = DefaultRouter()
router.register(r'galleries', GalleryViewSet, basename='gallery')
router.register(r'exhibits', ExhibitViewSet, basename='exhibit')

urlpatterns = [
    # Public Viewer (by slug)
    path('galleries/g/<slug:slug>/', GalleryPublicView.as_view(), name='gallery-public-viewer'),

    # Guest: single gallery entrypoint
    path('guest/gallery/', GuestGalleryView.as_view(), name='guest-gallery'),
    
    # Nested Exhibits (recommended)
    path('galleries/<uuid:gallery_id>/exhibits/', GalleryExhibitCreateView.as_view(), name='gallery-exhibit-create'),
    path('galleries/<uuid:gallery_id>/exhibits/<int:slot_index>/', GalleryExhibitSlotUpsertView.as_view(), name='gallery-exhibit-slot-upsert'),

    path('', include(router.urls)),
]
