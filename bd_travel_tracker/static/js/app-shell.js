(function () {
    "use strict";

    const loadingBar = document.querySelector(".app-loading-bar");
    const loadingFill = loadingBar && loadingBar.querySelector("span");
    let progressTimer;

    if (!loadingBar || !loadingFill) {
        return;
    }

    function startProgress() {
        window.clearTimeout(progressTimer);
        loadingFill.style.width = "18%";
        loadingBar.classList.add("is-active");
        document.body.classList.add("app-is-navigating");
        progressTimer = window.setTimeout(function () {
            loadingFill.style.width = "72%";
        }, 140);
    }

    function finishProgress() {
        window.clearTimeout(progressTimer);
        loadingFill.style.width = "100%";
        window.setTimeout(function () {
            loadingBar.classList.remove("is-active");
            document.body.classList.remove("app-is-navigating");
            loadingFill.style.width = "0";
        }, 180);
    }

    document.addEventListener("click", function (event) {
        const link = event.target.closest("a[href]");
        if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
        }

        const destination = new URL(link.href, window.location.href);
        if (link.target === "_blank" || link.hasAttribute("download") || destination.origin !== window.location.origin || destination.href === window.location.href || destination.hash) {
            return;
        }
        startProgress();
    });

    document.addEventListener("submit", startProgress);
    window.addEventListener("pageshow", finishProgress);
    window.addEventListener("load", finishProgress);
}());
