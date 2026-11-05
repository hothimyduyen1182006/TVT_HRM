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
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.conf import settings
from django.conf.urls.static import static
from employees import views as employee_views


class TVTAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'Đăng nhập thất bại, tài khoản hoặc mật khẩu không đúng',
    }


class TVTLoginView(auth_views.LoginView):
    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.POST.get('remember') != '1':
            self.request.session.set_expiry(0)
        return response


urlpatterns = [
    path('', login_required(TemplateView.as_view(template_name='dashboard.html')), name='dashboard'),
    path('employees/', employee_views.employee_list, name='employees'),
    path('employees/me/', employee_views.personal_profile, name='personal_profile'),
    path('employees/new/', employee_views.employee_create, name='employee_create'),
    path('employees/<int:employee_id>/edit/', employee_views.employee_edit, name='employee_edit'),
    path('employees/<int:employee_id>/education/new/', employee_views.education_edit, name='education_create'),
    path('employees/<int:employee_id>/education/<int:record_id>/edit/', employee_views.education_edit, name='education_edit'),
    path('employees/<int:employee_id>/contracts/new/', employee_views.contract_edit, name='contract_create'),
    path('employees/<int:employee_id>/contracts/<int:record_id>/edit/', employee_views.contract_edit, name='contract_edit'),
    path('employees/<int:employee_id>/', employee_views.employee_detail, name='employee_detail'),
    path('accounts/login/', TVTLoginView.as_view(authentication_form=TVTAuthenticationForm), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('attendance/', include('attendance.urls')),
    path('payroll/', include('payroll.urls')),
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
