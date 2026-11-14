from django.apps import AppConfig


class BangCongConfig(AppConfig):
    """Cấu hình ứng dụng Bảng công."""

    # Kiểu khóa chính tự tăng mặc định của các bảng.
    default_auto_field = 'django.db.models.BigAutoField'

    # Tên thư mục ứng dụng trong dự án.
    name = 'bang_cong'

    # Giữ định danh cũ để khớp migration, quan hệ dữ liệu và quyền truy cập.
    label = 'attendance'

    # Tên hiển thị trên trang quản trị Django.
    verbose_name = 'Bảng công'
