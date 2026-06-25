from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from .models import Partido, Pronostico, PerfilQuiniela, PuntosDiarios, ConfiguracionQuiniela

class QuinielaTestCase(TestCase):
    def setUp(self):
        # Create test users
        self.user_a = User.objects.create_user(username='userA', email='usera@test.com', password='password123')
        self.user_b = User.objects.create_user(username='userB', email='userb@test.com', password='password123')
        self.user_c = User.objects.create_user(username='userC', email='userc@test.com', password='password123')
        
        # Create a test match
        self.fecha_partido = timezone.now() + timedelta(days=1)
        self.partido = Partido.objects.create(
            equipo_local="Real Madrid",
            equipo_visitante="Barcelona",
            fecha_partido=self.fecha_partido,
            es_partido_especial=False
        )

    def test_duplicate_forecast_prevention(self):
        """
        Tests that two different users cannot forecast the exact same score for the same match
        only if bloquear_marcadores_repetidos configuration is active.
        """
        config = ConfiguracionQuiniela.obtener_config()
        
        # Scenario 1: Lock is active (default)
        config.bloquear_marcadores_repetidos = True
        config.save()

        # User A forecasts 2 - 1 (should succeed)
        pronostico_a = Pronostico.objects.create(
            usuario=self.user_a,
            partido=self.partido,
            goles_local_pronostico=2,
            goles_visitante_pronostico=1
        )
        
        # User B attempts to forecast 2 - 1 for the same match (should fail validation)
        pronostico_b_invalid = Pronostico(
            usuario=self.user_b,
            partido=self.partido,
            goles_local_pronostico=2,
            goles_visitante_pronostico=1
        )
        with self.assertRaises(ValidationError):
            pronostico_b_invalid.save()

        # Scenario 2: Lock is deactivated
        config.bloquear_marcadores_repetidos = False
        config.save()

        # User B attempts to forecast 2 - 1 for the same match again (should now succeed)
        pronostico_b_valid = Pronostico.objects.create(
            usuario=self.user_b,
            partido=self.partido,
            goles_local_pronostico=2,
            goles_visitante_pronostico=1
        )
        self.assertIsNotNone(pronostico_b_valid.id)

        # Restore lock default for other tests
        config.bloquear_marcadores_repetidos = True
        config.save()

    def test_scoring_distribution_rules(self):
        """
        Checks rule:
        - Exact match score = 4 pts.
        - Match winner/draw match but wrong score = 1 pt.
        - Otherwise = 0 pts.
        """
        # User A: Exact match (2 - 1)
        Pronostico.objects.create(
            usuario=self.user_a,
            partido=self.partido,
            goles_local_pronostico=2,
            goles_visitante_pronostico=1
        )
        # User B: Correct outcome (local wins), wrong score (3 - 0)
        Pronostico.objects.create(
            usuario=self.user_b,
            partido=self.partido,
            goles_local_pronostico=3,
            goles_visitante_pronostico=0
        )
        # User C: Incorrect outcome (draw/visitor wins) (1 - 2)
        Pronostico.objects.create(
            usuario=self.user_c,
            partido=self.partido,
            goles_local_pronostico=1,
            goles_visitante_pronostico=2
        )

        # Finalize the match with score 2 - 1
        self.partido.goles_local_real = 2
        self.partido.goles_visitante_real = 1
        self.partido.finalizado = True
        self.partido.save()

        # Refresh objects
        perfil_a = PerfilQuiniela.objects.get(usuario=self.user_a)
        perfil_b = PerfilQuiniela.objects.get(usuario=self.user_b)
        perfil_c = PerfilQuiniela.objects.get(usuario=self.user_c)

        # Assert points awarded
        self.assertEqual(perfil_a.puntos_totales, 4)
        self.assertEqual(perfil_b.puntos_totales, 1)
        self.assertEqual(perfil_c.puntos_totales, 0)

        # Verify PuntosDiarios
        puntos_diarios_a = PuntosDiarios.objects.get(usuario=self.user_a, fecha=timezone.localdate(self.fecha_partido))
        puntos_diarios_b = PuntosDiarios.objects.get(usuario=self.user_b, fecha=timezone.localdate(self.fecha_partido))
        puntos_diarios_c = PuntosDiarios.objects.get(usuario=self.user_c, fecha=timezone.localdate(self.fecha_partido))

        self.assertEqual(puntos_diarios_a.puntos, 4)
        self.assertEqual(puntos_diarios_b.puntos, 1)
        self.assertEqual(puntos_diarios_c.puntos, 0)

    def test_special_match_scoring(self):
        """
        Checks rule:
        - Exact score on es_partido_especial increments User's marcadores_especiales_atinados by 1.
        - tiene_premio_especial() returns True if marcadores_especiales_atinados >= 2.
        """
        # Create special match 1
        partido_esp_1 = Partido.objects.create(
            equipo_local="Manchester City",
            equipo_visitante="Arsenal",
            fecha_partido=self.fecha_partido,
            es_partido_especial=True
        )
        # Create special match 2
        partido_esp_2 = Partido.objects.create(
            equipo_local="Bayern",
            equipo_visitante="Dortmund",
            fecha_partido=self.fecha_partido,
            es_partido_especial=True
        )

        # User A makes exact forecast for match 1
        Pronostico.objects.create(
            usuario=self.user_a,
            partido=partido_esp_1,
            goles_local_pronostico=1,
            goles_visitante_pronostico=1
        )
        # User A makes exact forecast for match 2
        Pronostico.objects.create(
            usuario=self.user_a,
            partido=partido_esp_2,
            goles_local_pronostico=2,
            goles_visitante_pronostico=0
        )

        # Finalize match 1 with exact score
        partido_esp_1.goles_local_real = 1
        partido_esp_1.goles_visitante_real = 1
        partido_esp_1.finalizado = True
        partido_esp_1.save()

        # Check: user should have 1 special forecast correct
        perfil_a = PerfilQuiniela.objects.get(usuario=self.user_a)
        self.assertEqual(perfil_a.marcadores_especiales_atinados, 1)
        self.assertFalse(perfil_a.tiene_premio_especial())
        
        # Verify daily special matches score count in PuntosDiarios
        puntos_diarios_a = PuntosDiarios.objects.get(usuario=self.user_a, fecha=timezone.localdate(self.fecha_partido))
        self.assertEqual(puntos_diarios_a.marcadores_especiales, 1)

        # Finalize match 2 with exact score
        partido_esp_2.goles_local_real = 2
        partido_esp_2.goles_visitante_real = 0
        partido_esp_2.finalizado = True
        partido_esp_2.save()

        # Check: user should now have 2 special forecasts correct and win special prize
        perfil_a.refresh_from_db()
        self.assertEqual(perfil_a.marcadores_especiales_atinados, 2)
        self.assertTrue(perfil_a.tiene_premio_especial())

        # Verify daily special matches score count updated in PuntosDiarios
        puntos_diarios_a.refresh_from_db()
        self.assertEqual(puntos_diarios_a.marcadores_especiales, 2)

    def test_apostar_partido_context_when_repeat_markers_disabled_or_enabled(self):
        """
        Tests that when bloquear_marcadores_repetidos is False, the context variables
        reflect this and marcadores_ocupados is empty. When True, it should have the occupied markers.
        """
        from django.urls import reverse
        # User A forecasts 2 - 1
        Pronostico.objects.create(
            usuario=self.user_a,
            partido=self.partido,
            goles_local_pronostico=2,
            goles_visitante_pronostico=1
        )
        
        config = ConfiguracionQuiniela.obtener_config()
        
        # Log in User B to request the page
        self.client.force_login(self.user_b)
        
        # Case 1: lock is active
        config.bloquear_marcadores_repetidos = True
        config.save()
        
        response = self.client.get(reverse('apostar_partido', args=[self.partido.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['bloquear_marcadores_repetidos'])
        self.assertIn('2 - 1', response.context['marcadores_ocupados'])
        
        # Case 2: lock is inactive
        config.bloquear_marcadores_repetidos = False
        config.save()
        
        response = self.client.get(reverse('apostar_partido', args=[self.partido.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['bloquear_marcadores_repetidos'])
        self.assertEqual(len(response.context['marcadores_ocupados']), 0)
