"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from .views import home, dashboard, departments, protected_media
from django.contrib.auth.forms import AuthenticationForm
from django.conf import settings


class TVTAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'Đăng nhập thất bại, tài khoản hoặc mật khẩu không đúng',
    }


class TVTLoginView(auth_views.LoginView):
    def form_valid(self, form):
        response = super().form_valid(form)
        expiry = settings.SESSION_COOKIE_AGE if self.request.POST.get('remember') == '1' else 0
        self.request.session.set_expiry(expiry)
        return response


class TVTLogoutView(auth_views.LogoutView):
    http_method_names = ['post', 'options']


urlpatterns = [
    path('', home, name='home'),
    path('dashboard/', dashboard, name='dashboard'),
    path('departments/', departments, name='departments'),
    path('nhan_vien/', include('nhan_vien.urls')),
    path('accounts/login/', TVTLoginView.as_view(authentication_form=TVTAuthenticationForm), name='login'),
    path('accounts/logout/', TVTLogoutView.as_view(), name='logout'),
    path('bang_cong/', include('bang_cong.urls')),
    path('bang_luong/', include('bang_luong.urls')),
    path('thuong/', include('thuong.urls')),
    path('nghi_phep/', include('nghi_phep.urls')),
    path('admin/', admin.site.urls),
    path(settings.MEDIA_URL.strip('/') + '/<path:path>', protected_media, name='protected-media'),
]
