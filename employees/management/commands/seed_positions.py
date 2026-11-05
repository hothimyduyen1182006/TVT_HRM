from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from employees.models import Department, Employee, Position


POSITION_DATA = {
    'MKT': [('Nhân viên Marketing', '1.0'), ('Trưởng phòng Marketing', '2.5')],
    'SX': [('Nhân viên sản xuất', '1.0'), ('Tổ trưởng sản xuất', '1.6'), ('Trưởng phòng sản xuất', '2.5')],
    'TK': [('Nhân viên thiết kế', '1.2'), ('Trưởng phòng thiết kế', '2.5')],
    'NS': [('Chuyên viên nhân sự', '1.2'), ('Trưởng phòng nhân sự', '2.5')],
    'IT': [('Nhân viên IT', '1.3'), ('Trưởng phòng IT', '2.5')],
    'KD': [('Nhân viên kinh doanh', '1.2'), ('Trưởng phòng kinh doanh', '2.5')],
    'TC': [('Kế toán viên', '1.3'), ('Kế toán trưởng', '2.5')],
}


class Command(BaseCommand):
    help = 'Tạo dữ liệu chức vụ mẫu theo phòng ban và gán chức vụ cho nhân viên chưa có chức vụ.'

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        assigned = 0
        for department in Department.objects.order_by('code'):
            suffix = department.code.rsplit('-', 1)[-1].upper()
            department_label = department.name.replace('Phòng ', '').replace(' (DEMO)', '').strip()
            positions = POSITION_DATA.get(suffix, [
                (f'Nhân viên {department_label}', '1.0'),
                (f'Trưởng phòng {department_label}', '2.5'),
            ])
            staff_position = None
            for index, (name, coefficient) in enumerate(positions):
                position, was_created = Position.objects.get_or_create(
                    department=department,
                    name=name,
                    defaults={'salary_coefficient': Decimal(coefficient)},
                )
                created += int(was_created)
                if index == 0:
                    staff_position = position
            if staff_position:
                assigned += Employee.objects.filter(
                    department=department, position__isnull=True,
                ).update(position=staff_position)

        self.stdout.write(self.style.SUCCESS(
            f'Created {created} positions and assigned positions to {assigned} employees.'
        ))
