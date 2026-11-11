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
    // Delegation also supports the form loaded inside the settings dialog.
    module.addEventListener('click', event => {
        const addInsurance = event.target.closest('[data-add-insurance]');
        if (addInsurance) {
            const form = addInsurance.closest('form');
            const total = form.querySelector('#id_insurance-TOTAL_FORMS');
            const limit = form.querySelector('#id_insurance-MAX_NUM_FORMS');
            const index = Number(total.value);
            if (index >= Number(limit.value)) {
                addInsurance.disabled = true;
                return;
            }
            const html = form.querySelector('#pr-insurance-empty').innerHTML.replace(/__prefix__/g, index);
            form.querySelector('#pr-insurance-rows').insertAdjacentHTML('beforeend', html);
            total.value = index + 1;
        }
    });

    const settings = module.querySelector('#pr-inputs');
    if (!settings) return;
    const overview = settings.querySelector('[data-input-overview]');
    const editor = settings.querySelector('[data-input-editor]');
    const error = settings.querySelector('[data-input-error]');
    let pending = false;
    async function loadEditor(url, options = {}) {
        if (pending) return;
        pending = true;
        error.hidden = true;
        settings.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(url, {credentials: 'same-origin', ...options});
            if (response.redirected) {
                window.location.assign(response.url);
                return;
            }
            if (!response.ok) throw new Error('request failed');
            const page = new DOMParser().parseFromString(await response.text(), 'text/html');
            const content = page.querySelector('.pr-input-editor');
            if (!content) throw new Error('missing form');
            editor.replaceChildren(content);
            const form = editor.querySelector('form');
            if (form) form.action = url;
            overview.hidden = true;
            editor.hidden = false;
            settings.scrollTop = 0;
            const focus = editor.querySelector('input:not([type="hidden"]), select, a');
            if (focus) focus.focus();
        } catch (_) {
            error.textContent = 'Không thể tải hoặc lưu thiết lập. Vui lòng kiểm tra kết nối và thử lại.';
            error.hidden = false;
        } finally {
            pending = false;
            settings.removeAttribute('aria-busy');
        }
    }
    settings.addEventListener('click', event => {
        const link = event.target.closest('a');
        if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        if (link.hasAttribute('data-input-back')) {
            event.preventDefault();
            if (pending) return;
            editor.hidden = true;
            overview.hidden = false;
            editor.replaceChildren();
        } else if (new URL(link.href).pathname.startsWith('/payroll/inputs/')) {
            event.preventDefault();
            loadEditor(link.href);
        }
    });
    settings.addEventListener('submit', event => {
        if (!event.target.matches('#pr-input-form')) return;
        event.preventDefault();
        loadEditor(event.target.action, {method: 'POST', body: new FormData(event.target)});
    });
    if (settings.hasAttribute('data-auto-open')) settings.showModal();
});
