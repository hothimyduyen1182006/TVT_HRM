(() => {
  const oNgayBatDau = document.querySelector('[name="ngay_bat_dau"]');
  const oNgayKetThuc = document.querySelector('[name="ngay_ket_thuc"]');
  const oSoNgayNghi = document.querySelector('#leave-days-count');
  const oChonTep = document.querySelector('.leave-file-input');
  const tenTepDaChon = document.querySelector('[data-evidence-name]');

  // Hiển thị số ngày tính cả ngày bắt đầu và ngày kết thúc.
  const capNhatSoNgayNghi = () => {
    if (!oSoNgayNghi) return;
    if (!oNgayBatDau?.value || !oNgayKetThuc?.value) {
      oSoNgayNghi.value = '0';
      return;
    }

    const mocBatDau = Date.parse(`${oNgayBatDau.value}T00:00:00Z`);
    const mocKetThuc = Date.parse(`${oNgayKetThuc.value}T00:00:00Z`);
    oSoNgayNghi.value = Number.isFinite(mocBatDau)
      && Number.isFinite(mocKetThuc)
      && mocKetThuc >= mocBatDau
      ? String(Math.floor((mocKetThuc - mocBatDau) / 86400000) + 1)
      : '0';
  };

  oNgayBatDau?.addEventListener('change', capNhatSoNgayNghi);
  oNgayKetThuc?.addEventListener('change', capNhatSoNgayNghi);
  capNhatSoNgayNghi();

  if (oChonTep && tenTepDaChon) oChonTep.addEventListener('change', () => {
    const [tep] = oChonTep.files;
    tenTepDaChon.textContent = tep ? `Đã chọn: ${tep.name}` : 'Chưa chọn tệp';
  });
})();
