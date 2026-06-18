(function () {
    function parseJsonScript(id) {
        const node = document.getElementById(id);
        if (!node) {
            return null;
        }
        try {
            return JSON.parse(node.textContent || "null");
        } catch (error) {
            return null;
        }
    }

    function escapeHtml(value) {
        return String(value || "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }

    function resetSelect(select, placeholder) {
        if (!select) {
            return;
        }
        select.innerHTML = "";
        const option = document.createElement("option");
        option.value = "";
        option.textContent = placeholder;
        select.appendChild(option);
    }

    function populateSelect(select, items, placeholder) {
        resetSelect(select, placeholder);
        items.forEach(function (item) {
            const option = document.createElement("option");
            option.value = String(item.id);
            option.textContent = item.name;
            select.appendChild(option);
        });
    }

    async function fetchItems(url, queryKey, queryValue) {
        const params = new URLSearchParams();
        params.set(queryKey, queryValue);
        const response = await fetch(url + "?" + params.toString());
        if (!response.ok) {
            return [];
        }
        const payload = await response.json();
        return payload.results || [];
    }

    function initDestinationFilters() {
        const form = document.getElementById("destinationFilterForm");
        if (!form) {
            return;
        }

        const divisionSelect = document.getElementById("destinationDivision");
        const districtSelect = document.getElementById("destinationDistrict");
        const upazilaSelect = document.getElementById("destinationUpazila");

        if (!divisionSelect || !districtSelect || !upazilaSelect) {
            return;
        }

        const endpoints = {
            districts: form.dataset.districtUrl,
            upazilas: form.dataset.upazilaUrl,
        };

        async function updateDistricts(preselect) {
            const divisionId = divisionSelect.value;
            populateSelect(districtSelect, [], "All districts");
            populateSelect(upazilaSelect, [], "All upazilas");
            districtSelect.disabled = true;
            upazilaSelect.disabled = true;

            if (!divisionId) {
                return;
            }

            const districts = await fetchItems(endpoints.districts, "division_id", divisionId);
            populateSelect(districtSelect, districts, "All districts");
            districtSelect.disabled = false;

            if (preselect) {
                districtSelect.value = String(preselect);
            }
        }

        async function updateUpazilas(preselect) {
            const districtId = districtSelect.value;
            populateSelect(upazilaSelect, [], "All upazilas");
            upazilaSelect.disabled = true;

            if (!districtId) {
                return;
            }

            const upazilas = await fetchItems(endpoints.upazilas, "district_id", districtId);
            populateSelect(upazilaSelect, upazilas, "All upazilas");
            upazilaSelect.disabled = false;

            if (preselect) {
                upazilaSelect.value = String(preselect);
            }
        }

        divisionSelect.addEventListener("change", function () {
            updateDistricts();
        });

        districtSelect.addEventListener("change", function () {
            updateUpazilas();
        });
    }

    function initExplorerMap(spots) {
        const mapNode = document.getElementById("destinationsMap");
        if (!mapNode) {
            return;
        }

        if (!window.L || !Array.isArray(spots) || !spots.length) {
            mapNode.innerHTML = "<div class=\"destination-map-empty\">No mapped destinations in this result set.</div>";
            return;
        }

        const mappedSpots = spots.filter(function (spot) {
            return typeof spot.latitude === "number" && typeof spot.longitude === "number";
        });

        if (!mappedSpots.length) {
            mapNode.innerHTML = "<div class=\"destination-map-empty\">No mapped destinations in this result set.</div>";
            return;
        }

        const map = L.map(mapNode, {
            scrollWheelZoom: false,
        });
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: "&copy; OpenStreetMap contributors",
        }).addTo(map);

        const bounds = [];
        mappedSpots.forEach(function (spot) {
            const latLng = [spot.latitude, spot.longitude];
            bounds.push(latLng);

            let color = "#94a3b8";
            if (spot.my_visits > 0) {
                color = "#1f9d55";
            } else if (spot.is_saved) {
                color = "#2563eb";
            }

            const marker = L.circleMarker(latLng, {
                radius: 8,
                weight: 2,
                color: "#ffffff",
                fillColor: color,
                fillOpacity: 0.95,
            }).addTo(map);

            const popup = [
                "<div class=\"destination-map-popup\">",
                "<strong>" + escapeHtml(spot.name) + "</strong>",
                "<span>" + escapeHtml(spot.district) + " | " + escapeHtml(spot.upazila) + "</span>",
                "<small><i class=\"bi bi-star-fill\"></i> " + escapeHtml(spot.traveler_score) + " traveler score</small>",
                "<small><i class=\"bi bi-eye\"></i> " + escapeHtml(spot.total_visits) + " visits</small>",
                "<div class=\"destination-map-popup__actions\">",
                "<a href=\"" + escapeHtml(spot.detail_url) + "\">View</a>",
                "<a href=\"" + escapeHtml(spot.trip_url) + "\">Add Trip</a>",
                "</div>",
                "</div>",
            ].join("");

            marker.bindPopup(popup);
        });

        if (bounds.length === 1) {
            map.setView(bounds[0], 10);
        } else {
            map.fitBounds(bounds, {padding: [24, 24]});
        }
        window.setTimeout(function () {
            map.invalidateSize();
        }, 120);
    }

    function haversineDistanceKm(origin, destination) {
        const toRadians = function (value) {
            return value * (Math.PI / 180);
        };

        const earthRadiusKm = 6371;
        const dLat = toRadians(destination.latitude - origin.latitude);
        const dLng = toRadians(destination.longitude - origin.longitude);
        const lat1 = toRadians(origin.latitude);
        const lat2 = toRadians(destination.latitude);

        const a =
            Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.sin(dLng / 2) * Math.sin(dLng / 2) * Math.cos(lat1) * Math.cos(lat2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

        return earthRadiusKm * c;
    }

    function renderNearby(container, items) {
        container.innerHTML = "";
        items.forEach(function (item) {
            const node = document.createElement("a");
            node.className = "destination-list__item";
            node.href = item.detail_url;
            node.innerHTML = [
                "<div>",
                "<strong>" + escapeHtml(item.name) + "</strong>",
                "<span>" + escapeHtml(item.district) + " | " + escapeHtml(item.upazila) + "</span>",
                "</div>",
                "<div class=\"destination-list__meta\">",
                "<span><i class=\"bi bi-signpost-2\"></i> " + escapeHtml(item.distance) + " km</span>",
                "</div>",
            ].join("");
            container.appendChild(node);
        });
    }

    function initNearbyDestinations(spots) {
        const statusNode = document.getElementById("nearbyStatus");
        const listNode = document.getElementById("nearbyDestinations");
        const nearbyPanel = document.getElementById("nearbyPanel");
        const triggers = document.querySelectorAll("[data-nearby-trigger]");

        if (!statusNode || !listNode || !triggers.length) {
            return;
        }

        const mappedSpots = (Array.isArray(spots) ? spots : []).filter(function (spot) {
            return typeof spot.latitude === "number" && typeof spot.longitude === "number";
        });

        if (!mappedSpots.length) {
            statusNode.textContent = "No mapped destinations are available for nearby suggestions.";
            return;
        }

        function requestNearby(event) {
            if (event) {
                event.preventDefault();
            }
            if (nearbyPanel) {
                nearbyPanel.scrollIntoView({behavior: "smooth", block: "start"});
            }
            if (!navigator.geolocation) {
                statusNode.textContent = "Your browser does not support location-based suggestions.";
                return;
            }

            statusNode.textContent = "Detecting your current location...";
            navigator.geolocation.getCurrentPosition(
                function (position) {
                    const origin = {
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                    };
                    const nearest = mappedSpots
                        .map(function (spot) {
                            return Object.assign({}, spot, {
                                distance: haversineDistanceKm(origin, spot).toFixed(1),
                            });
                        })
                        .sort(function (left, right) {
                            return Number(left.distance) - Number(right.distance);
                        })
                        .slice(0, 4);

                    if (!nearest.length) {
                        statusNode.textContent = "No nearby destination matched the current result set.";
                        listNode.innerHTML = "";
                        return;
                    }

                    statusNode.textContent = "Closest matched destinations from your current location.";
                    renderNearby(listNode, nearest);
                },
                function () {
                    statusNode.textContent = "Location access was blocked. Enable it to see nearby destinations.";
                },
                {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 60000,
                }
            );
        }

        triggers.forEach(function (trigger) {
            trigger.addEventListener("click", requestNearby);
        });
    }

    function initDestinationDetailMap(detailSpot) {
        const mapNode = document.getElementById("destinationDetailMap");
        if (!mapNode) {
            return;
        }

        if (!window.L || !detailSpot || typeof detailSpot.latitude !== "number" || typeof detailSpot.longitude !== "number") {
            mapNode.innerHTML = "<div class=\"destination-map-empty\">Location coordinates are not available for this destination.</div>";
            return;
        }

        const map = L.map(mapNode, {
            scrollWheelZoom: false,
        }).setView([detailSpot.latitude, detailSpot.longitude], 10);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: "&copy; OpenStreetMap contributors",
        }).addTo(map);

        L.marker([detailSpot.latitude, detailSpot.longitude])
            .addTo(map)
            .bindPopup(escapeHtml(detailSpot.name))
            .openPopup();

        window.setTimeout(function () {
            map.invalidateSize();
        }, 120);
    }

    initDestinationFilters();
    initExplorerMap(parseJsonScript("destinations-map-data"));
    initNearbyDestinations(parseJsonScript("destinations-map-data"));
    initDestinationDetailMap(parseJsonScript("destination-detail-map-data"));
})();
