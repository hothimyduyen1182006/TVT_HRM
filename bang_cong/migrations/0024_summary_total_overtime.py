from django.db import migrations, models
from django.db.models import Sum


def ensure_overtime_column(apps, schema_editor):
    summary = apps.get_model('attendance', 'TongHopCong')
    field = summary._meta.get_field('tong_gio_tang_ca')
    with schema_editor.connection.cursor() as cursor:
        columns = schema_editor.connection.introspection.get_table_description(cursor, summary._meta.db_table)
    if field.column not in {column.name for column in columns}:
        schema_editor.add_field(summary, field)


def backfill_monthly_overtime(apps, schema_editor):
    TongHopCong = apps.get_model('attendance', 'TongHopCong')
    ChamCong = apps.get_model('attendance', 'ChamCong')
    alias = schema_editor.connection.alias

    for summary in TongHopCong.objects.using(alias).all().iterator():
        total = ChamCong.objects.using(alias).filter(
            nhan_vien_id=summary.nhan_vien_id,
            ngay__year=summary.nam,
            ngay__month=summary.thang,
        ).aggregate(total=Sum('so_gio_tang_ca'))['total']
        summary.tong_gio_tang_ca = total or 0
        summary.save(using=alias, update_fields=['tong_gio_tang_ca'])


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0023_remove_attendance_adjustment_history'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name='tonghopcong',
                    name='tong_gio_tang_ca',
                    field=models.DecimalField(
                        db_column='Tong_gio_tang_ca', decimal_places=4, default=0,
                        max_digits=14, verbose_name='Tổng giờ tăng ca',
                    ),
                ),
            ],
        ),
        migrations.RunPython(ensure_overtime_column, migrations.RunPython.noop),
        migrations.RunPython(backfill_monthly_overtime, migrations.RunPython.noop),
    ]
