from django.contrib import admin
from django.utils.html import format_html

from .models import CategoriaProducto, Cliente, Producto, Venta, VentaItem


@admin.register(CategoriaProducto)
class CategoriaProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "orden", "activa")
    list_editable = ("orden", "activa")
    search_fields = ("nombre",)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "documento", "telefono", "email", "activo", "ver_qr", "creado_en")
    search_fields = ("nombre", "documento", "telefono", "email")
    list_filter = ("activo",)
    readonly_fields = ("qr_token", "ver_qr")
    fields = ("nombre", "documento", "telefono", "email", "notas", "activo", "qr_token", "ver_qr")

    def ver_qr(self, obj):
        if obj and obj.pk:
            return format_html(
                '<a href="/clientes/{}/qr-page/" target="_blank">Ver / imprimir QR</a>',
                obj.pk,
            )
        return "Guarda el cliente primero"

    ver_qr.short_description = "QR"


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "categoria",
        "precio",
        "stock",
        "controlar_stock",
        "activo",
        "mostrar_en_pos",
        "orden_pos",
        "vista_previa",
    )
    list_editable = ("precio", "stock", "controlar_stock", "activo", "mostrar_en_pos", "orden_pos")
    search_fields = ("nombre", "sku", "descripcion")
    list_filter = ("categoria", "activo", "mostrar_en_pos", "controlar_stock")
    readonly_fields = ("vista_previa",)
    fields = (
        "categoria",
        "nombre",
        "sku",
        "descripcion",
        "precio",
        "stock",
        "controlar_stock",
        "activo",
        "mostrar_en_pos",
        "orden_pos",
        "color_pos",
        "imagen",
        "vista_previa",
    )

    def vista_previa(self, obj):
        if obj and obj.imagen:
            return format_html(
                '<img src="{}" style="height:70px; width:70px; object-fit:cover; border-radius:8px;" />',
                obj.imagen.url,
            )
        return "Sin imagen"

    vista_previa.short_description = "Vista previa"


class VentaItemInline(admin.TabularInline):
    model = VentaItem
    extra = 1


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "estado", "metodo_pago", "total", "creada_en")
    list_filter = ("estado", "metodo_pago", "creada_en")
    inlines = [VentaItemInline]