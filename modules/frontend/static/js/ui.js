(function () {
    const HOLD_ACTIVATION_DURATION_MS = 2000;
    const STATE_SYNC_INTERVAL_MS = 1000;
    const MAX_STATE_SYNC_INTERVAL_MS = 10000;
    const backendBaseUrlValue = typeof window.__BACKEND_BASE_URL__ === 'string' ? window.__BACKEND_BASE_URL__.trim() : '';
    const BACKEND_BASE_URL = backendBaseUrlValue ? backendBaseUrlValue.replace(/\/+$/, '') : '';
    let statePoller = null;
    const STATE_STORAGE_KEY = 'surgical-robot-ui:state-cache';

    function loadStoredState() {
        try {
            const raw = window.sessionStorage.getItem(STATE_STORAGE_KEY);
            if (!raw) {
                return null;
            }
            const parsed = JSON.parse(raw);
            if (parsed && typeof parsed === 'object') {
                return parsed;
            }
        } catch (error) {
            console.warn('상태 캐시 로드 실패:', error);
        }
        return null;
    }

    function storeState(nextState) {
        try {
            window.sessionStorage.setItem(STATE_STORAGE_KEY, JSON.stringify(nextState));
        } catch (error) {
            console.warn('상태 캐시 저장 실패:', error);
        }
    }

    function pickLatestState(initialState, storedState) {
        if (!storedState) {
            return initialState;
        }

        function toTimestamp(state, path) {
            const value = getNestedValue(state, path);
            const parsed = new Date(value);
            return Number.isNaN(parsed.getTime()) ? 0 : parsed.getTime();
        }

        const initialUpdated = toTimestamp(initialState, 'system.last_updated');
        const cachedUpdated = toTimestamp(storedState, 'system.last_updated');
        return cachedUpdated > initialUpdated ? storedState : initialState;
    }

    let appState = pickLatestState(window.__INITIAL_STATE__ || {}, loadStoredState());
    const MODE_STATUS_IDLE_TEXT = '2초 이상 길게 누르면 명령이 전송됩니다.';
    const VOICE_CANCELABLE_STAGES = [
        'recording_stopping',
        'saving_audio',
        'audio_saved',
        'stt_requesting',
        'stt_done',
        'llm_requesting',
        'llm_response',
        'keyword_parsed',
        'command_parsed'
    ];
    let isVoiceCancelRequestInFlight = false;

    function setPressedState(button, isActive) {
        button.setAttribute('aria-pressed', String(isActive));
        button.classList.toggle('is-active', isActive);
        const activeText = button.dataset.activeText;
        const inactiveText = button.dataset.inactiveText;
        if (isActive && activeText) {
            button.textContent = activeText;
        } else if (!isActive && inactiveText) {
            button.textContent = inactiveText;
        }
    }

    function getNestedValue(object, path) {
        if (!object || !path) {
            return undefined;
        }
        return path.split('.').reduce(function (result, key) {
            if (result && typeof result === 'object' && key in result) {
                return result[key];
            }
            return undefined;
        }, object);
    }

    var VALID_STATUS_COLORS = ['black', 'red', 'green'];

    function normalizeStatusColor(value) {
        if (typeof value === 'string') {
            var normalized = value.trim().toLowerCase();
            if (VALID_STATUS_COLORS.indexOf(normalized) !== -1) {
                return normalized;
            }
        }
        return 'black';
    }

    function applyStatusColor(element, color) {
        if (!element) {
            return;
        }
        var normalized = normalizeStatusColor(color);
        VALID_STATUS_COLORS.forEach(function (name) {
            element.classList.remove('color-' + name);
        });
        element.classList.add('color-' + normalized);
    }

    function mergePayload(payload, path, value) {
        const segments = path.split('.');
        let cursor = payload;
        segments.forEach(function (segment, index) {
            if (index === segments.length - 1) {
                cursor[segment] = value;
            } else {
                if (!cursor[segment] || typeof cursor[segment] !== 'object') {
                    cursor[segment] = {};
                }
                cursor = cursor[segment];
            }
        });
        return payload;
    }

    function applyLocalStatePatch(patch) {
        if (!patch || typeof patch !== 'object') {
            return;
        }

        const nextState = JSON.parse(JSON.stringify(appState || {}));

        function mergeInto(target, source) {
            Object.keys(source).forEach(function (key) {
                const value = source[key];
                if (value && typeof value === 'object' && !Array.isArray(value)) {
                    if (!target[key] || typeof target[key] !== 'object' || Array.isArray(target[key])) {
                        target[key] = {};
                    }
                    mergeInto(target[key], value);
                } else {
                    target[key] = value;
                }
            });
        }

        if (patch.voice_control && Object.prototype.hasOwnProperty.call(patch.voice_control, 'result_json')) {
            if (!nextState.voice_control || typeof nextState.voice_control !== 'object') {
                nextState.voice_control = {};
            }
            nextState.voice_control.result_json = patch.voice_control.result_json;
            delete patch.voice_control.result_json;
        }

        mergeInto(nextState, patch);
        refreshState(nextState);
    }

    function formatTimestamp(value) {
        if (!value) {
            return '기록 없음';
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return date.toLocaleString('ko-KR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });
    }

    function parseAlarmTimestamp(value) {
        if (!value) {
            return -Infinity;
        }
        const parsedDate = new Date(value);
        if (!Number.isNaN(parsedDate.getTime())) {
            return parsedDate.getTime();
        }
        if (typeof value === 'string') {
            const parts = value.split(':').map(Number);
            if (parts.length >= 2 && parts.every(function (part) { return !Number.isNaN(part); })) {
                const now = new Date();
                now.setHours(parts[0], parts[1], parts[2] || 0, 0);
                return now.getTime();
            }
        }
        return -Infinity;
    }

    function getAlarmValue(entry, primaryKey, fallbackKey) {
        if (!entry) {
            return undefined;
        }
        if (typeof entry[primaryKey] !== 'undefined' && entry[primaryKey] !== null) {
            return entry[primaryKey];
        }
        return entry[fallbackKey];
    }

    function getAlarmSeverity(entry) {
        if (!entry) {
            return '';
        }

        const severityText = getAlarmValue(entry, 'severity', '종류');
        if (!severityText) {
            return '';
        }
        const normalized = severityText.toString().toLowerCase();
        if (['조치완료', 'resolved'].some(function (keyword) { return normalized.includes(keyword); })) {
            return 'resolved';
        }
        if (['에러', 'error'].some(function (keyword) { return normalized.includes(keyword); })) {
            return 'error';
        }
        return 'info';
    }

    function isAlertSeverity(entry) {
        return getAlarmSeverity(entry) === 'error';
    }

    function replaceChildren(container, children) {
        while (container.firstChild) {
            container.removeChild(container.firstChild);
        }
        children.forEach(function (child) {
            container.appendChild(child);
        });
    }

    function buildAlarmCell(className, value) {
        const cell = document.createElement('td');
        cell.className = className;
        cell.textContent = value || '-';
        return cell;
    }

    function buildAlarmPlaceholderRow(message) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.className = 'placeholder';
        cell.colSpan = 4;
        cell.textContent = message;
        row.appendChild(cell);
        return row;
    }

    function buildAlarmRow(entry) {
        const severity = getAlarmSeverity(entry);
        const row = document.createElement('tr');
        row.className = 'alarm-row';
        row.classList.toggle('alarm-critical', severity === 'error');
        row.classList.toggle('alarm-resolved', severity === 'resolved');
        row.appendChild(buildAlarmCell('column-time', getAlarmValue(entry, 'time', '시간')));
        row.appendChild(buildAlarmCell('column-type', getAlarmValue(entry, 'code', '종류')));
        row.appendChild(buildAlarmCell('column-content', getAlarmValue(entry, 'message', '내용')));
        row.appendChild(buildAlarmCell('column-action', getAlarmValue(entry, 'action', '조치')));
        return row;
    }

    function updateAlarmLogs() {
        document.querySelectorAll('[data-alarm-log]').forEach(function (container) {
            const alarms = getNestedValue(appState, container.dataset.alarmLog);
            if (!alarms || typeof alarms !== 'object') {
                replaceChildren(container, [buildAlarmPlaceholderRow('기록 없음')]);
                return;
            }

            const sortedEntries = Object.keys(alarms)
                .map(function (key) { return alarms[key]; })
                .filter(function (entry) { return entry && typeof entry === 'object'; })
                .sort(function (a, b) {
                    const timeDiff = parseAlarmTimestamp(getAlarmValue(b, 'time', '시간')) -
                        parseAlarmTimestamp(getAlarmValue(a, 'time', '시간'));
                    if (timeDiff !== 0) {
                        return timeDiff;
                    }
                    const contentA = (getAlarmValue(a, 'message', '내용') || '').toString();
                    const contentB = (getAlarmValue(b, 'message', '내용') || '').toString();
                    return contentA.localeCompare(contentB);
                });

            const viewMode = container.dataset.alarmView === 'latest' ? 'latest' : 'all';
            const entriesToRender = viewMode === 'latest' ? sortedEntries.slice(0, 1) : sortedEntries;

            if (entriesToRender.length === 0) {
                const placeholder = viewMode === 'latest' ? '최근 알림 없음' : '기록 없음';
                replaceChildren(container, [buildAlarmPlaceholderRow(placeholder)]);
                return;
            }

            replaceChildren(container, entriesToRender.map(buildAlarmRow));
        });
    }

    function formatJsonOutput(value) {
        if (typeof value === 'undefined' || value === null) {
            return JSON.stringify({ status: 'waiting' }, null, 2);
        }

        try {
            return JSON.stringify(value, null, 2);
        } catch (error) {
            return String(value);
        }
    }

    function updateJsonOutputs() {
        document.querySelectorAll('[data-state-json]').forEach(function (element) {
            const value = getNestedValue(appState, element.dataset.stateJson);
            element.textContent = formatJsonOutput(value);
        });
    }

    function voiceProgressIndex(stage) {
        const normalized = typeof stage === 'string' ? stage : '';
        if (['recording', 'recording_stopping', 'saving_audio', 'audio_saved'].indexOf(normalized) !== -1) {
            return 0;
        }
        if (['stt_requesting', 'stt_done'].indexOf(normalized) !== -1) {
            return 1;
        }
        if (['llm_requesting', 'llm_response', 'keyword_parsed', 'command_parsed', 'parse_rejected'].indexOf(normalized) !== -1) {
            return 2;
        }
        if (normalized === 'done') {
            return 3;
        }
        if (normalized === 'cancelled') {
            return -1;
        }
        if (normalized === 'error') {
            return -2;
        }
        return -1;
    }

    function compactVoiceStageLabel(stage, message) {
        if (stage === 'error' || stage === 'parse_rejected') {
            return '확인 필요';
        }
        if (stage === 'done') {
            return '완료';
        }
        if (stage === 'cancelled') {
            return '정지됨';
        }
        if (stage === 'stt_requesting') {
            return 'STT 중';
        }
        if (stage === 'llm_requesting') {
            return '해석 중';
        }
        if (stage) {
            return '진행 중';
        }
        return message || '대기';
    }

    function isVoiceCancelableStage(stage) {
        return VOICE_CANCELABLE_STAGES.indexOf(stage) !== -1;
    }

    function updateVoiceCancelButton(stage) {
        const button = document.querySelector('[data-voice-cancel]');
        if (!button) {
            return;
        }
        const canCancel = isVoiceCancelableStage(stage);
        button.hidden = !canCancel;
        button.disabled = !canCancel || isVoiceCancelRequestInFlight;
    }

    function voiceAuxLabel(aux0) {
        const labels = {
            right: 'X 방향',
            left: 'X 반대 방향',
            up: 'Y 방향',
            down: 'Y 반대 방향',
            forward: 'Z 방향',
            zoom_in: 'Z 반대 방향',
            backward: 'Z 반대 방향',
            zoom_out: 'Z 방향',
            clockwise: '시계방향 회전',
            counterclockwise: '반시계방향 회전',
            idle: 'Idle',
            prep: 'Prep',
            direct: '직접 교시',
            fixed: '선고정',
            point: '점고정',
            line: '선고정',
            plane: '면고정',
            rcm: 'RCM'
        };
        return labels[aux0] || aux0 || '-';
    }

    function formatVoiceCommand(command) {
        if (!command || typeof command !== 'object' || !command.action) {
            return '-';
        }
        if (command.action === 'mode') {
            return '모드: ' + voiceAuxLabel(command.aux0);
        }
        if (command.action === 'movel') {
            return 'MoveL: ' + voiceAuxLabel(command.aux0);
        }
        return command.action + (command.aux0 ? ': ' + voiceAuxLabel(command.aux0) : '');
    }

    function formatVoiceVector(command) {
        if (!command || typeof command !== 'object' || command.action !== 'movel' || !Array.isArray(command.tpos)) {
            return '-';
        }
        const axisNames = ['X', 'Y', 'Z', 'U', 'V', 'W'];
        const values = command.tpos
            .map(function (value, index) {
                const numeric = Number(value);
                if (!Number.isFinite(numeric) || numeric === 0) {
                    return null;
                }
                const sign = numeric > 0 ? '+' : '';
                const unit = index < 3 ? 'mm' : 'deg';
                return axisNames[index] + ' ' + sign + numeric + unit;
            })
            .filter(Boolean);
        return values.length > 0 ? values.join(', ') : '-';
    }

    function setVoiceResultField(name, value) {
        const element = document.querySelector('[data-voice-result-field="' + name + '"]');
        if (element) {
            element.textContent = value || '-';
        }
    }

    function updateVoiceResultPanel() {
        const result = getNestedValue(appState, 'voice_control.result_json') || {};
        const command = result.action_json || {};
        const stage = typeof result.stage === 'string' ? result.stage : '';
        const message = typeof result.message === 'string' ? result.message : '';
        const currentIndex = voiceProgressIndex(stage);
        const isError = stage === 'error' || stage === 'parse_rejected' || Boolean(result.last_error);

        document.querySelectorAll('[data-voice-step]').forEach(function (step, index) {
            step.classList.toggle('is-error', isError && (currentIndex < 0 || index === currentIndex));
            step.classList.toggle('is-complete', !isError && currentIndex >= 0 && index < currentIndex);
            step.classList.toggle('is-active', !isError && currentIndex >= 0 && index === currentIndex);
        });

        const badge = document.querySelector('[data-voice-stage-badge]');
        if (badge) {
            badge.textContent = compactVoiceStageLabel(stage, message);
            badge.classList.toggle('is-error', isError);
        }

        setVoiceResultField('stt', result.stt_text || '대기 중');
        setVoiceResultField('command', formatVoiceCommand(command));
        setVoiceResultField('vector', formatVoiceVector(command));
        setVoiceResultField('reply', command.aux1 || message || '-');
        updateVoiceCancelButton(stage);
    }

    function updateUi() {
        document.querySelectorAll('[data-state-text]').forEach(function (element) {
            const value = getNestedValue(appState, element.dataset.stateText);
            if (typeof value !== 'undefined') {
                element.textContent = value;
            }
        });

        document.querySelectorAll('[data-state-title]').forEach(function (element) {
            const value = getNestedValue(appState, element.dataset.stateTitle);
            if (typeof value !== 'undefined') {
                element.setAttribute('title', value);
            }
        });

        document.querySelectorAll('[data-state-aria-label]').forEach(function (element) {
            const value = getNestedValue(appState, element.dataset.stateAriaLabel);
            if (typeof value !== 'undefined') {
                element.setAttribute('aria-label', value);
            }
        });

        document.querySelectorAll('[data-state-time]').forEach(function (element) {
            const value = getNestedValue(appState, element.dataset.stateTime);
            element.textContent = formatTimestamp(value);
        });

        document.querySelectorAll('[data-state-flag]').forEach(function (element) {
            const value = Boolean(getNestedValue(appState, element.dataset.stateFlag));
            const trueText = element.dataset.flagTrueText || '요청됨';
            const falseText = element.dataset.flagFalseText || '대기 중';
            element.textContent = value ? trueText : falseText;
            element.classList.toggle('is-active', value);
        });

        document.querySelectorAll('[data-state-toggle]').forEach(function (button) {
            const value = Boolean(getNestedValue(appState, button.dataset.stateToggle));
            setPressedState(button, value);
        });

        document.querySelectorAll('[data-state-array]').forEach(function (button) {
            const arr = getNestedValue(appState, button.dataset.stateArray);
            const index = Number(button.dataset.index);
            const value = Array.isArray(arr) ? Boolean(arr[index]) : false;
            setPressedState(button, value);
        });

        document.querySelectorAll('[data-state-mode]').forEach(function (button) {
            const path = button.dataset.stateMode;
            const modeValue = button.dataset.modeValue;
            const current = getNestedValue(appState, path);
            const isActive = current === modeValue;
            button.classList.toggle('is-active', isActive);
            button.setAttribute('aria-pressed', String(isActive));
        });

        document.querySelectorAll('[data-state-radio]').forEach(function (input) {
            const path = input.dataset.stateRadio;
            const current = getNestedValue(appState, path);
            input.checked = input.value === current;
        });

        document.querySelectorAll('[data-state-color]').forEach(function (element) {
            const colorValue = getNestedValue(appState, element.dataset.stateColor);
            applyStatusColor(element, colorValue);
        });

        const manualHintElement = document.querySelector('[data-state-text="position_control.motion_hint"]');
        if (manualHintElement) {
            const isMoving = Boolean(getNestedValue(appState, 'position_control.is_moving'));
            manualHintElement.textContent = isMoving ? '이동 중…' : '버튼을 누르고 있는 동안 선택한 위치로 이동합니다.';
        }

        updateAlarmLogs();
        updateJsonOutputs();
        updateVoiceResultPanel();
    }

    function openAlarmHistory() {
        window.location.assign('/alarms');
    }

    function setupAlarmHistoryOpener() {
        const trigger = document.querySelector('[data-open-alarms]');
        if (!trigger) {
            return;
        }

        trigger.addEventListener('click', function (event) {
            if (event.defaultPrevented) {
                return;
            }
            openAlarmHistory();
        });

        trigger.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                openAlarmHistory();
            }
        });
    }

    function refreshState(nextState) {
        if (!nextState || typeof nextState !== 'object') {
            return;
        }
        appState = nextState;
        storeState(appState);
        updateUi();
    }

    function handleError(error) {
        console.error(error);
        window.alert('상태를 업데이트하는 중 오류가 발생했습니다. 자세한 내용은 콘솔을 확인하세요.');
    }

    function requestJson(method, url, body) {
        const options = {
            method: method,
            headers: { Accept: 'application/json' },
        };
        if (body !== undefined) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(body);
        }
        return fetch(url, options).then(function (response) {
            return parseResponsePayload(response).then(function (payload) {
                if (!response.ok) {
                    const message = getResponseErrorMessage(payload);
                    throw new Error(message);
                }
                return payload;
            });
        });
    }

    function parseResponsePayload(response) {
        if (response.status === 204) {
            return Promise.resolve(null);
        }

        const contentType = response.headers.get('content-type') || '';
        if (contentType.toLowerCase().indexOf('application/json') !== -1) {
            return response.json();
        }

        return response.text().then(function (text) {
            return text ? { message: text } : null;
        });
    }

    function getResponseErrorMessage(payload) {
        if (!payload || typeof payload !== 'object') {
            return '요청이 실패했습니다.';
        }
        if (payload.error) {
            return payload.error;
        }
        if (payload.detail) {
            if (typeof payload.detail === 'string') {
                return payload.detail;
            }
            if (Array.isArray(payload.detail)) {
                return payload.detail.map(function (entry) {
                    return entry && entry.msg ? entry.msg : JSON.stringify(entry);
                }).join(', ');
            }
            return JSON.stringify(payload.detail);
        }
        if (payload.message) {
            return payload.message;
        }
        return '요청이 실패했습니다.';
    }

    function backendRequest(method, path, body) {
        if (!BACKEND_BASE_URL) {
            return Promise.reject(new Error('백엔드 URL이 구성되지 않았습니다.'));
        }
        const url = BACKEND_BASE_URL + path;
        return requestJson(method, url, body);
    }

    function pushUpdate(payload) {
        if (!payload || Object.keys(payload).length === 0) {
            return Promise.resolve();
        }
        const requester = BACKEND_BASE_URL ? backendRequest : requestJson;
        return requester('PATCH', '/api/state', payload).then(function (data) {
            refreshState(data);
        });
    }

    function touchState(path) {
        if (!path) {
            return Promise.resolve();
        }
        const requester = BACKEND_BASE_URL ? backendRequest : requestJson;
        return requester('POST', '/api/state/touch/' + encodeURIComponent(path)).then(function (data) {
            refreshState(data);
        });
    }

    function attachLongPressHandler(target, callback, options) {
        if (!target) {
            return;
        }
        options = options || {};
        let holdTimer = null;
        let wasActivated = false;
        let holdDuration = HOLD_ACTIVATION_DURATION_MS;

        if (typeof options.holdDuration === 'number' && options.holdDuration >= 0) {
            holdDuration = options.holdDuration;
        } else if (target.dataset && typeof target.dataset.holdDuration !== 'undefined') {
            const parsedDuration = Number(target.dataset.holdDuration);
            if (!Number.isNaN(parsedDuration) && parsedDuration >= 0) {
                holdDuration = parsedDuration;
            }
        }

        function clearTimer() {
            if (holdTimer !== null) {
                window.clearTimeout(holdTimer);
                holdTimer = null;
            }
        }

        function invokeCallback(phase, event) {
            if (typeof callback !== 'function') {
                return;
            }
            try {
                const result = callback({ phase: phase, event: event, target: target });
                if (result && typeof result.then === 'function') {
                    result.catch(handleError);
                }
            } catch (error) {
                handleError(error);
            }
        }

        function stopHold(event) {
            if (typeof event !== 'undefined' && typeof event.pointerId === 'number' && target.hasPointerCapture && target.hasPointerCapture(event.pointerId)) {
                target.releasePointerCapture(event.pointerId);
            }
            target.classList.remove('is-holding');
            target.classList.remove('is-held');
            clearTimer();
            if (wasActivated) {
                wasActivated = false;
                invokeCallback('deactivated', event);
            }
        }

        function handleActivation(event) {
            wasActivated = true;
            holdTimer = null;
            target.classList.add('is-held');
            invokeCallback('activated', event);
        }

        function startHold(event) {
            if (event && event.type === 'pointerdown') {
                if (event.pointerType === 'mouse' && event.button !== 0) {
                    return;
                }
                if (typeof event.pointerId === 'number' && target.setPointerCapture) {
                    try {
                        target.setPointerCapture(event.pointerId);
                    } catch (error) {
                        /* noop */
                    }
                }
            }
            target.classList.add('is-holding');
            wasActivated = false;
            clearTimer();
            holdTimer = window.setTimeout(function () {
                handleActivation(event);
            }, holdDuration);
        }

        target.addEventListener('pointerdown', startHold);
        ['pointerup', 'pointerleave', 'pointercancel'].forEach(function (eventName) {
            target.addEventListener(eventName, function (event) {
                stopHold(event);
            });
        });

        target.addEventListener('keydown', function (event) {
            if ((event.code === 'Space' || event.code === 'Enter') && !event.repeat) {
                event.preventDefault();
                startHold();
            }
        });

        target.addEventListener('keyup', function (event) {
            if (event.code === 'Space' || event.code === 'Enter') {
                event.preventDefault();
                stopHold(event);
            }
        });

        target.addEventListener('blur', function () {
            if (holdTimer !== null || wasActivated) {
                stopHold({});
            }
        });
    }

    class StatePoller {
        constructor(options) {
            options = options || {};
            this.interval = options.interval || STATE_SYNC_INTERVAL_MS;
            this.maxInterval = options.maxInterval || MAX_STATE_SYNC_INTERVAL_MS;
            this.fetcher = options.fetcher;
            this.onData = options.onData || function () { return Promise.resolve(); };
            this.onError = options.onError || function (error) {
                console.warn('State poll failed:', error);
            };
            this.timer = null;
            this.isRunning = false;
            this.isFetching = false;
            this.consecutiveFailures = 0;
        }

        start() {
            if (this.isRunning || typeof this.fetcher !== 'function') {
                return;
            }
            this.isRunning = true;
            this.poll();
        }

        scheduleNextPoll(delay) {
            if (!this.isRunning) {
                return;
            }
            if (this.timer !== null) {
                window.clearTimeout(this.timer);
                this.timer = null;
            }
            this.timer = window.setTimeout(this.poll.bind(this), delay || this.interval);
        }

        poll() {
            if (!this.isRunning || this.isFetching) {
                return;
            }
            if (document.hidden) {
                this.scheduleNextPoll(this.interval);
                return;
            }
            this.isFetching = true;
            this.fetcher()
                .then((payload) => {
                    this.consecutiveFailures = 0;
                    if (!payload) {
                        return null;
                    }
                    return Promise.resolve(this.onData(payload));
                })
                .catch((error) => {
                    this.consecutiveFailures += 1;
                    if (this.consecutiveFailures === 1 || this.consecutiveFailures % 5 === 0) {
                        this.onError(error);
                    }
                })
                .finally(() => {
                    const nextDelay = this.consecutiveFailures > 0
                        ? Math.min(this.interval * Math.pow(2, this.consecutiveFailures), this.maxInterval)
                        : this.interval;
                    this.isFetching = false;
                    this.scheduleNextPoll(nextDelay);
                });
        }

        stop() {
            this.isRunning = false;
            if (this.timer !== null) {
                window.clearTimeout(this.timer);
                this.timer = null;
            }
        }
    }

    function setupToggleButtons() {
        document.querySelectorAll('[data-state-toggle]').forEach(function (button) {
            if (button.dataset.directTeachTrigger) {
                return;
            }
            button.addEventListener('click', function () {
                const path = button.dataset.stateToggle;
                const current = Boolean(getNestedValue(appState, path));
                const next = !current;
                const payload = mergePayload({}, path, next);

                pushUpdate(payload).catch(handleError);
            });
        });
    }

    function setupArrayToggles() {
        document.querySelectorAll('[data-state-array]').forEach(function (button) {
            if (button.dataset.servoAction) {
                return;
            }
            button.addEventListener('click', function () {
                const path = button.dataset.stateArray;
                const index = Number(button.dataset.index);
                const current = getNestedValue(appState, path);
                const next = Array.isArray(current) ? current.slice() : [];
                next[index] = !Boolean(next[index]);
                const payload = mergePayload({}, path, next);
                pushUpdate(payload).catch(handleError);
            });
        });
    }

    function setupModeButtons() {
        document.querySelectorAll('[data-state-mode]').forEach(function (button) {
            button.addEventListener('click', function () {
                const path = button.dataset.stateMode;
                const value = button.dataset.modeValue;
                if (!path || !value) {
                    return;
                }
                const current = getNestedValue(appState, path);
                if (current === value) {
                    return;
                }
                const payload = mergePayload({}, path, value);
                pushUpdate(payload).catch(handleError);
            });
        });
    }

    function findPositionIndex(positionId) {
        if (typeof positionId !== 'string' || positionId.length === 0) {
            return null;
        }
        const positions = getNestedValue(appState, 'position_control.available_positions');
        if (!Array.isArray(positions)) {
            return null;
        }
        const index = positions.findIndex(function (position) {
            return position && position.id === positionId;
        });
        return index >= 0 ? index : null;
    }

    function setupRadioInputs() {
        document.querySelectorAll('[data-state-radio]').forEach(function (input) {
            input.addEventListener('change', function () {
                if (!input.checked) {
                    return;
                }
                const path = input.dataset.stateRadio;
                const payload = mergePayload({}, path, input.value);
                const rawIndex = input.dataset.positionIndex;
                const positionIndex = rawIndex !== undefined ? Number(rawIndex) : findPositionIndex(input.value);
                if (positionIndex !== null && !Number.isNaN(positionIndex)) {
                    mergePayload(payload, 'position_control.target_position_index', positionIndex);
                }
                applyLocalStatePatch(payload);
            });
        });
    }

    function getSelectedPosition() {
        const selected = document.querySelector('input[name="position-control"]:checked');
        if (!selected) {
            return { targetPosition: null, targetIndex: null };
        }

        const targetValue = typeof selected.value === 'string' ? selected.value : '';
        const rawIndex = selected.dataset ? selected.dataset.positionIndex : undefined;
        const positionIndex = rawIndex !== undefined ? Number(rawIndex) : findPositionIndex(targetValue);

        return {
            targetPosition: targetValue && targetValue.length > 0 ? targetValue : null,
            targetIndex: positionIndex !== null && !Number.isNaN(positionIndex) ? positionIndex : null,
        };
    }

    function buildPositionPayload() {
        const payload = {};
        const selection = getSelectedPosition();

        if (selection.targetPosition) {
            mergePayload(payload, 'position_control.target_position', selection.targetPosition);
        }
        if (selection.targetIndex !== null) {
            mergePayload(payload, 'position_control.target_position_index', selection.targetIndex);
        }

        return payload;
    }


    function extractPositionBackendOverrides(positionPayload) {
        const overrides = {};
        if (!positionPayload || typeof positionPayload !== 'object') {
            return overrides;
        }
        const positionControl = positionPayload.position_control;
        if (positionControl && typeof positionControl === 'object') {
            if (Object.prototype.hasOwnProperty.call(positionControl, 'target_position_index')) {
                overrides.target_position_index = positionControl.target_position_index;
            }
            if (Object.prototype.hasOwnProperty.call(positionControl, 'target_position')) {
                overrides.target_position = positionControl.target_position;
            }
        }
        return overrides;
    }


    function applyPositionControlState(state) {
        if (!state || typeof state !== 'object') {
            return Promise.resolve();
        }
        const payload = {};
        let hasChanges = false;

        let nextIsMoving = Boolean(getNestedValue(appState, 'position_control.is_moving'));

        if (Object.prototype.hasOwnProperty.call(state, 'is_moving')) {
            const isMoving = Boolean(state.is_moving);
            if (nextIsMoving !== isMoving) {
                nextIsMoving = isMoving;
                mergePayload(payload, 'position_control.is_moving', isMoving);
                hasChanges = true;
            }
        }

        if (Object.prototype.hasOwnProperty.call(state, 'last_moved_at')) {
            if (getNestedValue(appState, 'position_control.last_moved_at') !== state.last_moved_at) {
                mergePayload(payload, 'position_control.last_moved_at', state.last_moved_at);
                hasChanges = true;
            }
        }

        const desiredHint = nextIsMoving ? '이동 중…' : '버튼을 누르고 있는 동안 선택한 위치로 이동합니다.';
        if (getNestedValue(appState, 'position_control.motion_hint') !== desiredHint) {
            mergePayload(payload, 'position_control.motion_hint', desiredHint);
            hasChanges = true;
        }

        if (!hasChanges) {
            return Promise.resolve();
        }
        applyLocalStatePatch(payload);
        return Promise.resolve();
    }


    let isVoiceHoldActive = false;

    function applyVoiceControlState(state) {
        if (!state || typeof state !== 'object') {
            return Promise.resolve();
        }

        const payload = {};
        let hasChanges = false;

        let nextIsListening = Boolean(getNestedValue(appState, 'voice_control.is_listening'));

        Object.keys(state).forEach(function (key) {
            if (key === 'status_text') {
                return;
            }
            const path = 'voice_control.' + key;
            const current = getNestedValue(appState, path);
            const next = state[key];
            const bothObjects = current && next && typeof current === 'object' && typeof next === 'object';
            const hasSameValue = bothObjects ? JSON.stringify(current) === JSON.stringify(next) : current === next;
            if (!hasSameValue) {
                mergePayload(payload, path, next);
                hasChanges = true;
            }
            if (key === 'is_listening') {
                nextIsListening = Boolean(next);
            }
        });

        const shouldForceActiveText = nextIsListening === true || isVoiceHoldActive === true;
        const backendStatusText = typeof state.status_text === 'string' && state.status_text.trim()
            ? state.status_text
            : null;
        const desiredStatusText = backendStatusText || (
            shouldForceActiveText
                ? '음성 녹음 중…'
                : '버튼을 누르면 음성을 녹음합니다.'
        );

        if (getNestedValue(appState, 'voice_control.status_text') !== desiredStatusText) {
            mergePayload(payload, 'voice_control.status_text', desiredStatusText);
            hasChanges = true;
        }

        if (!hasChanges) {
            return Promise.resolve();
        }

        applyLocalStatePatch(payload);
        return Promise.resolve();
    }


    function applySystemState(systemState) {
        if (!systemState || typeof systemState !== 'object') {
            return Promise.resolve();
        }

        const payload = {};
        let hasChanges = false;

        Object.keys(systemState).forEach(function (key) {
            const path = 'system.' + key;
            const current = getNestedValue(appState, path);
            const next = systemState[key];
            if (typeof next === 'object' && next !== null) {
                if (JSON.stringify(current) !== JSON.stringify(next)) {
                    mergePayload(payload, path, next);
                    hasChanges = true;
                }
            } else if (current !== next) {
                mergePayload(payload, path, next);
                hasChanges = true;
            }
        });

        if (!hasChanges) {
            return Promise.resolve();
        }
        applyLocalStatePatch(payload); // <-- 화면만 갱신
        return Promise.resolve();
        // return pushUpdate(payload);
    }


    function applyServoState(servoState) {
        if (!servoState || typeof servoState !== 'object') {
            return Promise.resolve();
        }

        const payload = {};
        let hasChanges = false;

        ['servos', 'brakes'].forEach(function (key) {
            if (Object.prototype.hasOwnProperty.call(servoState, key)) {
                const current = getNestedValue(appState, 'servo_control.' + key);
                const next = servoState[key];
                if (JSON.stringify(current) !== JSON.stringify(next)) {
                    mergePayload(payload, 'servo_control.' + key, next);
                    hasChanges = true;
                }
            }
        });

        if (!hasChanges) {
            return Promise.resolve();
        }
        applyLocalStatePatch(payload); // <-- 화면만 갱신
        return Promise.resolve();
        // return pushUpdate(payload);
    }


    function sendPositionMovementCommand(kind, overrides) {
        if (!BACKEND_BASE_URL) {
            return Promise.resolve();
        }
        const endpoint = kind === 'start' ? '/api/position-control/move/start' : '/api/position-control/move/stop';
        const body = {};

        const selection = getSelectedPosition();

        let targetIndex;
        if (overrides && Object.prototype.hasOwnProperty.call(overrides, 'target_position_index')) {
            targetIndex = overrides.target_position_index;
        } else {
            targetIndex = getNestedValue(appState, 'position_control.target_position_index');
            if (typeof targetIndex === 'undefined' || Number.isNaN(targetIndex)) {
                targetIndex = selection.targetIndex;
            }
        }
        if (typeof targetIndex === 'number' && !Number.isNaN(targetIndex)) {
            body.target_position_index = targetIndex;
        }

        let targetPosition;
        if (overrides && Object.prototype.hasOwnProperty.call(overrides, 'target_position')) {
            targetPosition = overrides.target_position;
        } else {
            targetPosition = getNestedValue(appState, 'position_control.target_position');
            if (typeof targetPosition === 'undefined' || targetPosition === null || targetPosition === '') {
                targetPosition = selection.targetPosition;
            }
        }
        if (typeof targetPosition === 'string' && targetPosition.length > 0) {
            body.target_position = targetPosition;
        }

        return backendRequest('POST', endpoint, body).then(function () {
            return Promise.resolve();
        });
    }


    function sendVoiceControlCommand(kind) {
        if (!BACKEND_BASE_URL) {
            return Promise.resolve();
        }

        const endpoint = kind === 'start' ? '/api/voice-control/move/start' : '/api/voice-control/move/stop';

        // Send an empty JSON body so the backend Body(...) declaration accepts the request
        // even when no extra payload is required.
        const body = {};

        return backendRequest('POST', endpoint, body).then(function () {
            return Promise.resolve();
        });
    }

    function sendVoiceCancelCommand() {
        if (!BACKEND_BASE_URL) {
            return Promise.resolve();
        }

        return backendRequest('POST', '/api/voice-control/move/cancel', {}).then(function (payload) {
            if (payload && payload.voice_control) {
                return applyVoiceControlState(payload.voice_control);
            }
            return Promise.resolve();
        });
    }

    function setVoiceDeviceStatus(message, isError) {
        const status = document.querySelector('[data-voice-device-status]');
        if (!status) {
            return;
        }
        status.textContent = message || '';
        status.classList.toggle('is-error', Boolean(isError));
    }


    function buildVoiceDeviceLabel(device) {
        const parts = [device.name || '마이크'];
        if (device.hostapi) {
            parts.push(device.hostapi);
        }
        if (device.max_input_channels) {
            parts.push(device.max_input_channels + 'ch');
        }
        return parts.join(' · ');
    }


    function renderVoiceDeviceOptions(payload) {
        const select = document.querySelector('[data-voice-device-select]');
        if (!select) {
            return;
        }

        const devices = payload && Array.isArray(payload.devices) ? payload.devices : [];
        const voiceState = payload && payload.voice_control ? payload.voice_control : {};
        const selectedId = voiceState.selected_device_id;
        const selectedValue = selectedId === null || typeof selectedId === 'undefined' ? '' : String(selectedId);

        while (select.firstChild) {
            select.removeChild(select.firstChild);
        }

        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = '기본 입력 장치';
        select.appendChild(defaultOption);

        devices.forEach(function (device) {
            const option = document.createElement('option');
            option.value = String(device.id);
            option.textContent = buildVoiceDeviceLabel(device);
            select.appendChild(option);
        });

        select.value = selectedValue;
        if (select.value !== selectedValue) {
            select.value = '';
        }

        if (payload && payload.error) {
            setVoiceDeviceStatus('마이크 목록을 불러오지 못했습니다.', true);
        } else if (devices.length === 0) {
            setVoiceDeviceStatus('사용 가능한 입력 장치가 없습니다.', true);
        } else {
            setVoiceDeviceStatus('마이크 목록이 준비되었습니다.', false);
        }
    }


    function loadVoiceDevices() {
        if (!document.querySelector('[data-voice-device-select]')) {
            return Promise.resolve();
        }
        if (!BACKEND_BASE_URL) {
            setVoiceDeviceStatus('백엔드 URL이 설정되지 않았습니다.', true);
            return Promise.resolve();
        }

        setVoiceDeviceStatus('마이크 목록 불러오는 중...', false);
        return backendRequest('GET', '/api/voice-control/devices')
            .then(function (payload) {
                renderVoiceDeviceOptions(payload);
                if (payload && payload.voice_control) {
                    return applyVoiceControlState(payload.voice_control);
                }
                return Promise.resolve();
            })
            .catch(function (error) {
                console.warn('마이크 목록 불러오기 실패:', error);
                setVoiceDeviceStatus('마이크 목록을 불러오지 못했습니다.', true);
            });
    }


    function applyVoiceDeviceSelection(button) {
        const select = document.querySelector('[data-voice-device-select]');
        if (!select || !BACKEND_BASE_URL) {
            return Promise.resolve();
        }

        const selectedValue = select.value;
        const deviceId = selectedValue === '' ? null : Number(selectedValue);
        if (selectedValue !== '' && Number.isNaN(deviceId)) {
            setVoiceDeviceStatus('마이크 선택값이 올바르지 않습니다.', true);
            return Promise.resolve();
        }

        if (button) {
            button.disabled = true;
        }
        setVoiceDeviceStatus('마이크 적용 중...', false);

        return backendRequest('POST', '/api/voice-control/device', { device_id: deviceId })
            .then(function (payload) {
                renderVoiceDeviceOptions(payload);
                if (payload && payload.voice_control) {
                    return applyVoiceControlState(payload.voice_control);
                }
                return Promise.resolve();
            })
            .then(function () {
                const selectedName = getNestedValue(appState, 'voice_control.selected_device_name') || '기본 입력 장치';
                setVoiceDeviceStatus(selectedName + ' 적용됨', false);
            })
            .catch(function (error) {
                console.warn('마이크 적용 실패:', error);
                setVoiceDeviceStatus(error.message || '마이크 적용에 실패했습니다.', true);
            })
            .finally(function () {
                if (button) {
                    button.disabled = false;
                }
            });
    }


    function setupVoiceDeviceControls() {
        const applyButton = document.querySelector('[data-voice-device-apply]');
        if (!applyButton) {
            return;
        }

        applyButton.addEventListener('click', function () {
            applyVoiceDeviceSelection(applyButton);
        });
        loadVoiceDevices();
    }


    function setupVoiceCancelControl() {
        const button = document.querySelector('[data-voice-cancel]');
        if (!button) {
            return;
        }

        button.addEventListener('click', function () {
            if (isVoiceCancelRequestInFlight) {
                return;
            }
            isVoiceCancelRequestInFlight = true;
            button.disabled = true;
            sendVoiceCancelCommand()
                .catch(handleError)
                .finally(function () {
                    isVoiceCancelRequestInFlight = false;
                    updateVoiceResultPanel();
                });
        });
    }


    function hasElement(selector) {
        return Boolean(document.querySelector(selector));
    }

    function shouldPollFullBackendState() {
        return Boolean(
            document.querySelector(
                '[data-cb-control-sync], [data-servo-action], [data-hold-button], [data-mode-action], ' +
                '[data-state-mode], [data-state-radio], [data-state-toggle], [data-state-array], ' +
                '[data-state-text^="cb_control"], [data-state-text^="position_control"], ' +
                '[data-state-text^="voice_control"], [data-state-text^="mode_control"]'
            )
        );
    }

    function shouldPollSystemState() {
        return hasElement('[data-state-text^="system"], [data-state-time^="system"], [data-state-color^="system"]');
    }

    function shouldPollAlarmLog() {
        return hasElement('[data-alarm-log]');
    }

    function mergeBackendPayload(target, payload) {
        if (!payload || typeof payload !== 'object') {
            return target;
        }

        Object.keys(payload).forEach(function (key) {
            target[key] = payload[key];
        });
        return target;
    }

    function fetchBackendSnapshot() {
        if (!BACKEND_BASE_URL) {
            return Promise.resolve(null);
        }

        const requests = [];
        if (shouldPollFullBackendState()) {
            requests.push(backendRequest('GET', '/api/state'));
        } else if (shouldPollSystemState()) {
            requests.push(backendRequest('GET', '/api/system/state'));
        }

        if (shouldPollAlarmLog()) {
            requests.push(backendRequest('GET', '/api/alarms'));
        }

        if (requests.length === 0) {
            return Promise.resolve(null);
        }

        return Promise.all(requests).then(function (payloads) {
            return payloads.reduce(mergeBackendPayload, {});
        });
    }

    function applyBackendSnapshot(payload) {
        if (!payload || typeof payload !== 'object') {
            return Promise.resolve();
        }
        const operations = [];
        if (payload.system) {
            operations.push(applySystemState(payload.system));
        }
        if (payload.servo_control) {
            operations.push(applyServoState(payload.servo_control));
        }
        if (payload.cb_control) {
            operations.push(applyCbControlState(payload.cb_control));
        }
        if (payload.position_control) {
            operations.push(applyPositionControlState(payload.position_control));
        }
        if (payload.voice_control) {
            operations.push(applyVoiceControlState(payload.voice_control));
        }
        if (payload.mode_control) {
            operations.push(applyModeControlState(payload.mode_control));
        }
        if (payload.alarms || payload.last_updated) {
            operations.push(applyBackendAlarmSnapshot(payload));
        }
        if (operations.length === 0) {
            return Promise.resolve();
        }
        return Promise.all(operations);
    }

    function applyBackendAlarmSnapshot(payload) {
        if (!payload || typeof payload !== 'object') {
            return Promise.resolve();
        }

        const updates = {};
        let hasChanges = false;

        if (payload.alarms && typeof payload.alarms === 'object') {
            const current = getNestedValue(appState, 'system.alarms');
            if (JSON.stringify(current) !== JSON.stringify(payload.alarms)) {
                mergePayload(updates, 'system.alarms', payload.alarms);
                hasChanges = true;
            }
        }

        if (payload.last_updated) {
            const currentUpdated = getNestedValue(appState, 'system.alarms_last_updated');
            if (currentUpdated !== payload.last_updated) {
                mergePayload(updates, 'system.alarms_last_updated', payload.last_updated);
                hasChanges = true;
            }
        }

        if (!hasChanges) {
            return Promise.resolve();
        }
        applyLocalStatePatch(updates);
        return Promise.resolve();
    }

    function initialiseStatePoller() {
        if (!BACKEND_BASE_URL) {
            return;
        }
        if (statePoller) {
            statePoller.stop();
        }
        statePoller = new StatePoller({
            interval: STATE_SYNC_INTERVAL_MS,
            fetcher: fetchBackendSnapshot,
            onData: applyBackendSnapshot,
            onError: function (error) {
                console.warn('백엔드 상태 동기화 실패:', error);
            },
        });
        statePoller.start();
    }

    function handleServoToggle(button) {
        const kind = button.dataset.servoAction;
        const joint = Number(button.dataset.servoIndex);
        if (!BACKEND_BASE_URL || Number.isNaN(joint) || !kind) {
            return Promise.resolve();
        }

        const path = kind === 'brake' ? 'servo_control.brakes' : 'servo_control.servos';
        const current = getNestedValue(appState, path);
        const currentValue = Array.isArray(current) ? Boolean(current[joint]) : false;
        const nextValue = !currentValue;

        button.disabled = true;

        return backendRequest('POST', '/api/servo-control/set', {
            kind: kind,
            joint: joint,
            value: nextValue,
        })
            .then(function (payload) {
                if (payload && payload.servo_control) {
                    return applyServoState(payload.servo_control);
                }
                return Promise.resolve();
            })
            .catch(handleError)
            .finally(function () {
                button.disabled = false;
            });
    }

    function handlePositionHoldActivation(button) {
        const payload = buildPositionPayload();
        const backendOverrides = extractPositionBackendOverrides(payload);
        if (button.dataset.holdActivate) {
            mergePayload(payload, button.dataset.holdActivate, true);
            if (button.dataset.holdActivate === 'position_control.is_moving') {
                mergePayload(payload, 'position_control.motion_hint', '이동 중…');
            }
        }
        if (button.dataset.holdTouch) {
            mergePayload(payload, button.dataset.holdTouch, new Date().toISOString());
        }
        if (Object.keys(payload).length > 0) {
            applyLocalStatePatch(payload);
        }
        return sendPositionMovementCommand('start', backendOverrides);
    }

    function handlePositionHoldDeactivation(button) {
        const payload = buildPositionPayload();
        const backendOverrides = extractPositionBackendOverrides(payload);
        if (button.dataset.holdDeactivate) {
            mergePayload(payload, button.dataset.holdDeactivate, false);
            if (button.dataset.holdDeactivate === 'position_control.is_moving') {
                mergePayload(payload, 'position_control.motion_hint', '버튼을 누르고 있는 동안 선택한 위치로 이동합니다.');
            }
        }
        if (button.dataset.holdTouch) {
            mergePayload(payload, button.dataset.holdTouch, new Date().toISOString());
        }
        if (Object.keys(payload).length > 0) {
            applyLocalStatePatch(payload);
        }
        return sendPositionMovementCommand('stop', backendOverrides);
    }


    function handleVoiceHoldActivation(button) {
        const payload = {};
        const timestamp = new Date().toISOString();
        const activeText = '음성 녹음 중…';

        isVoiceHoldActive = true;

        if (button.dataset.holdActivate) {
            mergePayload(payload, button.dataset.holdActivate, true);
        }
        if (button.dataset.holdTouch) {
            mergePayload(payload, button.dataset.holdTouch, timestamp);
        }

        mergePayload(payload, 'voice_control.status_text', activeText);

        if (Object.keys(payload).length > 0) {
            applyLocalStatePatch(payload);
        }

        return sendVoiceControlCommand('start');
    }


    function handleVoiceHoldDeactivation(button) {
        const payload = {};
        const timestamp = new Date().toISOString();
        const idleText = '버튼을 누르면 음성을 녹음합니다.';

        isVoiceHoldActive = false;

        if (button.dataset.holdDeactivate) {
            mergePayload(payload, button.dataset.holdDeactivate, false);
        }

        mergePayload(payload, 'voice_control.status_text', idleText);
        mergePayload(payload, 'voice_control.last_stopped_at', timestamp);

        if (Object.keys(payload).length > 0) {
            applyLocalStatePatch(payload);
        }

        return sendVoiceControlCommand('stop');
    }


    function applyModeControlState(modeState) {
        if (!modeState || typeof modeState !== 'object') {
            return Promise.resolve();
        }

        const payload = {};
        let hasChanges = false;

        Object.keys(modeState).forEach(function (key) {
            const path = 'mode_control.' + key;
            const current = getNestedValue(appState, path);
            const next = modeState[key];
            if (typeof next === 'object' && next !== null) {
                const currentString = JSON.stringify(current);
                const nextString = JSON.stringify(next);
                if (currentString !== nextString) {
                    mergePayload(payload, path, next);
                    hasChanges = true;
                }
            } else if (current !== next) {
                mergePayload(payload, path, next);
                hasChanges = true;
            }
        });

        if (!hasChanges) {
            return Promise.resolve();
        }

        applyLocalStatePatch(payload);
        return Promise.resolve();
    }


    function sendModeControlCommand(action, modeId) {
        if (!BACKEND_BASE_URL || !modeId) {
            return Promise.resolve();
        }

        const endpoint = '/api/mode-control/' + action;
        const payload = { mode: modeId };

        return backendRequest('POST', endpoint, payload).then(function (response) {
            if (response && response.mode_control) {
                return applyModeControlState(response.mode_control);
            }
            return Promise.resolve();
        });
    }


    function handleModeAction(button) {
        const modeId = button.dataset.modeId;
        if (!modeId) {
            return Promise.resolve();
        }

        button.disabled = true;

        return sendModeControlCommand('execute', modeId)
            .catch(function (error) {
                handleError(error);
            })
            .finally(function () {
                button.disabled = false;
            });
    }


    function setupModeControlActions() {
        document.querySelectorAll('[data-mode-action]').forEach(function (button) {
            attachLongPressHandler(button, function (context) {
                if (context.phase === 'activated') {
                    return handleModeAction(button);
                }
                return Promise.resolve();
            });
        });
    }

    function applyCbControlState(cbState) {
        if (!cbState || typeof cbState !== 'object') {
            return Promise.resolve();
        }
        const payload = {};
        let hasChanges = false;
        Object.keys(cbState).forEach(function (key) {
            const path = 'cb_control.' + key;
            const current = getNestedValue(appState, path);
            const next = cbState[key];
            if (typeof next === 'object' && next !== null) {
                const currentString = JSON.stringify(current);
                const nextString = JSON.stringify(next);
                if (currentString !== nextString) {
                    mergePayload(payload, path, next);
                    hasChanges = true;
                }
            } else if (current !== next) {
                mergePayload(payload, path, next);
                hasChanges = true;
            }
        });
        if (!hasChanges) {
            return Promise.resolve();
        }
        applyLocalStatePatch(payload); // <-- 화면만 갱신
        return Promise.resolve();
        // return pushUpdate(payload);
    }

    function handleCbControlAction(kind) {
        const endpoint = '/api/cb-control/' + kind;
        const timestamp = new Date().toISOString();

        return backendRequest('POST', endpoint, { requested_at: timestamp })
            .then(function () {
                return backendRequest('GET', '/api/cb-control/state');
            })
            .then(function (payload) {
                if (payload && payload.cb_control) {
                    return applyCbControlState(payload.cb_control);
                }
                return Promise.resolve();
            });
    }

    function setupTriggers() {
        document.querySelectorAll('[data-state-trigger]').forEach(function (button) {
            button.addEventListener('click', function () {
                const action = button.dataset.stateTrigger;
                if (!action) {
                    return;
                }
                if (action === 'cb_control.reboot') {
                    button.disabled = true;
                    handleCbControlAction('reboot')
                        .then(function () {
                            button.disabled = false;
                        })
                        .catch(function (error) {
                            button.disabled = false;
                            handleError(error);
                        });
                    return;
                }
                if (action === 'cb_control.shutdown') {
                    button.disabled = true;
                    handleCbControlAction('shutdown')
                        .then(function () {
                            button.disabled = false;
                        })
                        .catch(function (error) {
                            button.disabled = false;
                            handleError(error);
                        });
                    return;
                }
                console.warn('처리되지 않은 상태 트리거:', action);
            });
        });
    }

    function handleHoldTriggerAction(button, action) {
        if (!action) {
            return Promise.resolve();
        }
        let request;
        if (action === 'cb_control.reboot') {
            request = handleCbControlAction('reboot');
        } else if (action === 'cb_control.shutdown') {
            request = handleCbControlAction('shutdown');
        } else if (action === 'cb_control.motion_start') {
            request = handleCbControlAction('motion-start');
        } else if (action === 'cb_control.motion_stop') {
            request = handleCbControlAction('motion-stop');
        } else if (action === 'system.update') {
            const timestamp = new Date().toISOString();
            request = handleSystemUpdateAction(timestamp);
        } else {
            console.warn('처리되지 않은 Hold 상태 트리거:', action);
            return Promise.resolve();
        }

        button.disabled = true;
        return request
            .catch(function (error) {
                handleError(error);
            })
            .finally(function () {
                button.disabled = false;
            });
    }

    function setupLongPressControls() {
        document.querySelectorAll('[data-servo-action]').forEach(function (button) {
            attachLongPressHandler(button, function (context) {
                if (context.phase === 'activated') {
                    return handleServoToggle(button);
                }
                return Promise.resolve();
            });
        });

        document.querySelectorAll('[data-hold-button]:not([data-servo-action])').forEach(function (button) {
            if (button.dataset.directTeachTrigger || button.dataset.stateTriggerHold) {
                return;
            }
            const holdKind = button.dataset.holdKind || 'position';
            attachLongPressHandler(button, function (context) {
                if (context.phase === 'activated') {
                    if (holdKind === 'voice_control') {
                        return handleVoiceHoldActivation(button);
                    }
                    return handlePositionHoldActivation(button);
                }
                if (context.phase === 'deactivated') {
                    if (holdKind === 'voice_control') {
                        return handleVoiceHoldDeactivation(button);
                    }
                    return handlePositionHoldDeactivation(button);
                }
                return Promise.resolve();
            });
        });

        document.querySelectorAll('[data-state-trigger-hold]').forEach(function (button) {
            const action = button.dataset.stateTriggerHold;
            if (!action) {
                return;
            }
            attachLongPressHandler(button, function (context) {
                if (context.phase === 'activated') {
                    return handleHoldTriggerAction(button, action);
                }
                return Promise.resolve();
            });
        });
    }

    function handleSystemUpdateAction(requestedAt) {
        if (!BACKEND_BASE_URL) {
            return Promise.resolve();
        }
        const payload = { requested_at: requestedAt };

        return backendRequest('POST', '/api/system/update', payload)
            .then(function (response) {
                if (response && response.system) {
                    return applySystemState(response.system);
                }
                return Promise.resolve();
            });
    }

    function initialise() {
        storeState(appState);
        updateUi();
        setupAlarmHistoryOpener();
        setupToggleButtons();
        setupArrayToggles();
        setupModeButtons();
        setupModeControlActions();
        setupRadioInputs();
        setupLongPressControls();
        setupTriggers();
        setupVoiceDeviceControls();
        setupVoiceCancelControl();
        initialiseStatePoller();

    }

    document.addEventListener('DOMContentLoaded', initialise);

    document.addEventListener('visibilitychange', function () {
        if (!document.hidden && statePoller) {
            statePoller.poll();
        }
    });

    window.addEventListener('beforeunload', function () {
        if (statePoller) {
            statePoller.stop();
            statePoller = null;
        }
    });
})();
