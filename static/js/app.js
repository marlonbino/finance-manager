window.PesaPlan = (function () {
    const money = new Intl.NumberFormat('en-KE', {
        style: 'currency',
        currency: 'KES',
        maximumFractionDigits: 0
    });

    function formatMoney(value) {
        return money.format(Number(value || 0)).replace('Ksh', 'KES');
    }

    function escapeHtml(value) {
        return String(value || '').replace(/[&<>"']/g, char => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        }[char]));
    }

    function relativeTime(iso) {
        const date = new Date(iso);
        const diff = Date.now() - date.getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'Just now';
        if (mins < 60) return `${mins}m ago`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours}h ago`;
        const days = Math.floor(hours / 24);
        if (days < 7) return `${days}d ago`;
        return date.toLocaleDateString('en-KE', { day: 'numeric', month: 'short' });
    }

    let toastTimer;

    function showToast(message, type = 'error') {
        let toast = document.getElementById('pp-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'pp-toast';
            toast.className = 'toast';
            document.body.appendChild(toast);
        }
        toast.textContent = message;
        toast.className = `toast show ${type === 'success' ? 'success' : type === 'error' ? 'error' : ''}`;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toast.classList.remove('show'), 3200);
    }

    async function fetchJson(url, options) {
        const res = await fetch(url, options);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(data.error || 'Something went wrong');
        }
        return data;
    }

    function getSheetRoot() {
        return document.getElementById('money-sheet');
    }

    function openSheet(mode) {
        const root = getSheetRoot();
        if (!root) return;
        root.classList.add('open');
        root.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        if (mode) {
            setSheetMode(mode);
        }
    }

    function closeSheet() {
        const root = getSheetRoot();
        if (!root) return;
        root.classList.remove('open');
        root.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
        document.querySelectorAll('.type-grid').forEach(el => {
            el.style.display = '';
        });
        setSheetMode('spend');
    }

    function setSheetMode(mode) {
        document.querySelectorAll('.type-tile').forEach(tile => {
            tile.classList.toggle('active', tile.dataset.mode === mode);
        });
        document.querySelectorAll('.sheet-form').forEach(form => {
            form.classList.toggle('active', form.dataset.mode === mode);
        });
        const titles = {
            spend: ['Log expense', 'Record what you spent and from which wallet.'],
            income: ['Record income', 'We split it across your wallets automatically.'],
            transfer: ['Move money', 'Shift balance between wallets — not spending.'],
            wallet: ['Add wallet', 'Name it and set its share of income (total must reach 100%).'],
            edit: ['Edit wallet', 'Update name, cap, or income share.']
        };
        const [title, sub] = titles[mode] || titles.spend;
        const titleEl = document.getElementById('sheet-title');
        const subEl = document.getElementById('sheet-sub');
        if (titleEl) titleEl.textContent = title;
        if (subEl) subEl.textContent = sub;
    }

    function bindSheet() {
        const root = getSheetRoot();
        if (!root) return;

        root.querySelectorAll('[data-sheet-close]').forEach(el => {
            el.addEventListener('click', closeSheet);
        });

        document.querySelectorAll('.type-tile').forEach(tile => {
            tile.addEventListener('click', () => setSheetMode(tile.dataset.mode));
        });

        document.addEventListener('keydown', event => {
            if (event.key === 'Escape') closeSheet();
        });
    }

    document.addEventListener('DOMContentLoaded', bindSheet);

    return {
        formatMoney,
        escapeHtml,
        relativeTime,
        showToast,
        fetchJson,
        openSheet,
        closeSheet,
        setSheetMode
    };
})();
