from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q
from datetime import datetime

from .models import Partido, Pronostico, PerfilQuiniela, PuntosDiarios

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

    # Get list of occupied scores (exclude current user)
    # Formatted as a dictionary or set for checking, and list of formatted strings for display
    ocupados_qs = Pronostico.objects.filter(partido=partido).exclude(usuario=request.user)
    marcadores_ocupados = []
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
    }
    return render(request, 'quiniela/apostar.html', context)


def tabla_posiciones(request):
    tipo = request.GET.get('tipo', 'general')
    fecha_str = request.GET.get('fecha', '')

    # Fetch all dates that have matches scheduled to populate the date selector dropdown
    fechas_disponibles = Partido.objects.values_list('fecha_partido__date', flat=True).distinct().order_by('-fecha_partido__date')
    
    posiciones = []
    fecha_seleccionada = None

    if tipo == 'diaria':
        if fecha_str:
            try:
                fecha_seleccionada = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        # If date is invalid or not provided, default to the latest date that has matches, or today
        if not fecha_seleccionada:
            if fechas_disponibles:
                fecha_seleccionada = fechas_disponibles[0]
            else:
                fecha_seleccionada = timezone.now().date()
        
        # Query PuntosDiarios for that date, ordered by points descending
        posiciones = PuntosDiarios.objects.filter(fecha=fecha_seleccionada).order_by('-puntos', 'usuario__username')
    else:
        # Query PerfilQuiniela ordered by points descending
        posiciones = PerfilQuiniela.objects.all().order_by('-puntos_totales', '-marcadores_especiales_atinados', 'usuario__username')

    context = {
        'tipo': tipo,
        'posiciones': posiciones,
        'fechas_disponibles': fechas_disponibles,
        'fecha_seleccionada': fecha_seleccionada,
        'fecha_seleccionada_str': fecha_seleccionada.strftime('%Y-%m-%d') if fecha_seleccionada else '',
    }
    return render(request, 'quiniela/posiciones.html', context)
