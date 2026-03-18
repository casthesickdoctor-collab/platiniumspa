from decimal import Decimal, InvalidOperation
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

from .models import Casillero, Cliente, Producto, Venta, VentaItem


def normalizar_qr(valor):
    valor = (valor or "").strip()
    if not valor:
        return ""

    if "/scan/" in valor:
        valor = valor.split("/scan/")[-1]

    return valor.strip().strip("/")


def extraer_token_casillero(valor):
    valor = (valor or "").strip()

    if valor.startswith("CASILLERO:") and "|TOKEN:" in valor:
        return valor.split("|TOKEN:", 1)[1].strip()

    return ""


def resolver_qr(valor):
    valor_original = (valor or "").strip()
    valor_normalizado = normalizar_qr(valor_original)

    token_casillero = extraer_token_casillero(valor_original)
    if token_casillero:
        casillero = Casillero.objects.filter(qr_token=token_casillero).first()
        if casillero:
            return "casillero", casillero

    cliente = Cliente.objects.filter(qr_token=valor_normalizado).first()
    if cliente:
        return "cliente", cliente

    casillero = Casillero.objects.filter(qr_token=valor_normalizado).first()
    if casillero:
        return "casillero", casillero

    return None, None


def build_public_url(request, path):
    base_url = getattr(settings, "PUBLIC_BASE_URL", "").strip().rstrip("/")
    if base_url:
        return f"{base_url}{path}"
    return request.build_absolute_uri(path)


def asegurar_qr_token(cliente):
    if not cliente.qr_token:
        cliente.save()
    return cliente


def parse_decimal_safe(valor, default="0.00"):
    try:
        texto = str(valor).replace(",", ".").strip()
        if not texto:
            return Decimal(default)
        return Decimal(texto)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def get_cart(request):
    cart = request.session.get("pos_cart", {})
    if not isinstance(cart, dict):
        return {}
    return cart


def save_cart(request, cart):
    request.session["pos_cart"] = cart
    request.session.modified = True


def clear_cart(request):
    if "pos_cart" in request.session:
        del request.session["pos_cart"]

    request.session["pos_descuento_porcentaje"] = "0.00"
    request.session["pos_descuento_manual"] = "0.00"
    request.session.modified = True


def get_sale_discount_porcentaje(request):
    return parse_decimal_safe(request.session.get("pos_descuento_porcentaje", "0.00"))


def get_sale_discount_manual(request):
    return parse_decimal_safe(request.session.get("pos_descuento_manual", "0.00"))


def set_sale_discounts(request, descuento_porcentaje, descuento_manual):
    request.session["pos_descuento_porcentaje"] = str(descuento_porcentaje)
    request.session["pos_descuento_manual"] = str(descuento_manual)
    request.session.modified = True


def normalize_cart(cart):
    cart_normalizado = {}

    for product_id, value in (cart or {}).items():
        cantidad = 0
        descuento_porcentaje = Decimal("0.00")
        es_cortesia = False

        if isinstance(value, int):
            cantidad = value
        elif isinstance(value, str):
            try:
                cantidad = int(value)
            except ValueError:
                cantidad = 0
        elif isinstance(value, dict):
            try:
                cantidad = int(value.get("cantidad", 0))
            except (TypeError, ValueError):
                cantidad = 0

            descuento_porcentaje = parse_decimal_safe(
                value.get("descuento_porcentaje", "0.00")
            )
            es_cortesia = bool(value.get("es_cortesia", False))

        if cantidad < 1:
            continue

        if descuento_porcentaje < 0:
            descuento_porcentaje = Decimal("0.00")
        if descuento_porcentaje > 100:
            descuento_porcentaje = Decimal("100.00")

        cart_normalizado[str(product_id)] = {
            "cantidad": cantidad,
            "descuento_porcentaje": str(descuento_porcentaje),
            "es_cortesia": es_cortesia,
        }

    return cart_normalizado


def build_cart_items(cart):
    items = []
    subtotal_cobrable = Decimal("0.00")

    cart = normalize_cart(cart)

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

    for product_id, entry in cart.items():
        try:
            producto = products.get(int(product_id))
        except ValueError:
            producto = None

        if not producto:
            continue

        cantidad = int(entry.get("cantidad", 1))
        descuento_porcentaje = parse_decimal_safe(entry.get("descuento_porcentaje", "0.00"))
        es_cortesia = bool(entry.get("es_cortesia", False))

        subtotal_bruto = (producto.precio or Decimal("0.00")) * cantidad

        if es_cortesia:
            valor_descuento_item = Decimal("0.00")
            subtotal = Decimal("0.00")
        else:
            valor_descuento_item = (subtotal_bruto * descuento_porcentaje) / Decimal("100.00")
            subtotal = subtotal_bruto - valor_descuento_item
            if subtotal < Decimal("0.00"):
                subtotal = Decimal("0.00")

        subtotal_cobrable += subtotal

        items.append(
            {
                "producto": producto,
                "cantidad": cantidad,
                "descuento_porcentaje": descuento_porcentaje,
                "es_cortesia": es_cortesia,
                "subtotal_bruto": subtotal_bruto,
                "valor_descuento_item": valor_descuento_item,
                "subtotal": subtotal,
            }
        )

    items.sort(key=lambda x: (x["producto"].orden_pos, x["producto"].nombre.lower()))
    return items, subtotal_cobrable


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

    if "casillero" in request.GET:
        casillero_id = request.GET.get("casillero")
        if casillero_id:
            request.session["pos_casillero_id"] = casillero_id
        else:
            request.session.pop("pos_casillero_id", None)
        request.session.modified = True

    if "sin_casillero" in request.GET:
        request.session.pop("pos_casillero_id", None)
        request.session.modified = True

    cliente = None
    cliente_id = request.session.get("pos_cliente_id")
    if cliente_id:
        cliente = Cliente.objects.filter(id=cliente_id).first()

    casillero = None
    casillero_id = request.session.get("pos_casillero_id")
    if casillero_id:
        casillero = Casillero.objects.filter(id=casillero_id).first()

    cart = normalize_cart(get_cart(request))
    save_cart(request, cart)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_product":
            producto_id = request.POST.get("producto_id")
            if producto_id:
                entry = cart.get(
                    str(producto_id),
                    {
                        "cantidad": 0,
                        "descuento_porcentaje": "0.00",
                        "es_cortesia": False,
                    },
                )
                entry["cantidad"] = int(entry.get("cantidad", 0)) + 1
                cart[str(producto_id)] = entry
                save_cart(request, cart)
            return redirect("pos")

        if action == "update_item":
            producto_id = request.POST.get("producto_id")
            if producto_id and str(producto_id) in cart:
                cantidad = request.POST.get("cantidad", "1")
                descuento_porcentaje = request.POST.get("descuento_porcentaje", "0.00")
                es_cortesia = request.POST.get("es_cortesia") == "on"

                try:
                    cantidad = int(cantidad)
                except ValueError:
                    cantidad = 1

                if cantidad < 1:
                    cantidad = 1

                descuento_porcentaje = parse_decimal_safe(descuento_porcentaje, "0.00")
                if descuento_porcentaje < 0:
                    descuento_porcentaje = Decimal("0.00")
                if descuento_porcentaje > 100:
                    descuento_porcentaje = Decimal("100.00")

                cart[str(producto_id)] = {
                    "cantidad": cantidad,
                    "descuento_porcentaje": str(descuento_porcentaje),
                    "es_cortesia": es_cortesia,
                }
                save_cart(request, cart)

            return redirect("pos")

        if action == "remove_item":
            producto_id = request.POST.get("producto_id")
            if producto_id and str(producto_id) in cart:
                del cart[str(producto_id)]
                save_cart(request, cart)
            return redirect("pos")

        if action == "apply_sale_discounts":
            descuento_porcentaje = parse_decimal_safe(
                request.POST.get("descuento_porcentaje_venta", "0.00"),
                "0.00",
            )
            descuento_manual = parse_decimal_safe(
                request.POST.get("descuento_manual_venta", "0.00"),
                "0.00",
            )

            if descuento_porcentaje < 0:
                descuento_porcentaje = Decimal("0.00")
            if descuento_porcentaje > 100:
                descuento_porcentaje = Decimal("100.00")
            if descuento_manual < 0:
                descuento_manual = Decimal("0.00")

            set_sale_discounts(request, descuento_porcentaje, descuento_manual)
            messages.success(request, "Descuentos de la venta actualizados.")
            return redirect("pos")

        if action == "clear_cart":
            clear_cart(request)
            messages.info(request, "Carrito limpiado.")
            return redirect("pos")

        if action == "confirm_sale":
            cart_items, subtotal_cobrable = build_cart_items(cart)

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
            descuento_porcentaje_venta = get_sale_discount_porcentaje(request)
            descuento_manual_venta = get_sale_discount_manual(request)

            venta = Venta.objects.create(
                casillero=casillero,
                cliente=cliente,
                estado=Venta.Estado.PAGADA,
                metodo_pago=metodo_pago,
                descuento_porcentaje=descuento_porcentaje_venta,
                descuento_manual=descuento_manual_venta,
            )

            for item in cart_items:
                producto = item["producto"]

                VentaItem.objects.create(
                    venta=venta,
                    producto=producto,
                    cantidad=item["cantidad"],
                    precio_unitario=producto.precio,
                    descuento_porcentaje=item["descuento_porcentaje"],
                    es_cortesia=item["es_cortesia"],
                )

            venta.recalcular_total()

            clear_cart(request)
            messages.success(request, f"Venta #{venta.id} creada correctamente.")
            return redirect(f"/admin/core/venta/{venta.id}/change/")

    productos = (
        Producto.objects.filter(activo=True, mostrar_en_pos=True)
        .select_related("categoria")
        .order_by("categoria__orden", "orden_pos", "nombre")
    )

    cart_items, subtotal_cobrable = build_cart_items(cart)

    descuento_porcentaje_venta = get_sale_discount_porcentaje(request)
    descuento_manual_venta = get_sale_discount_manual(request)
    valor_descuento_porcentaje_venta = (
        subtotal_cobrable * descuento_porcentaje_venta
    ) / Decimal("100.00")

    total_carrito = subtotal_cobrable - valor_descuento_porcentaje_venta - descuento_manual_venta
    if total_carrito < Decimal("0.00"):
        total_carrito = Decimal("0.00")

    return render(
        request,
        "core/pos.html",
        {
            "productos": productos,
            "cliente": cliente,
            "casillero": casillero,
            "cart_items": cart_items,
            "subtotal_cobrable": subtotal_cobrable,
            "descuento_porcentaje_venta": descuento_porcentaje_venta,
            "descuento_manual_venta": descuento_manual_venta,
            "valor_descuento_porcentaje_venta": valor_descuento_porcentaje_venta,
            "total_carrito": total_carrito,
            "metodos_pago": Venta.MetodoPago.choices,
        },
    )


@require_http_methods(["GET", "POST"])
def scan_qr(request):
    error = None

    if request.method == "POST":
        token = request.POST.get("token")
        tipo, entidad = resolver_qr(token)

        if tipo == "cliente" and entidad:
            return redirect(f"/pos/?cliente={entidad.id}")

        if tipo == "casillero" and entidad:
            return redirect(f"/pos/?casillero={entidad.id}")

        error = "No se encontró un cliente o casillero con ese QR."

    return render(request, "core/scan_qr.html", {"error": error})


def scan_qr_token(request, token):
    tipo, entidad = resolver_qr(token)

    if tipo == "cliente" and entidad:
        return redirect(f"/pos/?cliente={entidad.id}")

    if tipo == "casillero" and entidad:
        return redirect(f"/pos/?casillero={entidad.id}")

    messages.error(request, "No se encontró un cliente o casillero con ese QR.")
    return redirect("scan_qr")


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