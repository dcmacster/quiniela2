from django.contrib import admin
from .models import Partido, Pronostico, PerfilQuiniela, PuntosDiarios

@admin.action(description="Recalcular puntos y tabla de posiciones")
def recalcular_puntos(modeladmin, request, queryset):
    for partido in queryset:
        if partido.finalizado:
            partido.calcular_y_repartir_puntos()
            partido.actualizar_tabla_posiciones_global()
    modeladmin.message_user(request, "Se han recalculado los puntos para los partidos seleccionados.")

@admin.register(Partido)
class PartidoAdmin(admin.ModelAdmin):
    list_display = (
        'equipo_local', 
        'equipo_visitante', 
        'fecha_partido', 
        'goles_local_real', 
        'goles_visitante_real', 
        'finalizado', 
        'es_partido_especial',
        'codigo_bandera_local',
        'codigo_bandera_visitante'
    )
    list_filter = ('finalizado', 'es_partido_especial', 'fecha_partido')
    search_fields = ('equipo_local', 'equipo_visitante')
    actions = [recalcular_puntos]
    ordering = ('fecha_partido',)


@admin.register(Pronostico)
class PronosticoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'partido', 'goles_local_pronostico', 'goles_visitante_pronostico', 'puntos_ganados')
    list_filter = ('partido', 'usuario')
    search_fields = ('usuario__username', 'partido__equipo_local', 'partido__equipo_visitante')


@admin.register(PerfilQuiniela)
class PerfilQuinielaAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'puntos_totales', 'marcadores_especiales_atinados', 'tiene_premio_especial_badge')
    search_fields = ('usuario__username',)
    ordering = ('-puntos_totales',)

    @admin.display(boolean=True, description="Premio Especial")
    def tiene_premio_especial_badge(self, obj):
        return obj.tiene_premio_especial()


@admin.action(description="Confirmar pago para los registros seleccionados")
def confirmar_pago(modeladmin, request, queryset):
    queryset.update(pago_confirmado=True)
    modeladmin.message_user(request, "Pagos confirmados para los registros seleccionados.")

@admin.action(description="Cancelar pago para los registros seleccionados")
def cancelar_pago(modeladmin, request, queryset):
    queryset.update(pago_confirmado=False)
    modeladmin.message_user(request, "Pagos cancelados para los registros seleccionados.")

@admin.register(PuntosDiarios)
class PuntosDiariosAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'fecha', 'puntos', 'pago_confirmado')
    list_filter = ('fecha', 'pago_confirmado')
    search_fields = ('usuario__username',)
    actions = [confirmar_pago, cancelar_pago]
    ordering = ('-fecha', '-puntos')
