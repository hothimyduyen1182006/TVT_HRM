from datetime import date, datetime
from decimal import Decimal

from django.db import migrations


REQUESTS = [
    {
        'pk': 16,
        'employee_code': 'NV05',
        'start_date': date(2026, 11, 21),
        'end_date': date(2026, 11, 25),
        'units': Decimal('1.0000'),
        'leave_type': 'annual',
        'paid': True,
        'reason': 'Bị ốm',
        'status': 'pending',
        'evidence': 'leave_evidence/2026/11/1794276216158_1870162432003839934_195831632834318333_af8fa63ecb8b_0WyAgM0.jpg',
        'created_at': datetime.fromisoformat('2026-11-12T10:34:25.849394+00:00'),
    },
    {
        'pk': 17,
        'employee_code': 'NV05',
        'start_date': date(2026, 11, 30),
        'end_date': date(2026, 12, 1),
        'units': Decimal('1.0000'),
        'leave_type': 'unpaid',
        'paid': False,
        'reason': 'Tôi bận việc gấp',
        'status': 'pending',
        'evidence': 'leave_evidence/2026/11/CĐS._C3._Lộ_trình_CĐS.pdf',
        'created_at': datetime.fromisoformat('2026-11-12T10:48:04.523521+00:00'),
    },
]


def sync_requests(apps, schema_editor):
    database = schema_editor.connection.alias
    Employee = apps.get_model('employees', 'Employee')
    LeaveRequest = apps.get_model('leaves', 'LeaveRequest')

    for source in REQUESTS:
        employee = Employee.objects.using(database).filter(code=source['employee_code']).first()
        if employee is None:
            raise RuntimeError(f"Không tìm thấy nhân viên {source['employee_code']} để đồng bộ đơn nghỉ phép.")

        lookup = {
            'employee_id': employee.pk,
            'start_date': source['start_date'],
            'end_date': source['end_date'],
            'leave_type': source['leave_type'],
            'reason': source['reason'],
        }
        request = LeaveRequest.objects.using(database).filter(pk=source['pk']).first()
        if request is not None and any(getattr(request, key) != value for key, value in lookup.items()):
            request = None
        if request is None:
            request = LeaveRequest.objects.using(database).filter(**lookup).first()

        if request is not None:
            if request.evidence and request.evidence != source['evidence']:
                raise RuntimeError(f'Đơn nghỉ phép {request.pk} đã có minh chứng khác; không ghi đè tệp.')
            if request.evidence != source['evidence']:
                LeaveRequest.objects.using(database).filter(pk=request.pk).update(evidence=source['evidence'])
            continue

        values = {
            key: value for key, value in source.items()
            if key not in {'pk', 'employee_code', 'created_at'}
        }
        values['employee_id'] = employee.pk
        request_id = source['pk']
        if LeaveRequest.objects.using(database).filter(pk=request_id).exists():
            request_id = None
        request = LeaveRequest.objects.using(database).create(pk=request_id, **values)
        LeaveRequest.objects.using(database).filter(pk=request.pk).update(created_at=source['created_at'])


class Migration(migrations.Migration):
    dependencies = [
        ('leaves', '0004_alter_leaverequest_status'),
    ]

    operations = [
        migrations.RunPython(sync_requests, migrations.RunPython.noop),
    ]
