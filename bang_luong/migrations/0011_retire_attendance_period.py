from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('payroll', '0010_unified_month_data'), ('attendance', '0012_unified_month_links')]
    operations = [migrations.RemoveField('payrollperiod', 'attendance_period')]
