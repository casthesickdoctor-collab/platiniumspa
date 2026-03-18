from decimal import Decimal
import uuid

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class CategoriaProducto(models.Model):
    nombre = models.CharField(max_length=100)
    orden = models.PositiveIntegerField(default=0)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"

    def __str__(self):
        return self.nombre


class Cliente(models.Model):
    nombre = models.CharField(max_length=150)
    documento = models.CharField(max_length=50, blank=True)
    telefono = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    notas = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    qr_token = models.CharField(
        max_length=36,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.qr_token:
            self.qr_token = str(uuid.uuid4())
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class Casillero(models.Model):
    numero = models.PositiveIntegerField(unique=True)
    activo = models.BooleanField(default=True)
    qr_token = models.CharField(
        max_length=36,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )
    cliente_actual = models.OneToOneField(
        Cliente,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="casillero_actual",
    )
    nombre_ocupante = models.CharField(max_length=150, blank=True)
    asignado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["numero"]
        verbose_name = "Casillero"
        verbose_name_plural = "Casilleros"

    def __str__(self):
        return f"Casillero {self.numero}"

    @property
    def disponible(self):
        if not self.activo:
            return False
        if self.cliente_actual:
            return False
        if self.nombre_ocupante:
            return False
        if self.ventas.filter(estado="ABIERTA").exists():
            return False
        return True

    @property
    def ocupante_mostrado(self):
        if self.cliente_actual:
            return self.cliente_actual.nombre
        if self.nombre_ocupante:
            return self.nombre_ocupante
        return "Sin asignar"

    def clean(self):
        if (self.cliente_actual or self.nombre_ocupante) and not self.activo:
            raise ValidationError("No puedes asignar un ocupante a un casillero inactivo.")

    def save(self, *args, **kwargs):
        if not self.qr_token:
            self.qr_token = str(uuid.uuid4())

        if self.cliente_actual or self.nombre_ocupante:
            if self.asignado_en is None:
                self.asignado_en = timezone.now()
        else:
            self.asignado_en = None

        self.full_clean()
        super().save(*args, **kwargs)

    def ocupar(self, cliente=None, nombre_ocupante=""):
        self.cliente_actual = cliente
        self.nombre_ocupante = (nombre_ocupante or "").strip()
        self.asignado_en = timezone.now()
        self.save()

    def liberar(self):
        self.cliente_actual = None
        self.nombre_ocupante = ""
        self.asignado_en = None
        self.save(update_fields=["cliente_actual", "nombre_ocupante", "asignado_en"])


class Producto(models.Model):
    categoria = models.ForeignKey(
        CategoriaProducto,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="productos",
    )
    nombre = models.CharField(max_length=150)
    sku = models.CharField(max_length=60, blank=True)
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    stock = models.IntegerField(default=0)
    controlar_stock = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    mostrar_en_pos = models.BooleanField(default=True)
    orden_pos = models.PositiveIntegerField(default=0)
    color_pos = models.CharField(max_length=20, blank=True, default="#0a8f08")
    imagen = models.ImageField(upload_to="productos/", blank=True, null=True)

    class Meta:
        ordering = ["orden_pos", "nombre"]

    def __str__(self):
        return self.nombre


class Venta(models.Model):
    class Estado(models.TextChoices):
        ABIERTA = "ABIERTA", "Abierta"
        PAGADA = "PAGADA", "Pagada"
        ANULADA = "ANULADA", "Anulada"

    class MetodoPago(models.TextChoices):
        EFECTIVO = "EFECTIVO", "Efectivo"
        TARJETA = "TARJETA", "Tarjeta"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferencia"
        MIXTO = "MIXTO", "Mixto"

    casillero = models.ForeignKey(
        Casillero,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ventas",
    )
    cliente = models.ForeignKey(
        Cliente,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ventas",
    )
    nombre_cliente_libre = models.CharField(max_length=150, blank=True)
    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.ABIERTA,
    )
    metodo_pago = models.CharField(
        max_length=15,
        choices=MetodoPago.choices,
        default=MetodoPago.EFECTIVO,
    )
    descuento_porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    descuento_manual = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    creada_en = models.DateTimeField(auto_now_add=True)
    notas = models.TextField(blank=True)

    class Meta:
        ordering = ["-creada_en"]

    def __str__(self):
        if self.casillero:
            return f"Venta #{self.id} - Casillero {self.casillero.numero}"
        return f"Venta #{self.id}"

    @property
    def cliente_mostrado(self):
        if self.cliente:
            return self.cliente.nombre
        if self.nombre_cliente_libre:
            return self.nombre_cliente_libre
        return "Sin nombre"

    @property
    def subtotal_cobrable(self):
        return sum((item.subtotal for item in self.items.all()), Decimal("0.00"))

    @property
    def valor_descuento_porcentaje(self):
        subtotal = self.subtotal_cobrable
        porcentaje = self.descuento_porcentaje or Decimal("0.00")
        return (subtotal * porcentaje) / Decimal("100.00")

    def clean(self):
        if self.descuento_manual < 0:
            raise ValidationError("El descuento manual no puede ser negativo.")

        if self.descuento_porcentaje < 0 or self.descuento_porcentaje > 100:
            raise ValidationError("El descuento por porcentaje debe estar entre 0 y 100.")

        if self.casillero and not self.casillero.activo:
            raise ValidationError("No puedes usar un casillero inactivo en una venta.")

        if self.casillero and self.estado == self.Estado.ABIERTA:
            qs = Venta.objects.filter(
                casillero=self.casillero,
                estado=self.Estado.ABIERTA,
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)

            if qs.exists():
                raise ValidationError(
                    f"El casillero {self.casillero.numero} ya tiene una cuenta abierta."
                )

    def recalcular_total(self):
        subtotal_items = self.subtotal_cobrable
        descuento_pct = self.valor_descuento_porcentaje
        descuento_manual = self.descuento_manual or Decimal("0.00")

        total_final = subtotal_items - descuento_pct - descuento_manual
        if total_final < Decimal("0.00"):
            total_final = Decimal("0.00")

        self.total = total_final
        self.save(update_fields=["total"])

    def sincronizar_ocupante_con_casillero(self):
        if not self.casillero or self.estado != self.Estado.ABIERTA:
            return

        nombre_libre = (self.nombre_cliente_libre or "").strip()
        self.casillero.ocupar(cliente=self.cliente, nombre_ocupante=nombre_libre)

    def liberar_casillero_si_corresponde(self):
        if not self.casillero:
            return

        hay_abiertas = self.casillero.ventas.filter(estado=self.Estado.ABIERTA).exists()
        if not hay_abiertas:
            self.casillero.liberar()

    def save(self, *args, **kwargs):
        estado_anterior = None
        casillero_anterior = None

        if self.pk:
            try:
                anterior = Venta.objects.get(pk=self.pk)
                estado_anterior = anterior.estado
                casillero_anterior = anterior.casillero
            except Venta.DoesNotExist:
                estado_anterior = None
                casillero_anterior = None

        self.full_clean()
        super().save(*args, **kwargs)

        if self.estado == self.Estado.ABIERTA:
            self.sincronizar_ocupante_con_casillero()

        if (
            casillero_anterior
            and self.casillero
            and casillero_anterior.pk != self.casillero.pk
            and estado_anterior == self.Estado.ABIERTA
        ):
            if not casillero_anterior.ventas.filter(estado=self.Estado.ABIERTA).exists():
                casillero_anterior.liberar()

        estados_de_cierre = [self.Estado.PAGADA, self.Estado.ANULADA]
        if self.estado in estados_de_cierre and estado_anterior != self.estado:
            self.liberar_casillero_si_corresponde()


class VentaItem(models.Model):
    venta = models.ForeignKey(
        Venta,
        related_name="items",
        on_delete=models.CASCADE,
    )
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    descuento_porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    es_cortesia = models.BooleanField(default=False)

    @property
    def subtotal_bruto(self):
        return (self.precio_unitario or Decimal("0.00")) * self.cantidad

    @property
    def valor_descuento(self):
        if self.es_cortesia:
            return Decimal("0.00")
        return (self.subtotal_bruto * (self.descuento_porcentaje or Decimal("0.00"))) / Decimal("100.00")

    @property
    def subtotal(self):
        if self.es_cortesia:
            return Decimal("0.00")
        subtotal_final = self.subtotal_bruto - self.valor_descuento
        if subtotal_final < Decimal("0.00"):
            return Decimal("0.00")
        return subtotal_final

    def clean(self):
        if self.descuento_porcentaje < 0 or self.descuento_porcentaje > 100:
            raise ValidationError("El descuento del ítem debe estar entre 0 y 100.")

    def ajustar_stock(self, producto, cantidad_delta):
        if not producto or not producto.controlar_stock:
            return

        nuevo_stock = (producto.stock or 0) - cantidad_delta
        if nuevo_stock < 0:
            raise ValidationError(
                f"No hay stock suficiente para {producto.nombre}. Stock actual: {producto.stock}"
            )

        producto.stock = nuevo_stock
        producto.save(update_fields=["stock"])

    @transaction.atomic
    def save(self, *args, **kwargs):
        producto_anterior = None
        cantidad_anterior = 0

        if self.pk:
            try:
                anterior = VentaItem.objects.get(pk=self.pk)
                producto_anterior = anterior.producto
                cantidad_anterior = anterior.cantidad
            except VentaItem.DoesNotExist:
                producto_anterior = None
                cantidad_anterior = 0

        if self.precio_unitario in (None, Decimal("0.00")):
            self.precio_unitario = self.producto.precio

        self.full_clean()

        if producto_anterior and producto_anterior.pk != self.producto.pk:
            self.ajustar_stock(producto_anterior, -cantidad_anterior)
            self.ajustar_stock(self.producto, self.cantidad)
        else:
            diferencia = self.cantidad - cantidad_anterior
            self.ajustar_stock(self.producto, diferencia)

        super().save(*args, **kwargs)
        self.venta.recalcular_total()

    @transaction.atomic
    def delete(self, *args, **kwargs):
        venta = self.venta
        producto = self.producto
        cantidad = self.cantidad

        self.ajustar_stock(producto, -cantidad)
        super().delete(*args, **kwargs)
        venta.recalcular_total()


class ConfiguracionSitio(models.Model):
    nombre_negocio = models.CharField(max_length=120, default="Mi Negocio")
    logo = models.ImageField(upload_to="configuracion/", blank=True, null=True)
    color_primario = models.CharField(max_length=7, default="#0d6efd")
    color_secundario = models.CharField(max_length=7, default="#6c757d")
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración del sitio"
        verbose_name_plural = "Configuración del sitio"

    def __str__(self):
        return self.nombre_negocio