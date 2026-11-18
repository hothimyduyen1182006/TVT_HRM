from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('leaves', '0015_link_to_vietnamese_employee'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='ngaynghi',
            name='unique_leave_request_day',
        ),
    ]
