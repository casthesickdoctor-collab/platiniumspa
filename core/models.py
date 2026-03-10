from decimal import Decimal
import uuid
from django.db import models


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
    qr_token = models.CharField(max_length=36, unique=True, null=True, blank=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.qr_token:
            self.qr_token = str(uuid.uuid4())
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


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
    precio = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
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

    cliente = models.ForeignKey(Cliente, null=True, blank=True, on_delete=models.SET_NULL)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ABIERTA)
    metodo_pago = models.CharField(max_length=15, choices=MetodoPago.choices, default=MetodoPago.EFECTIVO)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    creada_en = models.DateTimeField(auto_now_add=True)
    notas = models.TextField(blank=True)

    def recalcular_total(self):
        total = sum((item.subtotal for item in self.items.all()), Decimal("0.00"))
        self.total = total
        self.save(update_fields=["total"])

    def __str__(self):
        return f"Venta #{self.id} - {self.estado} - {self.total}"


class VentaItem(models.Model):
    venta = models.ForeignKey(Venta, related_name="items", on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    @property
    def subtotal(self):
        return (self.precio_unitario or Decimal("0.00")) * self.cantidad

    def save(self, *args, **kwargs):
        if self.precio_unitario in (None, Decimal("0.00")):
            self.precio_unitario = self.producto.precio
        super().save(*args, **kwargs)
        self.venta.recalcular_total()

    def delete(self, *args, **kwargs):
        venta = self.venta
        super().delete(*args, **kwargs)
        venta.recalcular_total()