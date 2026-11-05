document.addEventListener('DOMContentLoaded', () => {
    const module = document.querySelector('.payroll-module');
    if (!module) return;
    module.querySelectorAll('[data-open-dialog]').forEach(button => {
        button.addEventListener('click', () => {
            const dialog = document.getElementById(button.dataset.openDialog);
            if (dialog) dialog.showModal();
        });
    });
    module.querySelectorAll('[data-close-dialog]').forEach(button => {
        button.addEventListener('click', () => button.closest('dialog').close());
    });
    module.querySelectorAll('[data-print-payslip]').forEach(button => {
        button.addEventListener('click', () => window.print());
    });
    const addInsurance = module.querySelector('[data-add-insurance]');
    if (addInsurance) {
        addInsurance.addEventListener('click', () => {
            const total = module.querySelector('#id_insurance-TOTAL_FORMS');
            const limit = module.querySelector('#id_insurance-MAX_NUM_FORMS');
            const index = Number(total.value);
            if (index >= Number(limit.value)) {
                addInsurance.disabled = true;
                return;
            }
            const html = module.querySelector('#pr-insurance-empty').innerHTML.replace(/__prefix__/g, index);
            module.querySelector('#pr-insurance-rows').insertAdjacentHTML('beforeend', html);
            total.value = index + 1;
        });
    }
});
