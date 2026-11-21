from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('payroll', '0022_combine_insurance_deductions'),
    ]

    operations = [
        migrations.AlterField(
            model_name='luong',
            name='trang_thai',
            field=models.CharField(
                max_length=20,
                default='Cho_duyet',
                choices=[
                    ('Cho_duyet', 'Chờ HR kiểm tra'),
                    ('Cho_giam_doc_duyet', 'Chờ Giám đốc ký duyệt'),
                    ('Da_duyet', 'Đã duyệt'),
                ],
                db_column='Trang_thai',
            ),
        ),
    ]
