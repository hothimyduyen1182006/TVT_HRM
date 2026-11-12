from django.db import migrations


def preserve_approvals(apps, schema_editor):
    alias = schema_editor.connection.alias
    Period = apps.get_model('attendance', 'AttendancePeriod')
    Record = apps.get_model('attendance', 'AttendanceRecord')
    Approval = apps.get_model('attendance', 'EmployeeAttendanceApproval')
    Employee = apps.get_model('employees', 'Employee')
    for period in Period.objects.using(alias).filter(status='approved').iterator():
        ids = period.employee_ids or list(Record.objects.using(alias).filter(
            date__year=period.year, date__month=period.month).values_list('employee_id', flat=True).distinct())
        valid_ids = Employee.objects.using(alias).filter(pk__in=ids).values_list('pk', flat=True)
        Approval.objects.using(alias).bulk_create([
            Approval(period_id=period.pk, employee_id=employee_id, approved_by_id=period.approved_by_id)
            for employee_id in valid_ids])
        if period.approved_at:
            Approval.objects.using(alias).filter(period_id=period.pk).update(approved_at=period.approved_at)


class Migration(migrations.Migration):
    dependencies = [('attendance', '0003_employeeattendanceapproval_and_more')]
    operations = [migrations.RunPython(preserve_approvals, migrations.RunPython.noop)]
