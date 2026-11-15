from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('attendance', '0012_unified_month_links'), ('payroll', '0011_retire_attendance_period')]
    operations = [
        # Bỏ model hoạt động; giữ bảng gốc để tra cứu và khôi phục lịch sử.
        migrations.SeparateDatabaseAndState(database_operations=[],
            state_operations=[migrations.DeleteModel(name='KyCong')]),
    ]
