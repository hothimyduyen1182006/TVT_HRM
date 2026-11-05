from django.contrib.admin import AdminSite


class TVTAdminSite(AdminSite):
    site_header = 'Quản trị hệ thống nhân sự TVT'
    site_title = 'TVT HRM'

    def has_permission(self, request):
        # Cổng dữ liệu gốc dành cho quản trị viên. Vai trò nghiệp vụ dùng các view
        # đã giới hạn phạm vi, tránh quyền staff vô tình vượt phạm vi phòng/bản thân.
        return request.user.is_active and request.user.is_superuser
