from django.contrib import admin
from .models import Cliente, Producto, Venta, VentaItem

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "documento", "telefono", "email", "activo", "creado_en")
    search_fields = ("nombre", "documento", "telefono", "email")
    list_filter = ("activo",)

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