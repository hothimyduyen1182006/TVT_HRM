from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Tạo nhóm vai trò; không tạo tài khoản hoặc tự cấp quyền admin.'

    def handle(self, *args, **options):
        for name in ['Nhân viên', 'Trưởng phòng', 'Nhân sự', 'Giám đốc']:
            Group.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS('Role groups created successfully.'))
