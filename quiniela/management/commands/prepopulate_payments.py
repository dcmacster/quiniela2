from django.core.management.base import BaseCommand
from django.db.models import Sum
from quiniela.models import PuntosTorneoUsuario, PuntosDiarios, Partido

class Command(BaseCommand):
    help = 'Pre-popula y recalcula el monto_pagado_acumulado para todos los PuntosTorneoUsuario'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Recalculando pagos acumulados por torneo para todos los usuarios...'))
        updated_count = 0
        for ptu in PuntosTorneoUsuario.objects.all():
            fechas_del_torneo = Partido.objects.filter(torneo=ptu.torneo).values_list('fecha_partido__date', flat=True).distinct()
            total_pagado = PuntosDiarios.objects.filter(
                usuario=ptu.usuario,
                fecha__in=fechas_del_torneo
            ).aggregate(total=Sum('monto_pagado'))['total'] or 0.00
            
            ptu.monto_pagado_acumulado = total_pagado
            ptu.save(update_fields=['monto_pagado_acumulado'])
            self.stdout.write(self.style.SUCCESS(
                f"Usuario: {ptu.usuario.username} | Torneo: {ptu.torneo.nombre} | Pagado Acumulado: {total_pagado}"
            ))
            updated_count += 1
        self.stdout.write(self.style.SUCCESS(f"Proceso finalizado. Se actualizaron {updated_count} registros."))
