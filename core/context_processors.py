from .models import ConfiguracionSitio


def configuracion_sitio(request):
    return {
        "config_sitio": ConfiguracionSitio.objects.first()
    }