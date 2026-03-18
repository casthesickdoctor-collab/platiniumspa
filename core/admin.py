from io import BytesIO

import qrcode
from django import forms
from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html

from .models import (
    Casillero,
    CategoriaProducto,
    Cliente,
    Producto,
    Venta,
    VentaItem,
    ConfiguracionSitio,
)

admin.site.site_header = "Administración del sistema"
admin.site.site_title = "Panel administrativo"
admin.site.index_title = "Gestión del negocio"
admin.site.site_url = "/pos/"


class ClienteAdminForm(forms.ModelForm):
    casillero_editor = forms.ModelChoiceField(
        queryset=Casillero.objects.none(),
        required=False,
        label="Asignar casillero",
        help_text="Selecciona un casillero libre para este cliente.",
    )

    class Meta:
        model = Cliente
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        disponibles = Casillero.objects.filter(activo=True, cliente_actual__isnull=True)
        actual = Casillero.objects.none()

        if self.instance and self.instance.pk:
            actual = Casillero.objects.filter(cliente_actual=self.instance)

        self.fields["casillero_editor"].queryset = (disponibles | actual).distinct().order_by("numero")

        if self.instance and self.instance.pk:
            try:
                self.fields["casillero_editor"].initial = self.instance.casillero_actual
            except Casillero.DoesNotExist:
                pass

    def clean_casillero_editor(self):
        casillero = self.cleaned_data.get("casillero_editor")

        if casillero and casillero.cliente_actual and casillero.cliente_actual != self.instance:
            raise forms.ValidationError("Ese casillero ya está asignado a otro cliente.")

        return casillero


@admin.register(CategoriaProducto)
class CategoriaProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "orden", "activa")
    list_editable = ("orden", "activa")
    search_fields = ("nombre",)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    form = ClienteAdminForm

    list_display = (
        "nombre",
        "documento",
        "telefono",
        "email",
        "casillero_asignado",
        "activo",
        "ver_qr",
        "creado_en",
    )
    search_fields = ("nombre", "documento", "telefono", "email")
    list_filter = ("activo",)
    readonly_fields = ("qr_token", "ver_qr", "casillero_asignado")
    fields = (
        "nombre",
        "documento",
        "telefono",
        "email",
        "notas",
        "activo",
        "casillero_editor",
        "casillero_asignado",
        "qr_token",
        "ver_qr",
    )

    def ver_qr(self, obj):
        if obj and obj.pk:
            return format_html(
                '<a href="/clientes/{}/qr-page/" target="_blank">Ver / imprimir QR</a>',
                obj.pk,
            )
        return "Guarda el cliente primero"

    ver_qr.short_description = "QR"

    def casillero_asignado(self, obj):
        try:
            return f"Casillero {obj.casillero_actual.numero}"
        except Casillero.DoesNotExist:
            return "Sin casillero"

    casillero_asignado.short_description = "Casillero actual"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        casillero_seleccionado = form.cleaned_data.get("casillero_editor")
        casilleros_actuales = Casillero.objects.filter(cliente_actual=obj)

        if casillero_seleccionado:
            for casillero in casilleros_actuales.exclude(pk=casillero_seleccionado.pk):
                casillero.liberar()

            casillero_seleccionado.ocupar(cliente=obj, nombre_ocupante="")
        else:
            for casillero in casilleros_actuales:
                casillero.liberar()


@admin.register(Casillero)
class CasilleroAdmin(admin.ModelAdmin):
    list_display = (
        "numero",
        "estado_ocupacion",
        "ocupante_actual",
        "activo",
        "asignado_en",
        "ver_qr",
    )
    list_filter = ("activo",)
    search_fields = ("=numero", "cliente_actual__nombre", "nombre_ocupante")
    readonly_fields = (
        "qr_token",
        "ver_qr",
        "asignado_en",
        "creado_en",
    )
    fields = (
        "numero",
        "activo",
        "cliente_actual",
        "nombre_ocupante",
        "qr_token",
        "ver_qr",
        "asignado_en",
        "creado_en",
    )
    actions = ["liberar_casilleros"]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:casillero_id>/qr-page/",
                self.admin_site.admin_view(self.qr_page_view),
                name="core_casillero_qr_page",
            ),
            path(
                "<int:casillero_id>/qr-image/",
                self.admin_site.admin_view(self.qr_image_view),
                name="core_casillero_qr_image",
            ),
        ]
        return custom_urls + urls

    def estado_ocupacion(self, obj):
        return "Disponible" if obj.disponible else "Ocupado"

    estado_ocupacion.short_description = "Estado"

    def ocupante_actual(self, obj):
        return obj.ocupante_mostrado

    ocupante_actual.short_description = "Ocupante"

    def ver_qr(self, obj):
        if obj and obj.pk:
            url = reverse("admin:core_casillero_qr_page", args=[obj.pk])
            return format_html(
                '<a href="{}" target="_blank">Ver / imprimir QR</a>',
                url,
            )
        return "Guarda el casillero primero"

    ver_qr.short_description = "QR"

    def liberar_casilleros(self, request, queryset):
        for casillero in queryset:
            casillero.liberar()

    liberar_casilleros.short_description = "Liberar casilleros seleccionados"

    def qr_page_view(self, request, casillero_id):
        casillero = get_object_or_404(Casillero, pk=casillero_id)
        config_sitio = ConfiguracionSitio.objects.first()

        context = {
            **self.admin_site.each_context(request),
            "casillero": casillero,
            "config_sitio": config_sitio,
        }
        return render(request, "admin/casillero_qr_page.html", context)

    def qr_image_view(self, request, casillero_id):
        casillero = get_object_or_404(Casillero, pk=casillero_id)

        contenido_qr = f"CASILLERO:{casillero.numero}|TOKEN:{casillero.qr_token}"

        qr = qrcode.QRCode(
            version=1,
            box_size=10,
            border=4,
        )
        qr.add_data(contenido_qr)
        qr.make(fit=True)

        imagen = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        imagen.save(buffer, format="PNG")
        buffer.seek(0)

        return HttpResponse(buffer.getvalue(), content_type="image/png")


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
    list_editable = (
        "precio",
        "stock",
        "controlar_stock",
        "activo",
        "mostrar_en_pos",
        "orden_pos",
    )
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
    fields = (
        "producto",
        "cantidad",
        "precio_unitario",
        "descuento_porcentaje",
        "es_cortesia",
    )
    autocomplete_fields = ("producto",)


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "casillero",
        "cliente_o_referencia",
        "estado",
        "metodo_pago",
        "descuento_porcentaje",
        "descuento_manual",
        "total",
        "ver_ticket",
        "creada_en",
    )
    list_filter = ("estado", "metodo_pago", "creada_en", "casillero")
    search_fields = ("=id", "casillero__numero", "cliente__nombre", "nombre_cliente_libre")
    readonly_fields = ("total",)
    fields = (
        "casillero",
        "cliente",
        "nombre_cliente_libre",
        "estado",
        "metodo_pago",
        "descuento_porcentaje",
        "descuento_manual",
        "total",
        "notas",
    )
    inlines = [VentaItemInline]
    autocomplete_fields = ("casillero", "cliente")

    def cliente_o_referencia(self, obj):
        return obj.cliente_mostrado

    cliente_o_referencia.short_description = "Cliente / referencia"

    def ver_ticket(self, obj):
        return format_html(
            '<a href="/ventas/{}/ticket/" target="_blank">Ver / imprimir</a>',
            obj.id,
        )

    ver_ticket.short_description = "Ticket"


@admin.register(ConfiguracionSitio)
class ConfiguracionSitioAdmin(admin.ModelAdmin):
    list_display = (
        "nombre_negocio",
        "color_primario",
        "color_secundario",
        "vista_previa_logo",
        "actualizado_en",
    )
    readonly_fields = ("vista_previa_logo", "actualizado_en")
    fields = (
        "nombre_negocio",
        "logo",
        "vista_previa_logo",
        "color_primario",
        "color_secundario",
        "actualizado_en",
    )

    def vista_previa_logo(self, obj):
        if obj and obj.logo:
            return format_html(
                '<img src="{}" style="height:70px; max-width:220px; object-fit:contain;" />',
                obj.logo.url,
            )
        return "Sin logo"

    vista_previa_logo.short_description = "Vista previa del logo"

    def has_module_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        if not request.user.is_superuser:
            return False
        return not ConfiguracionSitio.objects.exists()

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False