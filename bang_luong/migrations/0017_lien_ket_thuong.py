from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('payroll', '0016_payroll_submission_state'),
        ('bonuses', '0007_hai_bang_thuong_de_xuat'),
    ]
    operations = [
        # Mã thưởng đã được giữ nguyên khi chuyển dữ liệu; chỉ đổi bảng tham chiếu.
        migrations.AlterField(
            model_name='luong', name='tong_thuong',
            field=models.OneToOneField(
                to='bonuses.thuong', on_delete=django.db.models.deletion.PROTECT,
                related_name='phieu_luong', db_column='Ma_thuong',
            ),
        ),
    ]
