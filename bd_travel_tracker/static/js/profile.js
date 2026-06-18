(function () {
    const root = document.getElementById("profilePage");
    if (!root) {
        return;
    }

    const tabButtons = Array.from(document.querySelectorAll("[data-profile-tab]"));
    const tabPanels = Array.from(document.querySelectorAll("[data-profile-panel]"));
    const tabLinks = Array.from(document.querySelectorAll("[data-profile-tab-link]"));
    const defaultTab = root.dataset.defaultTab || "posts";
    const autoUploadForms = Array.from(document.querySelectorAll("[data-auto-upload-form]"));
    const editorCard = document.querySelector("[data-profile-editor]");
    const editorOpenButtons = Array.from(document.querySelectorAll("[data-profile-editor-open]"));
    const editorCloseButtons = Array.from(document.querySelectorAll("[data-profile-editor-close]"));
    const editorShouldStartOpen = root.dataset.editorOpen === "true";

    function setActiveTab(tabName, updateHash) {
        const hasTarget = tabPanels.some((panel) => panel.dataset.profilePanel === tabName);
        const targetTab = hasTarget ? tabName : defaultTab;

        tabButtons.forEach((button) => {
            button.classList.toggle("is-active", button.dataset.profileTab === targetTab);
        });

        tabPanels.forEach((panel) => {
            panel.classList.toggle("is-active", panel.dataset.profilePanel === targetTab);
        });

        if (updateHash) {
            window.history.replaceState(null, "", `#${targetTab}`);
        }
    }

    tabButtons.forEach((button) => {
        button.addEventListener("click", () => {
            setActiveTab(button.dataset.profileTab, true);
        });
    });

    tabLinks.forEach((link) => {
        link.addEventListener("click", () => {
            const target = link.dataset.profileTabLink;
            if (target) {
                setActiveTab(target, true);
            }
        });
    });

    const initialHash = window.location.hash.replace("#", "");
    setActiveTab(initialHash || defaultTab, false);

    function setEditorOpen(isOpen, shouldScroll) {
        if (!editorCard) {
            return;
        }

        root.classList.toggle("is-editor-open", isOpen);
        editorCard.hidden = !isOpen;

        if (isOpen && shouldScroll) {
            editorCard.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    setEditorOpen(editorShouldStartOpen, false);

    editorOpenButtons.forEach((button) => {
        button.addEventListener("click", () => {
            setEditorOpen(true, true);

            const focusTarget = button.dataset.profileFocusTarget;
            if (!focusTarget) {
                return;
            }

            window.setTimeout(() => {
                const input = document.getElementById(focusTarget);
                input?.focus();
            }, 200);
        });
    });

    editorCloseButtons.forEach((button) => {
        button.addEventListener("click", () => {
            setEditorOpen(false, false);
        });
    });

    autoUploadForms.forEach((form) => {
        const fileInput = form.querySelector('input[type="file"]');
        if (!fileInput) {
            return;
        }

        fileInput.addEventListener("change", () => {
            if (!fileInput.files || !fileInput.files.length) {
                return;
            }
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit();
                return;
            }
            form.submit();
        });
    });
})();
