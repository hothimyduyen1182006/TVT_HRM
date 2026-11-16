from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('bonuses', '0007_hai_bang_thuong_de_xuat'), ('payroll', '0017_lien_ket_thuong')]
    operations = [
        # Chỉ bỏ model khỏi trạng thái Django. Hai bảng dữ liệu gốc vẫn được giữ nguyên.
        migrations.SeparateDatabaseAndState(database_operations=[], state_operations=[
            migrations.DeleteModel('KhoanThuongCu'), migrations.DeleteModel('TongThuongCu'),
        ]),
    ]
