"""Prepare an isolated month of realistic workflow states for existing TVT employees."""
import sqlite3
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from bang_cong.models import KyCong, ChamCong, LichLamViec, LichSuTangCa
from bang_cong.services import calculations as attendance_calculations
from bang_cong.services.workflow import save_record, approve_employee
from thuong.models import Bonus
from thuong.views import calculate_automatic
from nhan_vien.access import has_role, HR, DIRECTOR
from nhan_vien.models import Employee
from nghi_phep.models import LeaveRequest, LeaveDay
from bang_luong.models import PayrollPeriod, PayrollInput, PayrollAdjustment, PayrollRecord, PayrollAuditLog
from bang_luong.services.calculations import calculate_payroll
from bang_luong.services.inputs import save_input
from bang_luong.services.workflow import approve_record


YEAR, MONTH = 2026, 10
MARKER = 'prepare_october_training'
VERSION = 'october-workflows-v1'


class Command(BaseCommand):
    help = 'Chuẩn bị tình huống công/thưởng/lương tháng 10/2026 cho NV01–NV08; không chi trả, không ghi đè.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Kiểm tra bằng transaction rồi hoàn tác toàn bộ.')

    def handle(self, *args, **options):
        if getattr(attendance_calculations, 'OT_POLICY', '') != 'automatic-checkout-1700-v1':
            raise CommandError('Cần bản OT tự động từ check-out trước khi chuẩn bị bộ dữ liệu này.')
        if PayrollAuditLog.objects.filter(action=MARKER, period__attendance_period__nam=YEAR,
                                         period__attendance_period__thang=MONTH).exists():
            self.stdout.write('Bộ tình huống tháng 10/2026 đã có; giữ nguyên mọi thao tác bạn đã thực hiện.')
            return
        self._require_empty_month()
        people = {e.code: e for e in Employee.objects.filter(code__in=[f'NV{i:02}' for i in range(1,9)]).select_related('user','department')}
        if len(people) != 8 or any(not e.is_active or not e.user.is_active or e.hire_date > date(YEAR,MONTH,1) for e in people.values()):
            raise CommandError('Cần đủ 8 nhân viên NV01–NV08 đang hoạt động và đã vào làm trước tháng 10.')
        if Employee.objects.filter(is_active=True,hire_date__lte=date(YEAR,MONTH,31)).exclude(pk__in=[e.pk for e in people.values()]).exists():
            raise CommandError('Có nhân viên khác ngoài NV01–NV08 cần dữ liệu trong kỳ; dừng để không tạo kỳ công thiếu người.')
        hr, director = people['NV05'].user, people['NV08'].user
        if not has_role(hr, HR) or not has_role(director, DIRECTOR):
            raise CommandError('NV05 cần quyền Nhân sự; NV08 cần quyền Giám đốc.')
        if not options['dry_run']:
            self._backup()
        try:
            with transaction.atomic():
                self._require_empty_month()
                period = KyCong(nam=YEAR,thang=MONTH,gio_bat_dau=time(8),bat_dau_nghi_trua=time(12),
                    ket_thuc_nghi_trua=time(13),gio_ket_thuc=time(17),gio_chuan=8)
                period.full_clean(); period.save()
                for number in range(1,32):
                    day = date(YEAR,MONTH,number)
                    LichLamViec.objects.create(ngay=day,loai_ngay='work' if day.weekday()<5 else 'rest',
                        cong_chuan=1 if day.weekday()<5 else 0,ghi_chu='' if day.weekday()<5 else 'Nghỉ hằng tuần')
                self._leaves(people, hr)
                for code, employee in sorted(people.items()):
                    for calendar_day in LichLamViec.objects.filter(ngay__year=YEAR,ngay__month=MONTH,loai_ngay='work').order_by('ngay'):
                        day = calendar_day.ngay
                        values = dict(nhan_vien=employee,ngay=day,trang_thai='present',
                            gio_vao=time(7,55+day.day%3),gio_ra=time(17),ghi_chu='')
                        if code=='NV02' and day.day in [5,16]:
                            values.update(gio_vao=time(8,20 if day.day==5 else 45),ghi_chu='Đi trễ, tính theo thời gian thực tế')
                        if code=='NV03' and day.day in [7,19]:
                            values.update(gio_vao=time(8),gio_ra=time(19) if day.day==7 else time(18,30),
                                ghi_chu='Hoàn thành đơn hàng sản xuất, giữ giờ ra thực tế')
                        if code=='NV04' and day.day==12:
                            values.update(trang_thai='leave',gio_vao=None,gio_ra=None,ghi_chu='Nghỉ phép năm đã được duyệt')
                        if code=='NV04' and day.day==30:
                            values.update(trang_thai='incomplete',gio_vao=None,gio_ra=None,ghi_chu='Đang chờ xử lý đơn nghỉ phép; cần cập nhật chấm công sau khi có kết quả')
                        if code=='NV05' and day.day==14:
                            values.update(trang_thai='absent',gio_vao=None,gio_ra=None,ghi_chu='Nghỉ không phép, không tính công ngày này')
                        if code=='NV05' and day.day==21:
                            values.update(trang_thai='incomplete',gio_vao=time(8),gio_ra=None,ghi_chu='Thiếu check-out; cần đối chiếu giờ ra trước khi duyệt')
                        if code=='NV05' and day.day==20:
                            values.update(gio_ra=time(18),ghi_chu='Hoàn tất hồ sơ nhân sự cuối ngày')
                        if code=='NV06' and day.day==15:
                            values.update(trang_thai='leave',gio_vao=None,gio_ra=None,ghi_chu='Nghỉ không lương đã được duyệt')
                        if code=='NV06' and day.day==16:
                            values.update(gio_ra=time(16),ghi_chu='Về sớm một giờ, tính công theo thời gian thực tế')
                        if code=='NV06' and day.day==8:
                            values.update(gio_ra=time(18),ghi_chu='Bảo trì hệ thống sau giờ làm việc')
                        if code=='NV07' and day.day==9:
                            values.update(gio_vao=time(8),gio_ra=time(12),ghi_chu='Làm buổi sáng, nghỉ phép hưởng lương nửa ngày buổi chiều')
                        if code=='NV07' and day.day==13:
                            values.update(gio_vao=time(9),ghi_chu='Đi trễ một giờ; không tạo khoản phạt tiền riêng')
                        record = save_record(hr,ChamCong(**values),'Nhập dữ liệu chấm công tháng 10/2026')
                        if code=='NV01' and day.day==9:
                            record.gio_vao=time(8,12)
                            save_record(hr,record,'Ghi nhận ban đầu cần đối chiếu máy chấm công')
                            record.gio_vao=time(7,58)
                            save_record(hr,record,'Đã đối chiếu log máy, điều chỉnh đúng giờ vào thực tế')
                save_record(hr,ChamCong(nhan_vien=people['NV03'],ngay=date(YEAR,MONTH,24),
                    trang_thai='present',gio_vao=time(8),gio_ra=time(12),ghi_chu='Sản xuất bổ sung sáng thứ Bảy; không cộng công thường'),
                    'Ghi nhận giờ làm thực tế ngày nghỉ tuần')
                for code in ['NV02','NV03','NV06']:
                    approve_employee(hr,people[code],period.pk)
                self._bonuses(people,hr,director)
                payroll, _ = PayrollPeriod.objects.get_or_create(attendance_period=period)
                self._inputs(people,period,payroll,hr)
                calculate_payroll(hr,payroll.pk,'Chuẩn bị phiếu lương tháng 10 từ công đã duyệt và thưởng hợp lệ')
                approve_record(director,PayrollRecord.objects.get(period=payroll,employee=people['NV02']).pk)
                PayrollAuditLog.objects.create(period=payroll,actor=hr,action=MARKER,
                    reason='Chuẩn bị dữ liệu thực hành; không thực hiện thanh toán',
                    snapshot=[{'version':VERSION,'year':YEAR,'month':MONTH,'employees':sorted(people)}])
                if options['dry_run']:
                    transaction.set_rollback(True)
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from error
        self.stdout.write(self.style.SUCCESS('Kiểm tra thành công, chưa ghi dữ liệu.' if options['dry_run'] else
            'Đã chuẩn bị 10/2026: 31 ngày lịch, 177 bản ghi công, 5 đơn phép, 8 đầu vào lương, 3 phiếu lương.'))
        self.stdout.write('Công duyệt sẵn: NV02/NV03/NV06. Lương NV02 đã duyệt; NV03/NV06 chờ duyệt. Không có phiếu đã chi trả.')
        self.stdout.write('NV04 cần xử lý phép 30/10; NV05 thiếu giờ ra 21/10; NV08 cần xác nhận căn cứ BH/thuế trước khi tính lương.')

    def _require_empty_month(self):
        checks = [
            KyCong.objects.filter(nam=YEAR,thang=MONTH),
            ChamCong.objects.filter(ngay__year=YEAR,ngay__month=MONTH),
            LichLamViec.objects.filter(ngay__year=YEAR,ngay__month=MONTH),
            LichSuTangCa.objects.filter(ngay__year=YEAR,ngay__month=MONTH),
            Bonus.objects.filter(year=YEAR,month=MONTH),
            LeaveDay.objects.filter(date__year=YEAR,date__month=MONTH),
            LeaveRequest.objects.filter(start_date__lte=date(YEAR,MONTH,31),end_date__gte=date(YEAR,MONTH,1)),
        ]
        if any(rows.exists() for rows in checks):
            raise CommandError('Tháng 10/2026 đã có dữ liệu. Dừng để không ghi đè; không xóa hoặc đặt lại dữ liệu.')

    def _leaves(self, people, hr):
        specs = [('NV04',12,'annual',True,Decimal(1),'approved','Việc gia đình đã sắp xếp công việc'),
                 ('NV06',15,'unpaid',False,Decimal(1),'approved','Nghỉ việc riêng không hưởng lương'),
                 ('NV07',9,'annual',True,Decimal('.5'),'approved','Nghỉ phép buổi chiều để giải quyết việc gia đình'),
                 ('NV04',30,'annual',True,Decimal(1),'pending','Xin nghỉ một ngày, đang chờ sắp xếp người thay thế'),
                 ('NV07',23,'personal',False,Decimal(1),'rejected','Đề nghị nghỉ việc riêng')]
        for code,number,kind,paid,units,state,reason in specs:
            day=date(YEAR,MONTH,number)
            request=LeaveRequest(employee=people[code],start_date=day,end_date=day,leave_type=kind,
                paid=paid,units=units,status=state,reason=reason)
            if state!='pending':
                request.reviewed_by=hr
                request.reviewed_at=timezone.now()
            if state=='rejected':
                request.review_note='Trùng lịch bàn giao khách hàng; nhân viên đã đi làm bình thường.'
            request.full_clean();request.save()
            if state=='approved':
                leave=LeaveDay(employee=people[code],date=day,units=units,paid=paid,reason=reason,approved=True)
                leave.full_clean();leave.save()

    def _bonuses(self, people, hr, director):
        states={'NV01':'draft','NV02':'approved','NV03':'pending','NV04':'draft',
                'NV05':'draft','NV06':'draft','NV07':'rejected','NV08':'approved'}
        extras={'NV01':('Hiệu quả chiến dịch truyền thông',250000,'Hoàn thành nội dung truyền thông theo kế hoạch'),
                'NV03':('Hoàn thành đơn hàng',400000,'Hoàn thành tiến độ đơn hàng sản xuất'),
                'NV06':('Hỗ trợ vận hành hệ thống',300000,'Hoàn thành bảo trì hệ thống theo kế hoạch'),
                'NV07':('Vượt chỉ tiêu kinh doanh',500000,'Đề xuất ghi nhận kết quả kinh doanh tháng 10')}
        for code,employee in sorted(people.items()):
            automatic,_=calculate_automatic(employee,MONTH,YEAR)
            rows=list(automatic)
            if code in extras:
                name,amount,reason=extras[code]
                rows.append(('other',name,Decimal(amount),reason))
            for kind,name,amount,reason in rows:
                row=Bonus(employee=employee,year=YEAR,month=MONTH,bonus_type=kind,name=name,
                    amount=amount,reason=reason,status=states[code],proposed_by=hr,proposed_at=timezone.now())
                if states[code] in ['approved','rejected']:
                    row.approved_by=director
                    row.approved_at=timezone.now()
                if states[code]=='rejected':
                    row.rejection_reason='Cần đối chiếu lại hồ sơ kết quả trước khi gửi lại đề xuất.'
                row.full_clean();row.save()

    def _inputs(self, people, attendance, payroll, hr):
        standard=sum(LichLamViec.objects.filter(ngay__year=YEAR,ngay__month=MONTH).values_list('cong_chuan',flat=True),Decimal(0))
        for code,employee in sorted(people.items()):
            rate=(employee.base_salary/standard/attendance.gio_chuan).quantize(Decimal('.0001'),rounding=ROUND_HALF_UP)
            basis=('Dữ liệu thực hành 10/2026: giả định cá nhân cư trú, 0 người phụ thuộc; giảm trừ bản thân '
                   '15.500.000đ, BH 10,5% lương cơ bản; thu nhập tính thuế bậc đầu không quá 10 triệu, thuế suất 5%. '
                   'Phụ cấp ăn trưa giả định đủ điều kiện loại khỏi thu nhập chịu thuế. Các nhân viên có OT '
                   'vẫn dưới ngưỡng chịu thuế kể cả tính toàn bộ tiền OT. Cần kiểm tra hồ sơ thật trước khi áp dụng thực tế.')
            if code=='NV08':
                basis+=' Chưa xác nhận: lương hồ sơ 20 triệu khác lương hợp đồng 11,5 triệu; HR cần đối chiếu căn cứ BH/thuế.'
            inputs=PayrollInput(period=payroll,employee=employee,insurance_base=employee.base_salary,
                insurance_rates={'BHXH':'0.08','BHYT':'0.015','BHTN':'0.01'},tax_method='resident_2026',
                tax_basis=basis,insurance_basis='Giả định thuộc diện BH bắt buộc, lương đóng BH bằng lương cơ bản; cần HR đối chiếu hồ sơ thực tế.',
                verified=code!='NV08',overtime_hourly_rate=rate,
                overtime_basis=f'Lương cơ bản {employee.base_salary} / {standard} công / 8 giờ; không gồm thưởng, ăn trưa và khoản hỗ trợ.')
            save_input(hr,inputs)
            adjustment=PayrollAdjustment(period=payroll,employee=employee,name='Phụ cấp ăn trưa',kind='allowance',
                amount=450000,tax_category='meal_cash',basis='Phụ cấp ăn trưa cố định tháng 10/2026, không tính vào căn cứ lương giờ OT.',approved=True)
            save_input(hr,adjustment)
        extras=[('NV03','Hỗ trợ điều kiện làm việc','allowance',200000,True,'Khoản hỗ trợ điều kiện làm việc tháng 10 đã chấp thuận'),
                ('NV06','Hỗ trợ điện thoại','allowance',200000,True,'Hỗ trợ liên lạc phục vụ công việc tháng 10'),
                ('NV06','Hoàn ứng tạm ứng','deduction',300000,True,'Hoàn lại tiền tạm ứng đã nhận; không trùng giảm công, không phạt đi trễ'),
                ('NV07','Đề xuất hỗ trợ điện thoại','allowance',200000,False,'Chờ kiểm tra chứng từ chi phí liên lạc'),
                ('NV07','Đề xuất hoàn ứng','deduction',200000,False,'Chờ đối chiếu số tiền đã tạm ứng, chưa được trừ lương')]
        for code,name,kind,amount,approved,basis in extras:
            save_input(hr,PayrollAdjustment(period=payroll,employee=people[code],name=name,kind=kind,
                amount=amount,approved=approved,basis=basis))

    def _backup(self):
        name=str(settings.DATABASES['default']['NAME'])
        if settings.DATABASES['default']['ENGINE']!='django.db.backends.sqlite3' or name==':memory:' or name.startswith('file:memorydb_'):
            return
        database=Path(name).resolve()
        folder=Path(settings.BASE_DIR)/'.local-backups'
        folder.mkdir(exist_ok=True)
        target=folder/('before-october-training-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
        source=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
        destination=sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close();source.close()
        self.stdout.write('Đã sao lưu vào .local-backups/'+target.name)
