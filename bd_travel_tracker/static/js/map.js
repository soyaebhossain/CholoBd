(function () {
    const page = document.getElementById("map-page");
    if (!page) {
        return;
    }

    const divisionSelect = document.getElementById("divisionFilter");
    const districtSelect = document.getElementById("districtFilter");
    const upazilaSelect = document.getElementById("upazilaFilter");
    const spotSelect = document.getElementById("spotFilter");

    const placeholder = document.getElementById("insightPlaceholder");
    const insightBody = document.getElementById("insightBody");
    const recentHistoryBody = document.getElementById("recentHistoryBody");

    function parseJsonScript(id) {
        const el = document.getElementById(id);
        if (!el) {
            return [];
        }
        try {
            let value = JSON.parse(el.textContent || "[]");
            if (typeof value === "string") {
                value = JSON.parse(value);
            }
            return Array.isArray(value) ? value : [];
        } catch (error) {
            console.error(`Failed to parse ${id}:`, error);
            return [];
        }
    }

    const divisionData = parseJsonScript("division-data");
    const spotData = parseJsonScript("spot-map-data");

    const endpoints = {
        districts: page.dataset.districtUrl,
        upazilas: page.dataset.upazilaUrl,
        spots: page.dataset.spotUrl,
        insight: page.dataset.insightUrl,
    };

    const map = L.map("map").setView([23.685, 90.3563], 7);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
        attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);

    const markersBySpotId = new Map();
    let activeSpotId = null;

    function createMapMarkers() {
        const bounds = [];
        for (const spot of spotData) {
            if (spot.latitude == null || spot.longitude == null) {
                continue;
            }

            const marker = L.circleMarker([spot.latitude, spot.longitude], {
                radius: 7,
                color: "#ffffff",
                weight: 2,
                fillColor: spot.my_visits > 0 ? "#2a9d8f" : "#7a8594",
                fillOpacity: 0.95,
            }).addTo(map);

            marker.bindPopup(
                `<strong>${spot.name}</strong><br>` +
                `${spot.upazila}, ${spot.district}<br>` +
                `Division: ${spot.division}<br>` +
                `Your visits: ${spot.my_visits} | Total visits: ${spot.total_visits}`
            );

            markersBySpotId.set(String(spot.id), marker);
            bounds.push([spot.latitude, spot.longitude]);
        }

        if (bounds.length) {
            map.fitBounds(bounds, {padding: [20, 20]});
        }
    }

    function fillSelect(select, items, placeholderText) {
        select.innerHTML = "";
        const placeholderOption = document.createElement("option");
        placeholderOption.value = "";
        placeholderOption.textContent = placeholderText;
        select.appendChild(placeholderOption);

        const sortedItems = [...items].sort((a, b) =>
            (a.name || "").localeCompare((b.name || ""), "bn")
        );
        for (const item of sortedItems) {
            const option = document.createElement("option");
            option.value = String(item.id);
            option.textContent = item.name;
            select.appendChild(option);
        }
    }

    async function fetchOptions(url, key, value) {
        const params = new URLSearchParams();
        params.set(key, value);

        const response = await fetch(`${url}?${params.toString()}`);
        if (!response.ok) {
            return [];
        }

        const payload = await response.json();
        return payload.results || [];
    }

    function resetInsight() {
        placeholder.classList.remove("d-none");
        insightBody.classList.add("d-none");
        recentHistoryBody.innerHTML = "";
    }

    function setText(id, value) {
        const node = document.getElementById(id);
        node.textContent = value;
    }

    function renderHistoryRows(rows) {
        recentHistoryBody.innerHTML = "";

        if (!rows.length) {
            const row = document.createElement("tr");
            row.innerHTML = '<td colspan="4" class="text-muted">No trip history for this spot.</td>';
            recentHistoryBody.appendChild(row);
            return;
        }

        for (const item of rows) {
            const row = document.createElement("tr");
            row.innerHTML = `
                <td>${item.visitor}</td>
                <td>${item.travel_date}</td>
                <td>${item.hotel}</td>
                <td>${Number(item.total_cost).toFixed(2)}</td>
            `;
            recentHistoryBody.appendChild(row);
        }
    }

    function highlightMarker(spotId) {
        if (activeSpotId && markersBySpotId.has(activeSpotId)) {
            const previousMarker = markersBySpotId.get(activeSpotId);
            const prevData = spotData.find((spot) => String(spot.id) === activeSpotId);
            previousMarker.setStyle({
                radius: 7,
                fillColor: prevData && prevData.my_visits > 0 ? "#2a9d8f" : "#7a8594",
            });
        }

        activeSpotId = spotId || null;

        if (!spotId || !markersBySpotId.has(spotId)) {
            return;
        }

        const marker = markersBySpotId.get(spotId);
        marker.setStyle({radius: 11, fillColor: "#4ea46e"});
        marker.openPopup();
        map.flyTo(marker.getLatLng(), 10, {duration: 0.5});
    }

    async function loadInsight(spotId) {
        if (!spotId) {
            resetInsight();
            highlightMarker(null);
            return;
        }

        const response = await fetch(`${endpoints.insight}?spot_id=${spotId}`);
        if (!response.ok) {
            resetInsight();
            highlightMarker(spotId);
            return;
        }

        const payload = await response.json();

        placeholder.classList.add("d-none");
        insightBody.classList.remove("d-none");

        setText("insightSpotName", payload.spot.name || "-");
        setText("insightDivision", payload.spot.division || "-");
        setText("insightDistrict", payload.spot.district || "-");
        setText("insightUpazila", payload.spot.upazila || "-");
        setText("insightTotalVisits", payload.stats.total_visits ?? 0);
        setText("insightUniqueVisitors", payload.stats.unique_visitors ?? 0);
        setText("insightAvgCost", Number(payload.stats.average_cost || 0).toFixed(2));
        setText("insightLastVisit", payload.stats.last_visit_date || "-");

        renderHistoryRows(payload.recent_history || []);
        highlightMarker(String(spotId));
    }

    async function onDivisionChange() {
        fillSelect(districtSelect, [], "-- Select District --");
        fillSelect(upazilaSelect, [], "-- Select Upazila --");
        fillSelect(spotSelect, [], "-- Select Spot --");

        districtSelect.disabled = true;
        upazilaSelect.disabled = true;
        spotSelect.disabled = true;
        resetInsight();

        if (!divisionSelect.value) {
            return;
        }

        const districts = await fetchOptions(endpoints.districts, "division_id", divisionSelect.value);
        fillSelect(districtSelect, districts, "-- Select District --");
        districtSelect.disabled = false;
    }

    async function onDistrictChange() {
        fillSelect(upazilaSelect, [], "-- Select Upazila --");
        fillSelect(spotSelect, [], "-- Select Spot --");

        upazilaSelect.disabled = true;
        spotSelect.disabled = true;
        resetInsight();

        if (!districtSelect.value) {
            return;
        }

        const upazilas = await fetchOptions(endpoints.upazilas, "district_id", districtSelect.value);
        fillSelect(upazilaSelect, upazilas, "-- Select Upazila --");
        upazilaSelect.disabled = false;
    }

    async function onUpazilaChange() {
        fillSelect(spotSelect, [], "-- Select Spot --");
        spotSelect.disabled = true;
        resetInsight();

        if (!upazilaSelect.value) {
            return;
        }

        const spots = await fetchOptions(endpoints.spots, "upazila_id", upazilaSelect.value);
        fillSelect(spotSelect, spots, "-- Select Spot --");
        spotSelect.disabled = false;
    }

    divisionSelect.addEventListener("change", onDivisionChange);
    districtSelect.addEventListener("change", onDistrictChange);
    upazilaSelect.addEventListener("change", onUpazilaChange);
    spotSelect.addEventListener("change", () => loadInsight(spotSelect.value));

    fillSelect(divisionSelect, divisionData, "-- Select Division --");

    createMapMarkers();
    resetInsight();
})();
