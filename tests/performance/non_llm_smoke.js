import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: Number(__ENV.K6_VUS || 5),
  duration: __ENV.K6_DURATION || '30s',
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<2000'],
  },
};

const BACKEND_URL = (__ENV.BACKEND_URL || 'https://cookhero-collab-20260215.onrender.com').replace(/\/$/, '');
const USERNAME = __ENV.SMOKE_USERNAME;
const PASSWORD = __ENV.SMOKE_PASSWORD;

export function setup() {
  if (!USERNAME || !PASSWORD) {
    console.warn('SMOKE_USERNAME/SMOKE_PASSWORD missing; running root-only checks.');
    return { token: null };
  }

  const loginRes = http.post(
    `${BACKEND_URL}/api/v1/auth/login`,
    JSON.stringify({ username: USERNAME, password: PASSWORD }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(loginRes, {
    'login status is 200': (r) => r.status === 200,
  });

  const json = loginRes.json();
  const token = json && json.access_token ? String(json.access_token) : null;
  return { token };
}

export default function (data) {
  const token = data && data.token ? String(data.token) : null;

  const rootRes = http.get(`${BACKEND_URL}/`);
  check(rootRes, { 'root status is 200': (r) => r.status === 200 });

  if (token) {
    const headers = { Authorization: `Bearer ${token}` };

    const profileRes = http.get(`${BACKEND_URL}/api/v1/user/profile`, { headers });
    check(profileRes, { 'profile status is 200': (r) => r.status === 200 });

    const convRes = http.get(`${BACKEND_URL}/api/v1/conversation?limit=1&offset=0`, { headers });
    check(convRes, { 'conversation list is 200': (r) => r.status === 200 });

    const agentSessionsRes = http.get(`${BACKEND_URL}/api/v1/agent/sessions?limit=1&offset=0`, { headers });
    check(agentSessionsRes, { 'agent sessions is 200': (r) => r.status === 200 });
  }

  sleep(1);
}

