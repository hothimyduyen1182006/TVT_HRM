# Ngoại lệ có sẵn của Django: khi được raise trong view, Django xử lý thành lỗi 403 (thiếu quyền).
from django.core.exceptions import PermissionDenied
# Dấu . chỉ module trong cùng app; import model để truy vấn hồ sơ nhân viên.
from .models import NhanVien

# Hằng số giữ tên các Group trong database; dùng lại để tránh gõ sai tên nhóm.
NHAN_SU = 'Nhân sự'
GIAM_DOC = 'Giám đốc'
TRUONG_PHONG = 'Trưởng phòng'

# nguoi_dung thường là request.user; *vai_tro gom các vai trò truyền vào thành tuple.
def co_vai_tro(nguoi_dung, *vai_tro): #Hàm co_vai_tro() – Kiểm tra quyền
    # and: phải đã đăng nhập; nếu False thì Python bỏ qua phần kiểm tra trong ngoặc.
    # or: superuser HOẶC thuộc ít nhất một nhóm yêu cầu; superuser không cần query nhóm.
    # groups là các Group của user; name__in lọc tên thuộc tuple; exists() trả True/False.
    return nguoi_dung.is_authenticated and (
        nguoi_dung.is_superuser or nguoi_dung.groups.filter(name__in=vai_tro).exists()
    )


# Khác co_vai_tro() chỉ trả bool, hàm này chặn luồng xử lý khi không đủ quyền.
def yeu_cau_vai_tro(nguoi_dung, *vai_tro): #Hàm này dùng để chặn người dùng không có quyền thực hiện thao tác.
    if not co_vai_tro(nguoi_dung, *vai_tro):
        # Phát sinh lỗi 403; đủ quyền thì hàm kết thúc bình thường để bên gọi chạy tiếp.
        raise PermissionDenied('Bạn không có quyền thực hiện thao tác này.')


# Trả QuerySet giới hạn phạm vi hồ sơ được xem; không trực tiếp dựng giao diện.
# Bên gọi vẫn cần yêu cầu đăng nhập, ví dụ dùng @login_required trong view.
def nhan_vien_duoc_hien_thi(nguoi_dung): #Hàm nhan_vien_duoc_hien_thi() – Lọc danh sách nhân viên
    # objects là manager truy vấn; select_related lấy kèm phòng ban/tài khoản bằng SQL JOIN.
    # Tránh query lặp khi đọc quan hệ; dòng này chưa lọc quyền và vẫn trả QuerySet.
    danh_sach_nhan_vien = NhanVien.objects.select_related('phong_ban', 'nguoi_dung')
    # Nhân sự/Giám đốc hoặc superuser xem toàn bộ; return kết thúc hàm tại nhánh phù hợp.
    if co_vai_tro(nguoi_dung, NHAN_SU, GIAM_DOC):
        return danh_sach_nhan_vien
    # Trưởng phòng chỉ xem nhân viên thuộc phòng mình thực sự được gán làm trưởng phòng.
    if co_vai_tro(nguoi_dung, TRUONG_PHONG):
        # __ đi qua quan hệ: nhân viên -> phòng ban -> trưởng phòng -> tài khoản trưởng phòng.
        # Tài khoản cuối đường dẫn phải bằng nguoi_dung đang kiểm tra.
        return danh_sach_nhan_vien.filter(phong_ban__truong_phong__nguoi_dung=nguoi_dung)
    # Bên trái là field của NhanVien; bên phải là biến tài khoản được truyền vào hàm.
    # Chỉ lấy hồ sơ chính chủ; filter vẫn trả QuerySet dù quan hệ OneToOne cho tối đa một hồ sơ.
    return danh_sach_nhan_vien.filter(nguoi_dung=nguoi_dung)
