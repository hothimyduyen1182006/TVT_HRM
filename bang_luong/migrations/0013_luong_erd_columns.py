"""Reduce only Luong; archive removed attributes before copying to its new key."""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models
import django.db.models.deletion


MONEY_FIELDS = (
    ('luong_co_ban', 'Luong_co_ban'), ('luong_theo_cong', 'Luong_theo_cong'),
    ('luong_tang_ca', 'Luong_tang_ca'), ('tong_tien_thuong', 'Tong_tien_thuong'),
    ('khau_tru_di_tre', 'Khau_tru_di_tre'), ('khau_tru_bhxh', 'Khau_tru_BHXH'),
    ('thue_tncn', 'Thue_TNCN'), ('luong_thuc_linh', 'Luong_thuc_linh'),
)
STATUSES = [('Cho_duyet', 'Chờ duyệt'), ('Da_duyet', 'Đã duyệt'), ('Da_chi_tra', 'Đã chi trả')]


def json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def transfer_salaries(apps, schema_editor):
    alias = schema_editor.connection.alias
    Old = apps.get_model('payroll', 'Luong')
    New = apps.get_model('payroll', 'LuongERD')
    Audit = apps.get_model('payroll', 'PayrollAuditLog')
    codes = {'pending': 'Cho_duyet', 'approved': 'Da_duyet', 'paid': 'Da_chi_tra'}
    for old in Old.objects.using(alias).select_related('tong_thuong', 'nhan_vien', 'ky_luong').iterator():
        original = {field.attname: getattr(old, field.attname) for field in Old._meta.concrete_fields}
        actor_id = (old.nguoi_duyet_id or old.ky_luong.submitted_by_id
                    or old.ky_luong.approved_by_id
                    or getattr(old.nhan_vien, 'nguoi_dung_id', None)
                    or getattr(old.nhan_vien, 'user_id', None))
        if not actor_id:
            latest = Audit.objects.using(alias).filter(period_id=old.ky_luong_id).order_by('-pk').first()
            actor_id = latest.actor_id if latest else None
        if not actor_id:
            raise ValueError(f'Cannot archive salary {old.ma_luong}: no account for the audit entry.')
        values = {}
        for name, _ in MONEY_FIELDS:
            value = Decimal(getattr(old, name))
            if not value.is_finite() or abs(value) >= Decimal('999999999999.5'):
                raise ValueError(f'{old.ma_luong}.{name} exceeds DECIMAL(12,0).')
            values[name] = value.quantize(Decimal(1), rounding=ROUND_HALF_UP)
        if old.trang_thai not in codes:
            raise ValueError(f'Unsupported salary status: {old.trang_thai}')
        Audit.objects.using(alias).create(
            period_id=old.ky_luong_id, actor_id=actor_id, action='salary_detail',
            reason='Archive payroll attributes before reducing Luong to ERD columns.',
            snapshot={'ma_luong': old.ma_luong, 'metadata': json_value(original)},
        )
        New.objects.using(alias).create(
            ma_luong=old.ma_luong, tong_hop_id=old.tong_hop_id,
            tong_thuong_id=old.tong_thuong.ma_thuong, trang_thai=codes[old.trang_thai], **values,
        )
    if Old.objects.using(alias).count() != New.objects.using(alias).count():
        raise ValueError('Salary count mismatch: aborting schema migration.')


class Migration(migrations.Migration):
    dependencies = [
        ('payroll', '0012_payroll_submission'),
        ('attendance', '0018_remove_summary_basis'),
        ('bonuses', '0004_tong_thuong'),
    ]

    operations = [
        migrations.CreateModel(
            name='LuongERD',
            fields=[
                ('ma_luong', models.CharField(primary_key=True, serialize=False, max_length=20,
                                               editable=False, db_column='Ma_luong')),
                ('tong_hop', models.OneToOneField(to='attendance.tonghopcong', related_name='+',
                    on_delete=django.db.models.deletion.PROTECT, db_column='Ma_tong_hop')),
                ('tong_thuong', models.OneToOneField(to='bonuses.tongthuong', to_field='ma_thuong', related_name='+',
                    on_delete=django.db.models.deletion.PROTECT, db_column='Ma_thuong')),
                *[(name, models.DecimalField(max_digits=12, decimal_places=0, db_column=column,
                    **({'default': 0} if name not in ('luong_co_ban', 'luong_theo_cong', 'luong_thuc_linh') else {})))
                  for name, column in MONEY_FIELDS],
                ('trang_thai', models.CharField(max_length=20, default='Cho_duyet',
                    choices=STATUSES, db_column='Trang_thai')),
            ],
            options={'db_table': 'Luong_erd_stage', 'ordering': ['tong_hop__nhan_vien__code'],
                'constraints': [models.CheckConstraint(check=models.Q(trang_thai__in=[item[0] for item in STATUSES]),
                                                       name='valid_salary_status')]},
        ),
        # No reverse operation: the original attributes are retained in the audit snapshot and database backup.
        migrations.RunPython(transfer_salaries),
        migrations.DeleteModel(name='Luong'),
        migrations.RenameModel(old_name='LuongERD', new_name='Luong'),
        migrations.AlterModelTable(name='luong', table='Luong'),
        migrations.AlterField(model_name='luong', name='tong_hop',
            field=models.OneToOneField(to='attendance.tonghopcong', related_name='phieu_luong',
                on_delete=django.db.models.deletion.PROTECT, db_column='Ma_tong_hop')),
        migrations.AlterField(model_name='luong', name='tong_thuong',
            field=models.OneToOneField(to='bonuses.tongthuong', to_field='ma_thuong', related_name='phieu_luong',
                on_delete=django.db.models.deletion.PROTECT, db_column='Ma_thuong')),
    ]
