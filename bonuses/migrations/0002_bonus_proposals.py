from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('bonuses', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name='bonus', name='bonus_type', field=models.CharField(choices=[('attendance', 'Thưởng chuyên cần'), ('seniority', 'Thưởng thâm niên'), ('other', 'Thưởng khác')], default='other', max_length=20, verbose_name='Loại thưởng')),
        migrations.AddField(model_name='bonus', name='reason', field=models.TextField(blank=True, verbose_name='Lý do')),
        migrations.AddField(model_name='bonus', name='proposed_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='bonus', name='rejection_reason', field=models.TextField(blank=True, verbose_name='Lý do từ chối')),
        migrations.AddField(model_name='bonus', name='proposed_by', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='bonus_proposals', to=settings.AUTH_USER_MODEL)),
        migrations.AlterField(model_name='bonus', name='status', field=models.CharField(choices=[('draft', 'Bản nháp'), ('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt'), ('rejected', 'Từ chối')], default='pending', max_length=10, verbose_name='Trạng thái')),
    ]
