from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import Casillero, Venta


@require_http_methods(["GET", "POST"])
def seleccionar_casillero_cliente(request):
    if request.method == "POST":
        casillero_id = request.POST.get("casillero_id")
        nombre_cliente_libre = (request.POST.get("nombre_cliente_libre") or "").strip()

        if not casillero_id:
            messages.error(request, "Debes seleccionar un casillero.")
            return redirect("cliente_seleccionar_casillero")

        casillero = get_object_or_404(Casillero, pk=casillero_id, activo=True)

        if not casillero.disponible:
            messages.error(request, f"El casillero {casillero.numero} ya no está disponible.")
            return redirect("cliente_seleccionar_casillero")

        venta = Venta(
            casillero=casillero,
            nombre_cliente_libre=nombre_cliente_libre,
            estado=Venta.Estado.ABIERTA,
            metodo_pago=Venta.MetodoPago.EFECTIVO,
        )

        try:
            venta.save()
        except ValidationError as e:
            messages.error(request, "No fue posible asignar el casillero.")
            if hasattr(e, "messages") and e.messages:
                messages.error(request, " ".join(e.messages))
            return redirect("cliente_seleccionar_casillero")

        return redirect("cliente_resumen_casillero", venta_id=venta.id)

    casilleros = Casillero.objects.filter(activo=True).order_by("numero")

    return render(
        request,
        "cliente/seleccionar_casillero.html",
        {
            "casilleros": casilleros,
        },
    )


def resumen_casillero_cliente(request, venta_id):
    venta = get_object_or_404(Venta, pk=venta_id)

    return render(
        request,
        "cliente/resumen_casillero.html",
        {
            "venta": venta,
            "casillero": venta.casillero,
        },
    )