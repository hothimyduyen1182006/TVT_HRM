from datetime import date, time
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.test import TestCase, Client

from bang_cong.models import KyCong, ChamCong, ChotBangCong, LichLamViec, LichSuTangCa
from bang_cong.services.quy_trinh import luu_cham_cong, duyet_cong_nhan_vien
from thuong.models import Bonus, payroll_bonus_records
from nhan_vien.models import Employee, Department, Education, LaborContract, Position
from nghi_phep.models import LeaveRequest, LeaveDay
from bang_luong.models import PayrollPeriod, Luong, PayrollInput, PayrollAdjustment
from bang_luong.services.tinh_toan import tinh_bang_luong
from bang_luong.services.quy_trinh import duyet_phieu_luong, xu_ly_trang_thai_luong, loi_duyet_luong
from bang_luong.services.quy_trinh import save_input
from bang_luong.services.hien_thi import xuat_du_lieu_luong


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
        self.assertEqual(Luong.objects.count(),3)
        self.assertEqual(Luong.objects.get(trang_thai='approved').nhan_vien.code,'NV02')
        self.assertFalse(Luong.objects.filter(trang_thai='paid').exists())
        self.assertFalse(LichSuTangCa.objects.exists())
        self.assertEqual(Luong.objects.get(nhan_vien=people['NV03']).so_gio_tang_ca,Decimal('7.5'))
        self.assertEqual(ChamCong.objects.get(nhan_vien=people['NV03'],ngay=date(2026,10,24)).tong_cong,0)
        self.assertEqual(ChamCong.objects.get(nhan_vien=people['NV07'],ngay=date(2026,10,9)).tong_cong,1)
        for row in Luong.objects.all():
            amount=sum(payroll_bonus_records(Bonus.objects.filter(employee=row.nhan_vien,year=2026,month=10)).values_list('amount',flat=True),Decimal(0))
            self.assertEqual(row.tong_tien_thuong,amount)

    def test_repeated_command_preserves_user_edits_and_other_months(self):
        other=KyCong.objects.create(nam=2026,thang=9,gio_bat_dau=time(8),bat_dau_nghi_trua=time(12),
            ket_thuc_nghi_trua=time(13),gio_ket_thuc=time(17),gio_chuan=8)
        before=KyCong.objects.values().get(pk=other.pk)
        self.prepare()
        people=self.people()
        record=ChamCong.objects.get(nhan_vien=people['NV01'],ngay=date(2026,10,23))
        record.gio_ra=time(18)
        luu_cham_cong(people['NV05'].user,record,'Người dùng thử chỉnh sửa giờ ra')
        models=[KyCong,ChamCong,LichLamViec,Bonus,PayrollPeriod,Luong,
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
        for model in [KyCong,ChamCong,LichLamViec,Bonus,PayrollPeriod,Luong,LeaveRequest,LeaveDay]:
            self.assertFalse(model.objects.exists())
        self.assertEqual(Employee.objects.count(),8)

    def test_bonus_approval_requires_recalculation_and_never_adds_twice(self):
        self.prepare()
        people=self.people()
        period=PayrollPeriod.objects.get()
        record=Luong.objects.get(nhan_vien=people['NV03'])
        locked=Luong.objects.values().get(nhan_vien=people['NV02'])
        self.assertEqual(record.tong_tien_thuong,0)
        client=Client()
        client.force_login(people['NV08'].user)
        from django.urls import reverse
        url=reverse('thuong:decision',args=[people['NV03'].pk,2026,10])
        response=client.post(url,{'action':'approve'})
        self.assertEqual(response.status_code,302)
        self.assertTrue(loi_duyet_luong(record))
        for attempt in range(2):
            tinh_bang_luong(people['NV05'].user,period.pk,'Tính lại sau duyệt thưởng')
            self.assertEqual(Luong.objects.count(),3)
            current=Luong.objects.get(nhan_vien=people['NV03'])
            self.assertEqual(current.tong_tien_thuong,1050000)
            self.assertEqual(current.so_gio_tang_ca,Decimal('7.5'))
            self.assertEqual(Luong.objects.values().get(nhan_vien=people['NV02']),locked)

    def test_roles_csrf_and_edit_lock_are_enforced(self):
        self.prepare()
        people=self.people()
        locked=ChamCong.objects.filter(nhan_vien=people['NV02']).first()
        editable=ChamCong.objects.get(nhan_vien=people['NV01'],ngay=date(2026,10,23))
        client=Client(enforce_csrf_checks=True)
        client.force_login(people['NV05'].user)
        self.assertEqual(client.get(f'/bang_cong/{locked.pk}/sua/').status_code,403)
        url=f'/bang_cong/{editable.pk}/sua/'
        client.get(url)
        values={'check_in':'08:10','check_out':'17:00','status':'present','note':'Đối chiếu giờ','reason':'Thử sửa công'}
        self.assertEqual(client.post(url,values).status_code,403)
        response=client.post(url,{**values,'csrfmiddlewaretoken':client.cookies['csrftoken'].value})
        self.assertEqual(response.status_code,302)
        editable.refresh_from_db()
        self.assertEqual(editable.so_phut_tre,10)
        client.force_login(people['NV02'].user)
        self.assertEqual(client.get(f'/bang_cong/nhan-vien/{people["NV03"].pk}/?month=10&year=2026').status_code,200)
        self.assertEqual(client.get(f'/bang_cong/nhan-vien/{people["NV04"].pk}/?month=10&year=2026').status_code,404)
        client.force_login(people['NV01'].user)
        self.assertEqual(client.get('/bang_luong/?month=10&year=2026').status_code,302)

    def test_remaining_workflow_can_be_completed_without_payment_in_prepared_state(self):
        self.prepare()
        people=self.people()
        period=PayrollPeriod.objects.get()
        attendance=period.attendance_period
        hr,director=people['NV05'].user,people['NV08'].user
        locked=Luong.objects.filter(trang_thai='approved')
        self.assertEqual(xuat_du_lieu_luong(hr,locked,'csv',10,2026,{}).status_code,200)
        with self.assertRaises(ValidationError): xuat_du_lieu_luong(hr,Luong.objects.all(),'csv',10,2026,{})
        with self.assertRaises(ValidationError): xu_ly_trang_thai_luong(director,period.pk,'paid','Chưa đủ bước','')
        request=LeaveRequest.objects.get(Trang_thai='pending')
        client=Client()
        client.force_login(hr)
        from django.urls import reverse
        self.assertEqual(client.post(reverse('nghi_phep:review',args=[request.pk,'approve'])).status_code,302)
        request.refresh_from_db()
        self.assertEqual(request.Trang_thai,'approved')
        record=ChamCong.objects.get(nhan_vien=people['NV04'],ngay=date(2026,10,30))
        record.trang_thai='leave'
        luu_cham_cong(hr,record,'Cập nhật công sau khi phép đã duyệt')
        record=ChamCong.objects.get(nhan_vien=people['NV05'],ngay=date(2026,10,21))
        record.trang_thai='present';record.gio_ra=time(17)
        luu_cham_cong(hr,record,'Đối chiếu và bổ sung giờ ra')
        inputs=PayrollInput.objects.get(employee=people['NV08'])
        inputs.verified=True
        save_input(hr,inputs)
        for code in ['NV01','NV04','NV05','NV07','NV08']:
            duyet_cong_nhan_vien(hr,people[code],attendance.pk)
        attendance.refresh_from_db()
        self.assertEqual(attendance.trang_thai,'approved')
        tinh_bang_luong(hr,period.pk,'Tính lương sau khi xử lý đủ dữ liệu')
        self.assertEqual(Luong.objects.count(),8)
        xu_ly_trang_thai_luong(director,period.pk,'approve','Đã đối chiếu đủ dữ liệu')
        # Only the isolated test database is paid; the prepared live dataset remains unpaid.
        xu_ly_trang_thai_luong(director,period.pk,'paid','Thử đủ quy trình trong database thử nghiệm','TEST-2026-10')
        self.assertEqual(Luong.objects.filter(trang_thai='paid').count(),8)

    def test_amount_tampering_still_blocks_approval_despite_sqlite_normalization(self):
        self.prepare()
        record=Luong.objects.get(nhan_vien__code='NV06')
        self.assertEqual(loi_duyet_luong(record),'')
        record.luong_theo_cong+=Decimal(1)
        record.save(update_fields=['luong_theo_cong'])
        self.assertTrue(loi_duyet_luong(record))
        with self.assertRaises(ValidationError):
            duyet_phieu_luong(self.people()['NV08'].user,record.pk)
