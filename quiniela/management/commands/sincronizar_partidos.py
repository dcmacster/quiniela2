import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, datetime
from quiniela.models import Partido

class Command(BaseCommand):
    help = "Sincroniza los partidos de fútbol para el día de hoy"

    def handle(self, *args, **options):
        self.stdout.write("Buscando partidos para hoy...")
        hoy_str = timezone.now().strftime("%Y-%m-%d")
        
        # Intentamos obtener partidos de una API pública y gratuita (TheSportsDB con API Key de prueba '3')
        url = f"https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={hoy_str}&s=Soccer"
        
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            events = data.get("events") or []
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"No se pudo conectar a la API: {e}. Usando generador local de partidos..."))
            events = []

        partidos_creados = 0

        if events:
            for event in events:
                local = event.get("strHomeTeam")
                visitante = event.get("strAwayTeam")
                # Parsear fecha y hora del evento
                date_str = event.get("dateEvent")
                time_str = event.get("strTime")
                
                try:
                    fecha_partido = timezone.make_aware(datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S"))
                except:
                    fecha_partido = timezone.now() + timedelta(hours=2)

                # Intentar mapear códigos de bandera de países comunes si el nombre coincide
                codigo_l = None
                codigo_v = None
                mapeo_banderas = {
                    "Spain": "es", "Portugal": "pt", "England": "gb-eng", "Italy": "it",
                    "Uruguay": "uy", "Colombia": "co", "Mexico": "mx", "Germany": "de",
                    "Argentina": "ar", "France": "fr", "Brazil": "br", "USA": "us"
                }
                for pais, codigo in mapeo_banderas.items():
                    if pais.lower() in local.lower():
                        codigo_l = codigo
                    if pais.lower() in visitante.lower():
                        codigo_v = codigo

                partido, created = Partido.objects.get_or_create(
                    equipo_local=local,
                    equipo_visitante=visitante,
                    defaults={
                        'fecha_partido': fecha_partido,
                        'es_partido_especial': False,
                        'codigo_bandera_local': codigo_l,
                        'codigo_bandera_visitante': codigo_v
                    }
                )
                if created:
                    partidos_creados += 1
        
        # Si la API no tiene partidos de fútbol hoy o falla, creamos partidos del mundial
        # interesantes simulados para hoy para permitir pruebas de juego
        if partidos_creados == 0:
            self.stdout.write("No se encontraron partidos en la API para hoy. Generando cartelera del día del Mundial...")
            
            partidos_hoy = [
                {"local": "España", "visitante": "Portugal", "especial": True, "codigo_l": "es", "codigo_v": "pt", "horas_offset": 2},
                {"local": "Inglaterra", "visitante": "Italia", "especial": False, "codigo_l": "gb-eng", "codigo_v": "it", "horas_offset": 4},
                {"local": "Uruguay", "visitante": "Colombia", "especial": False, "codigo_l": "uy", "codigo_v": "co", "horas_offset": 6},
                {"local": "Alemania", "visitante": "Japón", "especial": False, "codigo_l": "de", "codigo_v": "jp", "horas_offset": 8},
                {"local": "Brasil", "visitante": "Croacia", "especial": True, "codigo_l": "br", "codigo_v": "hr", "horas_offset": 10},
                {"local": "Argentina", "visitante": "Países Bajos", "especial": False, "codigo_l": "ar", "codigo_v": "nl", "horas_offset": 12},
                {"local": "México", "visitante": "Estados Unidos", "especial": True, "codigo_l": "mx", "codigo_v": "us", "horas_offset": 14},
                {"local": "Francia", "visitante": "Marruecos", "especial": False, "codigo_l": "fr", "codigo_v": "ma", "horas_offset": 16},
            ]
            
            for p in partidos_hoy:
                fecha = timezone.now() + timedelta(hours=p["horas_offset"])
                partido, created = Partido.objects.get_or_create(
                    equipo_local=p["local"],
                    equipo_visitante=p["visitante"],
                    defaults={
                        'fecha_partido': fecha,
                        'es_partido_especial': p["especial"],
                        'codigo_bandera_local': p["codigo_l"],
                        'codigo_bandera_visitante': p["codigo_v"]
                    }
                )
                if created:
                    partidos_creados += 1

        self.stdout.write(self.style.SUCCESS(f"Sincronización completada. Se añadieron {partidos_creados} partidos nuevos para hoy."))
