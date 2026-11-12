(() => {
  const fileInput = document.querySelector('.leave-file-input');
  const selectedFile = document.querySelector('[data-evidence-name]');

  if (!fileInput || !selectedFile) return;

  fileInput.addEventListener('change', () => {
    const [file] = fileInput.files;
    selectedFile.textContent = file ? `Đã chọn: ${file.name}` : 'Chưa chọn tệp';
  });
})();
