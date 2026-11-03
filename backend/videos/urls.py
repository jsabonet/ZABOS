from django.urls import path

from .views import (
    MediaAssetListCreateView,
    MediaAssetFileView,
    VideoGenerationDetailView,
    VideoGenerationFileView,
    VideoGenerationListCreateView,
    VideoGenerationRenderView,
)

urlpatterns = [
    path("", VideoGenerationListCreateView.as_view(), name="video-generation-list"),
    path("assets/", MediaAssetListCreateView.as_view(), name="media-asset-list-create"),
    path(
        "assets/<uuid:asset_id>/file/",
        MediaAssetFileView.as_view(),
        name="media-asset-file",
    ),
    path(
        "<uuid:generation_id>/render/",
        VideoGenerationRenderView.as_view(),
        name="video-generation-render",
    ),
    path("<uuid:generation_id>/", VideoGenerationDetailView.as_view(), name="video-generation-detail"),
    path(
        "<uuid:generation_id>/file/",
        VideoGenerationFileView.as_view(),
        name="video-generation-file",
    ),
]
