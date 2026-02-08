from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MeView, ScheduleViewSet, UploadView, StickerViewSet, PageViewSet, NotebookViewSet

router = DefaultRouter()
router.register(r'stickers', StickerViewSet, basename='sticker')
router.register(r'pages', PageViewSet, basename='page')
router.register(r'notebooks', NotebookViewSet, basename='notebook')
router.register(r'schedules', ScheduleViewSet, basename='schedule')

urlpatterns = [
    path('me/', MeView.as_view(), name='me'),
    
    # Upload (Actionベース)
    #path('uploads/issue/', UploadView.as_view(), {'post': 'issue_upload'}, name='upload-issue'), # ※View側の実装微修正が必要
    # あるいは単純に View 内で分岐させるなら path('uploads/<str:action>/', ...)
    path('uploads/<str:action>/', UploadView.as_view(), name='upload'),

    path('', include(router.urls)),
]