from django.db import migrations


def combine_insurance_deductions(apps, schema_editor):
    Luong = apps.get_model('payroll', 'Luong')
    database = schema_editor.connection.alias
    for phieu in Luong.objects.using(database).all().iterator():
        phieu.khau_tru_bhxh = (
            (phieu.khau_tru_bhxh or 0)
            + (phieu.khau_tru_bhyt or 0)
            + (phieu.khau_tru_bhtn or 0)
        )
        phieu.save(using=database, update_fields=['khau_tru_bhxh'])


class Migration(migrations.Migration):
    dependencies = [('payroll', '0021_payroll_director_approval')]

    operations = [
        migrations.RunPython(combine_insurance_deductions, migrations.RunPython.noop),
        migrations.RemoveField(model_name='luong', name='khau_tru_bhyt'),
        migrations.RemoveField(model_name='luong', name='khau_tru_bhtn'),
    ]
