(function () {
    function parseJsonScript(id) {
        const node = document.getElementById(id);
        if (!node) {
            return null;
        }

        try {
            let value = JSON.parse(node.textContent || "null");
            if (typeof value === "string") {
                value = JSON.parse(value);
            }
            return value;
        } catch (error) {
            console.error(`Failed to parse ${id}:`, error);
            return null;
        }
    }

    function setupReminderCountdown() {
        const reminderNode = document.querySelector("[data-next-reminder]");
        if (!reminderNode) {
            return;
        }

        const reminderAt = reminderNode.dataset.reminderAt || "";
        const reminderTitle = reminderNode.dataset.reminderTitle || "Next Trip";
        const reminderDate = new Date(reminderAt);
        if (Number.isNaN(reminderDate.getTime())) {
            return;
        }

        const countdownNode = document.getElementById("nextTripCountdown");
        const enableBtn = document.getElementById("enableReminderAlerts");
        const toastElement = document.getElementById("tripReminderToast");
        const toastBody = document.getElementById("tripReminderToastBody");
        const toastInstance = toastElement ? bootstrap.Toast.getOrCreateInstance(toastElement) : null;
        const storageKey = "trip-reminder-shown-" + reminderAt;

        function formatCountdown(ms) {
            const totalSeconds = Math.floor(ms / 1000);
            const days = Math.floor(totalSeconds / 86400);
            const hours = Math.floor((totalSeconds % 86400) / 3600);
            const minutes = Math.floor((totalSeconds % 3600) / 60);
            if (days > 0) {
                return `${days}d ${hours}h ${minutes}m`;
            }
            return `${hours}h ${minutes}m`;
        }

        function canNotify() {
            return "Notification" in window;
        }

        function showReminderNotice() {
            if (localStorage.getItem(storageKey) === "1") {
                return;
            }
            localStorage.setItem(storageKey, "1");

            const message = `${reminderTitle} time reached. Open My Trips for details.`;
            if (toastBody) {
                toastBody.textContent = message;
            }
            if (toastInstance) {
                toastInstance.show();
            }
            if (canNotify() && Notification.permission === "granted") {
                new Notification("Cholo Bd", {
                    body: message,
                });
            }
        }

        function updateCountdown() {
            if (!countdownNode) {
                return;
            }
            const diff = reminderDate.getTime() - Date.now();
            if (diff <= 0) {
                countdownNode.textContent = "Now";
                showReminderNotice();
                return;
            }
            countdownNode.textContent = formatCountdown(diff);
        }

        updateCountdown();
        setInterval(updateCountdown, 1000 * 20);

        if (!enableBtn) {
            return;
        }

        if (!canNotify()) {
            enableBtn.disabled = true;
            enableBtn.textContent = "Browser alert not supported";
        } else if (Notification.permission === "granted") {
            enableBtn.disabled = true;
            enableBtn.textContent = "Browser alert enabled";
        }

        enableBtn.addEventListener("click", async function () {
            if (!canNotify()) {
                return;
            }
            if (Notification.permission === "granted") {
                enableBtn.disabled = true;
                enableBtn.textContent = "Browser alert enabled";
                return;
            }
            const permission = await Notification.requestPermission();
            if (permission === "granted") {
                enableBtn.disabled = true;
                enableBtn.textContent = "Browser alert enabled";
                if (toastBody) {
                    toastBody.textContent = "Browser reminder permission granted.";
                }
                if (toastInstance) {
                    toastInstance.show();
                }
            }
        });
    }

    function setupReminderDestinationForm() {
        const form = document.getElementById("trip-reminder-form");
        if (!form) {
            return;
        }

        const divisionSelect = form.querySelector("[name='division']");
        const districtSelect = form.querySelector("[name='district']");
        const upazilaSelect = form.querySelector("[name='upazila']");
        const spotSelect = form.querySelector("[name='spot']");
        if (!divisionSelect || !districtSelect || !upazilaSelect || !spotSelect) {
            return;
        }

        const endpoints = {
            districts: form.dataset.districtUrl,
            upazilas: form.dataset.upazilaUrl,
            spots: form.dataset.spotUrl,
        };
        const districtData = parseJsonScript("trip-reminder-districts") || [];
        const upazilaData = parseJsonScript("trip-reminder-upazilas") || [];
        const spotData = parseJsonScript("trip-reminder-spots") || [];

        function resetSelect(select, placeholder) {
            select.innerHTML = "";
            const option = document.createElement("option");
            option.value = "";
            option.textContent = placeholder;
            select.appendChild(option);
        }

        function populateSelect(select, items, placeholder) {
            resetSelect(select, placeholder);
            for (const item of items) {
                const option = document.createElement("option");
                option.value = String(item.id);
                option.textContent = item.name;
                select.appendChild(option);
            }
        }

        async function fetchItems(url, queryKey, queryValue) {
            if (queryKey === "division_id" && districtData.length) {
                return districtData.filter(function (item) {
                    return String(item.division_id) === String(queryValue);
                });
            }

            if (queryKey === "district_id" && upazilaData.length) {
                return upazilaData.filter(function (item) {
                    return String(item.district_id) === String(queryValue);
                });
            }

            if (queryKey === "upazila_id" && spotData.length) {
                return spotData.filter(function (item) {
                    return String(item.upazila_id) === String(queryValue);
                });
            }

            const params = new URLSearchParams();
            params.set(queryKey, queryValue);

            const response = await fetch(`${url}?${params.toString()}`);
            if (!response.ok) {
                return [];
            }

            const payload = await response.json();
            return payload.results || [];
        }

        function hasValueOption(select) {
            return Array.from(select.options).some(function (option) {
                return option.value !== "";
            });
        }

        async function updateDistricts(preselect) {
            const divisionId = divisionSelect.value;
            populateSelect(districtSelect, [], "-- Select District --");
            populateSelect(upazilaSelect, [], "-- Select Upazila --");
            populateSelect(spotSelect, [], "-- Select Spot --");

            districtSelect.disabled = true;
            upazilaSelect.disabled = true;
            spotSelect.disabled = true;

            if (!divisionId) {
                return;
            }

            const districts = await fetchItems(endpoints.districts, "division_id", divisionId);
            populateSelect(districtSelect, districts, "-- Select District --");
            districtSelect.disabled = false;

            if (preselect) {
                districtSelect.value = String(preselect);
            }

            if (districtSelect.value) {
                await updateUpazilas(upazilaSelect.value);
            }
        }

        async function updateUpazilas(preselect) {
            const districtId = districtSelect.value;
            populateSelect(upazilaSelect, [], "-- Select Upazila --");
            populateSelect(spotSelect, [], "-- Select Spot --");

            upazilaSelect.disabled = true;
            spotSelect.disabled = true;

            if (!districtId) {
                return;
            }

            const upazilas = await fetchItems(endpoints.upazilas, "district_id", districtId);
            populateSelect(upazilaSelect, upazilas, "-- Select Upazila --");
            upazilaSelect.disabled = false;

            if (preselect) {
                upazilaSelect.value = String(preselect);
            }

            if (upazilaSelect.value) {
                await updateSpots(spotSelect.value);
            }
        }

        async function updateSpots(preselect) {
            const upazilaId = upazilaSelect.value;
            populateSelect(spotSelect, [], "-- Select Spot --");
            spotSelect.disabled = true;

            if (!upazilaId) {
                return;
            }

            const spots = await fetchItems(endpoints.spots, "upazila_id", upazilaId);
            populateSelect(spotSelect, spots, "-- Select Spot --");
            spotSelect.disabled = false;

            if (preselect) {
                spotSelect.value = String(preselect);
            }
        }

        divisionSelect.addEventListener("change", async function () {
            await updateDistricts();
        });

        districtSelect.addEventListener("change", async function () {
            await updateUpazilas();
        });

        upazilaSelect.addEventListener("change", async function () {
            await updateSpots();
        });

        async function syncCascadeFromCurrentSelection() {
            const currentDivision = divisionSelect.value;
            const currentDistrict = districtSelect.value;
            const currentUpazila = upazilaSelect.value;
            const currentSpot = spotSelect.value;

            if (!currentDivision) {
                districtSelect.disabled = true;
                upazilaSelect.disabled = true;
                spotSelect.disabled = true;
                return;
            }

            if (!hasValueOption(districtSelect) || currentDistrict) {
                await updateDistricts(currentDistrict);
                return;
            }

            districtSelect.disabled = false;
        }

        syncCascadeFromCurrentSelection();
        window.addEventListener("pageshow", function () {
            window.setTimeout(syncCascadeFromCurrentSelection, 0);
        });
        window.setTimeout(syncCascadeFromCurrentSelection, 150);
    }

    function setupRouteTracker() {
        const routeData = parseJsonScript("next-trip-route-data");
        if (!routeData) {
            return;
        }

        const statusNode = document.getElementById("nextTripTrackingStatus");
        const distanceNode = document.getElementById("nextTripDistance");
        const currentLocationNode = document.getElementById("nextTripCurrentLocation");
        const noteNode = document.getElementById("nextTripRouteNote");
        const fastestLink = document.getElementById("nextTripFastestRoute");
        const drivingLink = document.getElementById("nextTripDrivingRoute");
        const transitLink = document.getElementById("nextTripTransitRoute");
        const googleMapIframe = document.getElementById("nextTripGoogleMap");
        const routeMapNode = document.getElementById("nextTripRouteMap");
        const routeMapFallback = document.getElementById("nextTripRouteFallbackMap");

        const destination = {
            lat: routeData.latitude,
            lng: routeData.longitude,
            query: routeData.destination_query,
            label: `${routeData.spot_name}, ${routeData.district}`,
        };

        function buildOsmEmbedUrl(origin) {
            if (typeof destination.lat !== "number" || typeof destination.lng !== "number") {
                return "";
            }

            const points = [{ lat: destination.lat, lng: destination.lng }];
            if (origin && typeof origin.lat === "number" && typeof origin.lng === "number") {
                points.push(origin);
            }

            const latitudes = points.map(function (point) {
                return point.lat;
            });
            const longitudes = points.map(function (point) {
                return point.lng;
            });

            const minLat = Math.min.apply(null, latitudes);
            const maxLat = Math.max.apply(null, latitudes);
            const minLng = Math.min.apply(null, longitudes);
            const maxLng = Math.max.apply(null, longitudes);

            const latPadding = Math.max(0.05, (maxLat - minLat) * 0.35);
            const lngPadding = Math.max(0.05, (maxLng - minLng) * 0.35);

            const bottom = Math.max(-90, minLat - latPadding);
            const top = Math.min(90, maxLat + latPadding);
            const left = Math.max(-180, minLng - lngPadding);
            const right = Math.min(180, maxLng + lngPadding);
            const markerPoint = origin && typeof origin.lat === "number" && typeof origin.lng === "number"
                ? origin
                : destination;

            const params = new URLSearchParams();
            params.set(
                "bbox",
                `${left.toFixed(6)},${bottom.toFixed(6)},${right.toFixed(6)},${top.toFixed(6)}`
            );
            params.set("layer", "mapnik");
            params.set("marker", `${markerPoint.lat.toFixed(6)},${markerPoint.lng.toFixed(6)}`);
            return `https://www.openstreetmap.org/export/embed.html?${params.toString()}`;
        }

        function showRouteMapFallback(origin) {
            if (!routeMapFallback) {
                return;
            }

            const embedUrl = buildOsmEmbedUrl(origin);
            if (!embedUrl) {
                return;
            }

            if (routeMapFallback.getAttribute("src") !== embedUrl) {
                routeMapFallback.setAttribute("src", embedUrl);
            }
            routeMapFallback.classList.remove("d-none");
            if (routeMapNode) {
                routeMapNode.classList.add("d-none");
            }
        }

        function hideRouteMapFallback() {
            if (!routeMapFallback) {
                return;
            }

            routeMapFallback.classList.add("d-none");
            if (routeMapNode) {
                routeMapNode.classList.remove("d-none");
            }
        }

        function setLink(link, travelMode, origin) {
            if (!link || !destination.query) {
                return;
            }

            const params = new URLSearchParams();
            params.set("api", "1");
            params.set("destination", destination.query);
            if (origin) {
                params.set("origin", `${origin.lat.toFixed(6)},${origin.lng.toFixed(6)}`);
            }
            if (travelMode) {
                params.set("travelmode", travelMode);
            }
            link.href = `https://www.google.com/maps/dir/?${params.toString()}`;
        }

        function setGoogleIframe(origin) {
            if (!googleMapIframe || !destination.query) {
                return;
            }

            const currentSrc = googleMapIframe.getAttribute("src") || "";
            const keyMatch = currentSrc.match(/key=([^&]+)/);
            if (!keyMatch) {
                return;
            }

            const params = new URLSearchParams();
            params.set("key", decodeURIComponent(keyMatch[1]));
            params.set("destination", destination.query);
            if (origin) {
                params.set("origin", `${origin.lat.toFixed(6)},${origin.lng.toFixed(6)}`);
            } else {
                params.set("q", destination.query);
            }
            googleMapIframe.src = origin
                ? `https://www.google.com/maps/embed/v1/directions?${params.toString()}`
                : `https://www.google.com/maps/embed/v1/place?${params.toString()}`;
        }

        setLink(fastestLink, "", null);
        setLink(drivingLink, "driving", null);
        setLink(transitLink, "transit", null);
        setGoogleIframe(null);

        function haversineDistanceKm(origin, target) {
            const earthRadiusKm = 6371;
            const lat1 = origin.lat * Math.PI / 180;
            const lat2 = target.lat * Math.PI / 180;
            const deltaLat = (target.lat - origin.lat) * Math.PI / 180;
            const deltaLng = (target.lng - origin.lng) * Math.PI / 180;

            const a =
                Math.sin(deltaLat / 2) * Math.sin(deltaLat / 2) +
                Math.cos(lat1) * Math.cos(lat2) *
                Math.sin(deltaLng / 2) * Math.sin(deltaLng / 2);
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
            return earthRadiusKm * c;
        }

        function formatLatLng(position) {
            return `${position.lat.toFixed(5)}, ${position.lng.toFixed(5)}`;
        }

        let map = null;
        let destinationMarker = null;
        let currentMarker = null;
        let routeLine = null;
        let lastOrigin = null;
        let tileLoadObserved = false;

        function refreshRouteMap() {
            if (!map) {
                return;
            }

            map.invalidateSize();
        }

        function scheduleRouteMapRefresh() {
            if (!map) {
                return;
            }

            window.requestAnimationFrame(function () {
                refreshRouteMap();
                window.setTimeout(refreshRouteMap, 120);
                window.setTimeout(refreshRouteMap, 400);
            });
        }

        if (window.L && routeMapNode && typeof destination.lat === "number" && typeof destination.lng === "number") {
            try {
                map = L.map(routeMapNode).setView([destination.lat, destination.lng], 9);
                const tileLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                    maxZoom: 18,
                    attribution: "&copy; OpenStreetMap contributors",
                });

                tileLayer.on("load", function () {
                    tileLoadObserved = true;
                    hideRouteMapFallback();
                    scheduleRouteMapRefresh();
                });
                tileLayer.on("tileerror", function () {
                    if (!tileLoadObserved) {
                        showRouteMapFallback(lastOrigin);
                    }
                });
                tileLayer.addTo(map);

                destinationMarker = L.marker([destination.lat, destination.lng]).addTo(map);
                destinationMarker.bindPopup(`Destination: ${destination.label}`);
                destinationMarker.openPopup();

                map.whenReady(scheduleRouteMapRefresh);
                window.addEventListener("load", scheduleRouteMapRefresh);
                window.addEventListener("resize", scheduleRouteMapRefresh);
                document.addEventListener("visibilitychange", function () {
                    if (!document.hidden) {
                        scheduleRouteMapRefresh();
                    }
                });
                window.setTimeout(function () {
                    if (tileLoadObserved) {
                        scheduleRouteMapRefresh();
                        return;
                    }
                    showRouteMapFallback(lastOrigin);
                }, 1400);
            } catch (error) {
                console.error("Failed to initialize next trip route map:", error);
                showRouteMapFallback(null);
            }
        } else if (typeof destination.lat === "number" && typeof destination.lng === "number") {
            showRouteMapFallback(null);
        } else if (noteNode) {
            noteNode.textContent = "Destination saved. Exact route opens in Google Maps, but this spot has no map coordinates yet.";
        }

        function updateMapWithCurrentPosition(origin) {
            if (!map || typeof destination.lat !== "number" || typeof destination.lng !== "number") {
                return;
            }

            const currentLatLng = [origin.lat, origin.lng];
            const destinationLatLng = [destination.lat, destination.lng];

            if (!currentMarker) {
                currentMarker = L.circleMarker(currentLatLng, {
                    radius: 8,
                    color: "#ffffff",
                    weight: 2,
                    fillColor: "#255f3d",
                    fillOpacity: 0.95,
                }).addTo(map);
                currentMarker.bindPopup("Your live location");
            } else {
                currentMarker.setLatLng(currentLatLng);
            }

            if (!routeLine) {
                routeLine = L.polyline([currentLatLng, destinationLatLng], {
                    color: "#255f3d",
                    weight: 3,
                    opacity: 0.8,
                    dashArray: "8 6",
                }).addTo(map);
            } else {
                routeLine.setLatLngs([currentLatLng, destinationLatLng]);
            }

            map.fitBounds([currentLatLng, destinationLatLng], {padding: [24, 24]});
            scheduleRouteMapRefresh();
        }

        function updateCurrentPosition(origin) {
            lastOrigin = origin;
            if (statusNode) {
                statusNode.textContent = "Live location active";
            }
            if (currentLocationNode) {
                currentLocationNode.textContent = formatLatLng(origin);
            }

            setLink(fastestLink, "", origin);
            setLink(drivingLink, "driving", origin);
            setLink(transitLink, "transit", origin);
            setGoogleIframe(origin);

            if (typeof destination.lat !== "number" || typeof destination.lng !== "number") {
                if (distanceNode) {
                    distanceNode.textContent = "Destination has no coordinates";
                }
                return;
            }

            const distanceKm = haversineDistanceKm(origin, destination);
            if (distanceNode) {
                distanceNode.textContent = `${distanceKm.toFixed(1)} km away`;
            }
            updateMapWithCurrentPosition(origin);
            if (routeMapFallback && !routeMapFallback.classList.contains("d-none")) {
                showRouteMapFallback(origin);
            }
        }

        function handleLocationError(error) {
            if (statusNode) {
                statusNode.textContent = "Live location unavailable";
            }

            if (!noteNode) {
                return;
            }

            if (error && error.code === 1) {
                noteNode.textContent = "Location permission was denied. Google Maps buttons still work and can use your device location there.";
                return;
            }

            noteNode.textContent = "Could not detect your current location. You can still open the destination in Google Maps.";
        }

        if (!("geolocation" in navigator)) {
            handleLocationError();
            return;
        }

        navigator.geolocation.getCurrentPosition(
            function (position) {
                updateCurrentPosition({
                    lat: position.coords.latitude,
                    lng: position.coords.longitude,
                });
            },
            handleLocationError,
            {
                enableHighAccuracy: true,
                timeout: 12000,
                maximumAge: 60000,
            }
        );

        navigator.geolocation.watchPosition(
            function (position) {
                updateCurrentPosition({
                    lat: position.coords.latitude,
                    lng: position.coords.longitude,
                });
            },
            handleLocationError,
            {
                enableHighAccuracy: true,
                timeout: 20000,
                maximumAge: 10000,
            }
        );
    }

    function setupSelectionPreviewMap() {
        const mapNode = document.getElementById("nextTripSelectionMap");
        const noteNode = document.getElementById("nextTripSelectionNote");
        const spotSelect = document.querySelector("#trip-reminder-form [name='spot']");
        const spotData = parseJsonScript("trip-reminder-spots") || [];
        if (!mapNode || !spotSelect || !window.L) {
            return;
        }

        const map = L.map(mapNode).setView([23.685, 90.3563], 7);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 18,
            attribution: "&copy; OpenStreetMap contributors",
        }).addTo(map);

        let marker = null;

        function setNote(message) {
            if (noteNode) {
                noteNode.textContent = message;
            }
        }

        function updatePreview() {
            const selectedSpot = spotData.find(function (item) {
                return String(item.id) === String(spotSelect.value);
            });

            if (!selectedSpot) {
                if (marker) {
                    map.removeLayer(marker);
                    marker = null;
                }
                map.setView([23.685, 90.3563], 7);
                setNote("এখন Bangladesh overview map দেখানো হচ্ছে.");
                return;
            }

            if (selectedSpot.latitude == null || selectedSpot.longitude == null) {
                setNote("এই spot-এর coordinates নেই, তাই exact map preview দেখানো যাচ্ছে না.");
                return;
            }

            const latLng = [Number(selectedSpot.latitude), Number(selectedSpot.longitude)];
            if (!marker) {
                marker = L.marker(latLng).addTo(map);
            } else {
                marker.setLatLng(latLng);
            }
            marker.bindPopup(
                `${selectedSpot.name}<br>${selectedSpot.upazila__name || ""}, ${selectedSpot.upazila__district__name || ""}`
            );
            marker.openPopup();
            map.setView(latLng, 14);
            setNote("Selected destination preview map.");
        }

        spotSelect.addEventListener("change", updatePreview);
        window.setTimeout(function () {
            map.invalidateSize();
            updatePreview();
        }, 150);
    }

    setupReminderCountdown();
    setupReminderDestinationForm();
    setupRouteTracker();
    setupSelectionPreviewMap();
})();
