from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('payroll', '0011_retire_attendance_period'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AlterField(
            model_name='payrollperiod', name='status',
            field=models.CharField(max_length=10, default='pending', choices=[
                ('pending', 'Chờ HR kiểm tra'), ('submitted', 'Chờ Giám đốc duyệt'),
                ('approved', 'Đã duyệt'), ('paid', 'Đã chi trả'),
            ]),
        ),
        migrations.AddField(
            model_name='payrollperiod', name='submitted_by',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT, related_name='submitted_payrolls'),
        ),
        migrations.AddField(
            model_name='payrollperiod', name='submitted_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
