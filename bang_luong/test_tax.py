from datetime import date, time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase, SimpleTestCase

from bang_luong.services.thue import tinh_thue_luy_tien, loi_nguon_thue, POLICY
from bang_luong.models import PayrollInput, PayrollAdjustment, Luong
from bang_luong.services.tinh_toan import tinh_bang_luong
from bang_luong.services.quy_trinh import xu_ly_trang_thai_luong, duyet_phieu_luong, loi_duyet_luong
from bang_luong.services.quy_trinh import save_input
from bang_luong.services.hien_thi import xuat_du_lieu_luong
from bang_luong.forms import PayrollInputForm
from bang_luong import tests as legacy_fixtures
from bang_cong.models import ChamCong


class ProgressiveTaxTests(SimpleTestCase):
    def test_all_bracket_boundaries_and_whole_vnd_rounding(self):
        for income,expected in [(0,0),(-1,0),(10000000,500000),(10000001,500000),
            (30000000,2500000),(60000000,8500000),(100000000,20500000),(110000000,24000000),
            (3050000,152500),(Decimal('10.01'),1)]:
            with self.subTest(income=income):
                self.assertEqual(tinh_thue_luy_tien(income)[0],expected)
        self.assertEqual(len(tinh_thue_luy_tien(110000000)[1]),5)


class AutomaticTaxTests(TestCase):
    def setUp(self):
        legacy_fixtures.PayrollTests.setUp(self)
        self.attendance.thang=10
        self.attendance.save()
        from bang_cong.models import LichLamViec
        LichLamViec.objects.update(ngay=date(2026,10,5))
        ChamCong.objects.update(ngay=date(2026,10,5))
        PayrollInput.objects.update(tax_method='resident_2026',tax_amount=99999999,
            insurance_base=0,insurance_rates={},tax_basis='Cư trú; HĐ >= 3 tháng; đăng ký giảm trừ tại TVT; không người phụ thuộc')
        self.emp.base_salary=20000000
        self.emp.save()

    def salary(self):
        tinh_bang_luong(self.hr,self.period.pk,'Kiểm tra thuế tự động')
        return Luong.objects.get(nhan_vien=self.emp)

    def test_tax_is_automatic_and_ignores_old_or_forged_manual_amount(self):
        row=self.salary()
        self.assertEqual(row.thue_tncn,225000)
        self.assertEqual(row.luong_thuc_linh,19775000)
        self.assertEqual(row.chi_tiet['tax_calculation']['policy'],POLICY)
        self.assertEqual(row.chi_tiet['tax_calculation']['taxable_income'],'4500000')
        self.assertEqual(row.chi_tiet['source_data']['tax'],'225000')

    def test_dependents_and_personal_deduction_are_period_inputs(self):
        PayrollInput.objects.filter(employee=self.emp).update(tax_dependents=1)
        self.assertEqual(self.salary().tax,0)
        PayrollInput.objects.filter(employee=self.emp).update(tax_dependents=0,claim_personal_deduction=False)
        self.assertEqual(self.salary().tax,1500000)

    def test_meal_cash_cap_other_taxable_allowances_and_post_tax_deductions(self):
        for name,amount,category in [('Ăn trưa',1500000,'meal_cash'),('Điện thoại',200000,'taxable')]:
            save_input(self.hr,PayrollAdjustment(employee=self.emp,period=self.period,name=name,amount=amount,
                kind='allowance',tax_category=category,basis='Quy chế và chứng từ của khoản hỗ trợ',approved=True))
        save_input(self.hr,PayrollAdjustment(employee=self.emp,period=self.period,name='Hoàn ứng',amount=300000,
            kind='deduction',basis='Tiền tạm ứng đã nhận',approved=True))
        row=self.salary()
        self.assertEqual(row.thue_tncn,250000)
        self.assertEqual(row.chi_tiet['tax_calculation']['meal_exempt'],'1200000')
        self.assertEqual(row.chi_tiet['tax_calculation']['taxable_income'],'5000000')
        self.assertEqual(row.luong_thuc_linh,21150000)

    def test_lawful_ot_is_exempt_and_bonus_is_taxable(self):
        ChamCong.objects.filter(nhan_vien=self.emp).update(gio_ra=time(19))
        PayrollInput.objects.filter(employee=self.emp).update(overtime_hourly_rate=100000,overtime_basis='Lương giờ hợp lệ')
        row=self.salary()
        self.assertEqual(row.luong_tang_ca,300000)
        self.assertEqual(row.thue_tncn,225000)
        self.assertEqual(row.chi_tiet['tax_calculation']['overtime_exempt'],'300000')
        from thuong.models import Bonus
        from django.utils import timezone
        Bonus.objects.create(employee=self.emp,month=10,year=2026,name='Thưởng công việc',bonus_type='other',amount=1000000,
            reason='Hoàn thành công việc',status='approved',proposed_by=self.hr,proposed_at=timezone.now(),
            approved_by=self.director,approved_at=timezone.now())
        self.assertEqual(self.salary().tax,275000)

    def test_unsupported_scope_or_missing_verification_never_silently_returns_zero(self):
        PayrollInput.objects.filter(employee=self.emp).update(tax_method='other')
        with self.assertRaises(ValidationError): self.salary()
        PayrollInput.objects.filter(employee=self.emp).update(tax_method='resident_2026',verified=False)
        with self.assertRaises(ValidationError): self.salary()
        self.assertFalse(Luong.objects.exists())

    def test_excess_ot_needs_review_instead_of_assuming_all_pay_exempt(self):
        ChamCong.objects.filter(nhan_vien=self.emp).update(gio_ra=time(22))
        PayrollInput.objects.filter(employee=self.emp).update(overtime_hourly_rate=100000,overtime_basis='Căn cứ')
        with self.assertRaisesMessage(ValidationError,'cảnh báo'): self.salary()
        PayrollInput.objects.filter(employee=self.emp).update(tax_exempt_overtime=600000)
        row=self.salary()
        self.assertEqual(row.luong_tang_ca,750000)
        self.assertEqual(row.thue_tncn,232500)
        PayrollInput.objects.filter(employee=self.emp).update(tax_exempt_overtime=999999)
        with self.assertRaises(ValidationError): self.salary()

    def test_recalculation_is_not_cumulative_and_changed_relief_blocks_approval(self):
        first=self.salary()
        self.assertEqual(loi_duyet_luong(first),'')
        PayrollInput.objects.filter(employee=self.emp).update(tax_dependents=1)
        self.assertTrue(loi_duyet_luong(first))
        for _ in range(2):
            current=self.salary()
            self.assertEqual(current.tax,0)
            self.assertEqual(Luong.objects.count(),2)

    def test_approved_tax_cannot_be_tampered_with_or_paid_from_stale_inputs(self):
        row=self.salary()
        xu_ly_trang_thai_luong(self.director,self.period.pk,'approve','Đã kiểm tra')
        self.assertEqual(loi_nguon_thue(Luong.objects.get(pk=row.pk)),'')
        PayrollInput.objects.filter(employee=self.emp).update(tax_dependents=1)
        with self.assertRaises(ValidationError): xu_ly_trang_thai_luong(self.director,self.period.pk,'paid','Chi trả','Chứng từ')
        with self.assertRaises(ValidationError): xuat_du_lieu_luong(self.hr,Luong.objects.all(),'csv',10,2026,{})
        self.assertFalse(Luong.objects.filter(trang_thai='paid').exists())

    def test_form_does_not_accept_a_tax_override_or_legacy_method(self):
        form=PayrollInputForm(self.hr)
        self.assertNotIn('tax_amount',form.fields)
        self.assertNotIn('legacy',dict(form.fields['tax_method'].choices))

    def test_new_tax_pages_render_without_showing_historical_manual_amount(self):
        row=self.salary()
        self.client.force_login(self.hr)
        response=self.client.get(f'/nhan_vien/{self.emp.pk}/',{'month':10,'year':2026})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Thông tin thanh toán và bảo hiểm')
        obj=PayrollInput.objects.get(employee=self.emp)
        self.assertEqual(self.client.get(f'/bang_luong/inputs/tax/{obj.pk}/').status_code,200)
        self.client.force_login(self.user)
        response=self.client.get('/bang_luong/personal/',{'month':10,'year':2026})
        self.assertEqual(response.status_code,200)

    def test_other_period_does_not_silently_reuse_2026_policy(self):
        self.attendance.nam=2027
        self.attendance.save()
        from types import SimpleNamespace
        from bang_luong.services.thue import tinh_thue_tncn
        inputs=PayrollInput.objects.get(employee=self.emp)
        with self.assertRaisesMessage(ValidationError,'07–12/2026'):
            tinh_thue_tncn(inputs,SimpleNamespace(nam=2027,thang=10),20000000,0,0,0,
                PayrollAdjustment.objects.none(),[])

    def test_exempt_deductions_and_missing_exemption_basis_are_invalid(self):
        row=PayrollAdjustment(employee=self.emp,period=self.period,name='Hoàn ứng',kind='deduction',amount=100,
            basis='Căn cứ',tax_category='exempt')
        with self.assertRaises(ValidationError): row.full_clean()
        row.kind='allowance';row.basis=''
        with self.assertRaises(ValidationError): row.full_clean()
