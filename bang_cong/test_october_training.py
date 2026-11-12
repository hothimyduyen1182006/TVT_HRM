from datetime import date, time
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.test import TestCase, Client

from bang_cong.models import KyCong, ChamCong, ChotBangCong, LichLamViec, LichSuTangCa
from bang_cong.services.workflow import save_record, approve_employee
from thuong.models import Bonus, payroll_bonus_records
from nhan_vien.models import Employee, Department, Education, LaborContract, Position
from nghi_phep.models import LeaveRequest, LeaveDay
from bang_luong.models import PayrollPeriod, PayrollRecord, PayrollInput, PayrollAdjustment
from bang_luong.services.calculations import calculate_payroll
from bang_luong.services.workflow import approve_record, change_payroll, record_approval_error
from bang_luong.services.inputs import save_input
from bang_luong.services.exports import export_records


class OctoberTrainingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('import_tvt_profiles', password='Training-OnlyForTests@2026', stdout=StringIO())

    def prepare(self, **options):
        call_command('prepare_october_training', stdout=StringIO(), **options)

    def people(self):
        return {e.code:e for e in Employee.objects.select_related('user','department')}

    def test_all_scenarios_have_consistent_sources_without_changing_profiles(self):
        before={model:list(model.objects.order_by('pk').values()) for model in
                [Employee,Department,Position,Education,LaborContract,get_user_model()]}
        self.prepare()
        for model, rows in before.items():
            self.assertEqual(list(model.objects.order_by('pk').values()),rows)
        people=self.people()
        self.assertEqual(LichLamViec.objects.count(),31)
        self.assertEqual(LichLamViec.objects.filter(loai_ngay='work').count(),22)
        self.assertFalse(LichLamViec.objects.filter(loai_ngay='holiday').exists())
        self.assertEqual(ChamCong.objects.count(),177)
        self.assertEqual(ChamCong.objects.filter(trang_thai='incomplete').count(),2)
        self.assertEqual(ChamCong.objects.filter(trang_thai='absent').count(),1)
        self.assertEqual(LeaveRequest.objects.count(),5)
        self.assertEqual(LeaveDay.objects.count(),3)
        self.assertEqual(set(Bonus.objects.values_list('status',flat=True)),{'draft','pending','approved','rejected'})
        self.assertEqual(PayrollInput.objects.count(),8)
        self.assertEqual(PayrollInput.objects.filter(verified=False).get().employee.code,'NV08')
        self.assertEqual(PayrollAdjustment.objects.filter(name='Phụ cấp ăn trưa',amount=450000,approved=True).count(),8)
        self.assertEqual(set(ChotBangCong.objects.values_list('nhan_vien__code',flat=True)),{'NV02','NV03','NV06'})
        self.assertEqual(KyCong.objects.get().trang_thai,'pending')
        self.assertEqual(PayrollPeriod.objects.get().status,'pending')
        self.assertEqual(PayrollRecord.objects.count(),3)
        self.assertEqual(PayrollRecord.objects.get(status='approved').employee.code,'NV02')
        self.assertFalse(PayrollRecord.objects.filter(status='paid').exists())
        self.assertFalse(LichSuTangCa.objects.exists())
        self.assertEqual(PayrollRecord.objects.get(employee=people['NV03']).ot_hours,Decimal('7.5'))
        self.assertEqual(ChamCong.objects.get(nhan_vien=people['NV03'],ngay=date(2026,10,24)).tong_cong,0)
        self.assertEqual(ChamCong.objects.get(nhan_vien=people['NV07'],ngay=date(2026,10,9)).tong_cong,1)
        for row in PayrollRecord.objects.all():
            amount=sum(payroll_bonus_records(Bonus.objects.filter(employee=row.employee,year=2026,month=10)).values_list('amount',flat=True),Decimal(0))
            self.assertEqual(row.bonus_pay,amount)

    def test_repeated_command_preserves_user_edits_and_other_months(self):
        other=KyCong.objects.create(nam=2026,thang=9,gio_bat_dau=time(8),bat_dau_nghi_trua=time(12),
            ket_thuc_nghi_trua=time(13),gio_ket_thuc=time(17),gio_chuan=8)
        before=KyCong.objects.values().get(pk=other.pk)
        self.prepare()
        people=self.people()
        record=ChamCong.objects.get(nhan_vien=people['NV01'],ngay=date(2026,10,23))
        record.gio_ra=time(18)
        save_record(people['NV05'].user,record,'Người dùng thử chỉnh sửa giờ ra')
        models=[KyCong,ChamCong,LichLamViec,Bonus,PayrollPeriod,PayrollRecord,
                PayrollInput,PayrollAdjustment,LeaveDay,LeaveRequest]
        snapshots={model:list(model.objects.order_by('pk').values()) for model in models}
        self.prepare()
        for model,rows in snapshots.items():
            self.assertEqual(list(model.objects.order_by('pk').values()),rows)
        self.assertEqual(KyCong.objects.values().get(pk=other.pk),before)

    def test_conflicting_existing_data_is_never_overwritten(self):
        day=LichLamViec.objects.create(ngay=date(2026,10,1),loai_ngay='work',cong_chuan=1)
        with self.assertRaises(CommandError): self.prepare()
        self.assertEqual(LichLamViec.objects.count(),1)
        self.assertEqual(LichLamViec.objects.get().pk,day.pk)
        self.assertFalse(ChamCong.objects.exists())
        self.assertFalse(PayrollPeriod.objects.exists())

    def test_dry_run_rolls_back_every_business_record(self):
        self.prepare(dry_run=True)
        for model in [KyCong,ChamCong,LichLamViec,Bonus,PayrollPeriod,PayrollRecord,LeaveRequest,LeaveDay]:
            self.assertFalse(model.objects.exists())
        self.assertEqual(Employee.objects.count(),8)

    def test_bonus_approval_requires_recalculation_and_never_adds_twice(self):
        self.prepare()
        people=self.people()
        period=PayrollPeriod.objects.get()
        record=PayrollRecord.objects.get(employee=people['NV03'])
        locked=PayrollRecord.objects.values().get(employee=people['NV02'])
        self.assertEqual(record.bonus_pay,0)
        client=Client()
        client.force_login(people['NV08'].user)
        from django.urls import reverse
        url=reverse('thuong:decision',args=[people['NV03'].pk,2026,10])
        response=client.post(url,{'action':'approve'})
        self.assertEqual(response.status_code,302)
        self.assertTrue(record_approval_error(record))
        for attempt in range(2):
            calculate_payroll(people['NV05'].user,period.pk,'Tính lại sau duyệt thưởng')
            self.assertEqual(PayrollRecord.objects.count(),3)
            current=PayrollRecord.objects.get(employee=people['NV03'])
            self.assertEqual(current.bonus_pay,1050000)
            self.assertEqual(current.ot_hours,Decimal('7.5'))
            self.assertEqual(PayrollRecord.objects.values().get(employee=people['NV02']),locked)

    def test_roles_csrf_and_edit_lock_are_enforced(self):
        self.prepare()
        people=self.people()
        locked=ChamCong.objects.filter(nhan_vien=people['NV02']).first()
        editable=ChamCong.objects.get(nhan_vien=people['NV01'],ngay=date(2026,10,23))
        client=Client(enforce_csrf_checks=True)
        client.force_login(people['NV05'].user)
        self.assertEqual(client.get(f'/bang_cong/{locked.pk}/edit/').status_code,403)
        url=f'/bang_cong/{editable.pk}/edit/'
        client.get(url)
        values={'check_in':'08:10','check_out':'17:00','status':'present','note':'Đối chiếu giờ','reason':'Thử sửa công'}
        self.assertEqual(client.post(url,values).status_code,403)
        response=client.post(url,{**values,'csrfmiddlewaretoken':client.cookies['csrftoken'].value})
        self.assertEqual(response.status_code,302)
        editable.refresh_from_db()
        self.assertEqual(editable.so_phut_tre,10)
        client.force_login(people['NV02'].user)
        self.assertEqual(client.get(f'/bang_cong/employee/{people["NV03"].pk}/?month=10&year=2026').status_code,200)
        self.assertEqual(client.get(f'/bang_cong/employee/{people["NV04"].pk}/?month=10&year=2026').status_code,404)
        client.force_login(people['NV01'].user)
        self.assertEqual(client.get('/bang_luong/?month=10&year=2026').status_code,302)

    def test_remaining_workflow_can_be_completed_without_payment_in_prepared_state(self):
        self.prepare()
        people=self.people()
        period=PayrollPeriod.objects.get()
        attendance=period.attendance_period
        hr,director=people['NV05'].user,people['NV08'].user
        locked=PayrollRecord.objects.filter(status='approved')
        self.assertEqual(export_records(hr,locked,'csv',10,2026,{}).status_code,200)
        with self.assertRaises(ValidationError): export_records(hr,PayrollRecord.objects.all(),'csv',10,2026,{})
        with self.assertRaises(ValidationError): change_payroll(director,period.pk,'paid','Chưa đủ bước','')
        request=LeaveRequest.objects.get(Trang_thai='pending')
        client=Client()
        client.force_login(hr)
        from django.urls import reverse
        self.assertEqual(client.post(reverse('nghi_phep:review',args=[request.pk,'approve'])).status_code,302)
        request.refresh_from_db()
        self.assertEqual(request.Trang_thai,'approved')
        record=ChamCong.objects.get(nhan_vien=people['NV04'],ngay=date(2026,10,30))
        record.trang_thai='leave'
        save_record(hr,record,'Cập nhật công sau khi phép đã duyệt')
        record=ChamCong.objects.get(nhan_vien=people['NV05'],ngay=date(2026,10,21))
        record.trang_thai='present';record.gio_ra=time(17)
        save_record(hr,record,'Đối chiếu và bổ sung giờ ra')
        inputs=PayrollInput.objects.get(employee=people['NV08'])
        inputs.verified=True
        save_input(hr,inputs)
        for code in ['NV01','NV04','NV05','NV07','NV08']:
            approve_employee(hr,people[code],attendance.pk)
        attendance.refresh_from_db()
        self.assertEqual(attendance.trang_thai,'approved')
        calculate_payroll(hr,period.pk,'Tính lương sau khi xử lý đủ dữ liệu')
        self.assertEqual(PayrollRecord.objects.count(),8)
        change_payroll(director,period.pk,'approve','Đã đối chiếu đủ dữ liệu')
        # Only the isolated test database is paid; the prepared live dataset remains unpaid.
        change_payroll(director,period.pk,'paid','Thử đủ quy trình trong database thử nghiệm','TEST-2026-10')
        self.assertEqual(PayrollRecord.objects.filter(status='paid').count(),8)

    def test_amount_tampering_still_blocks_approval_despite_sqlite_normalization(self):
        self.prepare()
        record=PayrollRecord.objects.get(employee__code='NV06')
        self.assertEqual(record_approval_error(record),'')
        record.attendance_pay+=Decimal(1)
        record.save(update_fields=['attendance_pay'])
        self.assertTrue(record_approval_error(record))
        with self.assertRaises(ValidationError):
            approve_record(self.people()['NV08'].user,record.pk)
