document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('bm-submit-form')) {
const form = document.getElementById('bm-submit-form');
 const dialog = document.getElementById('bm-confirm-dialog');
 const confirmButton = document.getElementById('bm-confirm-approve');
 let confirmed = false;
 form.addEventListener('submit', event => {
   if (confirmed) return;
   event.preventDefault();
   const selected = [...document.querySelectorAll('.bm-select-row:checked')];
   document.getElementById('bm-confirm-text').textContent = selected.length
     ? `Bạn có chắc muốn gửi duyệt bảng thưởng của ${selected.length} nhân viên đã chọn không?`
     : 'Vui lòng chọn ít nhất một nhân viên.';
   confirmButton.hidden = !selected.length;
   dialog.showModal();
 });
 confirmButton.addEventListener('click', () => {
   confirmed = true;
   confirmButton.disabled = true;
   dialog.close();
   form.requestSubmit();
 });
  }

  if (document.getElementById('bm-bulk-form')) {
(() => {
 const rows = [...document.querySelectorAll('.bm-select-row')];

 document.getElementById('bm-bulk-form')?.addEventListener('submit', event => {
   const selected = rows.filter(row => row.checked);
   if (!selected.length) { event.preventDefault(); moXacNhan('Vui lòng chọn ít nhất một nhân viên.', false); return; }
   if (event.submitter?.value === 'reject') {
     event.preventDefault();
     if (selected.length > 1) { moXacNhan('Bạn chỉ có thể từ chối từng người. Vui lòng chọn một nhân viên và thực hiện từ chối riêng.', false); return; }
     moTuChoi(event.currentTarget);
   } else if (!daXacNhanDuyet) {
     event.preventDefault();
     moXacNhan(`Bạn có chắc muốn duyệt bảng thưởng của ${selected.length} nhân viên đã chọn không?`, true);
   }
 });
 const xacNhanDuyet = document.getElementById('bm-confirm-dialog');
 const nutDuyet = document.getElementById('bm-confirm-approve');
 const nutDong = xacNhanDuyet.querySelector('.bm-confirm-actions [data-bm-close-dialog]');
 function moXacNhan(noiDung, choPhepDuyet) {
   document.getElementById('bm-confirm-text').textContent = noiDung;
   nutDuyet.hidden = !choPhepDuyet;
   nutDong.textContent = choPhepDuyet ? 'Hủy' : 'OK';
   xacNhanDuyet.showModal();
 }
 let daXacNhanDuyet = false;
 nutDuyet.addEventListener('click', () => {
   daXacNhanDuyet = true;
   const form = document.getElementById('bm-bulk-form');
   form.requestSubmit(form.querySelector('button[value="approve"]'));
 });
 const dialog = document.getElementById('bm-reject-dialog');
 const reason = document.getElementById('bm-reject-text');
 let formTuChoi;
 function moTuChoi(form) {
   formTuChoi = form;
   reason.value = '';
   dialog.showModal();
   reason.focus();
 }
 document.getElementById('bm-reject-dialog-form').addEventListener('submit', event => {
   event.preventDefault();
   if (!reason.value.trim()) { reason.setCustomValidity('Vui lòng nhập lý do từ chối.'); reason.reportValidity(); return; }
   for (const [name, value] of [['ly_do', reason.value.trim()], ['action', 'reject']]) {
     let input = formTuChoi.querySelector(`input[name="${name}"]`);
     if (!input) { input = document.createElement('input'); input.type = 'hidden'; input.name = name; formTuChoi.append(input); }
     input.value = value;
   }
   HTMLFormElement.prototype.submit.call(formTuChoi);
 });
 reason.addEventListener('input', () => reason.setCustomValidity(''));
})();
  }

  if (document.getElementById('bm-select-all')) {
const chonTatCa = document.getElementById('bm-select-all');
const cacOChon = [...document.querySelectorAll('.bm-select-row')];
chonTatCa.addEventListener('change', () => {
 cacOChon.forEach(o => o.checked = chonTatCa.checked);
 chonTatCa.indeterminate = false;
});
cacOChon.forEach(o => o.addEventListener('change', () => {
 const soDaChon = cacOChon.filter(o => o.checked).length;
 chonTatCa.checked = soDaChon === cacOChon.length;
 chonTatCa.indeterminate = soDaChon > 0 && soDaChon < cacOChon.length;
}));
  }

  const deleteForms = document.querySelectorAll('[data-bm-delete-form]');
  if (deleteForms.length) {
    const dialog = document.getElementById('bm-confirm-dialog');
    const confirmButton = document.getElementById('bm-confirm-approve');
    let formToDelete;

    deleteForms.forEach(form => form.addEventListener('submit', event => {
      event.preventDefault();
      formToDelete = form;
      dialog.showModal();
    }));

    confirmButton.addEventListener('click', () => {
      confirmButton.disabled = true;
      formToDelete.submit();
    });
  }

  document.querySelectorAll('[data-bm-close-dialog]').forEach(button => {
    button.addEventListener('click', () => button.closest('dialog').close());
  });
});
