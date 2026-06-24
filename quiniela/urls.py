from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('apostar/<int:partido_id>/', views.apostar_partido, name='apostar_partido'),
    path('posiciones/', views.tabla_posiciones, name='tabla_posiciones'),
]
