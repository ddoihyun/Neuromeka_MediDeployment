(function () {
    const pageRoot = document.querySelector('.telemetry-page');
    if (!pageRoot) {
        return;
    }

    const POLL_INTERVAL_MS = 100;
    const MAX_POLL_INTERVAL_MS = 2000;
    const TAU_EXT_BAR_SCALE = 5;
    const backendBaseRaw = (window.__BACKEND_BASE_URL__ || '').toString().trim();
    const backendBase = backendBaseRaw.replace(/\/+$/, '');
    const TELEMETRY_URL = backendBase ? backendBase + '/api/robot/telemetry' : '/api/robot/telemetry';

    const pValueElements = Array.from(document.querySelectorAll('[data-telemetry-p]'));
    const tauValueElements = Array.from(document.querySelectorAll('[data-telemetry-tau-ext]'));
    const tauBarElements = Array.from(document.querySelectorAll('[data-tau-bar]'));
    const tauScaleElement = document.querySelector('[data-tau-scale]');
    const timestampElement = document.querySelector('[data-telemetry-timestamp]');

    function formatNumber(value) {
        const numeric = Number(value);
        if (Number.isNaN(numeric)) {
            return '0';
        }
        return numeric.toFixed(3);
    }

    function normalizeNumericVector(values, length) {
        const normalized = [];
        const source = Array.isArray(values) ? values : [];
        for (let index = 0; index < length; index += 1) {
            const numeric = Number(source[index]);
            normalized.push(Number.isNaN(numeric) ? 0 : numeric);
        }
        return normalized;
    }

    function updatePValues(pValues) {
        pValueElements.forEach(function (element) {
            const key = element.dataset.telemetryP;
            if (!key) {
                return;
            }
            element.textContent = formatNumber(pValues ? pValues[key] : 0);
        });
    }

    function updateTauExtValues(rawTauExt) {
        const tauExtValues = normalizeNumericVector(rawTauExt, 6);
        const scale = TAU_EXT_BAR_SCALE;

        if (tauScaleElement) {
            tauScaleElement.textContent = formatNumber(scale);
        }

        tauValueElements.forEach(function (element) {
            const index = Number(element.dataset.telemetryTauExt);
            const value = tauExtValues[index] || 0;
            element.textContent = formatNumber(value);
            element.classList.toggle('is-negative', value < 0);
            element.classList.toggle('is-positive', value > 0);
        });

        tauBarElements.forEach(function (element) {
            const index = Number(element.dataset.tauBar);
            const value = tauExtValues[index] || 0;
            const halfPercent = Math.min(Math.abs(value) / scale, 1) * 50;
            const isNegative = value < 0;

            element.style.left = isNegative ? (50 - halfPercent).toFixed(2) + '%' : '50%';
            element.style.width = halfPercent.toFixed(2) + '%';
            element.classList.toggle('is-negative', isNegative);
            element.classList.toggle('is-positive', value >= 0);
        });
    }

    function updateTimestamp(label) {
        if (!timestampElement) {
            return;
        }
        timestampElement.textContent = label;
    }

    function handleTelemetry(payload) {
        if (!payload || typeof payload !== 'object') {
            return;
        }
        const pValues = payload.p || {};
        const updatedAt = payload.last_updated || new Date().toISOString();
        const timestampLabel = new Date(updatedAt).toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false,
        });

        updateTimestamp(timestampLabel);
        updatePValues(pValues);
        updateTauExtValues(payload.tau_ext);
    }

    let pollTimer = null;
    let isFetching = false;
    let consecutiveFailures = 0;

    function clearPollTimer() {
        if (pollTimer !== null) {
            window.clearTimeout(pollTimer);
            pollTimer = null;
        }
    }

    function scheduleNextPoll(delay) {
        if (document.hidden) {
            clearPollTimer();
            return;
        }
        clearPollTimer();
        pollTimer = window.setTimeout(pollTelemetry, delay || POLL_INTERVAL_MS);
    }

    function pollTelemetry() {
        if (document.hidden) {
            clearPollTimer();
            return;
        }
        if (isFetching) {
            scheduleNextPoll();
            return;
        }

        isFetching = true;
        fetch(TELEMETRY_URL)
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Telemetry request failed: ' + response.status);
                }
                return response.json();
            })
            .then(function (payload) {
                consecutiveFailures = 0;
                handleTelemetry(payload);
            })
            .catch(function (error) {
                consecutiveFailures += 1;
                console.warn('Telemetry polling error:', error);
            })
            .finally(function () {
                const nextDelay = consecutiveFailures > 0
                    ? Math.min(POLL_INTERVAL_MS * Math.pow(2, consecutiveFailures), MAX_POLL_INTERVAL_MS)
                    : POLL_INTERVAL_MS;
                isFetching = false;
                scheduleNextPoll(nextDelay);
            });
    }

    pollTelemetry();

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            clearPollTimer();
            return;
        }
        if (!isFetching) {
            pollTelemetry();
        }
    });

    window.addEventListener('beforeunload', function () {
        clearPollTimer();
    });
})();
