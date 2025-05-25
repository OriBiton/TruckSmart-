from django.urls import path
from .views import login_view, register_view, logout_view,home_view,upload_file,results,cluster_orders_view,cluster_routes_view,download_excel_view

urlpatterns = [
    path("", home_view, name="home"),
    path("login/", login_view, name="login"),
    path("register/", register_view, name="register"),
    path("logout/", logout_view, name="logout"),
    path("upload/", upload_file, name="upload"),
    path('results/',results, name='results'),
    path('cluster_results/',cluster_orders_view, name='cluster_results'),
    path('cluster_routes/',cluster_routes_view, name='cluster_routes'),
    path('download_excel/<int:cluster_id>/', download_excel_view, name='download_excel'),


]
