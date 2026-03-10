from django.contrib import admin
from django.http import HttpResponse
from django.urls import path
from django.views.generic import RedirectView

from core import views


def ping(request):
    return HttpResponse("OK")


urlpatterns = [
    path("", RedirectView.as_view(url="/pos/", permanent=False)),
    path("ping/", ping, name="ping"),
    path("admin/", admin.site.urls),
    path("pos/", views.pos, name="pos"),
    path("scan/", views.scan_qr, name="scan_qr"),
    path("scan/<str:token>/", views.scan_qr_token, name="scan_qr_token"),
    path("clientes/<int:cliente_id>/qr/", views.cliente_qr, name="cliente_qr"),
    path("clientes/<int:cliente_id>/qr-page/", views.cliente_qr_page, name="cliente_qr_page"),
]