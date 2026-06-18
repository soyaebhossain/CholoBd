(function () {
    const config = window.communityConfig || {};

    function getCsrfToken() {
        const name = 'csrftoken=';
        const decoded = decodeURIComponent(document.cookie || '');
        const parts = decoded.split(';');
        for (const part of parts) {
            const trimmed = part.trim();
            if (trimmed.startsWith(name)) {
                return trimmed.substring(name.length);
            }
        }
        return '';
    }

    function buildUrl(template, id) {
        return String(template || '').replace('/0/', `/${id}/`);
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function updateText(postCard, selector, value) {
        if (!postCard) {
            return;
        }
        postCard.querySelectorAll(selector).forEach((node) => {
            node.textContent = String(value ?? 0);
        });
    }

    function renderReactionOverview(postCard, reactions) {
        if (!postCard) {
            return;
        }

        const container = postCard.querySelector('.js-reaction-overview-icons');
        if (!container) {
            return;
        }

        container.innerHTML = (reactions || [])
            .slice(0, 2)
            .map((reaction) => `
                <span class="community-reaction-chip community-reaction-chip-${escapeHtml(reaction.color || reaction.key || 'like')}">
                    ${escapeHtml(reaction.emoji || '👍')}
                </span>
            `)
            .join('');
    }

    function insertIntoField(field, text, options = {}) {
        if (!field) {
            return;
        }

        const append = options.append ?? true;
        const shouldReplace = options.replace || !field.value.trim();

        if (shouldReplace) {
            field.value = text;
        } else if (typeof field.selectionStart === 'number' && typeof field.selectionEnd === 'number') {
            const start = field.selectionStart;
            const end = field.selectionEnd;
            const spacer = append && start > 0 && !/\s$/.test(field.value.slice(0, start)) ? ' ' : '';
            field.value = `${field.value.slice(0, start)}${spacer}${text}${field.value.slice(end)}`;
            const caret = start + spacer.length + text.length;
            field.setSelectionRange(caret, caret);
        } else {
            field.value = append ? `${field.value.trim()} ${text}`.trim() : text;
        }

        field.dispatchEvent(new Event('input', { bubbles: true }));
        field.dispatchEvent(new Event('change', { bubbles: true }));
        field.focus();
    }

    function buildCommentSuggestions(container) {
        const title = (container.dataset.postTitle || '').trim();
        const postType = (container.dataset.postType || '').trim();
        const location = (container.dataset.postLocation || '').trim();
        const author = (container.dataset.postAuthor || '').trim();
        const locationSuffix = location ? ` about ${location}` : '';
        const authorPrefix = author ? `${author}, ` : '';

        const generic = [
            'Thank you so much! 😊',
            'Welcome 😊',
            'Good morning sunshine',
            'Looks amazing 😍',
            'Thanks for sharing this.',
            `${authorPrefix}beautiful post.`.trim(),
        ];

        const help = [
            `Can you share the budget${locationSuffix}?`,
            `Can you share the best route${locationSuffix}?`,
            'This is really helpful. Thank you.',
            'Could you share more details please?',
            'Please share the exact location pin.',
            'What time is best for this trip?',
        ];

        const experience = [
            'Mashallah, so সুন্দর লাগছে.',
            'This spot looks peaceful.',
            `I want to visit${locationSuffix} too.`,
            'Wonderful capture 📸',
            'How was the overall experience?',
            'Was it crowded there?',
        ];

        const planning = [
            `Can we make a group plan${locationSuffix}?`,
            'This will help a lot for planning.',
            'Please share transport timing too.',
            'How many days are enough for this trip?',
            'Any hotel recommendation?',
            'Thanks, saving this for later.',
        ];

        let pool = generic;
        if (['help', 'travel_question'].includes(postType)) {
            pool = [...help, ...generic];
        } else if (['travel_experience', 'photo_story'].includes(postType)) {
            pool = [...experience, ...generic];
        } else if (['trip_plan', 'trip_planning', 'transport_advice', 'budget_travel'].includes(postType)) {
            pool = [...planning, ...generic];
        }

        return Array.from(new Set(pool.filter(Boolean)));
    }

    function rotateSuggestions(pool, seed, maxItems) {
        if (!pool.length) {
            return [];
        }
        const normalizedSeed = ((seed % pool.length) + pool.length) % pool.length;
        const rotated = pool.slice(normalizedSeed).concat(pool.slice(0, normalizedSeed));
        return rotated.slice(0, Math.min(maxItems, rotated.length));
    }

    function renderCommentSuggestions(container) {
        const list = container.querySelector('.js-comment-suggestions');
        const textarea = container.querySelector('textarea');
        if (!list || !textarea) {
            return;
        }

        const seed = Number(container.dataset.suggestionSeed || '0');
        const suggestions = rotateSuggestions(buildCommentSuggestions(container), seed, 6);
        list.innerHTML = suggestions
            .map((suggestion) => `<button type="button" class="community-comment-suggestion-chip">${escapeHtml(suggestion)}</button>`)
            .join('');

        list.querySelectorAll('.community-comment-suggestion-chip').forEach((button) => {
            button.addEventListener('click', () => {
                insertIntoField(textarea, button.textContent || '', { replace: true, append: false });
            });
        });
    }

    function normalizeTargetSelector(value) {
        const trimmed = String(value || '').trim();
        if (!trimmed) {
            return '';
        }
        return trimmed.startsWith('#') ? trimmed : `#${trimmed}`;
    }

    function setComposerPanelState(selector, open) {
        const normalized = normalizeTargetSelector(selector);
        if (!normalized) {
            return;
        }

        const target = document.querySelector(normalized);
        if (!target) {
            return;
        }

        target.classList.toggle('d-none', !open);
        target.classList.toggle('is-open', open);

        document.querySelectorAll('.js-toggle-composer').forEach((button) => {
            const buttonTarget = normalizeTargetSelector(button.dataset.target);
            if (buttonTarget === normalized) {
                button.classList.toggle('active', open);
            }
        });
    }

    function openComposerPanels(selectors) {
        String(selectors || '')
            .split(',')
            .map((value) => normalizeTargetSelector(value))
            .filter(Boolean)
            .forEach((selector) => setComposerPanelState(selector, true));
    }

    function closeReactionPicker(wrapper) {
        if (!wrapper) {
            return;
        }
        wrapper.classList.remove('is-open');
    }

    function closeAllReactionPickers(exceptWrapper) {
        document.querySelectorAll('.community-reaction-action.is-open').forEach((wrapper) => {
            if (wrapper !== exceptWrapper) {
                closeReactionPicker(wrapper);
            }
        });
    }

    const reactionCloseTimers = new WeakMap();

    function clearReactionCloseTimer(wrapper) {
        const timer = reactionCloseTimers.get(wrapper);
        if (timer) {
            window.clearTimeout(timer);
            reactionCloseTimers.delete(wrapper);
        }
    }

    function openReactionPicker(wrapper) {
        if (!wrapper) {
            return;
        }
        clearReactionCloseTimer(wrapper);
        closeAllReactionPickers(wrapper);
        wrapper.classList.add('is-open');
    }

    function scheduleReactionPickerClose(wrapper) {
        if (!wrapper) {
            return;
        }
        clearReactionCloseTimer(wrapper);
        const timer = window.setTimeout(() => {
            closeReactionPicker(wrapper);
            reactionCloseTimers.delete(wrapper);
        }, 180);
        reactionCloseTimers.set(wrapper, timer);
    }

    async function submitReaction(button, reactionType) {
        const postId = button.dataset.postId;
        if (!postId) {
            return;
        }

        const url = buildUrl(config.likeUrlTemplate, postId);
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: new URLSearchParams({ reaction: reactionType || 'like' }).toString(),
        });
        if (!response.ok) {
            return;
        }

        const payload = await response.json();
        const countNode = button.querySelector('.js-like-count');
        const labelNode = button.querySelector('.js-reaction-label');
        const symbolNode = button.querySelector('.js-reaction-symbol');
        const postCard = button.closest('.community-post-card');

        if (countNode) {
            countNode.textContent = String(payload.like_count ?? 0);
        }
        if (labelNode) {
            labelNode.textContent = payload.reaction_label || 'Like';
        }
        if (symbolNode) {
            symbolNode.textContent = payload.reaction_emoji || '👍';
        }

        updateText(postCard, '.js-reaction-total', payload.like_count ?? 0);
        renderReactionOverview(postCard, payload.top_reactions || []);
        button.dataset.liked = payload.liked ? '1' : '0';
        button.dataset.reaction = payload.selected_reaction || '';
        closeReactionPicker(button.closest('.community-reaction-action'));
    }

    const csrfToken = getCsrfToken();
    const composerForm = document.getElementById('communityComposer');
    const composerModalElement = document.getElementById('communityPostModal');
    const composerModal = composerModalElement && typeof bootstrap !== 'undefined'
        ? bootstrap.Modal.getOrCreateInstance(composerModalElement)
        : null;
    let pendingComposerFocusSelector = '';

    if (composerModalElement) {
        composerModalElement.addEventListener('shown.bs.modal', () => {
            const selector = normalizeTargetSelector(pendingComposerFocusSelector) || '#id_content';
            const target = document.querySelector(selector);
            if (target) {
                target.focus();
            }
        });
    }

    document.querySelectorAll('.js-open-post-modal').forEach((button) => {
        button.addEventListener('click', () => {
            if (composerModal) {
                composerModal.show();
            }

            if (!composerForm) {
                return;
            }

            const typeField = composerForm.querySelector('#id_post_type');
            if (typeField && button.dataset.postType) {
                typeField.value = button.dataset.postType;
                typeField.dispatchEvent(new Event('change', { bubbles: true }));
            }

            pendingComposerFocusSelector = button.dataset.focusField || '#id_content';
            openComposerPanels(button.dataset.openPanel);
        });
    });

    document.querySelectorAll('.js-toggle-composer').forEach((button) => {
        button.addEventListener('click', () => {
            const targetSelector = normalizeTargetSelector(button.dataset.target);
            const target = targetSelector ? document.querySelector(targetSelector) : null;
            const shouldOpen = target ? target.classList.contains('d-none') : false;
            setComposerPanelState(targetSelector, shouldOpen);
        });
    });

    document.querySelectorAll('.js-focus-field').forEach((button) => {
        button.addEventListener('click', () => {
            const field = document.querySelector(button.dataset.field || '');
            if (!field) {
                return;
            }
            field.focus();
            field.scrollIntoView({behavior: 'smooth', block: 'center'});
        });
    });

    document.querySelectorAll('.js-insert-post-emoji').forEach((button) => {
        button.addEventListener('click', () => {
            const field = document.querySelector(button.dataset.target || '');
            insertIntoField(field, button.dataset.emoji || '😊');
        });
    });

    if (composerForm) {
        composerForm.addEventListener('submit', () => {
            const titleField = composerForm.querySelector('#id_title');
            const contentField = composerForm.querySelector('#id_content');
            const pollField = composerForm.querySelector('#id_poll_question');
            if (!titleField || titleField.value.trim()) {
                return;
            }

            const sourceText = [
                contentField ? contentField.value : '',
                pollField ? pollField.value : '',
            ]
                .map((value) => String(value || '').trim())
                .find(Boolean);

            if (!sourceText) {
                return;
            }

            titleField.value = sourceText
                .replace(/\s+/g, ' ')
                .trim()
                .split(' ')
                .slice(0, 8)
                .join(' ')
                .slice(0, 180);
        });
    }

    document.querySelectorAll('.js-like-btn').forEach((button) => {
        button.addEventListener('click', async () => {
            await submitReaction(button, button.dataset.reaction || 'like');
        });
    });

    document.querySelectorAll('.community-reaction-action').forEach((wrapper) => {
        const mainButton = wrapper.querySelector('.js-like-btn');
        const picker = wrapper.querySelector('.community-reaction-picker');

        wrapper.addEventListener('mouseenter', () => {
            openReactionPicker(wrapper);
        });
        wrapper.addEventListener('mouseleave', () => {
            scheduleReactionPickerClose(wrapper);
        });
        wrapper.addEventListener('focusin', () => {
            openReactionPicker(wrapper);
        });
        wrapper.addEventListener('focusout', (event) => {
            if (!wrapper.contains(event.relatedTarget)) {
                scheduleReactionPickerClose(wrapper);
            }
        });

        if (mainButton) {
            mainButton.addEventListener('pointerenter', () => {
                openReactionPicker(wrapper);
            });
        }

        if (picker) {
            picker.addEventListener('pointerenter', () => {
                openReactionPicker(wrapper);
            });
            picker.addEventListener('pointerleave', () => {
                scheduleReactionPickerClose(wrapper);
            });
        }
    });

    document.querySelectorAll('.js-reaction-option').forEach((button) => {
        const submitOptionReaction = async (event) => {
            event.preventDefault();
            event.stopPropagation();
            const wrapper = button.closest('.community-reaction-action');
            const mainButton = wrapper ? wrapper.querySelector('.js-like-btn') : null;
            if (!mainButton) {
                return;
            }
            await submitReaction(mainButton, button.dataset.reaction || 'like');
        };

        button.addEventListener('pointerdown', submitOptionReaction);
        button.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
        });
    });

    document.addEventListener('click', (event) => {
        if (!event.target.closest('.community-reaction-action')) {
            closeAllReactionPickers();
        }
    });

    document.querySelectorAll('.js-save-btn').forEach((button) => {
        button.addEventListener('click', async () => {
            const postId = button.dataset.postId;
            if (!postId) {
                return;
            }
            const url = buildUrl(config.saveUrlTemplate, postId);
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest',
                },
            });
            if (!response.ok) {
                return;
            }
            const payload = await response.json();
            const countNode = button.querySelector('.js-save-count');
            const iconNode = button.querySelector('i');
            const postCard = button.closest('.community-post-card');
            if (countNode) {
                countNode.textContent = String(payload.save_count ?? 0);
            }
            updateText(postCard, '.js-save-total', payload.save_count ?? 0);
            if (iconNode) {
                iconNode.className = `bi ${payload.saved ? 'bi-bookmark-check-fill' : 'bi-bookmark'} me-1`;
            }
            button.dataset.saved = payload.saved ? '1' : '0';
        });
    });

    document.querySelectorAll('.js-share-btn').forEach((button) => {
        button.addEventListener('click', async () => {
            const url = button.dataset.shareUrl || window.location.href;
            try {
                await navigator.clipboard.writeText(url);
                button.classList.remove('btn-outline-secondary');
                button.classList.add('btn-success');
                button.innerHTML = '<i class="bi bi-check2 me-1"></i>Copied';
                setTimeout(() => {
                    button.classList.remove('btn-success');
                    button.classList.add('btn-outline-secondary');
                    button.innerHTML = '<i class="bi bi-share me-1"></i>Share';
                }, 1200);
            } catch (error) {
                window.prompt('Copy this link:', url);
            }
        });
    });

    document.querySelectorAll('.js-focus-comment-btn').forEach((button) => {
        button.addEventListener('click', (event) => {
            event.preventDefault();
            const postCard = button.closest('.community-post-card');
            const comments = postCard ? postCard.querySelector('.community-comments') : null;
            const textarea = comments ? comments.querySelector('textarea') : null;
            if (comments) {
                comments.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
            if (textarea) {
                textarea.focus();
            }
        });
    });

    document.querySelectorAll('.community-comments').forEach((container) => {
        const refreshButton = container.querySelector('.js-refresh-comment-suggestions');
        const emojiButton = container.querySelector('.js-insert-comment-emoji');
        const textarea = container.querySelector('textarea');

        renderCommentSuggestions(container);

        if (refreshButton) {
            refreshButton.addEventListener('click', () => {
                const nextSeed = Number(container.dataset.suggestionSeed || '0') + 1;
                container.dataset.suggestionSeed = String(nextSeed);
                renderCommentSuggestions(container);
            });
        }

        if (emojiButton && textarea) {
            emojiButton.addEventListener('click', () => {
                insertIntoField(textarea, emojiButton.dataset.emoji || '😊');
            });
        }
    });

    const modalElement = document.getElementById('miniProfileModal');
    const modalBody = document.getElementById('miniProfileBody');
    const profileModal = modalElement ? new bootstrap.Modal(modalElement) : null;

    document.querySelectorAll('.js-mini-profile').forEach((button) => {
        button.addEventListener('click', async () => {
            const userId = button.dataset.userId;
            if (!userId || !profileModal || !modalBody) {
                return;
            }
            modalBody.innerHTML = '<div class="text-center text-muted">Loading profile...</div>';
            profileModal.show();

            const url = buildUrl(config.profileUrlTemplate, userId);
            const response = await fetch(url, {
                headers: {'X-Requested-With': 'XMLHttpRequest'},
            });
            if (!response.ok) {
                let message = 'Could not load profile.';
                try {
                    const payload = await response.json();
                    if (payload && payload.detail) {
                        message = payload.detail;
                    }
                } catch (error) {
                    // Ignore JSON parsing failures and keep the generic message.
                }
                modalBody.innerHTML = `<div class="alert alert-danger mb-0">${message}</div>`;
                return;
            }
            const profile = await response.json();
            const safeUsername = escapeHtml(profile.username);
            const safeName = escapeHtml(profile.name);
            const safeBio = escapeHtml(profile.bio);
            const avatarHtml = profile.avatar
                ? `<img src="${profile.avatar}" class="community-avatar-lg mb-3" alt="${safeUsername}">`
                : '<span class="community-avatar-placeholder-lg mb-3"><i class="bi bi-person"></i></span>';
            const followUrl = buildUrl(config.followUrlTemplate, userId);
            const followButtonHtml = profile.can_follow
                ? `<button type="button" class="btn ${profile.is_following ? 'btn-outline-secondary' : 'btn-primary'}" data-follow-url="${followUrl}">
                        <i class="bi ${profile.is_following ? 'bi-person-dash' : 'bi-person-plus'} me-1"></i>
                        <span>${profile.is_following ? 'Following' : 'Follow'}</span>
                   </button>`
                : '';
            const messageButtonHtml = profile.is_self
                ? ''
                : (profile.can_message
                    ? `<a href="${profile.message_url}" class="btn btn-outline-primary"><i class="bi bi-chat-dots me-1"></i>Message</a>`
                    : '<button type="button" class="btn btn-outline-secondary" disabled><i class="bi bi-chat-dots me-1"></i>Message Locked</button>');

            modalBody.innerHTML = `
                <div class="text-center">
                    <div class="community-avatar-wrap community-avatar-wrap-lg d-inline-flex">
                        ${avatarHtml}
                        ${profile.is_online ? '<span class="community-online-dot"></span>' : ''}
                    </div>
                    <h5 class="mb-0">${safeName}</h5>
                    <p class="text-muted mb-3">@${safeUsername}</p>
                    ${profile.bio ? `<p class="small mb-3">${safeBio}</p>` : ''}
                </div>
                <div class="row g-2 text-center">
                    <div class="col-3"><div class="mini-stat-card"><strong>${profile.trips_completed}</strong><span>Trips</span></div></div>
                    <div class="col-3"><div class="mini-stat-card"><strong>${profile.visited_districts}</strong><span>Districts</span></div></div>
                    <div class="col-3"><div class="mini-stat-card"><strong id="miniFollowerCount">${profile.follower_count}</strong><span>Followers</span></div></div>
                    <div class="col-3"><div class="mini-stat-card"><strong>${profile.reputation}</strong><span>Reputation</span></div></div>
                </div>
                <div class="d-flex flex-wrap justify-content-center gap-2 mt-3">
                    <a href="${profile.profile_url}" class="btn btn-outline-secondary"><i class="bi bi-person-vcard me-1"></i>View Profile</a>
                    ${followButtonHtml}
                    ${messageButtonHtml}
                </div>
            `;

            const followButton = modalBody.querySelector('[data-follow-url]');
            if (followButton) {
                followButton.addEventListener('click', async () => {
                    const followResponse = await fetch(followButton.dataset.followUrl, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': csrfToken,
                            'X-Requested-With': 'XMLHttpRequest',
                        },
                    });
                    if (!followResponse.ok) {
                        return;
                    }
                    const followPayload = await followResponse.json();
                    const label = followButton.querySelector('span');
                    const icon = followButton.querySelector('i');
                    const followerCountNode = modalBody.querySelector('#miniFollowerCount');
                    const isFollowing = !!followPayload.following;

                    followButton.classList.toggle('btn-primary', !isFollowing);
                    followButton.classList.toggle('btn-outline-secondary', isFollowing);
                    if (label) {
                        label.textContent = isFollowing ? 'Following' : 'Follow';
                    }
                    if (icon) {
                        icon.className = `bi ${isFollowing ? 'bi-person-dash' : 'bi-person-plus'} me-1`;
                    }
                    if (followerCountNode) {
                        followerCountNode.textContent = String(followPayload.follower_count ?? profile.follower_count ?? 0);
                    }
                });
            }
        });
    });

    const markReadBtn = document.getElementById('markNotifRead');
    if (markReadBtn) {
        markReadBtn.addEventListener('click', async () => {
            const response = await fetch(config.markReadUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest',
                },
            });
            if (!response.ok) {
                return;
            }
            const list = document.getElementById('notificationList');
            if (list) {
                list.innerHTML = '<p class="small text-muted mb-0">No unread notifications.</p>';
            }
        });
    }
})();
