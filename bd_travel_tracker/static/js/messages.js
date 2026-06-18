(function () {
    const thread = document.getElementById("messageThread");
    if (thread) {
        thread.scrollTop = thread.scrollHeight;
    }

    const textarea = document.querySelector(".message-composer-textarea");
    const attachmentInput = document.querySelector(".message-attachment-input");
    const sendButton = document.querySelector("[data-send-button]");
    const selectedFile = document.querySelector("[data-selected-file]");
    const attachmentTriggers = document.querySelectorAll("[data-attachment-trigger]");
    const picker = document.querySelector("[data-message-picker]");
    const pickerGrid = picker ? picker.querySelector("[data-picker-grid]") : null;
    const pickerEmpty = picker ? picker.querySelector("[data-picker-empty]") : null;
    const pickerLabel = picker ? picker.querySelector("[data-picker-label]") : null;
    const pickerSearch = picker ? picker.querySelector("[data-picker-search]") : null;
    const pickerOpenButtons = document.querySelectorAll("[data-picker-open]");
    const pickerTabs = picker ? picker.querySelectorAll("[data-picker-tab]") : [];
    const pickerCloseButton = picker ? picker.querySelector("[data-picker-close]") : null;

    if (!textarea || !sendButton) {
        return;
    }

    const sendIcon = sendButton.querySelector("i");
    const sendIconClass = sendButton.dataset.sendIcon;
    const likeIconClass = sendButton.dataset.likeIcon;
    const defaultAccept = attachmentInput ? attachmentInput.getAttribute("accept") || "" : "";
    const attachmentAcceptMap = {
        audio: "audio/*,.mp3,.wav,.ogg,.m4a",
        media: "image/*,video/*,.jpg,.jpeg,.png,.webp,.gif,.mp4,.webm,.mov",
        gif: "image/gif,.gif",
    };
    const recentStorageKey = "tour_point_message_picker_recent";

    const pickerCatalog = {
        emoji: {
            label: "Emoji",
            section: "Smiley faces and expressions",
            type: "emoji",
            items: [
                { id: "emoji-grinning", label: "Grinning face", value: "\u{1F600}" },
                { id: "emoji-smile", label: "Smiling face", value: "\u{1F603}" },
                { id: "emoji-laugh", label: "Laughing face", value: "\u{1F606}" },
                { id: "emoji-joy", label: "Face with tears of joy", value: "\u{1F602}" },
                { id: "emoji-rofl", label: "Rolling on the floor laughing", value: "\u{1F923}" },
                { id: "emoji-blush", label: "Blushing face", value: "\u{1F60A}" },
                { id: "emoji-wink", label: "Winking face", value: "\u{1F609}" },
                { id: "emoji-heart-eyes", label: "Heart eyes", value: "\u{1F60D}" },
                { id: "emoji-cool", label: "Cool face", value: "\u{1F60E}" },
                { id: "emoji-thinking", label: "Thinking face", value: "\u{1F914}" },
                { id: "emoji-party", label: "Partying face", value: "\u{1F973}" },
                { id: "emoji-relieved", label: "Relieved face", value: "\u{1F60C}" },
                { id: "emoji-sunglasses", label: "Smiling with sunglasses", value: "\u{1F60E}" },
                { id: "emoji-teary", label: "Smiling with tear", value: "\u{1F972}" },
                { id: "emoji-halo", label: "Smiling with halo", value: "\u{1F607}" },
                { id: "emoji-mindblown", label: "Exploding head", value: "\u{1F92F}" },
                { id: "emoji-star", label: "Star struck", value: "\u{1F929}" },
                { id: "emoji-sleepy", label: "Sleepy face", value: "\u{1F62A}" },
                { id: "emoji-neutral", label: "Neutral face", value: "\u{1F610}" },
                { id: "emoji-pleading", label: "Pleading face", value: "\u{1F97A}" },
                { id: "emoji-kiss", label: "Face blowing a kiss", value: "\u{1F618}" },
                { id: "emoji-hug", label: "Hugging face", value: "\u{1F917}" },
                { id: "emoji-celebrate", label: "Sparkles", value: "\u{2728}" },
                { id: "emoji-wave", label: "Waving hand", value: "\u{1F44B}" }
            ]
        },
        reactions: {
            label: "Reactions",
            section: "Quick reactions and gestures",
            type: "emoji",
            items: [
                { id: "reaction-like", label: "Thumbs up", value: "\u{1F44D}" },
                { id: "reaction-love", label: "Red heart", value: "\u{2764}\u{FE0F}" },
                { id: "reaction-clap", label: "Clapping hands", value: "\u{1F44F}" },
                { id: "reaction-pray", label: "Folded hands", value: "\u{1F64F}" },
                { id: "reaction-muscle", label: "Flexed biceps", value: "\u{1F4AA}" },
                { id: "reaction-ok", label: "OK hand", value: "\u{1F44C}" },
                { id: "reaction-victory", label: "Victory hand", value: "\u{270C}\u{FE0F}" },
                { id: "reaction-fire", label: "Fire", value: "\u{1F525}" },
                { id: "reaction-star", label: "Glowing star", value: "\u{1F31F}" },
                { id: "reaction-hundred", label: "One hundred", value: "\u{1F4AF}" },
                { id: "reaction-check", label: "Check mark", value: "\u{2705}" },
                { id: "reaction-rocket", label: "Rocket", value: "\u{1F680}" },
                { id: "reaction-heart-hands", label: "Heart hands", value: "\u{1FAF6}" },
                { id: "reaction-eyes", label: "Eyes", value: "\u{1F440}" },
                { id: "reaction-speaking", label: "Speaking head", value: "\u{1F5E3}\u{FE0F}" },
                { id: "reaction-phone", label: "Telephone", value: "\u{1F4DE}" },
                { id: "reaction-party", label: "Confetti ball", value: "\u{1F38A}" },
                { id: "reaction-microphone", label: "Microphone", value: "\u{1F3A4}" }
            ]
        },
        travel: {
            label: "Travel",
            section: "Trips, routes, and places",
            type: "emoji",
            items: [
                { id: "travel-plane", label: "Airplane", value: "\u{2708}\u{FE0F}" },
                { id: "travel-bus", label: "Bus", value: "\u{1F68C}" },
                { id: "travel-train", label: "Train", value: "\u{1F686}" },
                { id: "travel-car", label: "Car", value: "\u{1F697}" },
                { id: "travel-ferry", label: "Ferry", value: "\u{26F4}" },
                { id: "travel-suitcase", label: "Suitcase", value: "\u{1F9F3}" },
                { id: "travel-map", label: "Map", value: "\u{1F5FA}\u{FE0F}" },
                { id: "travel-compass", label: "Compass", value: "\u{1F9ED}" },
                { id: "travel-camera", label: "Camera", value: "\u{1F4F8}" },
                { id: "travel-beach", label: "Beach", value: "\u{1F3D6}\u{FE0F}" },
                { id: "travel-mountain", label: "Mountain", value: "\u{26F0}\u{FE0F}" },
                { id: "travel-city", label: "Cityscape", value: "\u{1F3D9}\u{FE0F}" },
                { id: "travel-camp", label: "Camping", value: "\u{1F3D5}\u{FE0F}" },
                { id: "travel-sunrise", label: "Sunrise", value: "\u{1F305}" },
                { id: "travel-rain", label: "Umbrella", value: "\u{2614}\u{FE0F}" },
                { id: "travel-location", label: "Location pin", value: "\u{1F4CD}" },
                { id: "travel-sandals", label: "Sandals", value: "\u{1FA74}" },
                { id: "travel-tent", label: "Tent", value: "\u{26FA}" }
            ]
        },
        gifts: {
            label: "Gifts",
            section: "Celebrations, gifts, and warm wishes",
            type: "emoji",
            items: [
                { id: "gift-box", label: "Gift box", value: "\u{1F381}" },
                { id: "gift-party", label: "Party popper", value: "\u{1F389}" },
                { id: "gift-balloon", label: "Balloon", value: "\u{1F388}" },
                { id: "gift-cake", label: "Birthday cake", value: "\u{1F382}" },
                { id: "gift-bouquet", label: "Bouquet", value: "\u{1F490}" },
                { id: "gift-heart", label: "Sparkling heart", value: "\u{1F496}" },
                { id: "gift-ribbon", label: "Reminder ribbon", value: "\u{1F397}\u{FE0F}" },
                { id: "gift-fireworks", label: "Fireworks", value: "\u{1F386}" },
                { id: "gift-stars", label: "Dizzy", value: "\u{1F4AB}" },
                { id: "gift-confetti", label: "Confetti ball", value: "\u{1F38A}" },
                { id: "gift-crown", label: "Crown", value: "\u{1F451}" },
                { id: "gift-trophy", label: "Trophy", value: "\u{1F3C6}" },
                { id: "gift-candy", label: "Candy", value: "\u{1F36C}" },
                { id: "gift-chocolate", label: "Chocolate", value: "\u{1F36B}" },
                { id: "gift-coffee", label: "Coffee", value: "\u{2615}" },
                { id: "gift-gift-heart", label: "Heart decoration", value: "\u{1F49D}" },
                { id: "gift-bubbles", label: "Bubbles", value: "\u{1FAE7}" },
                { id: "gift-handshake", label: "Handshake", value: "\u{1F91D}" }
            ]
        },
        replies: {
            label: "Quick replies",
            section: "Professional quick replies",
            type: "phrase",
            items: [
                { id: "reply-thanks", label: "Thanks a lot", preview: "Thanks a lot 🙏", value: "Thanks a lot \u{1F64F}" },
                { id: "reply-sounds-good", label: "Sounds good", preview: "Sounds good 👍", value: "Sounds good \u{1F44D}" },
                { id: "reply-on-my-way", label: "On my way", preview: "On my way 🚗", value: "On my way \u{1F697}" },
                { id: "reply-safe-travels", label: "Safe travels", preview: "Safe travels ✈️", value: "Safe travels \u{2708}\u{FE0F}" },
                { id: "reply-call-me", label: "Call me when free", preview: "Call me when free ☎️", value: "Call me when free \u{260E}\u{FE0F}" },
                { id: "reply-see-you", label: "See you soon", preview: "See you soon 👋", value: "See you soon \u{1F44B}" },
                { id: "reply-great-job", label: "Great job", preview: "Great job 🔥", value: "Great job \u{1F525}" },
                { id: "reply-congrats", label: "Congratulations", preview: "Congratulations 🎉", value: "Congratulations \u{1F389}" },
                { id: "reply-happy-birthday", label: "Happy birthday", preview: "Happy birthday 🎂", value: "Happy birthday \u{1F382}" },
                { id: "reply-lets-plan", label: "Let's plan it", preview: "Let's plan it 📅", value: "Let's plan it \u{1F4C5}" },
                { id: "reply-checking", label: "Checking and getting back", preview: "Checking and getting back 👀", value: "Checking and getting back \u{1F440}" },
                { id: "reply-thank-you", label: "Much appreciated", preview: "Much appreciated 💙", value: "Much appreciated \u{1F499}" }
            ]
        }
    };

    const itemIndex = new Map();
    Object.entries(pickerCatalog).forEach(function ([groupKey, group]) {
        group.items.forEach(function (item) {
            item.group = groupKey;
            item.type = group.type;
            itemIndex.set(item.id, item);
        });
    });

    let activePickerTab = "recent";

    function focusComposer() {
        textarea.focus({ preventScroll: true });
    }

    function insertAtCursor(value) {
        const text = value || "";
        const start = textarea.selectionStart ?? textarea.value.length;
        const end = textarea.selectionEnd ?? textarea.value.length;
        const currentValue = textarea.value;
        const suffix = text.endsWith(" ") ? "" : " ";

        textarea.value = currentValue.slice(0, start) + text + suffix + currentValue.slice(end);
        const nextPosition = start + text.length + suffix.length;
        textarea.setSelectionRange(nextPosition, nextPosition);
        focusComposer();
        syncComposerState();
    }

    function autosizeComposer() {
        textarea.style.height = "0px";
        textarea.style.height = Math.min(textarea.scrollHeight, 160) + "px";
    }

    function syncComposerState() {
        const hasText = textarea.value.trim().length > 0;
        const hasAttachment = Boolean(attachmentInput && attachmentInput.files && attachmentInput.files.length);
        const isReadyToSend = hasText || hasAttachment;

        sendIcon.className = "bi " + (isReadyToSend ? sendIconClass : likeIconClass);
        sendButton.title = isReadyToSend ? "Send message" : "Send quick like";

        if (selectedFile && attachmentInput) {
            if (hasAttachment) {
                selectedFile.hidden = false;
                selectedFile.textContent = attachmentInput.files[0].name;
            } else {
                selectedFile.hidden = true;
                selectedFile.textContent = "";
            }
        }

        autosizeComposer();
    }

    function getRecentIds() {
        try {
            const parsed = JSON.parse(window.localStorage.getItem(recentStorageKey) || "[]");
            return Array.isArray(parsed) ? parsed.filter(function (entry) {
                return typeof entry === "string" && itemIndex.has(entry);
            }) : [];
        } catch (error) {
            return [];
        }
    }

    function saveRecentItem(itemId) {
        if (!itemIndex.has(itemId)) {
            return;
        }

        const recentIds = getRecentIds().filter(function (entry) {
            return entry !== itemId;
        });
        recentIds.unshift(itemId);

        try {
            window.localStorage.setItem(recentStorageKey, JSON.stringify(recentIds.slice(0, 24)));
        } catch (error) {
            return;
        }
    }

    function getCategoryItems(tabKey) {
        if (tabKey === "recent") {
            const recentItems = getRecentIds().map(function (itemId) {
                return itemIndex.get(itemId);
            }).filter(Boolean);

            if (recentItems.length) {
                return recentItems;
            }

            return []
                .concat(pickerCatalog.emoji.items.slice(0, 8))
                .concat(pickerCatalog.reactions.items.slice(0, 4));
        }

        return pickerCatalog[tabKey] ? pickerCatalog[tabKey].items : [];
    }

    function getCategoryLabel(tabKey) {
        if (tabKey === "recent") {
            return "Recently used";
        }
        return pickerCatalog[tabKey] ? pickerCatalog[tabKey].section : "Emoji and more";
    }

    function renderPicker() {
        if (!picker || !pickerGrid || !pickerLabel || !pickerEmpty) {
            return;
        }

        const query = (pickerSearch ? pickerSearch.value : "").trim().toLowerCase();
        const sourceItems = getCategoryItems(activePickerTab);
        const filteredItems = sourceItems.filter(function (item) {
            if (!query) {
                return true;
            }
            return [item.label, item.preview || "", item.value].join(" ").toLowerCase().includes(query);
        });

        pickerGrid.innerHTML = "";
        pickerLabel.textContent = getCategoryLabel(activePickerTab);
        pickerGrid.classList.toggle("is-phrase-grid", activePickerTab === "replies");
        pickerEmpty.hidden = filteredItems.length > 0;

        filteredItems.forEach(function (item) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "message-picker-item " + (item.type === "phrase" ? "is-phrase" : "is-emoji");
            button.setAttribute("title", item.label);

            if (item.type === "phrase") {
                const title = document.createElement("span");
                title.className = "message-picker-item-title";
                title.textContent = item.label;

                const preview = document.createElement("span");
                preview.className = "message-picker-item-preview";
                preview.textContent = item.preview || item.value;

                button.appendChild(title);
                button.appendChild(preview);
            } else {
                const emoji = document.createElement("span");
                emoji.className = "message-picker-item-emoji";
                emoji.textContent = item.value;
                button.appendChild(emoji);
            }

            button.addEventListener("click", function () {
                insertAtCursor(item.value);
                saveRecentItem(item.id);
                closePicker();
            });

            pickerGrid.appendChild(button);
        });
    }

    function isPickerOpen() {
        return Boolean(picker) && !picker.hidden;
    }

    function setActivePickerTab(tabKey) {
        activePickerTab = (pickerCatalog[tabKey] || tabKey === "recent") ? tabKey : "emoji";

        pickerTabs.forEach(function (button) {
            const isActive = button.dataset.pickerTab === activePickerTab;
            button.classList.toggle("is-active", isActive);
            button.setAttribute("aria-selected", String(isActive));
        });

        renderPicker();
    }

    function openPicker(tabKey) {
        if (!picker) {
            return;
        }

        picker.hidden = false;
        picker.setAttribute("aria-hidden", "false");
        if (pickerSearch) {
            pickerSearch.value = "";
        }
        setActivePickerTab(tabKey || activePickerTab || "recent");
        if (pickerSearch) {
            window.setTimeout(function () {
                pickerSearch.focus({ preventScroll: true });
            }, 0);
        }
    }

    function closePicker() {
        if (!picker) {
            return;
        }
        picker.hidden = true;
        picker.setAttribute("aria-hidden", "true");
    }

    textarea.addEventListener("input", syncComposerState);

    pickerOpenButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            openPicker(button.dataset.pickerOpen || "emoji");
        });
    });

    pickerTabs.forEach(function (button) {
        button.addEventListener("click", function () {
            setActivePickerTab(button.dataset.pickerTab || "emoji");
        });
    });

    if (pickerSearch) {
        pickerSearch.addEventListener("input", renderPicker);
    }

    if (pickerCloseButton) {
        pickerCloseButton.addEventListener("click", function () {
            closePicker();
            focusComposer();
        });
    }

    attachmentTriggers.forEach(function (button) {
        button.addEventListener("click", function () {
            if (!attachmentInput) {
                return;
            }

            closePicker();
            const nextAccept = attachmentAcceptMap[button.dataset.attachmentTrigger] || defaultAccept;
            attachmentInput.value = "";
            attachmentInput.setAttribute("accept", nextAccept);
            attachmentInput.click();
        });
    });

    if (attachmentInput) {
        attachmentInput.addEventListener("change", function () {
            attachmentInput.setAttribute("accept", defaultAccept);
            syncComposerState();
        });
    }

    sendButton.addEventListener("click", function () {
        const hasText = textarea.value.trim().length > 0;
        const hasAttachment = Boolean(attachmentInput && attachmentInput.files && attachmentInput.files.length);
        if (!hasText && !hasAttachment) {
            textarea.value = "\u{1F44D}";
            syncComposerState();
        }
    });

    document.addEventListener("mousedown", function (event) {
        if (!isPickerOpen()) {
            return;
        }

        const clickedOpenButton = Array.from(pickerOpenButtons).some(function (button) {
            return button.contains(event.target);
        });

        if (!clickedOpenButton && picker && !picker.contains(event.target)) {
            closePicker();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && isPickerOpen()) {
            closePicker();
            focusComposer();
        }
    });

    focusComposer();
    renderPicker();
    syncComposerState();
})();
