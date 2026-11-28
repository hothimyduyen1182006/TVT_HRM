from django.apps import AppConfig


class BangCongConfig(AppConfig):
    """Cấu hình ứng dụng Bảng công."""

    default_auto_field = 'django.db.models.BigAutoField'

    name = 'bang_cong'

    # Giữ định danh cũ để khớp migration, quan hệ dữ liệu và quyền truy cập.
    label = 'attendance'

    verbose_name = 'Bảng công'
