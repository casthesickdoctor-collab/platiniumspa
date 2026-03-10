from io import BytesIO

import qrcode
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .models import Cliente, Producto, Venta, VentaItem


def normalizar_qr(valor):
    valor = (valor or "").strip()
    if not valor:
        return ""

    if "/scan/" in valor:
        valor = valor.split("/scan/")[-1]

    return valor.strip().strip("/")


def build_public_url(request, path):
    base_url = getattr(settings, "PUBLIC_BASE_URL", "").strip().rstrip("/")
    if base_url:
        return f"{base_url}{path}"
    return request.build_absolute_uri(path)


def asegurar_qr_token(cliente):
    if not cliente.qr_token:
        cliente.save()
    return cliente


@require_http_methods(["GET", "POST"])
def pos(request):
    productos = Producto.objects.filter(activo=True).order_by("nombre")
    cliente = None

    cliente_id = request.GET.get("cliente")
    if cliente_id:
        cliente = Cliente.objects.filter(id=cliente_id).first()

    if request.method == "POST":
        producto_id = request.POST.get("producto")
        cantidad = int(request.POST.get("cantidad", "1"))
        cliente_id_form = request.POST.get("cliente_id")

        if cliente_id_form:
            cliente = Cliente.objects.filter(id=cliente_id_form).first()
        else:
            cliente = None

        venta = Venta.objects.create(cliente=cliente)
        producto = get_object_or_404(Producto, id=producto_id)
        VentaItem.objects.create(
            venta=venta,
            producto=producto,
            cantidad=cantidad,
        )

        return redirect(f"/admin/core/venta/{venta.id}/change/")

    return render(
        request,
        "core/pos.html",
        {
            "productos": productos,
            "cliente": cliente,
        },
    )


@require_http_methods(["GET", "POST"])
def scan_qr(request):
    error = None

    if request.method == "POST":
        token = normalizar_qr(request.POST.get("token"))
        cliente = Cliente.objects.filter(qr_token=token).first()

        if cliente:
            return redirect(f"/pos/?cliente={cliente.id}")

        error = "No se encontro un cliente con ese QR."

    return render(request, "core/scan_qr.html", {"error": error})


def scan_qr_token(request, token):
    token = normalizar_qr(token)
    cliente = get_object_or_404(Cliente, qr_token=token)
    return redirect(f"/pos/?cliente={cliente.id}")


def cliente_qr(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    asegurar_qr_token(cliente)

    scan_path = reverse("scan_qr_token", args=[cliente.qr_token])
    qr_url = build_public_url(request, scan_path)

    img = qrcode.make(qr_url)
    buffer = BytesIO()
    img.save(buffer, format="PNG")

    return HttpResponse(buffer.getvalue(), content_type="image/png")


def cliente_qr_page(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    asegurar_qr_token(cliente)

    scan_path = reverse("scan_qr_token", args=[cliente.qr_token])
    qr_url = build_public_url(request, scan_path)

    return render(
        request,
        "core/cliente_qr_page.html",
        {
            "cliente": cliente,
            "qr_url": qr_url,
        },
    )