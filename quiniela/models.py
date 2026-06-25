from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

class Partido(models.Model):
    equipo_local = models.CharField(max_length=100)
    equipo_visitante = models.CharField(max_length=100)
    fecha_partido = models.DateTimeField()
    goles_local_real = models.IntegerField(null=True, blank=True)
    goles_visitante_real = models.IntegerField(null=True, blank=True)
    finalizado = models.BooleanField(default=False)
    es_partido_especial = models.BooleanField(default=False)
    codigo_bandera_local = models.CharField(max_length=10, blank=True, null=True, verbose_name="Código Bandera Local")
    codigo_bandera_visitante = models.CharField(max_length=10, blank=True, null=True, verbose_name="Código Bandera Visitante")

    class Meta:
        verbose_name = "Partido"
        verbose_name_plural = "Partidos"
        ordering = ['fecha_partido']

    def __str__(self):
        return f"{self.equipo_local} vs {self.equipo_visitante} ({self.fecha_partido.strftime('%Y-%m-%d %H:%M')})"

    def calcular_y_repartir_puntos(self):
        """
        Checks rules:
        - Exact match score = 4 pts.
        - Match winner/draw match but wrong score = 1 pt.
        - Otherwise = 0 pts.
        Saves the calculated points to each Pronostico associated with this match.
        """
        if not self.finalizado or self.goles_local_real is None or self.goles_visitante_real is None:
            return

        gl_r = self.goles_local_real
        gv_r = self.goles_visitante_real

        # Determine actual outcome: 1 for local win, 2 for visitor win, 0 for draw
        if gl_r > gv_r:
            resultado_real = 1
        elif gl_r < gv_r:
            resultado_real = 2
        else:
            resultado_real = 0

        pronosticos = self.pronosticos.all()
        for pronostico in pronosticos:
            gl_p = pronostico.goles_local_pronostico
            gv_p = pronostico.goles_visitante_pronostico

            # Determine forecast outcome: 1 for local win, 2 for visitor win, 0 for draw
            if gl_p > gv_p:
                resultado_pronostico = 1
            elif gl_p < gv_p:
                resultado_pronostico = 2
            else:
                resultado_pronostico = 0

            # Calculate points
            if gl_r == gl_p and gv_r == gv_p:
                puntos = 4
            elif resultado_real == resultado_pronostico:
                puntos = 1
            else:
                puntos = 0

            pronostico.puntos_ganados = puntos
            # Save without triggering full_clean again since it's already created/validated
            super(Pronostico, pronostico).save(update_fields=['puntos_ganados'])

    def actualizar_tabla_posiciones_global(self):
        """
        Sums historical scores to PerfilQuiniela and calculates specific daily score sums
        to PuntosDiarios filtered by fecha_partido__date.
        """
        fecha_partido_date = timezone.localdate(self.fecha_partido)
        usuarios = User.objects.all()

        for usuario in usuarios:
            # 1. Update PerfilQuiniela points and special scores count
            perfil, _ = PerfilQuiniela.objects.get_or_create(usuario=usuario)
            
            # Sum total points from all forecasts of finalized matches
            total_puntos = Pronostico.objects.filter(
                usuario=usuario,
                partido__finalizado=True
            ).aggregate(total=Sum('puntos_ganados'))['total'] or 0

            # Count of special matches with exact score (puntos_ganados == 4 and partido__es_partido_especial == True)
            marcadores_especiales = Pronostico.objects.filter(
                usuario=usuario,
                partido__finalizado=True,
                partido__es_partido_especial=True,
                puntos_ganados=4
            ).count()

            perfil.puntos_totales = total_puntos
            perfil.marcadores_especiales_atinados = marcadores_especiales
            perfil.save()

            # 2. Update PuntosDiarios for this match date
            # Sum points from all forecasts of finalized matches scheduled on this date
            puntos_dia = Pronostico.objects.filter(
                usuario=usuario,
                partido__finalizado=True,
                partido__fecha_partido__date=fecha_partido_date
            ).aggregate(total=Sum('puntos_ganados'))['total'] or 0

            # Count of special matches with exact score for this day
            marcadores_especiales_dia = Pronostico.objects.filter(
                usuario=usuario,
                partido__finalizado=True,
                partido__fecha_partido__date=fecha_partido_date,
                partido__es_partido_especial=True,
                puntos_ganados=4
            ).count()

            puntos_diarios_obj, _ = PuntosDiarios.objects.get_or_create(
                usuario=usuario,
                fecha=fecha_partido_date
            )
            puntos_diarios_obj.puntos = puntos_dia
            puntos_diarios_obj.marcadores_especiales = marcadores_especiales_dia
            puntos_diarios_obj.save()

    def save(self, *args, **kwargs):
        # Save first to establish/update score
        super().save(*args, **kwargs)
        if self.finalizado:
            self.calcular_y_repartir_puntos()
            self.actualizar_tabla_posiciones_global()


class Pronostico(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pronosticos')
    partido = models.ForeignKey(Partido, on_delete=models.CASCADE, related_name='pronosticos')
    goles_local_pronostico = models.IntegerField()
    goles_visitante_pronostico = models.IntegerField()
    puntos_ganados = models.IntegerField(default=0)

    class Meta:
        unique_together = ('usuario', 'partido')
        verbose_name = "Pronóstico"
        verbose_name_plural = "Pronósticos"

    def __str__(self):
        return f"{self.usuario.username} - {self.partido.equipo_local} vs {self.partido.equipo_visitante} ({self.goles_local_pronostico}-{self.goles_visitante_pronostico})"

    def clean(self):
        super().clean()
        if (self.partido and 
            self.goles_local_pronostico is not None and 
            self.goles_visitante_pronostico is not None):
            
            # Query existing forecasts for the same partido with identical scores
            # Reject if found from a different user to prevent duplicate scores per match.
            dup_query = Pronostico.objects.filter(
                partido=self.partido,
                goles_local_pronostico=self.goles_local_pronostico,
                goles_visitante_pronostico=self.goles_visitante_pronostico
            )
            if self.usuario:
                dup_query = dup_query.exclude(usuario=self.usuario)
            
            if dup_query.exists():
                raise ValidationError(
                    f"El marcador {self.goles_local_pronostico} - {self.goles_visitante_pronostico} "
                    "ya ha sido pronosticado por otro usuario para este partido. "
                    "Debes elegir un marcador diferente."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class PerfilQuiniela(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfilquiniela')
    puntos_totales = models.IntegerField(default=0)
    marcadores_especiales_atinados = models.IntegerField(default=0)

    class Meta:
        verbose_name = "Perfil de Quiniela"
        verbose_name_plural = "Perfiles de Quiniela"

    def __str__(self):
        return f"Perfil de {self.usuario.username} - Puntos: {self.puntos_totales}"

    def tiene_premio_especial(self):
        return self.marcadores_especiales_atinados >= 2


class PuntosDiarios(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='puntos_diarios')
    fecha = models.DateField()
    puntos = models.IntegerField(default=0)
    pago_confirmado = models.BooleanField(default=False)
    marcadores_especiales = models.IntegerField(default=0)

    class Meta:
        unique_together = ('usuario', 'fecha')
        verbose_name = "Puntos Diarios"
        verbose_name_plural = "Puntos Diarios"
        ordering = ['-fecha', '-puntos']

    def __str__(self):
        return f"{self.usuario.username} - {self.fecha}: {self.puntos} pts (Pago: {self.pago_confirmado})"


# Signals to auto-create and save PerfilQuiniela when a User is created/updated
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        PerfilQuiniela.objects.get_or_create(usuario=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # Ensure profile exists
    try:
        instance.perfilquiniela.save()
    except PerfilQuiniela.DoesNotExist:
        PerfilQuiniela.objects.create(usuario=instance)
