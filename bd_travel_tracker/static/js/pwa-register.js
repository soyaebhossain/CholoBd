(function () {
    "use strict";

    if (!("serviceWorker" in navigator) || !window.isSecureContext) {
        return;
    }

    window.addEventListener("load", function () {
        navigator.serviceWorker.register("/service-worker.js", { scope: "/" }).catch(function () {
            // The web experience remains fully functional when installation is unavailable.
        });
    });
}());
