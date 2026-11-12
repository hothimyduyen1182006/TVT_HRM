from decimal import Decimal
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ('leaves', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('employees', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='LeaveRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_date', models.DateField(verbose_name='Từ ngày')),
                ('end_date', models.DateField(verbose_name='Đến ngày')),
                ('units', models.DecimalField(decimal_places=4, max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0.0001')), django.core.validators.MaxValueValidator(1)], verbose_name='Số công mỗi ngày')),
                ('paid', models.BooleanField(default=False, verbose_name='Nghỉ hưởng lương')),
                ('reason', models.CharField(max_length=255, verbose_name='Lý do')),
                ('status', models.CharField(choices=[('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt'), ('rejected', 'Từ chối')], default='pending', max_length=12, verbose_name='Trạng thái')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='leave_requests', to='employees.employee')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reviewed_leave_requests', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
