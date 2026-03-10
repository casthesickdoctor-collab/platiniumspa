from django.contrib import admin
from django.utils.html import format_html

from .models import Cliente, Producto, Venta, VentaItem


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
    list_display = ("nombre", "sku", "precio", "stock", "activo")
    search_fields = ("nombre", "sku")
    list_filter = ("activo",)


class VentaItemInline(admin.TabularInline):
    model = VentaItem
    extra = 1


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "estado", "metodo_pago", "total", "creada_en")
    list_filter = ("estado", "metodo_pago", "creada_en")
    inlines = [VentaItemInline]