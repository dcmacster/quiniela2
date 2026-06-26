from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q
from datetime import datetime

from .models import Partido, Pronostico, PerfilQuiniela, PuntosDiarios, ConfiguracionQuiniela

def dashboard(request):
    now = timezone.now()
    # Active matches are matches that haven't started yet (or are not finalized)
    partidos_activos = Partido.objects.filter(finalizado=False).order_by('fecha_partido')
    # Past matches are matches that are finalized
    partidos_pasados = Partido.objects.filter(finalizado=True).order_by('-fecha_partido')

    # If the user is logged in, attach their prediction to each match for display
    if request.user.is_authenticated:
        for partido in partidos_activos:
            partido.mi_pronostico = Pronostico.objects.filter(usuario=request.user, partido=partido).first()
        for partido in partidos_pasados:
            partido.mi_pronostico = Pronostico.objects.filter(usuario=request.user, partido=partido).first()

    context = {
        'partidos_activos': partidos_activos,
        'partidos_pasados': partidos_pasados,
        'now': now,
    }
    return render(request, 'quiniela/dashboard.html', context)


@login_required
def apostar_partido(request, partido_id):
    partido = get_object_or_404(Partido, id=partido_id)
    now = timezone.now()

    # Check if match has already started/finalized
    if partido.fecha_partido < now or partido.finalizado:
        messages.error(request, "Este partido ya ha comenzado o finalizado. No puedes modificar tu pronóstico.")
        return redirect('dashboard')

    # Get the user's existing prediction, if any
    pronostico = Pronostico.objects.filter(usuario=request.user, partido=partido).first()

    config = ConfiguracionQuiniela.obtener_config()
    bloquear_marcadores_repetidos = config.bloquear_marcadores_repetidos

    # Get list of occupied scores (exclude current user)
    # Formatted as a dictionary or set for checking, and list of formatted strings for display
    ocupados_qs = Pronostico.objects.filter(partido=partido).exclude(usuario=request.user)
    marcadores_ocupados = []
    if bloquear_marcadores_repetidos:
        for o in ocupados_qs:
            marcadores_ocupados.append(f"{o.goles_local_pronostico} - {o.goles_visitante_pronostico}")

    if request.method == 'POST':
        goles_local = request.POST.get('goles_local_pronostico')
        goles_visitante = request.POST.get('goles_visitante_pronostico')

        if goles_local is None or goles_visitante is None or goles_local == '' or goles_visitante == '':
            messages.error(request, "Debes ingresar ambos marcadores.")
        else:
            try:
                goles_local = int(goles_local)
                goles_visitante = int(goles_visitante)

                if not pronostico:
                    pronostico = Pronostico(usuario=request.user, partido=partido)
                
                pronostico.goles_local_pronostico = goles_local
                pronostico.goles_visitante_pronostico = goles_visitante
                
                # full_clean() is called in the model's save method, which will trigger duplicate score validation
                pronostico.save()
                messages.success(request, "¡Pronóstico guardado exitosamente!")
                return redirect('dashboard')
            except ValueError:
                messages.error(request, "Los goles deben ser números enteros.")
            except ValidationError as e:
                # Capture the message string directly
                err_msg = e.messages[0] if hasattr(e, 'messages') else str(e)
                messages.error(request, err_msg)

    context = {
        'partido': partido,
        'pronostico': pronostico,
        'marcadores_ocupados': marcadores_ocupados,
        'bloquear_marcadores_repetidos': bloquear_marcadores_repetidos,
    }
    return render(request, 'quiniela/apostar.html', context)


def tabla_posiciones(request):
    tipo = request.GET.get('tipo', 'general')
    fecha_str = request.GET.get('fecha', '')

    # Fetch all dates that have matches scheduled to populate the date selector dropdown
    fechas_disponibles = Partido.objects.values_list('fecha_partido__date', flat=True).distinct().order_by('-fecha_partido__date')
    
    posiciones = []
    fecha_seleccionada = None
    partidos_con_pronosticos = []
    now = timezone.now()

    if tipo == 'diaria':
        if fecha_str:
            try:
                fecha_seleccionada = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        # If date is invalid or not provided, default to today's date if available.
        # Otherwise, fall back to the most recent past/today date with matches, or the first upcoming date.
        if not fecha_seleccionada:
            hoy = timezone.localdate()
            fechas_pasadas_o_hoy = [f for f in fechas_disponibles if f <= hoy]
            if fechas_pasadas_o_hoy:
                fecha_seleccionada = fechas_pasadas_o_hoy[0]
            elif fechas_disponibles:
                fecha_seleccionada = fechas_disponibles[-1]
            else:
                fecha_seleccionada = hoy
        
        # Query PuntosDiarios for that date, ordered by points descending
        posiciones = PuntosDiarios.objects.filter(fecha=fecha_seleccionada).order_by('-puntos', 'usuario__username')

        # Fetch matches and build match prediction mapping
        partidos_del_dia = Partido.objects.filter(fecha_partido__date=fecha_seleccionada).order_by('fecha_partido')
        usuarios_con_puntos = [p.usuario for p in posiciones]
        usuarios_con_puntos_ids = [u.id for u in usuarios_con_puntos]
        from django.contrib.auth.models import User
        otros_usuarios = User.objects.exclude(id__in=usuarios_con_puntos_ids).order_by('username')
        usuarios_ordenados = list(usuarios_con_puntos) + list(otros_usuarios)

        for partido in partidos_del_dia:
            # map of user_id -> pronostico object
            pronosticos_map = {p.usuario_id: p for p in partido.pronosticos.all()}
            pronosticos_lista = []
            for u in usuarios_ordenados:
                pronosticos_lista.append({
                    'usuario': u,
                    'pronostico': pronosticos_map.get(u.id)
                })
            partidos_con_pronosticos.append({
                'partido': partido,
                'pronosticos': pronosticos_lista
            })
    else:
        # Query PerfilQuiniela ordered by points descending
        posiciones = PerfilQuiniela.objects.all().order_by('-puntos_totales', '-marcadores_especiales_atinados', 'usuario__username')

    context = {
        'tipo': tipo,
        'posiciones': posiciones,
        'fechas_disponibles': fechas_disponibles,
        'fecha_seleccionada': fecha_seleccionada,
        'fecha_seleccionada_str': fecha_seleccionada.strftime('%Y-%m-%d') if fecha_seleccionada else '',
        'partidos_con_pronosticos': partidos_con_pronosticos,
        'now': now,
    }
    return render(request, 'quiniela/posiciones.html', context)
