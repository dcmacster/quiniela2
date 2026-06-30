from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from .models import Partido, Pronostico, PerfilQuiniela, PuntosDiarios, ConfiguracionQuiniela, Torneo, PuntosTorneoUsuario

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

    def test_flexible_payment_and_auto_generation_signals(self):
        """
        Tests:
        1. Creating a new Partido automatically generates PuntosDiarios for all existing users.
        2. Creating a new User automatically generates PuntosDiarios for all existing match dates.
        3. Storing and reading monto_pagado works correctly.
        """
        # Create a new match scheduled for a different date
        match_date = timezone.now() + timedelta(days=5)
        new_match = Partido.objects.create(
            equipo_local="France",
            equipo_visitante="Spain",
            fecha_partido=match_date
        )
        
        # Verify that PuntosDiarios records are automatically created for existing users for the new date
        fecha_local = timezone.localdate(match_date)
        
        # We expect PuntosDiarios to exist for user_a, user_b, user_c
        puntos_a = PuntosDiarios.objects.filter(usuario=self.user_a, fecha=fecha_local).first()
        puntos_b = PuntosDiarios.objects.filter(usuario=self.user_b, fecha=fecha_local).first()
        puntos_c = PuntosDiarios.objects.filter(usuario=self.user_c, fecha=fecha_local).first()
        
        self.assertIsNotNone(puntos_a)
        self.assertIsNotNone(puntos_b)
        self.assertIsNotNone(puntos_c)
        
        # Log a flexible payment on one of them
        puntos_a.monto_pagado = 150.50
        puntos_a.pago_confirmado = True
        puntos_a.save()
        
        # Refresh and verify
        puntos_a.refresh_from_db()
        self.assertEqual(float(puntos_a.monto_pagado), 150.50)
        self.assertTrue(puntos_a.pago_confirmado)
        
        # Now create a new User D
        user_d = User.objects.create_user(username='userD', email='userd@test.com', password='password123')
        
        # Verify that user_d gets PuntosDiarios records automatically generated for the existing match dates
        match_dates = Partido.objects.values_list('fecha_partido', flat=True).distinct()
        for fp in match_dates:
            fp_local = timezone.localdate(fp)
            puntos_d = PuntosDiarios.objects.filter(usuario=user_d, fecha=fp_local).first()
            self.assertIsNotNone(puntos_d)

    def test_daily_table_always_shows_predictions(self):
        """
        Tests that predictions made by users for future matches are visible to other users
        in the daily table positions view, and not hidden.
        """
        from django.urls import reverse
        
        # User A makes a prediction for the future match (2 - 1)
        Pronostico.objects.create(
            usuario=self.user_a,
            partido=self.partido,
            goles_local_pronostico=2,
            goles_visitante_pronostico=1
        )
        
        # Log in User B to request the page
        self.client.force_login(self.user_b)
        
        # Fetch the daily positions page for the date of the match
        fecha_str = timezone.localdate(self.fecha_partido).strftime('%Y-%m-%d')
        response = self.client.get(reverse('tabla_posiciones') + f'?tipo=diaria&fecha={fecha_str}')
        
        self.assertEqual(response.status_code, 200)
        # Verify the forecast is visible in the HTML (should render "2 - 1")
        self.assertContains(response, "2 - 1")
        # Verify "Oculto" is not in the response (since privacy check was removed)
        self.assertNotContains(response, "Oculto")

    def test_daily_leaderboard_ordering_by_points_and_special_matches(self):
        """
        Tests that if two users have the same daily points, they are sorted
        by the count of special matches won (marcadores_especiales) descending.
        """
        from django.urls import reverse
        
        # Create users: 'zzz_user' and 'xxx_user'
        user_z = User.objects.create_user(username='zzz_user', email='zzz@test.com', password='password123')
        user_x = User.objects.create_user(username='xxx_user', email='xxx@test.com', password='password123')
        
        # Create matches on the same date: one special, one normal
        match_date = timezone.now() + timedelta(days=2)
        partido_especial = Partido.objects.create(
            equipo_local="Team A",
            equipo_visitante="Team B",
            fecha_partido=match_date,
            es_partido_especial=True
        )
        partido_normal = Partido.objects.create(
            equipo_local="Team C",
            equipo_visitante="Team D",
            fecha_partido=match_date,
            es_partido_especial=False
        )
        
        # Forecasts:
        # zzz_user gets exact score on special match (4 pts, 1 special)
        # zzz_user gets wrong on normal match (0 pts)
        Pronostico.objects.create(
            usuario=user_z,
            partido=partido_especial,
            goles_local_pronostico=2,
            goles_visitante_pronostico=1
        )
        Pronostico.objects.create(
            usuario=user_z,
            partido=partido_normal,
            goles_local_pronostico=0,
            goles_visitante_pronostico=0
        )
        
        # xxx_user gets wrong on special match (0 pts)
        # xxx_user gets exact score on normal match (4 pts, 0 special)
        Pronostico.objects.create(
            usuario=user_x,
            partido=partido_especial,
            goles_local_pronostico=0,
            goles_visitante_pronostico=0
        )
        Pronostico.objects.create(
            usuario=user_x,
            partido=partido_normal,
            goles_local_pronostico=3,
            goles_visitante_pronostico=1
        )
        
        # Finalize the matches
        partido_especial.goles_local_real = 2
        partido_especial.goles_visitante_real = 1
        partido_especial.finalizado = True
        partido_especial.save()
        
        partido_normal.goles_local_real = 3
        partido_normal.goles_visitante_real = 1
        partido_normal.finalizado = True
        partido_normal.save()
        
        # Fetch positions for that day
        fecha_str = timezone.localdate(match_date).strftime('%Y-%m-%d')
        response = self.client.get(reverse('tabla_posiciones') + f'?tipo=diaria&fecha={fecha_str}')
        
        self.assertEqual(response.status_code, 200)
        posiciones = response.context['posiciones']
        
        # Filter down to our two test users
        pos_filtradas = [p for p in posiciones if p.usuario in (user_z, user_x)]
        
        self.assertEqual(len(pos_filtradas), 2)
        # zzz_user has 4 points and 1 special match won
        # xxx_user has 4 points and 0 special matches won
        # Therefore zzz_user must be first, despite 'xxx_user' being alphabetically first.
        self.assertEqual(pos_filtradas[0].usuario, user_z)
        self.assertEqual(pos_filtradas[1].usuario, user_x)

    def test_reset_puntos_con_nuevo_torneo(self):
        """
        Tests that creating a new active Torneo resets the active leaderboard to zero,
        while the previous Torneo's scores are preserved.
        """
        # The default setup should have auto-created a 'Torneo General' and linked self.partido to it.
        torneo_inicial = self.partido.torneo
        self.assertIsNotNone(torneo_inicial)
        
        # User A makes exact forecast (2 - 1)
        Pronostico.objects.create(
            usuario=self.user_a,
            partido=self.partido,
            goles_local_pronostico=2,
            goles_visitante_pronostico=1
        )
        self.partido.goles_local_real = 2
        self.partido.goles_visitante_real = 1
        self.partido.finalizado = True
        self.partido.save()
        
        # Verify User A has 4 points in the initial tournament
        puntos_torneo_inicial = PuntosTorneoUsuario.objects.get(usuario=self.user_a, torneo=torneo_inicial)
        self.assertEqual(puntos_torneo_inicial.puntos_totales, 4)
        
        # Create a new Torneo and activate it
        torneo_clausura = Torneo.objects.create(nombre="Torneo Clausura", activo=True)
        
        # The initial tournament must have been deactivated
        torneo_inicial.refresh_from_db()
        self.assertFalse(torneo_inicial.activo)
        self.assertTrue(torneo_clausura.activo)
        
        # Create a new Partido (should automatically link to the active 'Torneo Clausura')
        nuevo_partido = Partido.objects.create(
            equipo_local="Boca Juniors",
            equipo_visitante="River Plate",
            fecha_partido=timezone.now() + timedelta(days=2)
        )
        self.assertEqual(nuevo_partido.torneo, torneo_clausura)
        
        # User A makes exact forecast on the new match (1 - 0)
        Pronostico.objects.create(
            usuario=self.user_a,
            partido=nuevo_partido,
            goles_local_pronostico=1,
            goles_visitante_pronostico=0
        )
        nuevo_partido.goles_local_real = 1
        nuevo_partido.goles_visitante_real = 0
        nuevo_partido.finalizado = True
        nuevo_partido.save()
        
        # Verify points are calculated separately
        puntos_torneo_clausura = PuntosTorneoUsuario.objects.get(usuario=self.user_a, torneo=torneo_clausura)
        puntos_torneo_inicial.refresh_from_db()
        
        self.assertEqual(puntos_torneo_clausura.puntos_totales, 4)
        self.assertEqual(puntos_torneo_inicial.puntos_totales, 4)
        
        # Global profile should sum both (8 points)
        perfil_a = PerfilQuiniela.objects.get(usuario=self.user_a)
        self.assertEqual(perfil_a.puntos_totales, 8)

    def test_monto_pagado_acumulado_por_torneo(self):
        """
        Verifica:
        1. Al registrar pagos diarios (PuntosDiarios) para un usuario en fechas correspondientes al torneo activo,
           el total acumulado en PuntosTorneoUsuario se actualice correctamente.
        2. Los pagos de un torneo no interfieren con los pagos acumulados de otro torneo.
        """
        # Crear dos torneos
        torneo_1 = Torneo.objects.create(nombre="Torneo 1", activo=True)
        torneo_2 = Torneo.objects.create(nombre="Torneo 2", activo=False)
        
        # Fechas de partidos para los torneos
        fecha_t1 = timezone.now() + timedelta(days=10)
        fecha_t2 = timezone.now() + timedelta(days=20)
        
        # Partido para Torneo 1
        partido_t1 = Partido.objects.create(
            equipo_local="Real Madrid",
            equipo_visitante="Barcelona",
            fecha_partido=fecha_t1,
            torneo=torneo_1
        )
        
        # Partido para Torneo 2
        partido_t2 = Partido.objects.create(
            equipo_local="Boca Juniors",
            equipo_visitante="River Plate",
            fecha_partido=fecha_t2,
            torneo=torneo_2
        )
        
        # Obtener los PuntosDiarios creados por señal para el user_a en esas fechas
        fecha_t1_date = timezone.localdate(fecha_t1)
        fecha_t2_date = timezone.localdate(fecha_t2)
        
        puntos_diarios_t1 = PuntosDiarios.objects.get(usuario=self.user_a, fecha=fecha_t1_date)
        puntos_diarios_t2 = PuntosDiarios.objects.get(usuario=self.user_a, fecha=fecha_t2_date)
        
        # 1. Registrar pago diario en fecha del Torneo 1
        puntos_diarios_t1.monto_pagado = 100.00
        puntos_diarios_t1.save()
        
        # Verificar que el acumulado en PuntosTorneoUsuario para Torneo 1 sea 100.00 y para Torneo 2 sea 0.00
        ptu_t1 = PuntosTorneoUsuario.objects.get(usuario=self.user_a, torneo=torneo_1)
        ptu_t2 = PuntosTorneoUsuario.objects.get(usuario=self.user_a, torneo=torneo_2)
        
        self.assertEqual(float(ptu_t1.monto_pagado_acumulado), 100.00)
        self.assertEqual(float(ptu_t2.monto_pagado_acumulado), 0.00)
        
        # 2. Registrar pago diario en fecha del Torneo 2
        puntos_diarios_t2.monto_pagado = 150.50
        puntos_diarios_t2.save()
        
        # Refrescar objetos y verificar que los pagos de Torneo 2 no afecten a Torneo 1
        ptu_t1.refresh_from_db()
        ptu_t2.refresh_from_db()
        
        self.assertEqual(float(ptu_t1.monto_pagado_acumulado), 100.00)
        self.assertEqual(float(ptu_t2.monto_pagado_acumulado), 150.50)
