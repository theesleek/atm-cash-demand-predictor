const DEFAULT_RECONNECT_DELAY_MS = 500;
const MAX_RECONNECT_DELAY_MS = 10000;
const DEFAULT_API_URL = 'http://localhost:8000';

export function buildRealtimeWebSocketUrl(apiUrl = import.meta.env.VITE_API_URL || DEFAULT_API_URL) {
  if (apiUrl.startsWith('/')) {
    return `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}${apiUrl}/ws/events`;
  }

  const endpoint = new URL('/ws/events', apiUrl);
  endpoint.protocol = endpoint.protocol === 'https:' ? 'wss:' : 'ws:';
  return endpoint.toString();
}

export function consumeUnseenRealtimeEvents(events, seenRef) {
  if (seenRef.current === null) {
    seenRef.current = new Set(events.map((event) => [event.event_type, event.entity_type, event.entity_id, event.timestamp].join(':')));
    return [];
  }
  const unseen = [];
  for (const event of events) {
    const key = [event.event_type, event.entity_type, event.entity_id, event.timestamp].join(':');
    if (seenRef.current.has(key)) continue;
    seenRef.current.add(key);
    unseen.push(event);
  }
  while (seenRef.current.size > 100) seenRef.current.delete(seenRef.current.values().next().value);
  return unseen;
}

export function connectRealtime({ token, onEvent, onStatus }) {
  let socket = null;
  let reconnectTimer = null;
  let reconnectDelay = DEFAULT_RECONNECT_DELAY_MS;
  let stopped = false;

  const connect = () => {
    if (stopped) return;
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;
    const endpoint = buildRealtimeWebSocketUrl();
    let currentSocket;
    try {
      currentSocket = new WebSocket(endpoint, ['atm-events', `bearer.${token}`]);
    } catch {
      onStatus('reconnecting');
      reconnectTimer = window.setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY_MS);
      return;
    }
    socket = currentSocket;
    onStatus('connecting');

    currentSocket.addEventListener('open', () => {
      reconnectDelay = DEFAULT_RECONNECT_DELAY_MS;
      onStatus('connected');
    });
    currentSocket.addEventListener('message', (message) => {
      try {
        onEvent(JSON.parse(message.data));
      } catch {
        onStatus('error');
      }
    });
    currentSocket.addEventListener('close', () => {
      if (socket === currentSocket) socket = null;
      if (stopped) return;
      onStatus('reconnecting');
      reconnectTimer = null;
      reconnectTimer = window.setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY_MS);
    });
    currentSocket.addEventListener('error', () => currentSocket.close());
  };

  connect();

  return () => {
    stopped = true;
    if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
    if (socket && socket.readyState < WebSocket.CLOSING) socket.close(1000, 'Client disconnected');
    socket = null;
    onStatus('disconnected');
  };
}
