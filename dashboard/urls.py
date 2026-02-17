from django.urls import path
from . import views

urlpatterns = [
    path('',                views.index,          name='index'),
    path('api/mehsullar/',  views.api_mehsullar,  name='api_mehsullar'),
    path('api/data/',       views.api_data,        name='api_data'),
]
