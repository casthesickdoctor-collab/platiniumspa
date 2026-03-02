from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from .models import Producto, Venta, VentaItem

@require_http_methods(["GET", "POST"])
def pos(request):
    productos = Producto.objects.filter(activo=True).order_by("nombre")

    if request.method == "POST":
        producto_id = request.POST.get("producto")
        cantidad = int(request.POST.get("cantidad", "1"))

        venta = Venta.objects.create()  # venta sin cliente (rápida)
        producto = Producto.objects.get(id=producto_id)
        VentaItem.objects.create(venta=venta, producto=producto, cantidad=cantidad)

        # el total se recalcula solo (por tu models.py)
        return redirect("/admin/core/venta/%d/change/" % venta.id)

    return render(request, "core/pos.html", {"productos": productos})