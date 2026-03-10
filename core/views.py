from decimal import Decimal
from io import BytesIO

import qrcode
from django.conf import settings
from django.contrib import messages
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
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


def get_cart(request):
    return request.session.get("pos_cart", {})


def save_cart(request, cart):
    request.session["pos_cart"] = cart
    request.session.modified = True


def clear_cart(request):
    if "pos_cart" in request.session:
        del request.session["pos_cart"]
        request.session.modified = True


def build_cart_items(cart):
    items = []
    total = Decimal("0.00")

    product_ids = []
    for product_id in cart.keys():
        try:
            product_ids.append(int(product_id))
        except ValueError:
            pass

    products = {
        producto.id: producto
        for producto in Producto.objects.filter(id__in=product_ids)
    }

    for product_id, cantidad in cart.items():
        try:
            producto = products.get(int(product_id))
        except ValueError:
            producto = None

        if not producto:
            continue

        cantidad = int(cantidad)
        subtotal = producto.precio * cantidad
        total += subtotal

        items.append(
            {
                "producto": producto,
                "cantidad": cantidad,
                "subtotal": subtotal,
            }
        )

    items.sort(key=lambda x: (x["producto"].orden_pos, x["producto"].nombre.lower()))
    return items, total


@require_http_methods(["GET", "POST"])
def pos(request):
    if "cliente" in request.GET:
        cliente_id = request.GET.get("cliente")
        if cliente_id:
            request.session["pos_cliente_id"] = cliente_id
        else:
            request.session.pop("pos_cliente_id", None)
        request.session.modified = True

    if "sin_cliente" in request.GET:
        request.session.pop("pos_cliente_id", None)
        request.session.modified = True

    cliente = None
    cliente_id = request.session.get("pos_cliente_id")
    if cliente_id:
        cliente = Cliente.objects.filter(id=cliente_id).first()

    cart = get_cart(request)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_product":
            producto_id = request.POST.get("producto_id")
            if producto_id:
                cart[producto_id] = int(cart.get(producto_id, 0)) + 1
                save_cart(request, cart)
            return redirect("pos")

        if action == "remove_item":
            producto_id = request.POST.get("producto_id")
            if producto_id and producto_id in cart:
                del cart[producto_id]
                save_cart(request, cart)
            return redirect("pos")

        if action == "clear_cart":
            clear_cart(request)
            messages.info(request, "Carrito limpiado.")
            return redirect("pos")

        if action == "confirm_sale":
            cart_items, total_carrito = build_cart_items(cart)

            if not cart_items:
                messages.error(request, "No hay productos en la venta actual.")
                return redirect("pos")

            for item in cart_items:
                producto = item["producto"]
                cantidad = item["cantidad"]
                if producto.controlar_stock and producto.stock < cantidad:
                    messages.error(
                        request,
                        f"Stock insuficiente para {producto.nombre}. Disponible: {producto.stock}.",
                    )
                    return redirect("pos")

            metodo_pago = request.POST.get("metodo_pago", Venta.MetodoPago.EFECTIVO)

            venta = Venta.objects.create(
                cliente=cliente,
                estado=Venta.Estado.PAGADA,
                metodo_pago=metodo_pago,
            )

            for item in cart_items:
                producto = item["producto"]
                cantidad = item["cantidad"]

                VentaItem.objects.create(
                    venta=venta,
                    producto=producto,
                    cantidad=cantidad,
                    precio_unitario=producto.precio,
                )

                if producto.controlar_stock:
                    producto.stock -= cantidad
                    producto.save(update_fields=["stock"])

            clear_cart(request)
            messages.success(request, f"Venta #{venta.id} creada correctamente.")
            return redirect(f"/admin/core/venta/{venta.id}/change/")

    productos = (
        Producto.objects.filter(activo=True, mostrar_en_pos=True)
        .select_related("categoria")
        .order_by("categoria__orden", "orden_pos", "nombre")
    )

    cart_items, total_carrito = build_cart_items(cart)

    return render(
        request,
        "core/pos.html",
        {
            "productos": productos,
            "cliente": cliente,
            "cart_items": cart_items,
            "total_carrito": total_carrito,
            "metodos_pago": Venta.MetodoPago.choices,
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


def reportes_ventas(request):
    hoy = timezone.localdate()

    desde = parse_date(request.GET.get("desde", "")) or hoy
    hasta = parse_date(request.GET.get("hasta", "")) or hoy

    if desde > hasta:
        desde, hasta = hasta, desde

    ventas = Venta.objects.filter(
        estado=Venta.Estado.PAGADA,
        creada_en__date__range=(desde, hasta),
    )

    resumen = ventas.aggregate(
        cantidad=Count("id"),
        total=Sum("total"),
    )

    ventas_por_dia = (
        ventas.annotate(fecha=TruncDate("creada_en"))
        .values("fecha")
        .annotate(cantidad=Count("id"), total=Sum("total"))
        .order_by("fecha")
    )

    ventas_por_pago = (
        ventas.values("metodo_pago")
        .annotate(cantidad=Count("id"), total=Sum("total"))
        .order_by("-total", "metodo_pago")
    )

    total_producto_expr = ExpressionWrapper(
        F("cantidad") * F("precio_unitario"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

    ventas_por_producto = (
        VentaItem.objects.filter(
            venta__estado=Venta.Estado.PAGADA,
            venta__creada_en__date__range=(desde, hasta),
        )
        .values("producto__nombre")
        .annotate(
            unidades=Sum("cantidad"),
            total=Sum(total_producto_expr),
        )
        .order_by("-unidades", "producto__nombre")
    )

    return render(
        request,
        "core/reportes_ventas.html",
        {
            "desde": desde,
            "hasta": hasta,
            "resumen": resumen,
            "ventas_por_dia": ventas_por_dia,
            "ventas_por_pago": ventas_por_pago,
            "ventas_por_producto": ventas_por_producto,
        },
    )