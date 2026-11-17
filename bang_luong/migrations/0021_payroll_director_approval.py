from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('payroll', '0020_payroll_calculation_components')]

    operations = [
        migrations.RemoveConstraint(
            model_name='luong', name='valid_salary_status',
        ),
        migrations.AlterField(
            model_name='luong', name='trang_thai',
            field=models.CharField(
                choices=[
                    ('Cho_duyet', 'Chờ duyệt'),
                    ('Cho_giam_doc_duyet', 'Chờ Giám đốc ký'),
                    ('Da_duyet', 'Đã duyệt'),
                    ('Da_chi_tra', 'Đã chi trả'),
                ], db_column='Trang_thai', default='Cho_duyet', max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name='luong',
            constraint=models.CheckConstraint(
                check=models.Q(trang_thai__in=[
                    'Cho_duyet', 'Cho_giam_doc_duyet', 'Da_duyet', 'Da_chi_tra',
                ]), name='valid_salary_status',
            ),
        ),
    ]
