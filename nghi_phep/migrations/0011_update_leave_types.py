from django.db import migrations, models


def update_existing_leave_types(apps, schema_editor):
    LeaveRequest = apps.get_model('leaves', 'LeaveRequest')
    database = schema_editor.connection.alias

    LeaveRequest.objects.using(database).filter(leave_type='sick').update(
        leave_type='special_paid',
    )
    LeaveRequest.objects.using(database).filter(leave_type='personal').update(
        leave_type='unpaid',
    )


class Migration(migrations.Migration):
    dependencies = [
        ('leaves', '0010_simplify_leave_day_units'),
    ]

    operations = [
        migrations.RunPython(update_existing_leave_types, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='leaverequest',
            name='leave_type',
            field=models.CharField(
                choices=[
                    ('annual', 'Nghỉ theo quỹ phép'),
                    ('special_paid', 'Nghỉ hưởng lương đặc biệt'),
                    ('unpaid', 'Nghỉ không lương'),
                ],
                default='annual',
                max_length=20,
                verbose_name='Loại nghỉ',
            ),
        ),
    ]
