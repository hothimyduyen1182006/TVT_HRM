from decimal import Decimal

from django.db import migrations, models


def delete_partial_leave_records(apps, schema_editor):
    database = schema_editor.connection.alias
    LeaveDay = apps.get_model('leaves', 'LeaveDay')
    LeaveRequest = apps.get_model('leaves', 'LeaveRequest')
    full_day = Decimal('1.0000')

    LeaveDay.objects.using(database).exclude(units=full_day).delete()
    LeaveRequest.objects.using(database).exclude(units=full_day).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('leaves', '0008_alter_leaverequest_ly_do_alter_leaverequest_ma_don_and_more'),
    ]

    operations = [
        migrations.RunPython(delete_partial_leave_records, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='leaverequest',
            name='units',
        ),
        migrations.AddConstraint(
            model_name='leaveday',
            constraint=models.CheckConstraint(
                check=models.Q(units=Decimal('1.0000')),
                name='leave_day_full_day_only',
            ),
        ),
    ]
