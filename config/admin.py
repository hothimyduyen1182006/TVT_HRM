from django.contrib.admin.apps import AdminConfig


class TVTAdminConfig(AdminConfig):
    default_site = 'config.admin_site.TVTAdminSite'
