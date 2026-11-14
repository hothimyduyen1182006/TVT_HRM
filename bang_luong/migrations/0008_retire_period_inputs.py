from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('payroll', '0007_luong_structure')]

    operations = [
        # Chỉ bỏ các model khỏi trạng thái Django; giữ nguyên bảng và dữ liệu cũ.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name='PayrollInput'),
                migrations.DeleteModel(name='PayrollAdjustment'),
                migrations.DeleteModel(name='PayrollExportLog'),
            ],
        ),
    ]
