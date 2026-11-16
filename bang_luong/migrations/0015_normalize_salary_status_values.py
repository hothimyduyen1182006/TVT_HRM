from django.db import migrations, models


def to_english_codes(apps, schema_editor):
    Luong = apps.get_model('payroll', 'Luong')
    alias = schema_editor.connection.alias
    for old, new in [('Cho_duyet', 'pending'), ('Da_duyet', 'approved'), ('Da_chi_tra', 'paid')]:
        Luong.objects.using(alias).filter(trang_thai=old).update(trang_thai=new)


def to_vietnamese_codes(apps, schema_editor):
    Luong = apps.get_model('payroll', 'Luong')
    alias = schema_editor.connection.alias
    for old, new in [('pending', 'Cho_duyet'), ('approved', 'Da_duyet'), ('paid', 'Da_chi_tra')]:
        Luong.objects.using(alias).filter(trang_thai=old).update(trang_thai=new)


class Migration(migrations.Migration):
    dependencies = [('payroll', '0014_retire_period_and_audit_models')]

    operations = [
        migrations.RemoveConstraint('luong', 'valid_salary_status'),
        migrations.RunPython(to_english_codes, to_vietnamese_codes),
        migrations.AlterField(
            model_name='luong', name='trang_thai',
            field=models.CharField(max_length=20, default='pending', db_column='Trang_thai', choices=[
                ('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt'), ('paid', 'Đã chi trả'),
            ]),
        ),
        migrations.AddConstraint(
            'luong', models.CheckConstraint(
                check=models.Q(trang_thai__in=['pending', 'approved', 'paid']),
                name='valid_salary_status',
            ),
        ),
    ]
