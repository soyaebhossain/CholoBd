(function () {
    const form = document.getElementById("trip-form");
    if (!form) {
        return;
    }

    const divisionSelect = document.getElementById("id_division");
    const districtSelect = document.getElementById("id_district");
    const upazilaSelect = document.getElementById("id_upazila");
    const spotSelect = document.getElementById("id_spot");
    const tripSourceSelect = document.getElementById("id_trip_source");
    const agencyNameInput = document.getElementById("id_agency_name");
    const agencyNameGroup = agencyNameInput
        ? agencyNameInput.closest("[data-agency-name-group]")
        : null;

    const endpoints = {
        districts: form.dataset.districtUrl,
        upazilas: form.dataset.upazilaUrl,
        spots: form.dataset.spotUrl,
    };

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
        const params = new URLSearchParams();
        params.set(queryKey, queryValue);

        const response = await fetch(`${url}?${params.toString()}`);
        if (!response.ok) {
            return [];
        }

        const payload = await response.json();
        return payload.results || [];
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

    function syncAgencyField() {
        if (!tripSourceSelect || !agencyNameInput || !agencyNameGroup) {
            return;
        }

        const isAgency = tripSourceSelect.value === "agency";
        agencyNameGroup.hidden = !isAgency;
        agencyNameInput.required = isAgency;

        if (!isAgency) {
            agencyNameInput.value = "";
        }
    }

    divisionSelect.addEventListener("change", async () => {
        await updateDistricts();
    });

    districtSelect.addEventListener("change", async () => {
        await updateUpazilas();
    });

    upazilaSelect.addEventListener("change", async () => {
        await updateSpots();
    });
    if (tripSourceSelect) {
        tripSourceSelect.addEventListener("change", syncAgencyField);
    }

    const initialDivision = divisionSelect.value;
    const initialDistrict = districtSelect.value;
    const initialUpazila = upazilaSelect.value;
    const initialSpot = spotSelect.value;

    if (initialDivision) {
        updateDistricts(initialDistrict)
            .then(() => updateUpazilas(initialUpazila))
            .then(() => updateSpots(initialSpot));
    } else {
        districtSelect.disabled = true;
        upazilaSelect.disabled = true;
        spotSelect.disabled = true;
    }

    syncAgencyField();
})();
