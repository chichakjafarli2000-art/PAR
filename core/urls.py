from django.urls import path
from django.contrib.auth import views as auth_views
from dashboard import views

urlpatterns = [
    path('',               views.index,         name='index'),
    path('api/mehsullar/', views.api_mehsullar, name='api_mehsullar'),
    path('api/data/',      views.api_data,      name='api_data'),
    path('login/',  auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]
