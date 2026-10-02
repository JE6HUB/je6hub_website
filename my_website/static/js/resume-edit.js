/*
 * Resume のページ内編集 (superuser のみ読み込む)。
 * 「Resume を編集」で文字をその場で書き換えられるようにし、項目の追加・並べ替え・削除もできる。
 * 保存は表示中の言語の文字だけを送る (もう一方の言語の文字はサーバー側で項目の id ごとに引き継ぐ)。
 */
(() => {
    const editor = document.getElementById('resume-editor');
    const resume = document.getElementById('resume');
    const hero = document.querySelector('.resume-hero-text');
    if (!editor || !resume || !hero) return;

    const cfg = editor.dataset;
    const status = editor.querySelector('.resume-editor-status');
    const saveButton = editor.querySelector('[data-action="save"]');
    const imageOptions = editor.querySelector('.resume-edit-image-options');
    const csrf = editor.querySelector('[name=csrfmiddlewaretoken]').value;
    let editing = false;
    let dirty = false;

    const plaintextMode = (() => {
        const probe = document.createElement('div');
        try { probe.contentEditable = 'plaintext-only'; } catch (e) { return 'true'; }
        return probe.contentEditable === 'plaintext-only' ? 'plaintext-only' : 'true';
    })();

    const icon = (name) => `<span class="material-symbols-outlined" aria-hidden="true">${name}</span>`;
    const textOf = (el) => (el ? el.innerText.replace(/ /g, ' ').trim() : '');
    const placeholder = (field) => cfg['ph' + field.charAt(0).toUpperCase() + field.slice(1)] || '';

    function insertPlainText(event) {
        event.preventDefault();
        const text = (event.clipboardData || window.clipboardData).getData('text/plain');
        document.execCommand('insertText', false, text);
    }

    function makeEditable(el) {
        el.contentEditable = plaintextMode;
        el.spellcheck = true;
        el.dataset.placeholder = placeholder(el.dataset.edit);
        el.addEventListener('paste', insertPlainText);
        if (!el.hasAttribute('data-multiline')) {
            el.addEventListener('keydown', (event) => {
                if (event.key === 'Enter') event.preventDefault();
            });
        }
    }

    function makeLinesEditable(ul) {
        ul.contentEditable = 'true';
        if (!ul.querySelector('li')) ul.innerHTML = '<li><br></li>';
        ul.addEventListener('paste', insertPlainText);
        // 箇条書きを全部消しても <li> が 1 つは残るようにする
        ul.addEventListener('input', () => {
            if (!ul.querySelector('li')) ul.innerHTML = '<li><br></li>';
        });
    }

    function itemTools(item, list) {
        const tools = document.createElement('div');
        tools.className = 'resume-edit-tools';
        tools.contentEditable = 'false';
        tools.innerHTML =
            `<button type="button" data-tool="up" title="${cfg.labelUp}" aria-label="${cfg.labelUp}">${icon('arrow_upward')}</button>` +
            `<button type="button" data-tool="down" title="${cfg.labelDown}" aria-label="${cfg.labelDown}">${icon('arrow_downward')}</button>` +
            `<button type="button" data-tool="remove" title="${cfg.labelRemove}" aria-label="${cfg.labelRemove}">${icon('delete')}</button>`;
        tools.addEventListener('click', (event) => {
            const button = event.target.closest('button');
            if (!button) return;
            event.preventDefault();
            const tool = button.dataset.tool;
            if (tool === 'up' && item.previousElementSibling) list.insertBefore(item, item.previousElementSibling);
            if (tool === 'down' && item.nextElementSibling) list.insertBefore(item.nextElementSibling, item);
            if (tool === 'remove') item.remove();
            dirty = true;
        });
        item.prepend(tools);

        if (list.dataset.list === 'projects') {
            const panel = document.createElement('div');
            panel.className = 'resume-edit-project';
            const select = imageOptions.cloneNode(true);
            select.hidden = false;
            select.className = '';
            select.value = item.dataset.image || '';
            select.dataset.field = 'image';
            panel.innerHTML = `<label>${cfg.labelLink}</label><input type="text" data-field="url" placeholder="/blog/ · https://…"><label>${cfg.labelImage}</label>`;
            panel.querySelector('input').value = item.dataset.url || '';
            panel.append(select);
            panel.addEventListener('input', () => { dirty = true; });
            item.append(panel);
        }
    }

    function prepareItem(item, list) {
        item.querySelectorAll('[data-edit]').forEach(makeEditable);
        item.querySelectorAll('[data-edit-lines]').forEach(makeLinesEditable);
        itemTools(item, list);
    }

    function addButton(list) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'resume-edit-add';
        button.innerHTML = `${icon('add')}${cfg.labelAdd}`;
        button.addEventListener('click', () => {
            const template = document.querySelector(`template[data-template="${list.dataset.list}"]`);
            const item = template.content.firstElementChild.cloneNode(true);
            list.append(item);
            prepareItem(item, list);
            dirty = true;
            item.querySelector('[data-edit]').focus();
        });
        list.after(button);
    }

    function start() {
        editing = true;
        document.body.classList.add('resume-editing');
        hero.querySelectorAll('[data-edit]').forEach(makeEditable);
        resume.querySelector('[data-edit="summary"]') && makeEditable(resume.querySelector('[data-edit="summary"]'));
        resume.querySelectorAll('[data-list]').forEach((list) => {
            list.querySelectorAll(':scope > [data-item]').forEach((item) => prepareItem(item, list));
            addButton(list);
        });
        // 編集中はタイルのリンクで別のページへ移動しない
        resume.addEventListener('click', (event) => {
            if (editing && event.target.closest('a')) event.preventDefault();
        });
        document.addEventListener('input', () => { dirty = true; });
        // 画面の外にある .jh-reveal (スクロールで表示する演出) も編集できるように全部表示する
        document.querySelectorAll('.jh-reveal').forEach((el) => el.classList.add('visible'));
        hero.querySelector('[data-edit]').focus();
    }

    function collect() {
        const data = {
            name: textOf(hero.querySelector('[data-edit="name"]')),
            tagline: textOf(hero.querySelector('[data-edit="tagline"]')),
            summary: textOf(resume.querySelector('[data-edit="summary"]')),
        };
        resume.querySelectorAll('[data-list]').forEach((list) => {
            data[list.dataset.list] = [...list.querySelectorAll(':scope > [data-item]')].map((item) => {
                const row = { id: item.dataset.id || '' };
                item.querySelectorAll('[data-edit]').forEach((el) => { row[el.dataset.edit] = textOf(el); });
                item.querySelectorAll('[data-edit-lines]').forEach((ul) => {
                    row[ul.dataset.editLines] = [...ul.querySelectorAll('li')].map(textOf).filter(Boolean);
                });
                item.querySelectorAll('[data-field]').forEach((input) => { row[input.dataset.field] = input.value.trim(); });
                return row;
            });
        });
        return data;
    }

    async function save() {
        saveButton.disabled = true;
        status.classList.remove('is-error');
        status.textContent = cfg.labelSaving;
        try {
            const response = await fetch(cfg.saveUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' },
                body: JSON.stringify({ lang: cfg.lang, data: collect() }),
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok || !result.ok) throw new Error(result.error || cfg.labelError);
            dirty = false;
            window.location.reload();
        } catch (error) {
            status.textContent = error.message || cfg.labelError;
            status.classList.add('is-error');
            saveButton.disabled = false;
        }
    }

    editor.hidden = false;
    editor.addEventListener('click', (event) => {
        const action = event.target.closest('[data-action]')?.dataset.action;
        if (action === 'start') start();
        if (action === 'save') save();
        if (action === 'cancel' && (!dirty || window.confirm(cfg.labelDiscard))) {
            dirty = false;
            window.location.reload();
        }
    });
    window.addEventListener('beforeunload', (event) => {
        if (dirty) event.preventDefault();
    });
})();
