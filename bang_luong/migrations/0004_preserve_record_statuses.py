from django.db import migrations


def preserve_statuses(apps, schema_editor):
    Period = apps.get_model('payroll', 'PayrollPeriod')
    Record = apps.get_model('payroll', 'PayrollRecord')
    alias = schema_editor.connection.alias
    for period in Period.objects.using(alias).filter(status__in=['approved', 'paid']).iterator():
        Record.objects.using(alias).filter(period_id=period.pk).update(
            status=period.status, approved_by_id=period.approved_by_id, approved_at=period.approved_at)


class Migration(migrations.Migration):
    dependencies = [('payroll', '0003_payrollrecord_approved_at_payrollrecord_approved_by_and_more')]
    operations = [migrations.RunPython(preserve_statuses, migrations.RunPython.noop)]
