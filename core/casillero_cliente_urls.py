from django.urls import path

from .casillero_cliente_views import (
    resumen_casillero_cliente,
    seleccionar_casillero_cliente,
)

urlpatterns = [
    path(
        "cliente/casilleros/",
        seleccionar_casillero_cliente,
        name="cliente_seleccionar_casillero",
    ),
    path(
        "cliente/casilleros/<int:venta_id>/resumen/",
        resumen_casillero_cliente,
        name="cliente_resumen_casillero",
    ),
]